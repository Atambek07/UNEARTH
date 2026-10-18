"""REST API UNEARTH: прогноз, балансировка, обслуживание, финансы, сектора."""
from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException

import app
from app import config as cfg
from app.engines.finance import FinanceInput, run_finance
from app.engines.landgem import LandGEMInput, avg_power_mw, monthly_energy_mwh
from app.engines.maintenance import MaintenanceInput, run_maintenance
from app.engines.optimizer import auto_allocate, manual_allocate
from app.engines.seasonal import SeasonalParams, run_hybrid_forecast
from app.engines.sectors import build_sectors
from app.schemas import (
    FinanceRequest,
    ForecastRequest,
    MaintenanceRequest,
    OptimizeRequest,
    SectorsRequest,
)

try:  # Prophet — опциональная зависимость
    import prophet  # noqa: F401

    PROPHET_AVAILABLE = True
except Exception:  # noqa: BLE001
    PROPHET_AVAILABLE = False

router = APIRouter(prefix="/api")


def _start_month() -> date:
    """Первый месяц горизонта прогноза — следующий после текущего."""
    today = date.today()
    if today.month == 12:
        return date(today.year + 1, 1, 1)
    return date(today.year, today.month + 1, 1)


def _landgem_input(req: ForecastRequest) -> LandGEMInput:
    return LandGEMInput(
        total_legacy_tonnes=req.total_legacy_tonnes,
        annual_inflow_tonnes=req.annual_inflow_tonnes,
        lo_m3_per_tonne=req.lo_m3_per_tonne,
        k_per_year=req.k_per_year,
        horizon_years=req.horizon_years,
        collection_efficiency=req.collection_efficiency,
        genset_availability=req.genset_availability,
        kwh_per_m3_ch4=req.kwh_per_m3_ch4,
    )


def _forecast_payload(req: ForecastRequest) -> tuple[dict, LandGEMInput]:
    try:
        inp = _landgem_input(req)
        bundle = run_hybrid_forecast(
            inp, SeasonalParams(seed=req.seed), _start_month(), req.use_prophet
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    energy = [monthly_energy_mwh(q, inp) for q in bundle.forecast_ch4_m3]
    power = [avg_power_mw(e) for e in energy]

    monthly = [
        {
            "idx": i,
            "label": f"{d.year}-{d.month:02d}",
            "year": d.year,
            "month": d.month,
            "landgem_ch4_m3": round(bundle.landgem_ch4_m3[i], 1),
            "forecast_ch4_m3": round(bundle.forecast_ch4_m3[i], 1),
            "ci_lower": round(bundle.ci_lower[i], 1),
            "ci_upper": round(bundle.ci_upper[i], 1),
            "moisture_index": round(bundle.moisture_index[i], 3),
            "energy_mwh": round(energy[i], 1),
            "avg_power_mw": round(power[i], 3),
        }
        for i, d in enumerate(bundle.dates)
    ]

    annual = []
    for y in range(req.horizon_years):
        s = slice(y * 12, (y + 1) * 12)
        energy_year = sum(energy[s])
        annual.append(
            {
                "year": y + 1,
                "label": str(bundle.dates[y * 12].year),
                "landgem_ch4_m3": round(sum(bundle.landgem_ch4_m3[s]), 1),
                "forecast_ch4_m3": round(sum(bundle.forecast_ch4_m3[s]), 1),
                "ci_lower": round(sum(bundle.ci_lower[s]), 1),
                "ci_upper": round(sum(bundle.ci_upper[s]), 1),
                "energy_mwh": round(energy_year, 1),
                "avg_power_mw": round(energy_year / 8760.0, 3),
            }
        )

    summary = {
        "year1_avg_power_mw": annual[0]["avg_power_mw"],
        "year1_energy_mwh": annual[0]["energy_mwh"],
        "year5_avg_power_mw": annual[min(4, len(annual) - 1)]["avg_power_mw"],
        "year_last_avg_power_mw": annual[-1]["avg_power_mw"],
        "peak_power_mw": round(max(power), 3),
        "horizon_total_ch4_m3": round(sum(bundle.forecast_ch4_m3), 1),
        "horizon_total_energy_mwh": round(sum(energy), 1),
    }
    return {"meta": bundle.meta, "annual": annual, "monthly": monthly, "summary": summary}, inp


def _optimize_payload(req: OptimizeRequest) -> dict:
    if req.mode == "manual":
        return manual_allocate(
            available_mw=req.available_mw,
            ch4_fraction=req.ch4_fraction,
            h2s_ppm=req.h2s_ppm,
            btc_price=req.btc_price,
            gpu_rent=req.gpu_rent_usd_per_gpu_hour,
            manual_miners=req.manual_miners,
            manual_ai_servers=req.manual_ai_servers,
            seed=req.seed,
        )
    return auto_allocate(
        available_mw=req.available_mw,
        ch4_fraction=req.ch4_fraction,
        h2s_ppm=req.h2s_ppm,
        btc_price=req.btc_price,
        gpu_rent=req.gpu_rent_usd_per_gpu_hour,
        seed=req.seed,
        gpu_demand_cap=req.gpu_demand_cap,
    )


def _maintenance_payload(req: MaintenanceRequest) -> dict:
    return run_maintenance(
        MaintenanceInput(
            installed_mw=req.installed_mw,
            ch4_m3_month=req.ch4_m3_month,
            h2s_ppm=req.h2s_ppm,
            methane_fraction=req.methane_fraction,
            months_operated=req.months_operated,
            genset_availability=req.genset_availability,
            kwh_per_m3_ch4=req.kwh_per_m3_ch4,
        )
    )


def _finance_payload(req: FinanceRequest) -> dict:
    try:
        return run_finance(
            FinanceInput(
                horizon_years=req.horizon_years,
                monthly_power_mw=req.monthly_power_mw,
                monthly_ch4_m3_delivered=req.monthly_ch4_m3_delivered,
                miners_count=req.miners_count,
                ai_servers_count=req.ai_servers_count,
                btc_price=req.btc_price,
                gpu_rent_usd_per_gpu_hour=req.gpu_rent_usd_per_gpu_hour,
                opex_variable_annual_usd=req.opex_variable_annual_usd,
                opex_fixed_annual_usd=req.opex_fixed_annual_usd,
                seed=req.seed,
                n_sims=req.n_sims,
            )
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _sectors_payload(req: SectorsRequest) -> dict:
    return build_sectors(
        ch4_m3_delivered_month=req.ch4_m3_delivered_month,
        month=req.month,
        rows=req.rows,
        cols=req.cols,
        seed=req.seed,
    )


@router.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "prophet_available": PROPHET_AVAILABLE,
        "version": app.__version__,
    }


@router.post("/forecast")
def post_forecast(req: ForecastRequest) -> dict:
    payload, _inp = _forecast_payload(req)
    return payload


@router.post("/optimize")
def post_optimize(req: OptimizeRequest) -> dict:
    return _optimize_payload(req)


@router.post("/maintenance")
def post_maintenance(req: MaintenanceRequest) -> dict:
    return _maintenance_payload(req)


@router.post("/finance")
def post_finance(req: FinanceRequest) -> dict:
    return _finance_payload(req)


@router.post("/sectors")
def post_sectors(req: SectorsRequest) -> dict:
    return _sectors_payload(req)


@router.post("/simulation/run")
def post_simulation_run(req: ForecastRequest) -> dict:
    """Одношаговый прогон MVP: прогноз → авто-балансировка → OPEX → финансы → сектора.

    Дашборд использует гранулярные эндпоинты (в т.ч. ручной режим), а этот
    маршрут удобен для интеграций и быстрой проверки сквозной логики.
    """
    forecast, inp = _forecast_payload(req)
    year1_power = forecast["summary"]["year1_avg_power_mw"]
    first_month = forecast["monthly"][0]
    ch4_delivered_month = first_month["forecast_ch4_m3"] * req.collection_efficiency

    optimize = _optimize_payload(
        OptimizeRequest(
            available_mw=max(year1_power, 0.01),
            ch4_fraction=req.methane_fraction,
            h2s_ppm=30.0,
            seed=req.seed,
        )
    )
    miners = next(
        (r["count"] for r in optimize["allocation"] if r["node_type"] == "antminer_s19_pro"), 0
    )
    ai_servers = next(
        (r["count"] for r in optimize["allocation"] if r["node_type"] == "ai_server"), 0
    )

    maintenance = _maintenance_payload(
        MaintenanceRequest(
            installed_mw=max(year1_power, 0.01),
            ch4_m3_month=max(ch4_delivered_month, 1.0),
            h2s_ppm=30.0,
            methane_fraction=req.methane_fraction,
            genset_availability=req.genset_availability,
            kwh_per_m3_ch4=req.kwh_per_m3_ch4,
        )
    )

    finance = _finance_payload(
        FinanceRequest(
            horizon_years=req.horizon_years,
            monthly_power_mw=[m["avg_power_mw"] for m in forecast["monthly"]],
            monthly_ch4_m3_delivered=[
                m["forecast_ch4_m3"] * req.collection_efficiency for m in forecast["monthly"]
            ],
            miners_count=miners,
            ai_servers_count=ai_servers,
            opex_variable_annual_usd=maintenance["opex_variable_annual_usd"],
            opex_fixed_annual_usd=maintenance["opex_fixed_annual_usd"],
            seed=req.seed,
        )
    )

    sectors = _sectors_payload(
        SectorsRequest(
            ch4_m3_delivered_month=max(ch4_delivered_month, 0.001),
            month=_start_month().month,
            seed=req.seed,
        )
    )
    return {
        "forecast": forecast,
        "optimize": optimize,
        "maintenance": maintenance,
        "finance": finance,
        "sectors": sectors,
    }
