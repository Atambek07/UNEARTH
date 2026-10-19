"""Тесты live-провайдера рыночных данных (мок HTTP, кэш, откат)."""
from app import config as cfg
from app.engines import market_data as md


def _fake_get(responses: dict):
    def fake(url: str, timeout_s: float):
        for prefix, value in responses.items():
            if url.startswith(prefix):
                if isinstance(value, Exception):
                    raise value
                return value
        raise AssertionError(f"unexpected url: {url}")

    return fake


def test_live_success(monkeypatch):
    md.reset_cache()
    monkeypatch.setattr(
        md,
        "_http_get_json",
        _fake_get(
            {
                "https://api.coingecko": {"bitcoin": {"usd": 71_000.0}},
                "https://mempool.space": {"currentHashrate": 7.5e20},
            }
        ),
    )
    live = md.get_live_market(force_refresh=True, now=1_000.0)
    assert live.source == "live"
    assert live.btc_price == 71_000.0
    assert live.network_hashrate_ths == 750_000_000.0  # 7.5e20 H/s = 750 EH/s = 7.5e8 TH/s
    assert live.fetched_at is not None
    md.reset_cache()


def test_cache_hit_within_ttl(monkeypatch):
    md.reset_cache()
    calls = {"n": 0}

    def fake(url: str, timeout_s: float):
        calls["n"] += 1
        if "coingecko" in url:
            return {"bitcoin": {"usd": 71_000.0}}
        return {"currentHashrate": 7.5e20}

    monkeypatch.setattr(md, "_http_get_json", fake)
    md.get_live_market(force_refresh=True, now=1_000.0)
    second = md.get_live_market(now=1_000.0 + 60)
    assert second.source == "live"
    assert any("кэш" in note for note in second.notes)
    assert calls["n"] == 2  # btc + hashrate; повторный вызов из кэша
    md.reset_cache()


def test_fallback_on_network_error(monkeypatch):
    md.reset_cache()
    monkeypatch.setattr(
        md, "_http_get_json", _fake_get({"https://": TimeoutError("no network")})
    )
    live = md.get_live_market(force_refresh=True, now=2_000.0)
    assert live.source == "synthetic"
    assert live.btc_price == cfg.BTC_PRICE_DEFAULT
    assert live.network_hashrate_ths == cfg.NETWORK_HASHRATE_THS
    assert live.fetched_at is None
    assert any("недоступны" in note for note in live.notes)
    md.reset_cache()


def test_resolve_synthetic_defaults():
    md.reset_cache()
    btc, rent, hashrate, source, fetched_at, notes = md.resolve_market(
        "synthetic", None, None
    )
    assert source == "synthetic"
    assert hashrate is None
    assert btc == cfg.BTC_PRICE_DEFAULT
    assert rent == cfg.GPU_RENT_DEFAULT
    assert notes


def test_resolve_auto_falls_back(monkeypatch):
    md.reset_cache()
    monkeypatch.setattr(
        md, "_http_get_json", _fake_get({"https://": TimeoutError("no network")})
    )
    btc, rent, hashrate, source, fetched_at, notes = md.resolve_market("auto", None, None)
    assert source == "synthetic"
    assert any("откат" in note for note in notes)
    md.reset_cache()


def test_user_price_overrides_live(monkeypatch):
    md.reset_cache()
    monkeypatch.setattr(
        md,
        "_http_get_json",
        _fake_get(
            {
                "https://api.coingecko": {"bitcoin": {"usd": 71_000.0}},
                "https://mempool.space": {"currentHashrate": 7.5e20},
            }
        ),
    )
    btc, rent, hashrate, source, fetched_at, notes = md.resolve_market(
        "live", 60_000.0, 2.5
    )
    assert btc == 60_000.0
    assert rent == 2.5
    assert hashrate == 750_000_000.0
    assert source == "live"
    md.reset_cache()
