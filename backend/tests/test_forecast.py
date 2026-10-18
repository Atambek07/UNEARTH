"""Тесты гибридного ML-прогноза (сезонность, AR(1), доверительные интервалы)."""
from datetime import date

import numpy as np

from app.engines.landgem import LandGEMInput, monthly_ch4_history
from app.engines.seasonal import (
    HISTORY_MONTHS,
    SeasonalParams,
    decompose,
    moisture_index,
    run_hybrid_forecast,
    seasonal_multiplier,
)

START = date(2026, 11, 1)


def test_moisture_index_autumn_peak() -> None:
    """Осенний пик влажности (арбузы/дыни) больше летней засухи."""
    p = SeasonalParams()
    assert moisture_index(10, p) > moisture_index(7, p)
    assert moisture_index(9, p) > 1.0


def test_seasonal_multiplier_sane() -> None:
    p = SeasonalParams()
    for m in range(1, 13):
        mult = seasonal_multiplier(m, p)
        assert 0.8 < mult < 1.4


def test_builtin_forecast_structure_and_ci() -> None:
    inp = LandGEMInput(horizon_years=15)
    bundle = run_hybrid_forecast(inp, SeasonalParams(seed=42), START, use_prophet=False)
    assert len(bundle.dates) == 180
    assert bundle.dates[0] == START
    assert all(bundle.dates[i] < bundle.dates[i + 1] for i in range(len(bundle.dates) - 1))
    for point, lo, up, trend in zip(
        bundle.forecast_ch4_m3, bundle.ci_lower, bundle.ci_upper, bundle.landgem_ch4_m3
    ):
        assert lo <= point + 1e-6
        assert point <= up + 1e-6
        assert lo > 0
        assert up <= trend * 3.0 + 1e-6  # санити-потолок интервала
    assert bundle.meta["model"] == "builtin-seasonal-ar1"
    assert not bundle.meta["prophet_used"]
    assert -0.95 <= bundle.meta["ar1_rho"] <= 0.95
    assert abs(sum(bundle.meta["seasonal_index"]) / 12 - 1.0) < 0.05


def test_autumn_seasonality_survives_decomposition() -> None:
    """Эмпирические сезонные индексы: сентябрь–октябрь выше июля."""
    inp = LandGEMInput(horizon_years=15)
    trend_h = np.asarray(monthly_ch4_history(inp, HISTORY_MONTHS), dtype=float)
    months_h = np.arange(HISTORY_MONTHS)
    # календарные месяцы истории: октябрь 2026 назад на 48 мес
    hist_dates = np.array([month for month in _history_months()])
    p = SeasonalParams(seed=42)
    rng = np.random.default_rng(p.seed)
    obs = _synthetic_hist(trend_h, hist_dates, p, rng)
    fit = decompose(obs, hist_dates, p)
    assert fit.seasonal_index[8] > fit.seasonal_index[6]  # сентябрь > июль
    assert fit.seasonal_index[9] > fit.seasonal_index[6]  # октябрь > июль


def _history_months() -> list[int]:
    months = []
    y, m = 2026, 10  # последний месяц истории — октябрь 2026
    for _ in range(HISTORY_MONTHS):
        months.append(m)
        m -= 1
        if m == 0:
            m = 12
            y -= 1
    return list(reversed(months))


def _synthetic_hist(
    trend: np.ndarray, months: np.ndarray, p: SeasonalParams, rng: np.random.Generator
) -> np.ndarray:
    from app.engines.seasonal import _synthetic_history

    return _synthetic_history(trend, months, p, rng)


def test_prophet_fallback_when_unavailable() -> None:
    """Если Prophet не установлен — откат на builtin с примечанием в meta."""
    try:
        import prophet  # noqa: F401

        prophet_installed = True
    except Exception:
        prophet_installed = False
    if prophet_installed:
        return  # в среде с Prophet проверяется основной путь
    inp = LandGEMInput(horizon_years=5)
    bundle = run_hybrid_forecast(inp, SeasonalParams(seed=42), START, use_prophet=True)
    assert not bundle.meta["prophet_used"]
    assert bundle.meta["model"] == "builtin-seasonal-ar1"
    assert bundle.meta["notes"]
