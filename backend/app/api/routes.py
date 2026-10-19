"""REST API UNEARTH v0.2: прогноз, балансировка (точка + путь), обслуживание,
финансы с фискальным блоком КР, карбон, сектора, рынок, сценарии (БД)."""
from __future__ import annotations

from datetime import date, datetime, timezone

from fastapi import APIRouter, HTTPException

import app
from app import config as cfg
from app.engines.carbon import CarbonParams, compute_carbon
from app.engines import market_data as md
from app.engines.currency import CurrencyParams, compute_currency
from app.engines.finance import FinanceInput, run_finance
from app.engines.fiscal import FiscalParams, compute_fiscal
from app.engines.landgem import LandGEMInput, avg_power_mw, monthly_energy_mwh
from app.engines.maintenance import MaintenanceInput, run_maintenance
from app.engines.market import get_market_model
from app.engines.optimizer import auto_allocate, manual_allocate, optimize_path
from app.engines.seasonal import SeasonalParams, run_hybrid_forecast
from app.engines.sectors import build_sectors
from app.schemas import (
    CarbonRequest,
    CurrencyRequest,
    FinanceRequest,
    FiscalCompareRequest,
    ForecastRequest,
    MaintenanceRequest,
    OptimizePathRequest,
    OptimizeRequest,
    ScenarioCompareRequest,
    ScenarioCreate,
    ScenarioInputs,
    SectorsRequest,
)
from app import storage

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


def _resolve_market(req) -> tuple[float, float, float | None, dict]:
    """Разрешает цены по провайдеру и возвращает (btc, rent, hashrate, info)."""
    btc, rent, hashrate, source, fetched_at, notes = md.resolve_market(
        req.market_provider, req.btc_price, req.gpu_rent_usd_per_gpu_hour
    )
    info = {
        "source": source,
        "fetched_at": fetched_at,
        "network_hashrate_ths": round(hashrate, 1) if hashrate else None,
        "notes": notes,
    }
    return btc, rent, hashrate, info


def _optimize_payload(req: OptimizeRequest) -> dict:
    btc, rent, hashrate, info = _resolve_market(req)
    if req.mode == "manual":
        result = manual_allocate(
            available_mw=req.available_mw,
            ch4_fraction=req.ch4_fraction,
            h2s_ppm=req.h2s_ppm,
            btc_price=btc,
            gpu_rent=rent,
            manual_miners=req.manual_miners,
            manual_ai_servers=req.manual_ai_servers,
            seed=req.seed,
            network_hashrate_ths=hashrate,
        )
    else:
        result = auto_allocate(
            available_mw=req.available_mw,
            ch4_fraction=req.ch4_fraction,
            h2s_ppm=req.h2s_ppm,
            btc_price=btc,
            gpu_rent=rent,
            seed=req.seed,
            gpu_demand_cap=req.gpu_demand_cap,
            network_hashrate_ths=hashrate,
        )
    result["market"].update(info)
    return result


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
        result = run_finance(
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
    fx_params = CurrencyParams(**req.fx.model_dump()) if req.fx else CurrencyParams()
    result["fx"] = compute_currency(
        [row["revenue_p50_usd"] for row in result["annual"]], fx_params
    )
    return result


def _fiscal_block(req: FinanceRequest, finance: dict) -> dict:
    """Фискальный режим КР по годам: прибыль/выручка из Монте-Карло (P50)."""
    years = req.horizon_years
    power0 = req.monthly_power_mw[0]
    share = [
        sum(req.monthly_power_mw[y * 12 : (y + 1) * 12]) / (12.0 * power0)
        for y in range(years)
    ]
    split = finance["revenue_split"]
    params = FiscalParams(
        regime=req.fiscal_regime,
        usd_kgs_rate=req.fx.usd_kgs_rate if req.fx else cfg.USD_KGS_RATE_DEFAULT,
    )
    fiscal_years = []
    for y in range(years):
        miners_energy_kwh = req.miners_count * cfg.ANTMINER_POWER_KW * 8760.0 * share[y]
        fiscal_years.append(
            compute_fiscal(
                profit_before_tax_usd=finance["annual"][y]["net_profit_p50_usd"],
                ai_revenue_usd=float(split["ai_p50_usd"][y]),
                mining_revenue_usd=float(split["mining_p50_usd"][y]),
                miners_energy_kwh_year=miners_energy_kwh,
                labor_usd_year=cfg.OPEX_LABOR_USD_YEAR,
                params=params,
            )
        )
    return {
        "regime": req.fiscal_regime,
        "years": fiscal_years,
        "totals": {
            "taxes_total_usd": round(sum(fy["taxes_total_usd"] for fy in fiscal_years), 2),
            "net_profit_after_fiscal_usd": round(
                sum(fy["net_profit_after_fiscal_usd"] for fy in fiscal_years), 2
            ),
        },
        "disclaimer": cfg.DISCLAIMER,
    }


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


@router.get("/market/current")
def get_market_current(provider: str = "auto", seed: int = 42) -> dict:
    """Текущий рынок: live-данные (BTC, хешрейт) или синтетика + ML-прогноз."""
    if provider not in md.PROVIDERS:
        raise HTTPException(status_code=422, detail=f"provider must be one of {md.PROVIDERS}")
    btc, rent, hashrate, source, fetched_at, notes = md.resolve_market(provider, None, None)
    model = get_market_model(seed)
    predicted = model.predict_return_3m(btc, rent)
    return {
        "provider_requested": provider,
        "source": source,
        "btc_price_usd": round(btc, 2),
        "network_hashrate_ths": round(hashrate, 1) if hashrate else None,
        "network_hashrate_default_ths": cfg.NETWORK_HASHRATE_THS if hashrate is None else None,
        "gpu_rent_usd_per_gpu_hour": rent,
        "predicted_3m_return": round(predicted, 4),
        "miner_margin_multiplier": round(model.miner_margin_multiplier(predicted), 3),
        "regime": "bearish" if predicted < -0.08 else ("bullish" if predicted > 0.08 else "neutral"),
        "fetched_at": fetched_at,
        "notes": notes,
        "disclaimer": cfg.DISCLAIMER,
    }


@router.post("/forecast")
def post_forecast(req: ForecastRequest) -> dict:
    payload, _inp = _forecast_payload(req)
    return payload


@router.post("/optimize")
def post_optimize(req: OptimizeRequest) -> dict:
    return _optimize_payload(req)


@router.post("/optimize/path")
def post_optimize_path(req: OptimizePathRequest) -> dict:
    """Упреждающий план на горизонт: DP со стоимостью переключений и резервом."""
    return _path_payload(req)


@router.post("/maintenance")
def post_maintenance(req: MaintenanceRequest) -> dict:
    return _maintenance_payload(req)


@router.post("/finance")
def post_finance(req: FinanceRequest) -> dict:
    return _finance_with_fiscal(req)


@router.post("/carbon")
def post_carbon(req: CarbonRequest) -> dict:
    return _carbon_payload(req)


@router.post("/currency")
def post_currency(req: CurrencyRequest) -> dict:
    """Валютный блок: конвертация, репатриация и хеджирование выручки."""
    return compute_currency(
        req.annual_usd,
        CurrencyParams(
            usd_kgs_rate=req.usd_kgs_rate,
            conversion_spread=req.conversion_spread,
            repatriation_share=req.repatriation_share,
            repatriation_cost_share=req.repatriation_cost_share,
            hedging_cost_share=req.hedging_cost_share,
        ),
    )


@router.post("/fiscal/compare")
def post_fiscal_compare(req: FiscalCompareRequest) -> dict:
    """Сравнение налоговых режимов КР и Astana Hub при одинаковой базе."""
    rate = req.fx_rate_kgs_per_usd or cfg.USD_KGS_RATE_DEFAULT
    regimes = []
    for regime in ("none", "kr_general", "kr_htp", "kz_aifc"):
        res = compute_fiscal(
            profit_before_tax_usd=req.profit_before_tax_usd,
            ai_revenue_usd=req.ai_revenue_usd,
            mining_revenue_usd=req.mining_revenue_usd,
            miners_energy_kwh_year=req.miners_energy_kwh_year,
            labor_usd_year=req.labor_usd_year,
            params=FiscalParams(
                regime=regime,
                usd_kgs_rate=rate,
                kz_pe_profit_share=(
                    req.pe_risk_share
                    if req.pe_risk_share is not None
                    else cfg.KZ_PE_PROFIT_SHARE
                ),
            ),
        )
        regimes.append(
            {
                "regime": regime,
                "taxes_total_usd": res["taxes_total_usd"],
                "net_profit_after_fiscal_usd": res["net_profit_after_fiscal_usd"],
                "lines": res["lines"],
                "notes": res["notes"],
            }
        )
    taxable = [row for row in regimes if row["regime"] != "none"]
    best = min(taxable, key=lambda row: row["taxes_total_usd"])["regime"] if taxable else None
    return {
        "assumptions": {
            "usd_kgs_rate": rate,
            "tariff_kgs_per_kwh": cfg.KR_MINING_TARIFF_KGS_PER_KWH,
            "tariff_usd_per_kwh": round(cfg.KR_MINING_TARIFF_KGS_PER_KWH / rate, 5),
            "kz_pe_profit_share": (
                req.pe_risk_share
                if req.pe_risk_share is not None
                else cfg.KZ_PE_PROFIT_SHARE
            ),
        },
        "regimes": regimes,
        "best_regime": best,
        "notes": [
            "Сравнение по сумме налогов; не учитывает требования к структуре "
            "выручки, экспортную долю и риск постоянного представительства.",
            "Astana Hub — режим Казахстана: применим только к юрлицу в КЗ.",
            "Упрощённая модель; не налоговая консультация.",
        ],
        "disclaimer": cfg.DISCLAIMER,
    }


@router.post("/sectors")
def post_sectors(req: SectorsRequest) -> dict:
    return _sectors_payload(req)


def _finance_with_fiscal(req: FinanceRequest) -> dict:
    """Финансовый блок вместе с фискальным расчётом (API и сценарии)."""
    result = _finance_payload(req)
    result["fiscal"] = _fiscal_block(req, result)
    return result


def _path_payload(req: OptimizePathRequest) -> dict:
    """Упреждающий план: рынок, DP, пометки источника и дисклеймер."""
    btc, rent, hashrate, info = _resolve_market(req)
    try:
        result = optimize_path(
            monthly_power_mw=req.monthly_power_mw,
            monthly_moisture=req.monthly_moisture,
            monthly_btc_price=req.monthly_btc_price,
            ch4_fraction=req.ch4_fraction,
            h2s_ppm=req.h2s_ppm,
            btc_price=btc,
            gpu_rent=rent,
            seed=req.seed,
            gpu_demand_cap=req.gpu_demand_cap,
            switching_cost_miner_usd=req.switching_cost_miner_usd,
            switching_cost_ai_usd=req.switching_cost_ai_usd,
            network_hashrate_ths=hashrate,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result["market"].update(info)
    result["disclaimer"] = cfg.DISCLAIMER
    return result


def _carbon_payload(req: CarbonRequest) -> dict:
    try:
        return compute_carbon(
            req.monthly_ch4_m3_delivered,
            CarbonParams(
                gwp=req.gwp,
                buffer_share=req.buffer_share,
                verification_lag_months=req.verification_lag_months,
                price_p10=req.price_p10,
                price_p50=req.price_p50,
                price_p90=req.price_p90,
                validation_cost_usd=req.validation_cost_usd,
                verification_cost_usd_year=req.verification_cost_usd_year,
                monitoring_cost_usd_year=req.monitoring_cost_usd_year,
                issuance_fee_usd_per_credit=req.issuance_fee_usd_per_credit,
                discount_rate=req.discount_rate,
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _run_chain(inputs: ScenarioInputs) -> dict:
    """Полная цепочка: forecast → optimize → план → обслуживание → карбон → финансы → сектора."""
    forecast, _inp = _forecast_payload(
        ForecastRequest(
            total_legacy_tonnes=inputs.total_legacy_tonnes,
            annual_inflow_tonnes=inputs.annual_inflow_tonnes,
            lo_m3_per_tonne=inputs.lo_m3_per_tonne,
            k_per_year=inputs.k_per_year,
            methane_fraction=inputs.methane_fraction,
            horizon_years=inputs.horizon_years,
            collection_efficiency=inputs.collection_efficiency,
            genset_availability=inputs.genset_availability,
            kwh_per_m3_ch4=inputs.kwh_per_m3_ch4,
            seed=inputs.seed,
        )
    )
    year1_power = forecast["summary"]["year1_avg_power_mw"]
    first_month = forecast["monthly"][0]
    ch4_delivered_month = first_month["forecast_ch4_m3"] * inputs.collection_efficiency

    optimize = _optimize_payload(
        OptimizeRequest(
            available_mw=max(year1_power, 0.01),
            ch4_fraction=inputs.methane_fraction,
            h2s_ppm=inputs.h2s_ppm,
            btc_price=inputs.btc_price,
            gpu_rent_usd_per_gpu_hour=inputs.gpu_rent_usd_per_gpu_hour,
            market_provider=inputs.market_provider,
            mode=inputs.mode,
            manual_miners=inputs.manual_miners,
            manual_ai_servers=inputs.manual_ai_servers,
            seed=inputs.seed,
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
            h2s_ppm=inputs.h2s_ppm,
            methane_fraction=inputs.methane_fraction,
            genset_availability=inputs.genset_availability,
            kwh_per_m3_ch4=inputs.kwh_per_m3_ch4,
        )
    )

    # Цена и рента — из фактически разрешённого рынка (учитывает live-провайдера).
    btc_price = float(optimize["market"]["btc_price"])
    gpu_rent = float(optimize["market"]["gpu_rent_usd_per_gpu_hour"])
    finance = _finance_with_fiscal(
        FinanceRequest(
            horizon_years=inputs.horizon_years,
            monthly_power_mw=[m["avg_power_mw"] for m in forecast["monthly"]],
            monthly_ch4_m3_delivered=[
                m["forecast_ch4_m3"] * inputs.collection_efficiency for m in forecast["monthly"]
            ],
            miners_count=miners,
            ai_servers_count=ai_servers,
            btc_price=btc_price,
            gpu_rent_usd_per_gpu_hour=gpu_rent,
            opex_variable_annual_usd=maintenance["opex_variable_annual_usd"],
            opex_fixed_annual_usd=maintenance["opex_fixed_annual_usd"],
            seed=inputs.seed,
        )
    )

    plan = _path_payload(
        OptimizePathRequest(
            monthly_power_mw=[m["avg_power_mw"] for m in forecast["monthly"][:12]],
            monthly_moisture=[m["moisture_index"] for m in forecast["monthly"][:12]],
            ch4_fraction=inputs.methane_fraction,
            h2s_ppm=inputs.h2s_ppm,
            btc_price=inputs.btc_price,
            gpu_rent_usd_per_gpu_hour=inputs.gpu_rent_usd_per_gpu_hour,
            market_provider=inputs.market_provider,
            seed=inputs.seed,
        )
    )

    carbon = _carbon_payload(
        CarbonRequest(
            monthly_ch4_m3_delivered=[
                m["forecast_ch4_m3"] * inputs.collection_efficiency for m in forecast["monthly"]
            ],
        )
    )

    sectors = _sectors_payload(
        SectorsRequest(
            ch4_m3_delivered_month=max(ch4_delivered_month, 0.001),
            month=_start_month().month,
            seed=inputs.seed,
        )
    )

    return {
        "forecast": forecast,
        "optimize": optimize,
        "plan": plan,
        "maintenance": maintenance,
        "carbon": carbon,
        "finance": finance,
        "sectors": sectors,
    }


@router.post("/simulation/run")
def post_simulation_run(req: ForecastRequest) -> dict:
    """Полный прогон: прогноз → оптимизация → план → обслуживание → карбон → финансы → сектора."""
    inputs = ScenarioInputs(
        total_legacy_tonnes=req.total_legacy_tonnes,
        annual_inflow_tonnes=req.annual_inflow_tonnes,
        lo_m3_per_tonne=req.lo_m3_per_tonne,
        k_per_year=req.k_per_year,
        methane_fraction=req.methane_fraction,
        horizon_years=req.horizon_years,
        collection_efficiency=req.collection_efficiency,
        genset_availability=req.genset_availability,
        kwh_per_m3_ch4=req.kwh_per_m3_ch4,
        seed=req.seed,
    )
    return _run_chain(inputs)



# ----------------------------------------------------------------------------
# Сценарии (БД: SQLite по умолчанию, PostgreSQL через UNEARTH_DB_URL)
# ----------------------------------------------------------------------------
def _scenario_digest(chain: dict) -> dict:
    forecast = chain["forecast"]
    optimize = chain["optimize"]
    maintenance = chain["maintenance"]
    finance = chain["finance"]
    miners = next(
        (r["count"] for r in optimize["allocation"] if r["node_type"] == "antminer_s19_pro"), 0
    )
    ai_servers = next(
        (r["count"] for r in optimize["allocation"] if r["node_type"] == "ai_server"), 0
    )
    return {
        "year1_avg_power_mw": forecast["summary"]["year1_avg_power_mw"],
        "peak_power_mw": forecast["summary"]["peak_power_mw"],
        "ai_servers": ai_servers,
        "miners": miners,
        "used_mw": optimize["used_mw"],
        "daily_margin_usd": round(
            sum(r["margin_usd_day"] for r in optimize["allocation"]), 2
        ),
        "fleet_health_score": maintenance["fleet_health_score"],
        "opex_annual_usd": maintenance["opex_annual_usd"],
        "capex_total_usd": finance["capex_total_usd"],
        "payback_years": finance["payback_years"],
        "irr": finance["irr"],
        "net_profit_p50_usd": finance["totals"]["net_profit_p50_usd"],
        "co2_avoided_t": finance["totals"]["co2_avoided_t"],
        "green_fund_usd": finance["totals"]["green_fund_usd"],
        "trees_planted": finance["totals"]["trees_planted"],
    }


_COMPARE_DIRECTIONS = {
    "year1_avg_power_mw": "max",
    "daily_margin_usd": "max",
    "fleet_health_score": "max",
    "opex_annual_usd": "min",
    "capex_total_usd": "min",
    "payback_years": "min",
    "irr": "max",
    "net_profit_p50_usd": "max",
    "co2_avoided_t": "max",
    "green_fund_usd": "max",
    "trees_planted": "max",
}


@router.post("/scenarios", status_code=201)
def create_scenario(req: ScenarioCreate) -> dict:
    """Сохраняет сценарий; при run=true сначала прогоняет симуляцию."""
    if req.run:
        chain = _run_chain(req.inputs)
        stored = {
            "digest": _scenario_digest(chain),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "payload_version": 1,
            "payload": chain,
        }
    elif req.results is not None:
        stored = req.results
    else:
        stored = {"digest": {}}
    return storage.save_scenario(req.name, req.notes, req.inputs.model_dump(), stored)


@router.get("/scenarios")
def get_scenarios(limit: int = 100) -> dict:
    limit = max(1, min(limit, 500))
    items = storage.list_scenarios(limit)
    return {"items": items, "count": len(items)}


@router.get("/scenarios/{scenario_id}")
def get_scenario(scenario_id: int) -> dict:
    scenario = storage.get_scenario(scenario_id)
    if scenario is None:
        raise HTTPException(status_code=404, detail="сценарий не найден")
    return scenario


@router.delete("/scenarios/{scenario_id}")
def delete_scenario(scenario_id: int) -> dict:
    if not storage.delete_scenario(scenario_id):
        raise HTTPException(status_code=404, detail="сценарий не найден")
    return {"deleted": scenario_id}


@router.post("/scenarios/compare")
def compare_scenarios(req: ScenarioCompareRequest) -> dict:
    items: list[dict] = []
    missing: list[int] = []
    for scenario_id in req.ids:
        scenario = storage.get_scenario(scenario_id)
        if scenario is None:
            missing.append(scenario_id)
        else:
            items.append(scenario)
    if len(items) < 2:
        raise HTTPException(
            status_code=422,
            detail=f"нужно минимум 2 существующих сценария; не найдены: {missing}",
        )

    rows = [
        {"id": s["id"], "name": s["name"], "created_at": s["created_at"],
         "metrics": s["results"].get("digest", {})}
        for s in items
    ]
    best: dict[str, int | None] = {}
    for metric, direction in _COMPARE_DIRECTIONS.items():
        candidates = [
            (row["id"], row["metrics"].get(metric))
            for row in rows
            if isinstance(row["metrics"].get(metric), (int, float))
        ]
        if not candidates:
            best[metric] = None
            continue
        key = min if direction == "min" else max
        best[metric] = key(candidates, key=lambda pair: pair[1])[0]

    return {
        "comparison": rows,
        "best": best,
        "missing_ids": missing,
        "disclaimer": cfg.DISCLAIMER,
    }
