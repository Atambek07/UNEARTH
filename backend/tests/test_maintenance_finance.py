"""Тесты предиктивного обслуживания (H2S) и финансового блока."""
from app.engines.finance import FinanceInput, run_finance
from app.engines.maintenance import MaintenanceInput, run_maintenance, wear_pct_per_month

MONTHS = 180
POWER = [6.0] * MONTHS
CH4 = [1_800_000.0] * MONTHS


def test_wear_grows_with_h2s() -> None:
    assert wear_pct_per_month(100.0) > wear_pct_per_month(25.0)
    assert wear_pct_per_month(25.0) > 0


def test_scrubber_and_health_react_to_h2s() -> None:
    low = run_maintenance(MaintenanceInput(installed_mw=5.0, ch4_m3_month=2_000_000.0, h2s_ppm=20.0))
    high = run_maintenance(MaintenanceInput(installed_mw=5.0, ch4_m3_month=2_000_000.0, h2s_ppm=80.0))
    assert high["scrubber"]["life_months"] < low["scrubber"]["life_months"]
    assert high["fleet_health_score"] < low["fleet_health_score"]
    assert high["opex_monthly_usd"]["scrubbing_usd"] > low["opex_monthly_usd"]["scrubbing_usd"]
    assert len(low["generators"]) == 5  # 5 МВт → 5 ГПУ по 1 МВт
    assert all(0 < g["health_score"] <= 100 for g in low["generators"])
    assert all(g["rul_months"] >= 0 for g in low["generators"])


def test_finance_monte_carlo_structure() -> None:
    inp = FinanceInput(
        horizon_years=15,
        monthly_power_mw=POWER,
        monthly_ch4_m3_delivered=CH4,
        miners_count=1000,
        ai_servers_count=400,
        opex_variable_annual_usd=2_000_000.0,
        opex_fixed_annual_usd=1_500_000.0,
        n_sims=120,
    )
    res = run_finance(inp)
    assert res["capex_total_usd"] > 0
    assert len(res["annual"]) == 15
    assert len(res["chart"]) == 16  # Y0 + 15 лет
    assert res["chart"][0]["capex_usd"] > 0
    for row in res["annual"]:
        assert row["net_profit_p10_usd"] <= row["net_profit_p50_usd"] <= row["net_profit_p90_usd"]
        assert row["co2_avoided_t"] > 0
        assert row["green_fund_usd"] >= 0
        assert row["trees_planted"] >= 0
    # Фонд озеленения = ровно 5 % положительной чистой прибыли (p50)
    positive = [max(row["net_profit_p50_usd"], 0) for row in res["annual"]]
    expected_fund = sum(0.05 * p for p in positive)
    assert abs(res["totals"]["green_fund_usd"] - expected_fund) < 1.0
    if res["payback_years"] is not None:
        assert 0 < res["payback_years"] <= 15
    if res["irr"] is not None:
        assert -0.9 < res["irr"] < 3.0
