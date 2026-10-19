"""Карбоновый модуль: учёт предотвращённых выбросов и углеродных кредитов.

Логика — по духу CDM ACM0001 «Flaring or use of landfill gas»:
  * базовая линия — метан, который был бы вентилирован (или сожжён в факеле);
  * проект уничтожает CH4 в газопоршневых установках;
  * CO2e = масса уничтоженного CH4 × GWP (28, AR5, 100 лет);
  * из выпуска вычитается буферный резерв пула (20 %, ASSUMPTION);
  * кредиты года Y выпускаются с лагом верификации (12 мес) — выручка
    сдвигается на год вперёд;
  * затраты: валидация (разово), верификация и мониторинг (ежегодно),
    комиссия за выпуск кредитов;
  * цены кредитов — три сценария (P10/P50/P90, ASSUMPTION): 8 / 15 / 25 $/т.

Модуль НЕ учитывает: вытеснение электроэнергии сети (проект off-grid),
изменение запасов углерода, утечки при транспортировке газа. Все допущения
помечены и настраиваются через параметры запроса.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app import config as cfg


@dataclass(frozen=True)
class CarbonParams:
    gwp: float = cfg.GWP_CH4
    buffer_share: float = cfg.CARBON_BUFFER_SHARE
    verification_lag_months: int = cfg.CARBON_VERIFICATION_LAG_MONTHS
    price_p10: float = cfg.CARBON_PRICE_P10_P50_P90[0]
    price_p50: float = cfg.CARBON_PRICE_P10_P50_P90[1]
    price_p90: float = cfg.CARBON_PRICE_P10_P50_P90[2]
    validation_cost_usd: float = cfg.CARBON_VALIDATION_COST_USD
    verification_cost_usd_year: float = cfg.CARBON_VERIFICATION_COST_USD_YEAR
    monitoring_cost_usd_year: float = cfg.CARBON_MONITORING_COST_USD_YEAR
    issuance_fee_usd_per_credit: float = cfg.CARBON_ISSUANCE_FEE_USD_PER_CREDIT
    discount_rate: float = cfg.WACC

    def __post_init__(self) -> None:
        if self.gwp <= 0:
            raise ValueError("gwp must be positive")
        if not 0.0 <= self.buffer_share < 1.0:
            raise ValueError("buffer_share must be within [0, 1)")
        if not 0 <= self.verification_lag_months <= 36:
            raise ValueError("verification_lag_months must be within 0..36")
        if min(self.price_p10, self.price_p50, self.price_p90) <= 0:
            raise ValueError("credit prices must be positive")
        if self.verification_lag_months % 12 != 0:
            raise ValueError("verification_lag_months must be a multiple of 12")


def _npv(cashflows: list[float], rate: float) -> float:
    return float(sum(cf / (1.0 + rate) ** i for i, cf in enumerate(cashflows)))


def compute_carbon(
    monthly_ch4_m3_delivered: list[float],
    params: CarbonParams | None = None,
) -> dict:
    """Помесячный уничтоженный CH4 → годовые кредиты, выручка и NPV."""
    p = params or CarbonParams()
    months = len(monthly_ch4_m3_delivered)
    if months < 12 or months % 12 != 0:
        raise ValueError("monthly_ch4_m3_delivered must cover an integer number of years")

    years = months // 12
    ch4 = np.asarray(monthly_ch4_m3_delivered, dtype=float)
    if np.any(ch4 < 0):
        raise ValueError("monthly_ch4_m3_delivered must be non-negative")

    ch4_yearly_m3 = ch4.reshape(years, 12).sum(axis=1)
    ch4_yearly_t = ch4_yearly_m3 * cfg.CH4_DENSITY_KG_PER_M3 / 1000.0
    baseline_co2e_t = ch4_yearly_t * p.gwp

    gross_credits = baseline_co2e_t
    buffer_credits = gross_credits * p.buffer_share
    net_credits = gross_credits - buffer_credits

    lag_years = p.verification_lag_months // 12

    def build_cashflow(price: float) -> tuple[list[float], list[float]]:
        """Возвращает (выручка по годам проекта, чистый поток по годам проекта).

        Поток: [0] — затраты валидации; годы 1..years+lag — выпуск кредитов
        года (t − lag) с комиссией; верификация/мониторинг — в годы выпуска.
        """
        horizon = years + lag_years
        revenue = [0.0] * horizon
        cash = [0.0] * horizon
        cash[0] -= p.validation_cost_usd
        for y in range(1, horizon + 1):
            issue_year = y - lag_years  # 1-based год проекта, кредиты которого выпускаются
            if 1 <= issue_year <= years:
                credits = float(net_credits[issue_year - 1])
                gross_rev = credits * price
                rev = gross_rev - credits * p.issuance_fee_usd_per_credit
                revenue[y - 1] = rev
                cash[y - 1] += rev - p.verification_cost_usd_year - p.monitoring_cost_usd_year
        return revenue, cash

    scenarios = {}
    for label, price in (("p10", p.price_p10), ("p50", p.price_p50), ("p90", p.price_p90)):
        revenue, cash = build_cashflow(price)
        scenarios[label] = {
            "price_usd_per_t": price,
            "revenue_usd": [round(float(x), 2) for x in revenue],
            "cashflow_usd": [round(float(x), 2) for x in cash],
            "npv_usd": round(_npv(cash, p.discount_rate), 2),
            "total_revenue_usd": round(float(sum(revenue)), 2),
            "total_cash_usd": round(float(sum(cash)), 2),
        }

    annual = []
    for y in range(years):
        annual.append(
            {
                "year": y + 1,
                "ch4_destroyed_m3": round(float(ch4_yearly_m3[y]), 1),
                "ch4_destroyed_t": round(float(ch4_yearly_t[y]), 1),
                "baseline_co2e_t": round(float(baseline_co2e_t[y]), 1),
                "buffer_credits_t": round(float(buffer_credits[y]), 1),
                "net_credits_t": round(float(net_credits[y]), 1),
            }
        )

    return {
        "methodology": "CDM ACM0001 (landfill gas destruction), упрощённая модель",
        "params": {
            "gwp": p.gwp,
            "buffer_share": p.buffer_share,
            "verification_lag_months": p.verification_lag_months,
            "discount_rate": p.discount_rate,
            "issuance_fee_usd_per_credit": p.issuance_fee_usd_per_credit,
            "validation_cost_usd": p.validation_cost_usd,
            "verification_cost_usd_year": p.verification_cost_usd_year,
            "monitoring_cost_usd_year": p.monitoring_cost_usd_year,
        },
        "annual": annual,
        "totals": {
            "ch4_destroyed_t": round(float(ch4_yearly_t.sum()), 1),
            "baseline_co2e_t": round(float(baseline_co2e_t.sum()), 1),
            "net_credits_t": round(float(net_credits.sum()), 1),
            "buffer_credits_t": round(float(buffer_credits.sum()), 1),
        },
        "scenarios": scenarios,
        "notes": [
            "Базовая линия — вентирование метана; проект уничтожает CH4 в ГПУ.",
            "Вытеснение электроэнергии сети не учитывается (проект off-grid).",
            f"Буфер {p.buffer_share:.0%} и цены кредитов — допущения, настраиваются.",
            "Кредиты выпускаются с лагом верификации; выручка сдвинута.",
            "Карбоновая выручка не входит в /api/finance и не дублирует "
            "Фонд озеленения (5 % прибыли — отдельная ESG-программа).",
        ],
        "disclaimer": cfg.DISCLAIMER,
    }
