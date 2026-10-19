"""Тесты карбонового модуля (баланс массы, буфер, лаг, цены)."""
import pytest

from app.engines.carbon import CarbonParams, compute_carbon

MONTH_M3 = 1_600_000.0


def test_mass_balance_and_buffer():
    res = compute_carbon([MONTH_M3] * 24, CarbonParams())
    year1 = res["annual"][0]
    ch4_m3 = MONTH_M3 * 12
    ch4_t = ch4_m3 * 0.716 / 1000.0
    assert year1["ch4_destroyed_t"] == pytest.approx(ch4_t, rel=1e-6)
    assert year1["baseline_co2e_t"] == pytest.approx(ch4_t * 28.0, rel=1e-6)
    assert year1["net_credits_t"] == pytest.approx(ch4_t * 28.0 * 0.8, rel=1e-6)
    assert year1["buffer_credits_t"] == pytest.approx(ch4_t * 28.0 * 0.2, rel=1e-6)
    assert len(res["annual"]) == 2
    assert res["totals"]["net_credits_t"] == pytest.approx(year1["net_credits_t"] * 2, rel=1e-6)


def test_credit_revenue_matches_price_and_fee():
    res = compute_carbon([MONTH_M3] * 12, CarbonParams())
    net_credits = res["totals"]["net_credits_t"]
    expected = net_credits * 15.0 - net_credits * 0.10
    assert res["scenarios"]["p50"]["total_revenue_usd"] == pytest.approx(expected, rel=1e-6)
    p10, p50, p90 = (
        res["scenarios"][key]["total_revenue_usd"] for key in ("p10", "p50", "p90")
    )
    assert p10 < p50 < p90


def test_verification_lag_shifts_revenue():
    no_lag = compute_carbon([MONTH_M3] * 12, CarbonParams(verification_lag_months=0))
    lagged = compute_carbon([MONTH_M3] * 12, CarbonParams(verification_lag_months=12))
    assert no_lag["scenarios"]["p50"]["revenue_usd"][0] > 0
    assert lagged["scenarios"]["p50"]["revenue_usd"][0] == 0
    assert lagged["scenarios"]["p50"]["revenue_usd"][1] > 0


def test_validation():
    with pytest.raises(ValueError):
        CarbonParams(buffer_share=1.0)
    with pytest.raises(ValueError):
        CarbonParams(verification_lag_months=6)
    with pytest.raises(ValueError):
        compute_carbon([MONTH_M3] * 10)
    with pytest.raises(ValueError):
        compute_carbon([-1.0] * 12)


def test_notes_mention_methodology():
    res = compute_carbon([MONTH_M3] * 12)
    assert "ACM0001" in res["methodology"]
    assert any("вентирование" in note for note in res["notes"])
    assert res["disclaimer"]
