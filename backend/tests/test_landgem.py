"""Тесты физического ядра LandGEM."""
import pytest

from app.engines.landgem import (
    LandGEMInput,
    annual_aggregate,
    avg_power_mw,
    monthly_ch4_history,
    monthly_ch4_m3,
    monthly_energy_mwh,
)


def test_monthly_and_annual_shapes() -> None:
    inp = LandGEMInput(horizon_years=15)
    monthly = monthly_ch4_m3(inp)
    assert len(monthly) == 15 * 12
    assert all(q > 0 for q in monthly)
    annual = annual_aggregate(monthly)
    assert len(annual) == 15
    assert all(a > 0 for a in annual)


def test_legacy_curve_decays_without_inflow() -> None:
    """Без притока кривая обязана монотонно затухать (первый порядок распада)."""
    inp = LandGEMInput(annual_inflow_tonnes=0.0, horizon_years=20)
    monthly = monthly_ch4_m3(inp)
    assert monthly[0] > monthly[-1]
    assert all(monthly[i] >= monthly[i + 1] - 1e-6 for i in range(len(monthly) - 1))


def test_steady_inflow_holds_level() -> None:
    """Стационарный приток удерживает уровень генерации.

    За 20 лет legacy-компонента обязана затухнуть как e^(-k·T) ≈ 0.55, поэтому
    полное падение кривой ограничено (~20 % при доле legacy ~44 % в год 1),
    а итоговый уровень в разы выше сценария «без притока» (там осталась бы
    только затухшая legacy-компонента).
    """
    with_inflow = LandGEMInput(annual_inflow_tonnes=375_000, horizon_years=20)
    monthly = monthly_ch4_m3(with_inflow)
    assert monthly[-1] > 0.75 * monthly[0]

    without_inflow = LandGEMInput(annual_inflow_tonnes=0.0, horizon_years=20)
    legacy_only = monthly_ch4_m3(without_inflow)
    assert monthly[-1] > 2.5 * legacy_only[-1]


def test_history_trend_positive() -> None:
    inp = LandGEMInput(horizon_years=15)
    hist = monthly_ch4_history(inp, 48)
    assert len(hist) == 48
    assert all(q > 0 for q in hist)


def test_energy_conversion() -> None:
    """1 м³ CH4 × 3.5 кВт·ч × отбор × готовность → МВт·ч (константы из PDF)."""
    inp = LandGEMInput(collection_efficiency=0.75, genset_availability=0.92, kwh_per_m3_ch4=3.5)
    q = 1_000_000.0
    expected = q * 0.75 * 0.92 * 3.5 / 1000.0
    assert abs(monthly_energy_mwh(q, inp) - expected) < 1e-9
    assert abs(avg_power_mw(7300.0) - 10.0) < 1e-9


def test_invalid_inputs_rejected() -> None:
    with pytest.raises(ValueError):
        LandGEMInput(k_per_year=0.0)
    with pytest.raises(ValueError):
        LandGEMInput(horizon_years=2)
    with pytest.raises(ValueError):
        LandGEMInput(collection_efficiency=1.5)
