"""Фискальный модуль: КР (общий режим, ПВТ) и сравнение с Astana Hub (КЗ).

Проверенные основания (открытые источники, октябрь 2026):
  * Налог на майнинг КР — 10 % от стоимости потреблённой электроэнергии,
    включая НДС и налог с продаж (разъяснения ГНС; 24.kg, economist.kg).
    Тариф для энергоёмких потребителей-майнеров ≈ 6.06 сома/кВт·ч (2026).
  * ПВТ КР (закон № 84 от 08.07.2011): 0 % налог на прибыль, 0 % НДС,
    0 % налог с продаж; взнос 1 % с выручки в дирекцию; подоходный 5 % с ФОТ.
    Бессрочно с конца 2024. Требования: >90 % выручки от профильной IT-
    деятельности и >80 % экспорта.
  * Astana Hub (Казахстан, AIFC): 0 % КПН/НДС/социальный налог для
    приоритетной IT-деятельности. Это НЕ режим КР: применим только к
    казахстанскому юрлицу; деятельность в КР остаётся в поле КР (риск
    постоянного представительства) — моделируется отдельным сценарием.
  * Плата за загрязнение ОС — годовой параметр (ASSUMPTION).

ВАЖНО: упрощённая модель для симулятора, а не налоговая консультация.
Ставки и применимость режимов проверяйте у налогового консультанта.
"""
from __future__ import annotations

from dataclasses import dataclass

from app import config as cfg

REGIMES = ("none", "kr_general", "kr_htp", "kz_aifc")


@dataclass(frozen=True)
class FiscalParams:
    regime: str = "kr_htp"
    mining_tariff_kgs_per_kwh: float = cfg.KR_MINING_TARIFF_KGS_PER_KWH
    usd_kgs_rate: float = cfg.USD_KGS_RATE_DEFAULT
    mining_tax_share: float = cfg.KR_MINING_TAX_SHARE
    cit_rate: float = cfg.KR_CIT_RATE
    kz_cit_rate: float = cfg.KZ_CIT_RATE
    kz_pe_profit_share: float = cfg.KZ_PE_PROFIT_SHARE
    htp_contribution_share: float = cfg.KR_HTP_CONTRIBUTION_SHARE
    htp_payroll_rate: float = cfg.KR_HTP_PAYROLL_RATE
    htp_ai_services_eligible: bool = cfg.KR_HTP_AI_ELIGIBLE
    htp_mining_eligible: bool = cfg.KR_HTP_MINING_ELIGIBLE
    environmental_fee_usd_year: float = cfg.KR_ENVIRONMENTAL_FEE_USD_YEAR

    def __post_init__(self) -> None:
        if self.regime not in REGIMES:
            raise ValueError(f"fiscal regime must be one of {REGIMES}")
        if self.mining_tariff_kgs_per_kwh <= 0:
            raise ValueError("mining_tariff_kgs_per_kwh must be positive")
        if self.usd_kgs_rate <= 0:
            raise ValueError("usd_kgs_rate must be positive")
        for name in (
            "mining_tax_share",
            "cit_rate",
            "kz_cit_rate",
            "htp_contribution_share",
            "htp_payroll_rate",
        ):
            value = getattr(self, name)
            if not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be within [0, 1]")
        if not 0.0 <= self.kz_pe_profit_share <= 1.0:
            raise ValueError("kz_pe_profit_share must be within [0, 1]")
        if self.environmental_fee_usd_year < 0:
            raise ValueError("environmental_fee_usd_year must be non-negative")

    @property
    def tariff_usd_per_kwh(self) -> float:
        """Тариф майнеров в USD по текущему курсу."""
        return self.mining_tariff_kgs_per_kwh / self.usd_kgs_rate


def _line(item: str, base_usd: float, rate: float, note: str = "") -> dict:
    return {
        "item": item,
        "base_usd": round(float(base_usd), 2),
        "rate": round(float(rate), 4),
        "amount_usd": round(max(0.0, float(base_usd)) * float(rate), 2),
        "note": note,
    }


def _profit_share(profit: float, part: float, total: float) -> float:
    """Прибыль, отнесённая на долю выручки (для раздельного учёта КЗ)."""
    if total <= 0:
        return 0.0
    return max(0.0, profit) * (part / total)


def compute_fiscal(
    profit_before_tax_usd: float,
    ai_revenue_usd: float,
    mining_revenue_usd: float,
    miners_energy_kwh_year: float,
    labor_usd_year: float,
    params: FiscalParams | None = None,
) -> dict:
    """Налоговая нагрузка на год и прибыль после налогов по режимам."""
    p = params or FiscalParams()
    lines: list[dict] = []
    notes: list[str] = [
        "Упрощённая фискальная модель; не налоговая консультация. Ставки и "
        "применимость режимов подтверждайте у налогового консультанта.",
        "НДС не начисляется: экспорт IT-услуг — 0 %, майнинг-налог включает "
        "НДС и налог с продаж.",
    ]

    if p.regime == "none":
        notes.append("Режим none: налоги не моделируются (pretax), как в v0.1.")
        taxes_total = 0.0
        net_profit = profit_before_tax_usd
    else:
        mining_tax_base = miners_energy_kwh_year * p.tariff_usd_per_kwh
        mining_tax = mining_tax_base * p.mining_tax_share

        if p.regime == "kr_general":
            cit = max(0.0, profit_before_tax_usd) * p.cit_rate
            lines.append(_line("Налог на прибыль КР (общий режим)", profit_before_tax_usd, p.cit_rate,
                               "10 % с прибыли; убыток не облагается"))
            lines.append(_line("Налог на майнинг (10 % от стоимости э/э)", mining_tax_base,
                               p.mining_tax_share, "включает НДС и налог с продаж"))
            lines.append(_line("Плата за загрязнение ОС", p.environmental_fee_usd_year, 1.0,
                               "годовой параметр (ASSUMPTION)"))
            taxes_total = cit + mining_tax + p.environmental_fee_usd_year

        elif p.regime == "kr_htp":
            htp_base = ai_revenue_usd if p.htp_ai_services_eligible else 0.0
            if p.htp_ai_services_eligible:
                lines.append(_line("Взнос в дирекцию ПВТ (1 % выручки IT)", htp_base,
                                   p.htp_contribution_share,
                                   "вместо налога на прибыль/НДС/налога с продаж"))
                notes.append(
                    "Резидент ПВТ: 0 % налог на прибыль, 0 % НДС, 0 % налог с "
                    "продаж; взнос 1 % с выручки. Требования: >90 % выручки от "
                    "IT-деятельности и >80 % экспорта."
                )
            if not p.htp_mining_eligible:
                lines.append(_line("Налог на майнинг (10 % от стоимости э/э)",
                                   mining_tax_base, p.mining_tax_share,
                                   "майнинг вне профильной деятельности ПВТ"))
                notes.append(
                    "Правовой статус майнинга в ПВТ КР неочевиден — применён "
                    "консервативный сценарий: майнинг облагается отдельно."
                )
            payroll = max(0.0, labor_usd_year) * p.htp_payroll_rate
            lines.append(_line("Подоходный налог с ФОТ (ПВТ, 5 %)", labor_usd_year,
                               p.htp_payroll_rate, "упрощённо с ФОТ"))
            lines.append(_line("Плата за загрязнение ОС", p.environmental_fee_usd_year, 1.0,
                               "годовой параметр (ASSUMPTION)"))
            taxes_total = (
                htp_base * p.htp_contribution_share
                + mining_tax
                + payroll
                + p.environmental_fee_usd_year
            )

        else:  # kz_aifc — Astana Hub (Казахстан)
            total_rev = ai_revenue_usd + mining_revenue_usd
            ai_profit = _profit_share(profit_before_tax_usd, ai_revenue_usd, total_rev)
            mining_profit = _profit_share(profit_before_tax_usd, mining_revenue_usd, total_rev)
            kz_cit = mining_profit * p.kz_cit_rate
            pe_base = max(0.0, profit_before_tax_usd) * p.kz_pe_profit_share
            kr_pe_cit = pe_base * p.cit_rate
            env_pe = p.environmental_fee_usd_year * p.kz_pe_profit_share
            lines.append(_line("КПН КЗ по IT-выручке (льгота Astana Hub)", ai_profit, 0.0,
                               "0 % для приоритетной IT-деятельности"))
            lines.append(_line("КПН КЗ по майнинговой выручке", mining_profit, p.kz_cit_rate,
                               "майнинг не входит в приоритетные виды Astana Hub"))
            lines.append(_line("КПН КР с прибыли постоянного представительства", pe_base, p.cit_rate,
                               f"риск ПП: {p.kz_pe_profit_share:.0%} прибыли КЗ-юрлица"))
            lines.append(_line("Налог на майнинг (10 % от стоимости э/э)", mining_tax_base,
                               p.mining_tax_share, "энергопотребление физически в КР"))
            lines.append(_line("Плата за загрязнение ОС (доля ПП)", p.environmental_fee_usd_year,
                               p.kz_pe_profit_share, "годовой параметр (ASSUMPTION)"))
            notes.extend(
                [
                    "Astana Hub — режим Казахстана (AIFC), а не Кыргызстана: "
                    "применим только к казахстанскому юрлицу.",
                    "Деятельность на территории КР может создавать постоянное "
                    "представительство и облагаться в КР — режим не устраняет "
                    "налоговую связь с КР.",
                    "Требование Astana Hub: ≥90 % дохода от приоритетных видов "
                    "ИТ-деятельности; экологические платежи КЗ не моделируются.",
                    "Риск постоянного представительства в КР учтён долей kz_pe_profit_share "
                    f"({p.kz_pe_profit_share:.0%} прибыли): она облагается КПН КР 10 %; "
                    "зачёт иностранного налога не моделируется.",
                ]
            )
            taxes_total = kz_cit + kr_pe_cit + mining_tax + env_pe

        net_profit = profit_before_tax_usd - taxes_total

    return {
        "regime": p.regime,
        "lines": lines,
        "assumptions": {
            "mining_tariff_kgs_per_kwh": p.mining_tariff_kgs_per_kwh,
            "usd_kgs_rate": p.usd_kgs_rate,
            "tariff_usd_per_kwh": round(p.tariff_usd_per_kwh, 5),
            "env_fee_usd_year": p.environmental_fee_usd_year,
            "kz_pe_profit_share": p.kz_pe_profit_share,
        },
        "taxes_total_usd": round(float(taxes_total), 2),
        "net_profit_after_fiscal_usd": round(float(net_profit), 2),
        "notes": notes,
        "disclaimer": cfg.DISCLAIMER,
    }
