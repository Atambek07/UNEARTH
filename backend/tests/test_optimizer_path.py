"""Тесты упреждающего балансировщика (optimize/path)."""
import pytest

from app.engines.optimizer import optimize_path

POWER = [13.0] * 12


def test_plan_respects_power_caps():
    power = [13.0, 10.0, 8.0, 13.0, 6.0, 12.0]
    res = optimize_path(monthly_power_mw=power)
    assert len(res["plan"]) == len(power)
    for row in res["plan"]:
        assert row["used_mw"] <= row["allocatable_mw"] + 1e-3
        assert row["ai_servers"] >= 0 and row["miners"] >= 0
    assert res["totals"]["improvement_usd"] >= 0


def test_reserve_grows_before_autumn():
    m = 10
    power = [13.0] * m
    # влажность по месяцам горизонта: пик бахчевых на 8-м месяце (10 значений под m)
    moisture = [1.0] * 7 + [1.15, 1.05, 1.0]
    res = optimize_path(monthly_power_mw=power, monthly_moisture=moisture)
    reserves = [row["reserve_share"] for row in res["plan"]]
    assert reserves[7] > reserves[0]  # резерв перед влажным месяцем выше


def test_dp_beats_naive_through_btc_dip():
    """Месячный провал BTC ниже безубыточности (~19.6 тыс. $): наивный greedy
    дважды переключает парк (изъять и вернуть ~2.4 тыс. асиков), DP выгоднее
    удержать парк через провал — improvement строго положителен."""
    btc_path = [65_000.0] * 12
    btc_path[5] = 15_000.0
    res = optimize_path(
        monthly_power_mw=POWER,
        monthly_btc_price=btc_path,
        switching_cost_miner_usd=40.0,
        switching_cost_ai_usd=200.0,
    )
    totals = res["totals"]
    assert totals["improvement_usd"] > 0
    assert totals["optimized_net_usd"] >= totals["naive_net_usd"]
    assert totals["naive_switch_cost_usd"] > 0


def test_switch_events_reflect_plan_changes():
    """При дешёвых переключениях DP тоже глушит парк в глубоком провале —
    и события переключений появляются на выбранном пути."""
    btc_path = [65_000.0] * 12
    btc_path[5] = 15_000.0
    res = optimize_path(
        monthly_power_mw=POWER,
        monthly_btc_price=btc_path,
        switching_cost_miner_usd=1.0,
        switching_cost_ai_usd=1.0,
    )
    events = res["switch_events"]
    assert events, "ожидались события переключений в глубоком провале"
    assert all(event["cost_usd"] >= 0 for event in events)


def test_validation_errors():
    with pytest.raises(ValueError):
        optimize_path(monthly_power_mw=[1.0, 2.0])
    with pytest.raises(ValueError):
        optimize_path(monthly_power_mw=POWER, monthly_moisture=[1.0] * 5)
    with pytest.raises(ValueError):
        optimize_path(monthly_power_mw=POWER, monthly_btc_price=[1.0] * 5)
