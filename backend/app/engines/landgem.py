"""Модуль 1а — физическое ядро: модель LandGEM (EPA, first-order decay).

Считает месячную кривую образования CH4 на 15–20 лет из двух источников:
  * «старое тело» свалки — 20 млн т, накопленных равномерно за 54 года (с 1972 г.):
    затухающие когорты Q_legacy(t) = r·L0·exp(-k·age)·Σ Mi·exp(-k·a0_i);
  * ежегодный приток 350–400 тыс. т/год: депонирование идёт непрерывно уже
    десятилетия, поэтому вклад притока — стационарный режим
    Q_inflow ≈ L0 × (M_год / 12) м³/мес (каждый месяц новая порция заменяет
    выгоревшие старые; точная сумма геометрической серии даёт множитель
    (k/12)/(1-e^{-k/12}) ≈ 1.013, которым для наглядности пренебрегаем).

LandGEM (годовая форма): Q(t) = Σ_i k · L0 · Mi · exp(-k · age_i(t)), м³ CH4/год.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from app import config as cfg


@dataclass(frozen=True)
class LandGEMInput:
    total_legacy_tonnes: float = cfg.LEGACY_TONNES_DEFAULT
    annual_inflow_tonnes: float = cfg.ANNUAL_INFLOW_TONNES_DEFAULT
    lo_m3_per_tonne: float = cfg.LO_DEFAULT
    k_per_year: float = cfg.K_DEFAULT
    legacy_deposition_years: int = cfg.LEGACY_DEPOSITION_YEARS
    horizon_years: int = cfg.HORIZON_YEARS_DEFAULT
    collection_efficiency: float = cfg.COLLECTION_EFFICIENCY_DEFAULT
    genset_availability: float = cfg.GENSET_AVAILABILITY_DEFAULT
    kwh_per_m3_ch4: float = cfg.KWH_PER_M3_CH4_DEFAULT

    def __post_init__(self) -> None:
        if self.total_legacy_tonnes < 0:
            raise ValueError("total_legacy_tonnes must be non-negative")
        if not 0.001 <= self.k_per_year <= 0.5:
            raise ValueError("k_per_year out of range")
        if self.lo_m3_per_tonne <= 0:
            raise ValueError("lo_m3_per_tonne must be positive")
        if self.annual_inflow_tonnes < 0:
            raise ValueError("annual_inflow_tonnes must be non-negative")
        if not 0 < self.collection_efficiency <= 1:
            raise ValueError("collection_efficiency must be in (0, 1]")
        if not 0 < self.genset_availability <= 1:
            raise ValueError("genset_availability must be in (0, 1]")
        if self.horizon_years < 3 or self.horizon_years > 25:
            raise ValueError("horizon_years must be within 3..25")


def legacy_cohorts(inp: LandGEMInput) -> list[tuple[float, float]]:
    """«Старое тело» свалки: список (возраст a0 в годах на сегодня, масса Mi, т).

    Равномерное накопление за legacy_deposition_years лет: возраст i-й порции
    a0 = i + 0.5 (середины лет), Mi = M_total / N.
    """
    n = max(1, int(inp.legacy_deposition_years))
    mass = inp.total_legacy_tonnes / n
    return [(i + 0.5, mass) for i in range(n)]


def _legacy_term(inp: LandGEMInput, age_offset_years: float) -> float:
    """Вклад legacy-когорт (м³ CH4/мес) при смещении возраста на age_offset_years.

    age_offset_years > 0 — будущие месяцы, < 0 — «история» для ML-слоя.
    Когорты, ещё не депонированные в моменте (a0 + offset < 0), дают ноль.
    """
    k = inp.k_per_year
    r = k / 12.0
    q = 0.0
    for a0, mass in legacy_cohorts(inp):
        age = a0 + age_offset_years
        if age >= 0:
            q += r * inp.lo_m3_per_tonne * mass * math.exp(-k * age)
    return q


def _inflow_term(inp: LandGEMInput) -> float:
    """Стационарный вклад притока, м³ CH4/мес ≈ L0 × месячная масса."""
    return (inp.annual_inflow_tonnes / 12.0) * inp.lo_m3_per_tonne


def monthly_ch4_m3(inp: LandGEMInput) -> list[float]:
    """Месячная кривая образования CH4, м³/мес, длина horizon_years × 12.

    Индекс 0 — первый месяц прогноза (следующий за текущим).
    """
    q_inflow = _inflow_term(inp)
    out: list[float] = []
    for t in range(inp.horizon_years * 12):
        out.append(_legacy_term(inp, t / 12.0) + q_inflow)
    return out


def monthly_ch4_history(inp: LandGEMInput, n_months: int) -> list[float]:
    """Физический тренд за n_months ДО старта горизонта (для обучения ML-слоя)."""
    q_inflow = _inflow_term(inp)
    out: list[float] = []
    for t in range(-n_months, 0):
        out.append(_legacy_term(inp, t / 12.0) + q_inflow)
    return out


def monthly_energy_mwh(q_m3_month: float, inp: LandGEMInput) -> float:
    """м³ CH4 → МВт·ч эл. с учётом отбора газа и готовности ГПУ."""
    return (
        q_m3_month
        * inp.collection_efficiency
        * inp.genset_availability
        * inp.kwh_per_m3_ch4
        / 1000.0
    )


def avg_power_mw(energy_mwh_month: float, hours_in_month: float = 730.0) -> float:
    """Средняя электрическая мощность за месяц, МВт."""
    return energy_mwh_month / hours_in_month


def annual_aggregate(monthly: list[float]) -> list[float]:
    """Сумма по 12 месяцам → годовые значения."""
    return [sum(monthly[i : i + 12]) for i in range(0, len(monthly), 12)]
