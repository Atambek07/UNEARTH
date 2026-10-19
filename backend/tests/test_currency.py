"""Тесты валютного блока."""
import pytest

from app.engines.currency import CurrencyParams, compute_currency


def test_conversion_and_costs():
    params = CurrencyParams(
        usd_kgs_rate=87.4,
        conversion_spread=0.015,
        repatriation_share=1.0,
        repatriation_cost_share=0.005,
        hedging_cost_share=0.01,
    )
    res = compute_currency([1_000_000.0], params)
    row = res["annual"][0]
    assert row["conversion_cost_usd"] == pytest.approx(15_000.0)
    assert row["repatriation_cost_usd"] == pytest.approx(5_000.0)
    assert row["hedging_cost_usd"] == pytest.approx(10_000.0)
    assert row["net_usd"] == pytest.approx(970_000.0)
    assert row["kgs_received"] == pytest.approx(970_000.0 * 87.4)
    assert res["totals"]["cost_share"] == pytest.approx(0.03, abs=1e-6)


def test_partial_repatriation():
    params = CurrencyParams(repatriation_share=0.5, repatriation_cost_share=0.01)
    res = compute_currency([100_000.0], params)
    assert res["annual"][0]["repatriated_usd"] == pytest.approx(50_000.0)
    assert res["annual"][0]["repatriation_cost_usd"] == pytest.approx(500.0)


def test_validation_errors():
    with pytest.raises(ValueError):
        CurrencyParams(usd_kgs_rate=0)
    with pytest.raises(ValueError):
        CurrencyParams(conversion_spread=1.5)
    with pytest.raises(ValueError):
        compute_currency([])
    with pytest.raises(ValueError):
        compute_currency([-1.0])
