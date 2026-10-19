"""Валютный блок: конвертация выручки, стоимость репатриации и хеджирования.

Валютное регулирование КР в рамках обзора не подтверждено первоисточниками
(требования репатриации/обязательной продажи зависят от контракта и периода),
поэтому модель полностью параметрическая: курс, спред, доля возвращаемой
выручки и стоимость процедур задаются запросом. Это позволяет считать
сценарии «полная репатриация» / «офшорная выручка» / «хеджирование».

Все ставки — доли суммы; курс — сомов за 1 USD.
"""
from __future__ import annotations

from dataclasses import dataclass

from app import config as cfg


@dataclass(frozen=True)
class CurrencyParams:
    usd_kgs_rate: float = cfg.USD_KGS_RATE_DEFAULT
    conversion_spread: float = cfg.FX_CONVERSION_SPREAD
    repatriation_share: float = cfg.FX_REPATRIATION_SHARE
    repatriation_cost_share: float = cfg.FX_REPATRIATION_COST_SHARE
    hedging_cost_share: float = cfg.FX_HEDGING_COST_SHARE

    def __post_init__(self) -> None:
        if self.usd_kgs_rate <= 0:
            raise ValueError("usd_kgs_rate must be positive")
        for name in (
            "conversion_spread",
            "repatriation_share",
            "repatriation_cost_share",
            "hedging_cost_share",
        ):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be within [0, 1]")


def compute_currency(
    annual_usd: list[float],
    params: CurrencyParams | None = None,
) -> dict:
    """По годам: валовая выручка → стоимость конвертации/репатриации → KGS."""
    p = params or CurrencyParams()
    if not annual_usd:
        raise ValueError("annual_usd must be non-empty")
    if any(value < 0 for value in annual_usd):
        raise ValueError("annual_usd must be non-negative")

    rows = []
    total_gross = total_conversion = total_repat = total_hedge = 0.0
    for i, gross in enumerate(annual_usd):
        conversion_cost = gross * p.conversion_spread
        repatriated = gross * p.repatriation_share
        repatriation_cost = repatriated * p.repatriation_cost_share
        hedging_cost = gross * p.hedging_cost_share
        net_usd = gross - conversion_cost - repatriation_cost - hedging_cost
        kgs_received = max(0.0, net_usd) * p.usd_kgs_rate
        rows.append(
            {
                "year": i + 1,
                "gross_usd": round(gross, 2),
                "conversion_cost_usd": round(conversion_cost, 2),
                "repatriated_usd": round(repatriated, 2),
                "repatriation_cost_usd": round(repatriation_cost, 2),
                "hedging_cost_usd": round(hedging_cost, 2),
                "net_usd": round(net_usd, 2),
                "kgs_received": round(kgs_received, 2),
            }
        )
        total_gross += gross
        total_conversion += conversion_cost
        total_repat += repatriation_cost
        total_hedge += hedging_cost

    total_net = total_gross - total_conversion - total_repat - total_hedge
    return {
        "params": {
            "usd_kgs_rate": p.usd_kgs_rate,
            "conversion_spread": p.conversion_spread,
            "repatriation_share": p.repatriation_share,
            "repatriation_cost_share": p.repatriation_cost_share,
            "hedging_cost_share": p.hedging_cost_share,
        },
        "annual": rows,
        "totals": {
            "gross_usd": round(total_gross, 2),
            "conversion_cost_usd": round(total_conversion, 2),
            "repatriation_cost_usd": round(total_repat, 2),
            "hedging_cost_usd": round(total_hedge, 2),
            "net_usd": round(total_net, 2),
            "kgs_received": round(total_net * p.usd_kgs_rate, 2),
            "cost_share": round(
                1 - total_net / total_gross if total_gross > 0 else 0.0, 4
            ),
        },
        "notes": [
            "Валютное регулирование КР параметризовано: требования репатриации/"
            "обязательной продажи в рамках обзора не подтверждены — проверяйте "
            "по действующей редакции закона и договору с банком.",
            "Курс и спред — входные параметры сценария, не прогноз.",
        ],
        "disclaimer": cfg.DISCLAIMER,
    }
