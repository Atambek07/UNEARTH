"""Модуль 2в — экономика: CAPEX/OPEX, Монте-Карло рынка, окупаемость, Green Tracker.

CAPEX (ASSUMPTION-константы из config.py) считается по парку ГПУ и мощности;
железо вычислений (Antminer × N, ИИ-серверы × N) добавляется из балансировщика.
Выручка моделируется Монте-Карло: траектории BTC (GBM + крэши, рост сложности
сети −2 %/мес к доходности на TH) и ренты GPU (OU) из engines/market.py.
Green Tracker (PDF): CO2-эквивалент от уничтоженного CH4 (GWP-28) и Фонд
озеленения — 5 % чистой цифровой прибыли на саженцы.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app import config as cfg
from app.engines.market import simulate_future_markets
from app.engines.optimizer import (
    ai_revenue_usd_day,
    mining_revenue_usd_day,
)


@dataclass(frozen=True)
class FinanceInput:
    horizon_years: int
    monthly_power_mw: list[float]          # средняя мощность по месяцам прогноза
    monthly_ch4_m3_delivered: list[float]  # CH4, поданный на ГПУ (с учётом отбора)
    miners_count: int
    ai_servers_count: int
    btc_price: float = cfg.BTC_PRICE_DEFAULT
    gpu_rent_usd_per_gpu_hour: float = cfg.GPU_RENT_DEFAULT
    opex_variable_annual_usd: float = 0.0  # скрубберы + расходники + капремонты (из maintenance)
    opex_fixed_annual_usd: float = 0.0     # ФОТ + страхование + амортизация станции
    seed: int = 42
    n_sims: int = 400


def estimate_plant_capex(genset_count: int, installed_mw: float) -> tuple[float, list[dict]]:
    """CAPEX станции (без железа вычислений): статьи + инжиниринг/резерв."""
    installed_kw = installed_mw * 1000.0
    breakdown = [
        {"item": "Скважины и система газосбора", "usd": round(cfg.CAPEX_WELLS_COLLECTION_USD)},
        {"item": "Резервная факельная установка", "usd": round(cfg.CAPEX_FLARE_BACKUP_USD)},
        {"item": f"Газопоршневые ГПУ ({genset_count} × {cfg.GENSET_RATING_MW:.0f} МВт)", "usd": round(cfg.CAPEX_GENSER_USD_PER_KW * installed_kw)},
        {"item": "Блоки осушки и сероочистки (на ГПУ)", "usd": round(cfg.CAPEX_SCRUBBER_PER_GENSET_USD * genset_count)},
        {"item": "Подстанция и распределение", "usd": round(cfg.CAPEX_SUBSTATION_USD)},
        {"item": "Контейнерные ЦОД", "usd": round(cfg.CAPEX_DC_CONTAINER_PER_MW_USD * installed_mw)},
    ]
    subtotal = sum(row["usd"] for row in breakdown)
    contingency = round(subtotal * cfg.CAPEX_CONTINGENCY_SHARE)
    breakdown.append({"item": f"Инжиниринг и резерв ({cfg.CAPEX_CONTINGENCY_SHARE:.0%})", "usd": contingency})
    return float(subtotal + contingency), breakdown


def _irr(cashflows: list[float]) -> float | None:
    """IRR методом бисекции; None, если корня нет на (-0.9, 3.0]."""

    def npv(rate: float) -> float:
        return sum(cf / (1.0 + rate) ** i for i, cf in enumerate(cashflows))

    lo, hi = -0.9, 3.0
    f_lo, f_hi = npv(lo), npv(hi)
    if f_lo * f_hi > 0:
        return None
    for _ in range(200):
        mid = (lo + hi) / 2.0
        f_mid = npv(mid)
        if f_lo * f_mid <= 0:
            hi, f_hi = mid, f_mid
        else:
            lo, f_lo = mid, f_mid
    return (lo + hi) / 2.0


def run_finance(inp: FinanceInput) -> dict:
    months = len(inp.monthly_power_mw)
    if months != len(inp.monthly_ch4_m3_delivered):
        raise ValueError("monthly_power_mw and monthly_ch4_m3_delivered must have equal length")
    if months == 0 or inp.monthly_power_mw[0] <= 0:
        raise ValueError("forecast must contain positive power values")

    years = inp.horizon_years
    power = np.asarray(inp.monthly_power_mw, dtype=float)
    share = np.clip(power / power[0], 0.0, 2.0)  # масштаб парка относительно месяца 1

    btc, rent = simulate_future_markets(
        inp.seed, months, btc_start=inp.btc_price, n_sims=inp.n_sims
    )
    t = np.arange(months, dtype=float)
    difficulty = (1.0 + 0.02) ** t  # рост сложности сети снижает доход на TH

    base_miner_day = (
        cfg.BLOCKS_PER_DAY
        * cfg.BLOCK_REWARD_BTC
        / cfg.NETWORK_HASHRATE_THS
        * cfg.ANTMINER_HASHRATE_TH
        * (1.0 - cfg.POOL_FEE_SHARE)
    )  # $/день на асик при текущем btc_start → умножается на btc_t/btc_start

    miners_eff = inp.miners_count * share
    ai_eff = inp.ai_servers_count * share
    days = 30.44

    # Векторизованно: [n_sims, months]
    mining_month = (
        base_miner_day
        * (btc / inp.btc_price)
        / difficulty
        * days
        * miners_eff
    )
    ai_month = rent * 24.0 * cfg.GPUS_PER_AI_SERVER * days * ai_eff
    revenue_month = mining_month + ai_month
    revenue_years = revenue_month.reshape(inp.n_sims, years, 12).sum(axis=2)  # [sims, years]

    power_share_years = share.reshape(years, 12).mean(axis=1)  # [years]
    opex_years = inp.opex_variable_annual_usd * power_share_years + inp.opex_fixed_annual_usd

    net_years = revenue_years - opex_years[None, :]
    rev_p10, rev_p50, rev_p90 = np.percentile(revenue_years, [10, 50, 90], axis=0)
    net_p10, net_p50, net_p90 = np.percentile(net_years, [10, 50, 90], axis=0)

    # CAPEX
    genset_count = max(1, int(np.ceil(power[0] / cfg.GENSET_RATING_MW)))
    plant_capex, plant_breakdown = estimate_plant_capex(genset_count, float(power[0]))
    hardware = (
        inp.miners_count * cfg.ANTMINER_CAPEX_USD + inp.ai_servers_count * cfg.AI_SERVER_CAPEX_USD
    )
    capex_breakdown = plant_breakdown + [
        {"item": f"Antminer S19 Pro × {inp.miners_count}", "usd": round(inp.miners_count * cfg.ANTMINER_CAPEX_USD)},
        {"item": f"ИИ-серверы × {inp.ai_servers_count}", "usd": round(inp.ai_servers_count * cfg.AI_SERVER_CAPEX_USD)},
    ]
    capex_total = plant_capex + hardware

    # Green Tracker: CO2 и Фонд озеленения
    ch4_years = np.asarray(inp.monthly_ch4_m3_delivered, dtype=float).reshape(years, 12).sum(axis=1)
    co2_avoided_t = ch4_years * cfg.CH4_DENSITY_KG_PER_M3 / 1000.0 * cfg.GWP_CH4
    green_fund = 0.05 * np.maximum(net_p50, 0.0)
    trees = green_fund / cfg.SAPLING_COST_USD

    # Денежные потоки и окупаемость
    cashflows = [-capex_total] + [float(x) for x in net_p50]
    disc = np.asarray([cf / (1.0 + cfg.WACC) ** i for i, cf in enumerate(cashflows)])
    cum_disc = np.cumsum(disc)

    payback_years: float | None = None
    for i in range(1, len(cum_disc)):
        if cum_disc[i] >= 0 and cum_disc[i - 1] < 0:
            frac = -cum_disc[i - 1] / (cum_disc[i] - cum_disc[i - 1]) if cum_disc[i] != cum_disc[i - 1] else 0.0
            payback_years = round((i - 1) + frac, 1)
            break
    irr = _irr(cashflows)

    annual = []
    for y in range(years):
        annual.append(
            {
                "year": y + 1,
                "revenue_p10_usd": round(float(rev_p10[y])),
                "revenue_p50_usd": round(float(rev_p50[y])),
                "revenue_p90_usd": round(float(rev_p90[y])),
                "opex_usd": round(float(opex_years[y])),
                "net_profit_p10_usd": round(float(net_p10[y])),
                "net_profit_p50_usd": round(float(net_p50[y])),
                "net_profit_p90_usd": round(float(net_p90[y])),
                "cumulative_cashflow_p50_usd": round(float(cum_disc[y + 1])),
                "co2_avoided_t": round(float(co2_avoided_t[y]), 1),
                "green_fund_usd": round(float(green_fund[y])),
                "trees_planted": int(float(trees[y])),
            }
        )

    chart = [
        {
            "label": "Y0",
            "capex_usd": round(capex_total),
            "opex_usd": 0,
            "net_profit_p50_usd": 0,
            "cumulative_cashflow_p50_usd": round(float(cum_disc[0])),
        }
    ]
    for row in annual:
        chart.append(
            {
                "label": f"Y{row['year']}",
                "capex_usd": 0,
                "opex_usd": row["opex_usd"],
                "net_profit_p50_usd": row["net_profit_p50_usd"],
                "cumulative_cashflow_p50_usd": row["cumulative_cashflow_p50_usd"],
            }
        )

    return {
        "capex_total_usd": round(capex_total),
        "capex_breakdown": capex_breakdown,
        "annual": annual,
        "chart": chart,
        "year0": {"capex_usd": round(capex_total), "cumulative_cashflow_p50_usd": round(float(cum_disc[0]))},
        "payback_years": payback_years,
        "irr": round(irr, 3) if irr is not None else None,
        "wacc": cfg.WACC,
        "totals": {
            "revenue_p50_usd": round(float(rev_p50.sum())),
            "net_profit_p50_usd": round(float(net_p50.sum())),
            "co2_avoided_t": round(float(co2_avoided_t.sum()), 1),
            "green_fund_usd": round(float(green_fund.sum())),
            "trees_planted": int(float(trees.sum())),
            "carbon_credit_upside_usd": round(float(co2_avoided_t.sum()) * cfg.CARBON_CREDIT_USD_PER_T),
        },
    }
