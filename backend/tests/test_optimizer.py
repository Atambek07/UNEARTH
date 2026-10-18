"""Тесты Smart Grid балансировщика и рыночной ML-модели."""
from app.engines.market import get_market_model
from app.engines.optimizer import (
    AI_SERVER,
    ANTMINER,
    ai_revenue_usd_day,
    amortization_usd_day,
    auto_allocate,
    gas_quality,
    manual_allocate,
    mining_revenue_usd_day,
)

DEFAULTS = dict(ch4_fraction=0.52, h2s_ppm=30.0, btc_price=65_000.0, gpu_rent=2.0, seed=42)


def test_market_model_deterministic_and_bounded() -> None:
    m1 = get_market_model(42)
    m2 = get_market_model(42)
    assert m1 is m2  # lru_cache
    pred = m1.predict_return_3m(65_000.0, 2.0)
    assert -0.35 <= pred <= 0.35
    mult = m1.miner_margin_multiplier(pred)
    assert 0.25 <= mult <= 1.5


def test_revenue_and_amortization_formulas() -> None:
    """Доход майнера: 144 блока × 3.125 BTC / хешрейт сети × 110 TH (пул 1.5 %)."""
    expected_miner = (
        144 * 3.125 / 700_000_000.0 * 110.0 * 65_000.0 * (1 - 0.015)
    )
    assert abs(mining_revenue_usd_day(65_000.0) - expected_miner) < 1e-6
    assert abs(ai_revenue_usd_day(2.0) - 2.0 * 24 * 2) < 1e-9
    assert abs(amortization_usd_day(3.25) - 3.25 * 24 * 0.0175) < 1e-9


def test_auto_allocation_respects_power_cap() -> None:
    res = auto_allocate(available_mw=5.0, **DEFAULTS)
    used = sum(r["power_mw"] for r in res["allocation"])
    assert used <= res["allocatable_mw"] + 1e-3
    assert res["curtailed_mw"] >= 0
    assert not res["overcommitted"]
    assert res["used_mw"] > 0  # при нормальном рынке что-то работает
    assert all(r["count"] >= 0 for r in res["allocation"])


def test_ai_capped_by_gpu_market() -> None:
    res = auto_allocate(available_mw=50.0, **DEFAULTS)
    ai = next(r for r in res["allocation"] if r["node_type"] == "ai_server")
    assert ai["count"] == 1000 // 2  # 1000 арендуемых GPU / 2 на сервер
    assert res["curtailed_mw"] > 0 or (
        next(r for r in res["allocation"] if r["node_type"] == "antminer_s19_pro")["count"] > 0
    )


def test_quality_derate_and_stability() -> None:
    good = gas_quality(0.52, 20.0)
    bad = gas_quality(0.42, 120.0)
    assert bad["derate_factor"] < good["derate_factor"]
    assert good["stable"]
    assert not bad["stable"]


def test_manual_overcommit_flag() -> None:
    res = manual_allocate(
        available_mw=1.0,
        ch4_fraction=0.52,
        h2s_ppm=30.0,
        btc_price=65_000.0,
        gpu_rent=2.0,
        manual_miners=1000,
        manual_ai_servers=300,
        seed=42,
    )
    assert res["manual"]
    assert res["overcommitted"]


def test_shutdown_ladder_starts_with_miners() -> None:
    """Наименее маржинальные узлы (майнеры при базовых ценах) отключаются первыми."""
    res = auto_allocate(available_mw=0.4, **DEFAULTS)
    assert res["shutdown_order"][0] == ANTMINER.label
    assert AI_SERVER.label in res["shutdown_order"]
    rationale = " ".join(res["rationale"])
    assert "derate" in rationale
