"""Реальные рыночные данные: live-провайдер с кэшем и откатом на синтетику.

Источники (без ключей, публичные API):
  * курс BTC: CoinGecko `simple/price` → резерв Coinbase `prices/BTC-USD/spot`;
  * хешрейт сети: mempool.space `/api/v1/mining/hashrate/3d` (currentHashrate,
    H/s) → резерв blockchain.info `q/getdifficulty` (difficulty × 2^32 / 600 W).

Кэш в памяти с TTL (по умолчанию 10 мин). Любая сетевая ошибка/парсинг →
fallback на синтетические значения из config.py; в ответе всегда честно
указан источник (`live`/`synthetic`) и примечания.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from app import config as cfg

PROVIDERS = ("auto", "live", "synthetic")

BTC_URLS = [
    "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd",
    "https://api.coinbase.com/v2/prices/BTC-USD/spot",
]
HASHRATE_URLS = [
    "https://mempool.space/api/v1/mining/hashrate/3d",
    "https://blockchain.info/q/getdifficulty",
]


@dataclass
class LiveMarket:
    btc_price: float
    network_hashrate_ths: float
    source: str                # "live" | "synthetic"
    fetched_at: str | None     # ISO UTC, если удалось получить данные
    notes: list[str] = field(default_factory=list)


def _http_get_json(url: str, timeout_s: float) -> dict | list | str:
    """GET с JSON-парсингом; вынесен для мокирования в тестах."""
    request = urllib.request.Request(url, headers={"User-Agent": "UNEARTH-MVP/0.2"})
    with urllib.request.urlopen(request, timeout=timeout_s) as response:  # noqa: S310
        raw = response.read().decode("utf-8")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return raw  # blockchain.info/q возвращает plain text


def _fetch_btc_price(timeout_s: float) -> tuple[float, list[str]]:
    notes: list[str] = []
    for url in BTC_URLS:
        try:
            data = _http_get_json(url, timeout_s)
            if url.startswith("https://api.coingecko"):
                price = float(data["bitcoin"]["usd"])
            else:
                price = float(data["data"]["amount"])
            if price > 0:
                return price, notes
        except Exception as exc:  # noqa: BLE001 — источник может упасть, идём к следующему
            notes.append(f"{url}: {type(exc).__name__}")
    return cfg.BTC_PRICE_DEFAULT, [*notes, "BTC-курс: все live-источники недоступны, использован дефолт"]


def _fetch_hashrate(timeout_s: float) -> tuple[float, list[str]]:
    notes: list[str] = []
    for url in HASHRATE_URLS:
        try:
            data = _http_get_json(url, timeout_s)
            if "mempool" in url:
                hashrate_hs = float(data["currentHashrate"])
            else:
                difficulty = float(data)
                hashrate_hs = difficulty * (2**32) / 600.0  # W при блоке 10 мин
            if hashrate_hs > 0:
                return hashrate_hs / 1e12, notes  # H/s → TH/s
        except Exception as exc:  # noqa: BLE001
            notes.append(f"{url}: {type(exc).__name__}")
    return (
        cfg.NETWORK_HASHRATE_THS,
        [*notes, "Хешрейт: live-источники недоступны, использован дефолт"],
    )


_cache: dict[str, tuple[float, float, float, str]] = {}


def get_live_market(
    force_refresh: bool = False,
    timeout_s: float = cfg.MARKET_HTTP_TIMEOUT_S,
    now: float | None = None,
) -> LiveMarket:
    """Курс и хешрейт из публичных API (или откат на дефолты с пометкой)."""
    ts = time.time() if now is None else now
    cached = _cache.get("live")
    if not force_refresh and cached and ts - cached[0] < cfg.MARKET_TTL_SECONDS:
        return LiveMarket(cached[1], cached[2], "live", cached[3], ["из кэша (TTL 10 мин)"])

    notes: list[str] = []
    btc, btc_notes = _fetch_btc_price(timeout_s)
    hashrate, hr_notes = _fetch_hashrate(timeout_s)
    notes += btc_notes + hr_notes
    fetched_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts))
    is_fallback = any("недоступны" in n for n in notes)
    source = "synthetic" if is_fallback else "live"
    _cache["live"] = (ts, btc, hashrate, fetched_at)
    return LiveMarket(btc, hashrate, source, fetched_at if not is_fallback else None, notes)


def resolve_market(
    provider: str,
    btc_price: float | None,
    gpu_rent: float | None,
) -> tuple[float, float, float | None, str, str | None, list[str]]:
    """Разрешает цены для расчётов.

    Возвращает (btc_price, gpu_rent, network_hashrate_ths, source, fetched_at, notes).
    network_hashrate_ths — None для синтетики (используется константа config);
    для live — фактический хешрейт сети.
    """
    if provider not in PROVIDERS:
        raise ValueError(f"market provider must be one of {PROVIDERS}")

    btc = btc_price if btc_price is not None else cfg.BTC_PRICE_DEFAULT
    rent = gpu_rent if gpu_rent is not None else cfg.GPU_RENT_DEFAULT

    if provider == "synthetic":
        return btc, rent, None, "synthetic", None, ["Синтетический рынок (по ТЗ MVP)"]

    live = get_live_market()
    if provider == "auto" and live.source == "synthetic":
        notes = [*live.notes, "auto → откат на синтетику"]
        return btc, rent, None, "synthetic", None, notes

    # live (или auto с живыми данными): цены пользователя имеют приоритет
    used_btc = btc_price if btc_price is not None else live.btc_price
    used_rent = gpu_rent if gpu_rent is not None else cfg.GPU_RENT_DEFAULT
    notes = list(live.notes)
    return used_btc, used_rent, live.network_hashrate_ths, "live", live.fetched_at, notes


def reset_cache() -> None:
    """Сброс кэша (для тестов)."""
    _cache.clear()
