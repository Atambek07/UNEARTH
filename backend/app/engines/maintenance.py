"""Модуль 2б — предиктивное обслуживание: износ Jenbacher от H2S, скрубберы, OPEX.

Физика износа (риск №1 PDF: «агрессивный газ может сжечь генераторы за месяц»):
  * скорость износа, %/мес: базовые 0.35 %/мес при H2S ≤ 25 ppm (после скрубберов),
    рост по степенному закону (h2s/25)^1.35 — нелинейная коррозия;
  * health = 100 − wear × наработка(мес), пол HEALTH_FLOOR (15 %) = капремонт;
  * RUL = (health − floor) / wear — прогноз остаточного ресурса в месяцах;
  * риск отказа за 12 мес: линейное отображение RUL < 12 → [0.05 .. 0.95].
Скрубберы: суммарная загрузка сере = расход LFG × ppm × плотность H2S;
  ресурс партии сорбента = ёмкость / загрузка; замены → OPEX.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from app import config as cfg
from app.engines.finance import estimate_plant_capex


@dataclass(frozen=True)
class MaintenanceInput:
    installed_mw: float
    ch4_m3_month: float            # CH4, поданный на ГПУ, м³/мес (с учётом отбора газа)
    h2s_ppm: float = 30.0
    methane_fraction: float = cfg.METHANE_FRACTION_DEFAULT
    months_operated: int = 6       # средняя наработка парка на момент расчёта
    genset_availability: float = cfg.GENSET_AVAILABILITY_DEFAULT
    kwh_per_m3_ch4: float = cfg.KWH_PER_M3_CH4_DEFAULT


def wear_pct_per_month(h2s_ppm: float) -> float:
    """Скорость износа ГПУ, %/мес, в зависимости от H2S."""
    ratio = max(h2s_ppm, 1.0) / cfg.H2S_BASELINE_PPM
    return cfg.WEAR_BASE_PCT_MONTH * ratio ** cfg.WEAR_EXPONENT


def run_maintenance(inp: MaintenanceInput) -> dict:
    genset_count = max(1, math.ceil(inp.installed_mw / cfg.GENSET_RATING_MW))
    wear = wear_pct_per_month(inp.h2s_ppm)

    # Газ и сера
    lfg_flow_m3_month = inp.ch4_m3_month / inp.methane_fraction
    sulfur_kg_month = (
        lfg_flow_m3_month * inp.h2s_ppm * 1e-6 * cfg.H2S_DENSITY_KG_PER_M3
    )

    # Скрубберы: beds параллельных загрузок (по одной на ГПУ)
    beds = genset_count
    total_capacity_kg = beds * cfg.SCRUBBER_BED_CAPACITY_KG
    life_months = total_capacity_kg / sulfur_kg_month if sulfur_kg_month > 0 else 999.0
    replacements_per_year = 12.0 / life_months if life_months > 0 else 0.0
    scrubbing_usd_month = (
        sulfur_kg_month / cfg.SCRUBBER_BED_CAPACITY_KG * cfg.SCRUBBER_REPLACEMENT_USD
    )

    # Парк генераторов с детерминированным разбросом наработки (±4 мес)
    generators: list[dict] = []
    for i in range(genset_count):
        stagger = ((i * 7) % 9) - 4
        months_i = max(1, inp.months_operated + stagger)
        health = max(cfg.HEALTH_FLOOR_PCT, 100.0 - wear * months_i)
        rul = (health - cfg.HEALTH_FLOOR_PCT) / wear if wear > 0 else 999.0
        if rul < 12.0:
            risk = min(0.95, 0.05 + 0.9 * (12.0 - rul) / 12.0)
        else:
            risk = 0.05
        status = "healthy" if health >= 80 else ("degraded" if health >= 50 else "critical")
        generators.append(
            {
                "id": f"JEN-{i + 1:02d}",
                "health_score": round(health, 1),
                "wear_pct_month": round(wear, 2),
                "rul_months": round(rul, 1),
                "failure_risk_12m": round(risk, 2),
                "status": status,
            }
        )

    weakest = min(generators, key=lambda g: g["health_score"])

    # Электроэнергия и OPEX
    energy_mwh_month = (
        inp.ch4_m3_month
        * inp.genset_availability
        * inp.kwh_per_m3_ch4
        / 1000.0
    )
    consumables_usd_month = energy_mwh_month * cfg.OIL_CONSUMABLES_USD_PER_MWH
    labor_usd_month = cfg.OPEX_LABOR_USD_YEAR / 12.0

    plant_capex, _breakdown = estimate_plant_capex(genset_count, inp.installed_mw)
    depreciation_usd_month = plant_capex / 10.0 / 12.0        # амортизация станции 10 лет
    insurance_usd_month = plant_capex * cfg.OPEX_INSURANCE_SHARE / 12.0
    overhaul_reserve_month = (
        sum(g["failure_risk_12m"] for g in generators) * cfg.OVERHAUL_COST_USD / 12.0
    )

    opex_monthly = {
        "scrubbing_usd": round(scrubbing_usd_month, 2),
        "consumables_usd": round(consumables_usd_month, 2),
        "labor_usd": round(labor_usd_month, 2),
        "insurance_usd": round(insurance_usd_month, 2),
        "plant_depreciation_usd": round(depreciation_usd_month, 2),
        "overhaul_reserve_usd": round(overhaul_reserve_month, 2),
    }
    opex_monthly["total_usd"] = round(sum(opex_monthly.values()), 2)

    variable_annual = (scrubbing_usd_month + consumables_usd_month + overhaul_reserve_month) * 12.0
    fixed_annual = (labor_usd_month + insurance_usd_month + depreciation_usd_month) * 12.0

    return {
        "installed_mw": round(inp.installed_mw, 3),
        "genset_count": genset_count,
        "genset_rating_mw": cfg.GENSET_RATING_MW,
        "wear_pct_month": round(wear, 3),
        "gas": {
            "lfg_flow_m3_month": round(lfg_flow_m3_month, 1),
            "h2s_ppm": inp.h2s_ppm,
            "sulfur_load_kg_month": round(sulfur_kg_month, 2),
        },
        "generators": generators,
        "fleet_health_score": weakest["health_score"],
        "weakest": weakest,
        "scrubber": {
            "beds": beds,
            "bed_capacity_kg": cfg.SCRUBBER_BED_CAPACITY_KG,
            "total_capacity_kg": round(total_capacity_kg, 1),
            "load_kg_month": round(sulfur_kg_month, 2),
            "life_months": round(life_months, 1),
            "replacements_per_year": round(replacements_per_year, 2),
            "cost_per_replacement_usd": cfg.SCRUBBER_REPLACEMENT_USD,
            "annual_cost_usd": round(replacements_per_year * cfg.SCRUBBER_REPLACEMENT_USD, 2),
        },
        "energy_mwh_month": round(energy_mwh_month, 1),
        "opex_monthly_usd": opex_monthly,
        "opex_variable_annual_usd": round(variable_annual, 2),
        "opex_fixed_annual_usd": round(fixed_annual, 2),
        "opex_annual_usd": round(variable_annual + fixed_annual, 2),
    }
