"""Тесты фискального модуля КР."""
import pytest

from app.engines.fiscal import FiscalParams, compute_fiscal

BASE_ARGS = dict(
    profit_before_tax_usd=10_000_000.0,
    ai_revenue_usd=14_000_000.0,
    mining_revenue_usd=4_000_000.0,
    miners_energy_kwh_year=8_760_000.0,  # оценка: парк 307 ASIC × 3.25 кВт × 8760 ч
    labor_usd_year=140_000.0,
)


def test_htp_lines_and_total():
    """ПВТ: 0 % прибыль/НДС; 1 % взнос с IT-выручки; майнинг-налог отдельно; подоходный 5 %."""
    params = FiscalParams(regime="kr_htp")
    res = compute_fiscal(params=params, **BASE_ARGS)
    amounts = {line["item"]: line["amount_usd"] for line in res["lines"]}
    assert amounts["Взнос в дирекцию ПВТ (1 % выручки IT)"] == pytest.approx(140_000.0)
    assert amounts["Налог на майнинг (10 % от стоимости э/э)"] == pytest.approx(
        8_760_000.0 * params.tariff_usd_per_kwh * 0.10
    )
    assert amounts["Подоходный налог с ФОТ (ПВТ, 5 %)"] == pytest.approx(7_000.0)
    assert res["taxes_total_usd"] == pytest.approx(sum(amounts.values()), rel=1e-6)
    assert res["net_profit_after_fiscal_usd"] == pytest.approx(
        BASE_ARGS["profit_before_tax_usd"] - res["taxes_total_usd"]
    )
    assert res["disclaimer"]


def test_none_regime_is_pretax():
    res = compute_fiscal(params=FiscalParams(regime="none"), **BASE_ARGS)
    assert res["taxes_total_usd"] == 0.0
    assert res["net_profit_after_fiscal_usd"] == BASE_ARGS["profit_before_tax_usd"]


def test_htp_not_worse_than_general():
    """При одинаковой прибыли ПВТ (0 % CIT) не может проигрывать общему режиму."""
    htp = compute_fiscal(params=FiscalParams(regime="kr_htp"), **BASE_ARGS)
    general = compute_fiscal(params=FiscalParams(regime="kr_general"), **BASE_ARGS)
    assert htp["taxes_total_usd"] <= general["taxes_total_usd"]
    assert htp["net_profit_after_fiscal_usd"] >= general["net_profit_after_fiscal_usd"]
    # общий режим обязан включать налог на прибыль 10 % от прибыли
    amounts = {line["item"]: line["amount_usd"] for line in general["lines"]}
    assert amounts["Налог на прибыль КР (общий режим)"] == pytest.approx(1_000_000.0)


def test_regime_validation():
    with pytest.raises(ValueError):
        FiscalParams(regime="offshore")
    with pytest.raises(ValueError):
        FiscalParams(cit_rate=1.5)
    assert FiscalParams(regime="kz_aifc").regime == "kz_aifc"


def test_mining_tariff_in_kgs_converted_by_fx():
    """База майнинг-налога: тариф 6.06 сома/кВт·ч пересчитывается по курсу."""
    params = FiscalParams(regime="kr_general", mining_tariff_kgs_per_kwh=6.06, usd_kgs_rate=87.4)
    assert params.tariff_usd_per_kwh == pytest.approx(6.06 / 87.4)
    res = compute_fiscal(
        profit_before_tax_usd=0.0,
        ai_revenue_usd=0.0,
        mining_revenue_usd=1_000_000.0,
        miners_energy_kwh_year=1_000_000.0,
        labor_usd_year=0.0,
        params=params,
    )
    amounts = {line["item"]: line["amount_usd"] for line in res["lines"]}
    assert amounts["Налог на майнинг (10 % от стоимости э/э)"] == pytest.approx(
        1_000_000.0 * (6.06 / 87.4) * 0.10
    )


def test_kz_aifc_taxes_mining_and_pe_share():
    """Astana Hub: 0 % по IT, 20 % КПН по майнингу + КПН КР с доли ПП + майнинг-налог."""
    params = FiscalParams(regime="kz_aifc")
    res = compute_fiscal(params=params, **BASE_ARGS)
    total_rev = BASE_ARGS["ai_revenue_usd"] + BASE_ARGS["mining_revenue_usd"]
    mining_profit = BASE_ARGS["profit_before_tax_usd"] * (
        BASE_ARGS["mining_revenue_usd"] / total_rev
    )
    mining_tax = (
        BASE_ARGS["miners_energy_kwh_year"] * params.tariff_usd_per_kwh * params.mining_tax_share
    )
    pe_base = BASE_ARGS["profit_before_tax_usd"] * params.kz_pe_profit_share
    expected = (
        mining_profit * params.kz_cit_rate
        + pe_base * params.cit_rate
        + mining_tax
        + params.environmental_fee_usd_year * params.kz_pe_profit_share
    )
    assert res["taxes_total_usd"] == pytest.approx(expected)
    items = {line["item"]: line for line in res["lines"]}
    assert items["КПН КЗ по IT-выручке (льгота Astana Hub)"]["amount_usd"] == 0.0
    assert items["КПН КР с прибыли постоянного представительства"]["amount_usd"] == pytest.approx(
        pe_base * 0.1
    )
    assert "постоянного представительства" in " ".join(res["notes"])
    general = compute_fiscal(params=FiscalParams(regime="kr_general"), **BASE_ARGS)
    assert res["taxes_total_usd"] < general["taxes_total_usd"]


def test_kz_aifc_pe_risk_scales_taxes():
    """Чем выше доля ПП, тем больже налогов: 0 % < 50 % < 100 %."""
    zero = compute_fiscal(params=FiscalParams(regime="kz_aifc", kz_pe_profit_share=0.0), **BASE_ARGS)
    half = compute_fiscal(params=FiscalParams(regime="kz_aifc", kz_pe_profit_share=0.5), **BASE_ARGS)
    full = compute_fiscal(params=FiscalParams(regime="kz_aifc", kz_pe_profit_share=1.0), **BASE_ARGS)
    assert zero["taxes_total_usd"] < half["taxes_total_usd"] < full["taxes_total_usd"]


def test_loss_makes_profit_tax_zero():
    res = compute_fiscal(
        profit_before_tax_usd=-2_000_000.0,
        ai_revenue_usd=1_000_000.0,
        mining_revenue_usd=0.0,
        miners_energy_kwh_year=0.0,
        labor_usd_year=0.0,
        params=FiscalParams(regime="kr_general"),
    )
    amounts = {line["item"]: line["amount_usd"] for line in res["lines"]}
    assert amounts["Налог на прибыль КР (общий режим)"] == 0.0
