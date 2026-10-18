"""Модуль 2а — Smart Grid: ML-балансировщик нагрузки off-grid кластера.

Логика (ТЗ, Модуль 2 + риски №1/№2 из PDF):
  1) качество газа (CH4 %, H2S ppm) → derate-коэффициент доступной мощности;
  2) маржа на кВт·день по классам узлов:
       майнинг: доход TH·день × ML-множитель (прогноз BTC) − амортизация
                оборудования 1.75 ¢/кВт·ч (PDF, Модуль 2);
       ИИ:      рента GPU × 24 ч × GPU на сервер − та же амортизация;
  3) AI Auto-Optimize: жадное заполнение по убыванию маржи на кВт с рыночным
     ограничением спроса на GPU (не все серверы реально арендуются);
  4) при падении качества газа / мощности узлы отключаются по возрастанию
     маржи на кВт — «лестница отключений»: сначала майнеры, ядро ИИ остаётся.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app import config as cfg
from app.engines.market import MarketModel, get_market_model


@dataclass(frozen=True)
class NodeSpec:
    key: str
    label: str
    unit_power_kw: float
    capex_usd: float
    extra: dict = field(default_factory=dict)


ANTMINER = NodeSpec(
    key="antminer_s19_pro",
    label="Antminer S19 Pro (110 TH/s, 3.25 кВт)",
    unit_power_kw=cfg.ANTMINER_POWER_KW,
    capex_usd=cfg.ANTMINER_CAPEX_USD,
    extra={"hashrate_th": cfg.ANTMINER_HASHRATE_TH},
)
AI_SERVER = NodeSpec(
    key="ai_server",
    label="ИИ-сервер (2×GPU, 1.5 кВт)",
    unit_power_kw=cfg.AI_SERVER_POWER_KW,
    capex_usd=cfg.AI_SERVER_CAPEX_USD,
    extra={"gpus": cfg.GPUS_PER_AI_SERVER},
)


def r2(x: float, n: int = 2) -> float:
    return round(float(x), n)


def gas_quality(ch4_fraction: float, h2s_ppm: float) -> dict:
    """Derate доступной мощности по качеству газа.

    Стабильное горение ГПУ: CH4 ≥ 40 % (ниже — срывы пламени), полный номинал
    при ≥ 55 %. H2S > 50 ppm начинает ограничивать мощность (коррозия).
    """
    stability = cfg.clamp((ch4_fraction - 0.40) / 0.15, 0.0, 1.0)
    h2s_penalty = cfg.clamp((h2s_ppm - 50.0) / 150.0, 0.0, 0.45)
    derate = stability * (1.0 - h2s_penalty)
    return {
        "ch4_fraction": ch4_fraction,
        "h2s_ppm": h2s_ppm,
        "stability": r2(stability, 3),
        "h2s_penalty": r2(h2s_penalty, 3),
        "derate_factor": r2(derate, 3),
        "stable": bool(ch4_fraction >= 0.40 and h2s_ppm <= 100.0),
    }


def mining_revenue_usd_day(btc_price: float) -> float:
    """Доход одного Antminer S19 Pro, $/день (комиссия пула учтена)."""
    btc_per_th_day = cfg.BLOCKS_PER_DAY * cfg.BLOCK_REWARD_BTC / cfg.NETWORK_HASHRATE_THS
    return (
        btc_per_th_day
        * cfg.ANTMINER_HASHRATE_TH
        * btc_price
        * (1.0 - cfg.POOL_FEE_SHARE)
    )


def ai_revenue_usd_day(gpu_rent_usd_per_gpu_hour: float) -> float:
    """Доход одного ИИ-сервера, $/день (аренда GPU)."""
    return gpu_rent_usd_per_gpu_hour * 24.0 * cfg.GPUS_PER_AI_SERVER


def amortization_usd_day(power_kw: float) -> float:
    """Амортизация/износ оборудования, $/день: 1.5–2 ¢/кВт·ч (PDF, Модуль 2)."""
    return power_kw * 24.0 * cfg.AMORT_USD_PER_KWH


def _market_block(model: MarketModel, btc_price: float, gpu_rent: float) -> dict:
    pred = model.predict_return_3m(btc_price, gpu_rent)
    return {
        "btc_price": r2(btc_price),
        "gpu_rent_usd_per_gpu_hour": r2(gpu_rent),
        "predicted_3m_return": r2(pred, 4),
        "miner_margin_multiplier": r2(model.miner_margin_multiplier(pred), 3),
        "regime": "bearish" if pred < -0.08 else ("bullish" if pred > 0.08 else "neutral"),
    }


def _build_result(
    available_mw: float,
    quality: dict,
    market: dict,
    margins: dict,
    rows: list[dict],
    shutdown_order: list[str],
    rationale: list[str],
    manual: bool,
) -> dict:
    used_mw = sum(row["power_mw"] for row in rows)
    allocatable = available_mw * quality["derate_factor"] * (1.0 - cfg.AUX_LOAD_SHARE)
    return {
        "available_mw": r2(available_mw, 3),
        "allocatable_mw": r2(allocatable, 3),
        "quality": quality,
        "market": market,
        "margins": margins,
        "allocation": rows,
        "used_mw": r2(used_mw, 3),
        "curtailed_mw": r2(max(0.0, allocatable - used_mw), 3),
        "overcommitted": bool(used_mw > allocatable + 1e-9),
        "manual": manual,
        "shutdown_order": shutdown_order,
        "rationale": rationale,
    }


def auto_allocate(
    available_mw: float,
    ch4_fraction: float,
    h2s_ppm: float,
    btc_price: float,
    gpu_rent: float,
    seed: int = 42,
    gpu_demand_cap: int = cfg.MARKET_GPUS_RENTABLE,
) -> dict:
    """AI Auto-Optimize: максимизация прибыли при ограничениях мощности и рынка."""
    model = get_market_model(seed)
    quality = gas_quality(ch4_fraction, h2s_ppm)
    market = _market_block(model, btc_price, gpu_rent)

    m_mining = (
        mining_revenue_usd_day(btc_price) * market["miner_margin_multiplier"]
        - amortization_usd_day(ANTMINER.unit_power_kw)
    ) / ANTMINER.unit_power_kw
    m_ai = (
        ai_revenue_usd_day(gpu_rent) - amortization_usd_day(AI_SERVER.unit_power_kw)
    ) / AI_SERVER.unit_power_kw
    margins = {"mining_usd_per_kw_day": r2(m_mining), "ai_usd_per_kw_day": r2(m_ai)}

    max_ai_servers = int(gpu_demand_cap // cfg.GPUS_PER_AI_SERVER)
    classes = [
        (AI_SERVER, m_ai, max_ai_servers),
        (ANTMINER, m_mining, None),
    ]
    classes.sort(key=lambda item: -item[1])

    remaining_kw = available_mw * quality["derate_factor"] * (1.0 - cfg.AUX_LOAD_SHARE) * 1000.0
    rows: list[dict] = []
    for spec, margin, cap in classes:
        if margin <= 0:
            count = 0
        else:
            unit_draw_kw = spec.unit_power_kw * cfg.PUE_DC
            count = int(remaining_kw // unit_draw_kw) if unit_draw_kw > 0 else 0
            if cap is not None:
                count = min(count, cap)
        power_mw = count * spec.unit_power_kw * cfg.PUE_DC / 1000.0
        revenue_day = count * (
            mining_revenue_usd_day(btc_price) if spec.key == "antminer_s19_pro" else ai_revenue_usd_day(gpu_rent)
        )
        amort_day = count * amortization_usd_day(spec.unit_power_kw)
        rows.append(
            {
                "node_type": spec.key,
                "label": spec.label,
                "count": count,
                "unit_power_kw": spec.unit_power_kw,
                "power_mw": r2(power_mw, 3),
                "revenue_usd_day": r2(revenue_day),
                "margin_usd_day": r2(revenue_day - amort_day),
                "margin_per_kw_day": r2(margin),
                "status": "running" if count > 0 else "offline",
            }
        )
        remaining_kw -= power_mw * 1000.0

    shutdown_order = [
        spec.label for spec, margin, _ in sorted(classes, key=lambda item: item[1]) if margin > 0
    ]

    rationale = [
        f"Доступно {available_mw:.2f} МВт; derate по качеству газа ×{quality['derate_factor']:.2f} "
        f"(CH4 {ch4_fraction * 100:.0f} %, H2S {h2s_ppm:.0f} ppm)",
        f"Собственные нужды (скрубберы, насосы) −{cfg.AUX_LOAD_SHARE * 100:.0f} %, "
        f"PUE ЦОД {cfg.PUE_DC:.2f} → распределяется по ИТ-нагрузке",
        f"ML-прогноз BTC на 3 мес: {market['predicted_3m_return']:+.1%} → "
        f"множитель маржи майнинга ×{market['miner_margin_multiplier']:.2f}",
        f"Маржа на кВт·день: ИИ ${margins['ai_usd_per_kw_day']:.2f} против "
        f"майнинга ${margins['mining_usd_per_kw_day']:.2f}",
    ]
    if max_ai_servers > 0:
        rationale.append(
            f"Ёмкость рынка аренды: {gpu_demand_cap} GPU → максимум {max_ai_servers} ИИ-серверов"
        )
    if quality["derate_factor"] < 0.6:
        rationale.append(
            "Качество газа низкое: работают только самые маржинальные узлы "
            "(лестница отключений), ядро ИИ сохраняется"
        )

    return _build_result(available_mw, quality, market, margins, rows, shutdown_order, rationale, manual=False)


def manual_allocate(
    available_mw: float,
    ch4_fraction: float,
    h2s_ppm: float,
    btc_price: float,
    gpu_rent: float,
    manual_miners: int,
    manual_ai_servers: int,
    seed: int = 42,
) -> dict:
    """Manual Allocation: считает экономику заданного пользователем парка."""
    model = get_market_model(seed)
    quality = gas_quality(ch4_fraction, h2s_ppm)
    market = _market_block(model, btc_price, gpu_rent)

    m_mining = (
        mining_revenue_usd_day(btc_price) * market["miner_margin_multiplier"]
        - amortization_usd_day(ANTMINER.unit_power_kw)
    ) / ANTMINER.unit_power_kw
    m_ai = (
        ai_revenue_usd_day(gpu_rent) - amortization_usd_day(AI_SERVER.unit_power_kw)
    ) / AI_SERVER.unit_power_kw
    margins = {"mining_usd_per_kw_day": r2(m_mining), "ai_usd_per_kw_day": r2(m_ai)}

    rows: list[dict] = []
    for spec, count, margin in (
        (ANTMINER, manual_miners, m_mining),
        (AI_SERVER, manual_ai_servers, m_ai),
    ):
        power_mw = count * spec.unit_power_kw * cfg.PUE_DC / 1000.0
        revenue_day = count * (
            mining_revenue_usd_day(btc_price) if spec.key == "antminer_s19_pro" else ai_revenue_usd_day(gpu_rent)
        )
        amort_day = count * amortization_usd_day(spec.unit_power_kw)
        rows.append(
            {
                "node_type": spec.key,
                "label": spec.label,
                "count": count,
                "unit_power_kw": spec.unit_power_kw,
                "power_mw": r2(power_mw, 3),
                "revenue_usd_day": r2(revenue_day),
                "margin_usd_day": r2(revenue_day - amort_day),
                "margin_per_kw_day": r2(margin),
                "status": "running" if count > 0 else "offline",
            }
        )

    shutdown_order = [
        spec.label
        for spec, margin in sorted(
            [(ANTMINER, m_mining), (AI_SERVER, m_ai)], key=lambda item: item[1]
        )
        if margin > 0
    ]
    rationale = [
        f"Ручной режим: {manual_miners} Antminer S19 Pro и {manual_ai_servers} ИИ-серверов",
        f"Доступно {available_mw:.2f} МВт; derate по качеству газа ×{quality['derate_factor']:.2f}",
        f"Потребление парка (с PUE {cfg.PUE_DC:.2f}): {sum(r['power_mw'] for r in rows):.2f} МВт",
    ]
    return _build_result(available_mw, quality, market, margins, rows, shutdown_order, rationale, manual=True)
