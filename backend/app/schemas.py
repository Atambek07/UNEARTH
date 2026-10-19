"""Pydantic-контракты запросов API UNEARTH."""
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app import config as cfg


class ForecastRequest(BaseModel):
    """Входы Модуля 1: физика полигона + настройки ML-прогноза."""

    total_legacy_tonnes: float = Field(
        default=cfg.LEGACY_TONNES_DEFAULT, gt=0, description="Накопленные ТБО, т (ЕБРР/Мэрия: ~20 млн)"
    )
    annual_inflow_tonnes: float = Field(
        default=cfg.ANNUAL_INFLOW_TONNES_DEFAULT, ge=0, description="Приток отходов, т/год (350–400 тыс.)"
    )
    lo_m3_per_tonne: float = Field(
        default=cfg.LO_DEFAULT, gt=0, description="Потенциал метана L0, м³/т (70–80, EPA)"
    )
    k_per_year: float = Field(
        default=cfg.K_DEFAULT, ge=0.001, le=0.5, description="Скорость разложения k, 1/год (0.02–0.04, аридный климат)"
    )
    methane_fraction: float = Field(
        default=cfg.METHANE_FRACTION_DEFAULT, gt=0, lt=1, description="Доля CH4 в свалочном газе (50–55 %)"
    )
    horizon_years: int = Field(default=cfg.HORIZON_YEARS_DEFAULT, ge=3, le=25)
    collection_efficiency: float = Field(default=cfg.COLLECTION_EFFICIENCY_DEFAULT, gt=0, le=1)
    genset_availability: float = Field(default=cfg.GENSET_AVAILABILITY_DEFAULT, gt=0, le=1)
    kwh_per_m3_ch4: float = Field(default=cfg.KWH_PER_M3_CH4_DEFAULT, gt=0)
    use_prophet: bool = Field(
        default=False, description="Использовать Prophet, если пакет установлен (иначе builtin-seasonal-ar1)"
    )
    seed: int = Field(default=42, ge=0)


class OptimizeRequest(BaseModel):
    """Входы Smart Grid балансировщика (Модуль 2а)."""

    available_mw: float = Field(gt=0, le=500, description="Доступная электрическая мощность, МВт (из /api/forecast)")
    ch4_fraction: float = Field(default=cfg.METHANE_FRACTION_DEFAULT, gt=0, lt=1)
    h2s_ppm: float = Field(default=30.0, ge=0, le=1000)
    btc_price: float | None = Field(default=None, gt=0, description="Курс BTC; None → из провайдера рынка")
    gpu_rent_usd_per_gpu_hour: float | None = Field(default=None, gt=0, description="Аренда GPU; None → дефолт")
    market_provider: Literal["auto", "live", "synthetic"] = Field(
        default="synthetic", description="Источник рынка: live-данные или синтетика"
    )
    mode: Literal["auto", "manual"] = "auto"
    manual_miners: int = Field(default=0, ge=0, le=100_000)
    manual_ai_servers: int = Field(default=0, ge=0, le=100_000)
    gpu_demand_cap: int = Field(default=cfg.MARKET_GPUS_RENTABLE, ge=0, le=1_000_000)
    seed: int = Field(default=42, ge=0)


class MaintenanceRequest(BaseModel):
    """Входы предиктивного обслуживания (Модуль 2б)."""

    installed_mw: float = Field(gt=0, le=500)
    ch4_m3_month: float = Field(gt=0, description="CH4, поданный на ГПУ за месяц, м³ (с учётом отбора газа)")
    h2s_ppm: float = Field(default=30.0, ge=0, le=1000)
    methane_fraction: float = Field(default=cfg.METHANE_FRACTION_DEFAULT, gt=0, lt=1)
    months_operated: int = Field(default=6, ge=0, le=600)
    genset_availability: float = Field(default=cfg.GENSET_AVAILABILITY_DEFAULT, gt=0, le=1)
    kwh_per_m3_ch4: float = Field(default=cfg.KWH_PER_M3_CH4_DEFAULT, gt=0)


class FxRequest(BaseModel):
    """Параметры валютного блока (конвертация и репатриация)."""

    usd_kgs_rate: float = Field(default=cfg.USD_KGS_RATE_DEFAULT, gt=0, le=1000)
    conversion_spread: float = Field(default=cfg.FX_CONVERSION_SPREAD, ge=0, le=0.2)
    repatriation_share: float = Field(default=cfg.FX_REPATRIATION_SHARE, ge=0, le=1)
    repatriation_cost_share: float = Field(default=cfg.FX_REPATRIATION_COST_SHARE, ge=0, le=0.2)
    hedging_cost_share: float = Field(default=cfg.FX_HEDGING_COST_SHARE, ge=0, le=0.2)


class FinanceRequest(BaseModel):
    """Входы финансового блока (Модуль 2в)."""

    horizon_years: int = Field(ge=3, le=25)
    monthly_power_mw: list[float] = Field(min_length=12)
    monthly_ch4_m3_delivered: list[float] = Field(min_length=12)
    miners_count: int = Field(ge=0, le=100_000)
    ai_servers_count: int = Field(ge=0, le=100_000)
    btc_price: float = Field(default=cfg.BTC_PRICE_DEFAULT, gt=0)
    gpu_rent_usd_per_gpu_hour: float = Field(default=cfg.GPU_RENT_DEFAULT, gt=0)
    opex_variable_annual_usd: float = Field(default=0.0, ge=0)
    opex_fixed_annual_usd: float = Field(default=0.0, ge=0)
    seed: int = Field(default=42, ge=0)
    n_sims: int = Field(default=400, ge=50, le=2000)
    fiscal_regime: Literal["none", "kr_general", "kr_htp", "kz_aifc"] = Field(
        default="kr_htp",
        description="Фискальный режим: none (pretax), kr_general (прибыль 10 % + майнинг-налог), "
        "kr_htp (резидент ПВТ), kz_aifc (Astana Hub, Казахстан — сравнение)",
    )
    fx: FxRequest | None = Field(
        default=None, description="Валютный блок; None — дефолтный курс и спреды"
    )

    @model_validator(mode="after")
    def _check_lengths(self) -> "FinanceRequest":
        if len(self.monthly_power_mw) != len(self.monthly_ch4_m3_delivered):
            raise ValueError("monthly_power_mw и monthly_ch4_m3_delivered должны быть одной длины")
        if self.horizon_years * 12 != len(self.monthly_power_mw):
            raise ValueError("длина месячных рядов должна равняться horizon_years × 12")
        return self


class SectorsRequest(BaseModel):
    """Входы карты секторов."""

    ch4_m3_delivered_month: float = Field(gt=0, description="CH4, поданный из секторов за месяц, м³")
    month: int = Field(default=10, ge=1, le=12)
    rows: int = Field(default=cfg.SECTOR_ROWS, ge=2, le=20)
    cols: int = Field(default=cfg.SECTOR_COLS, ge=2, le=20)
    seed: int = Field(default=42, ge=0)


# ----------------------------------------------------------------------------
# v0.2: рыночные данные, упреждающий балансировщик, карбон, сценарии
# ----------------------------------------------------------------------------


class OptimizePathRequest(BaseModel):
    """Упреждающий многошаговый план (квартальный DP, switching costs, резерв)."""

    monthly_power_mw: list[float] = Field(
        min_length=3, max_length=600, description="Доступная мощность по месяцам (из /api/forecast)",
    )
    monthly_moisture: list[float] | None = Field(
        default=None, description="Индекс влажности по месяцам; None → нейтральная 1.0",
    )
    monthly_btc_price: list[float] | None = Field(
        default=None, description="Ожидаемый путь курса BTC по месяцам; None → константа btc_price",
    )
    ch4_fraction: float = Field(default=cfg.METHANE_FRACTION_DEFAULT, gt=0, lt=1)
    h2s_ppm: float = Field(default=30.0, ge=0, le=1000)
    btc_price: float | None = Field(default=None, gt=0)
    gpu_rent_usd_per_gpu_hour: float | None = Field(default=None, gt=0)
    market_provider: Literal["auto", "live", "synthetic"] = "synthetic"
    gpu_demand_cap: int = Field(default=cfg.MARKET_GPUS_RENTABLE, ge=0, le=1_000_000)
    seed: int = Field(default=42, ge=0)
    switching_cost_miner_usd: float = Field(default=cfg.SWITCH_COST_MINER_USD, ge=0, le=100_000)
    switching_cost_ai_usd: float = Field(default=cfg.SWITCH_COST_AI_USD, ge=0, le=1_000_000)

    @model_validator(mode="after")
    def _check_moisture(self) -> "OptimizePathRequest":
        if self.monthly_moisture is not None and len(self.monthly_moisture) != len(self.monthly_power_mw):
            raise ValueError("monthly_moisture должен совпадать по длине с monthly_power_mw")
        if self.monthly_btc_price is not None and len(self.monthly_btc_price) != len(self.monthly_power_mw):
            raise ValueError("monthly_btc_price должен совпадать по длине с monthly_power_mw")
        return self


class CarbonRequest(BaseModel):
    """Карбоновый модуль (CDM ACM0001): параметры кредита и базовая линия."""

    monthly_ch4_m3_delivered: list[float] = Field(
        min_length=12, description="Уничтоженный CH4 по месяцам, м³ (длина кратна 12)",
    )
    gwp: float = Field(default=cfg.GWP_CH4, gt=0, le=100)
    buffer_share: float = Field(default=cfg.CARBON_BUFFER_SHARE, ge=0, lt=1)
    verification_lag_months: int = Field(default=cfg.CARBON_VERIFICATION_LAG_MONTHS, ge=0, le=36)
    price_p10: float = Field(default=8.0, gt=0)
    price_p50: float = Field(default=15.0, gt=0)
    price_p90: float = Field(default=25.0, gt=0)
    validation_cost_usd: float = Field(default=cfg.CARBON_VALIDATION_COST_USD, ge=0)
    verification_cost_usd_year: float = Field(default=cfg.CARBON_VERIFICATION_COST_USD_YEAR, ge=0)
    monitoring_cost_usd_year: float = Field(default=cfg.CARBON_MONITORING_COST_USD_YEAR, ge=0)
    issuance_fee_usd_per_credit: float = Field(default=cfg.CARBON_ISSUANCE_FEE_USD_PER_CREDIT, ge=0)
    discount_rate: float = Field(default=cfg.WACC, ge=0, le=0.5)

    @model_validator(mode="after")
    def _check_months(self) -> "CarbonRequest":
        if any(value < 0 for value in self.monthly_ch4_m3_delivered):
            raise ValueError("monthly_ch4_m3_delivered должен быть неотрицательным")
        if len(self.monthly_ch4_m3_delivered) % 12 != 0:
            raise ValueError("длина monthly_ch4_m3_delivered должна быть кратна 12")
        return self


class ScenarioInputs(BaseModel):
    """Параметры сценария (сохраняются и используются при повторном прогоне)."""

    total_legacy_tonnes: float = Field(default=cfg.LEGACY_TONNES_DEFAULT, gt=0)
    annual_inflow_tonnes: float = Field(default=cfg.ANNUAL_INFLOW_TONNES_DEFAULT, ge=0)
    lo_m3_per_tonne: float = Field(default=cfg.LO_DEFAULT, gt=0)
    k_per_year: float = Field(default=cfg.K_DEFAULT, ge=0.001, le=0.5)
    methane_fraction: float = Field(default=cfg.METHANE_FRACTION_DEFAULT, gt=0, lt=1)
    horizon_years: int = Field(default=cfg.HORIZON_YEARS_DEFAULT, ge=3, le=25)
    collection_efficiency: float = Field(default=cfg.COLLECTION_EFFICIENCY_DEFAULT, gt=0, le=1)
    genset_availability: float = Field(default=cfg.GENSET_AVAILABILITY_DEFAULT, gt=0, le=1)
    kwh_per_m3_ch4: float = Field(default=cfg.KWH_PER_M3_CH4_DEFAULT, gt=0)
    h2s_ppm: float = Field(default=30.0, ge=0, le=1000)
    mode: Literal["auto", "manual"] = "auto"
    manual_miners: int = Field(default=0, ge=0, le=100_000)
    manual_ai_servers: int = Field(default=0, ge=0, le=100_000)
    btc_price: float | None = Field(default=None, gt=0)
    gpu_rent_usd_per_gpu_hour: float | None = Field(default=None, gt=0)
    market_provider: Literal["auto", "live", "synthetic"] = "synthetic"
    seed: int = Field(default=42, ge=0)


class ScenarioCreate(BaseModel):
    """Сохранение сценария: run=true — прогнать симуляцию и сохранить дайджест."""

    name: str = Field(min_length=1, max_length=200)
    notes: str = Field(default="", max_length=2000)
    inputs: ScenarioInputs
    run: bool = Field(default=True, description="Прогнать симуляцию с inputs и сохранить дайджест результатов")
    results: dict | None = Field(
        default=None,
        description="Готовые результаты (используются при run=false); иначе сохраняется пустой дайджест",
    )


class ScenarioCompareRequest(BaseModel):
    """Сравнение сохранённых сценариев по ключевым метрикам."""

    ids: list[int] = Field(min_length=2, max_length=10)


class CurrencyRequest(FxRequest):
    """Валютный расчёт по годам: конвертация, репатриация, хеджирование."""

    annual_usd: list[float] = Field(min_length=1, max_length=30)


class FiscalCompareRequest(BaseModel):
    """Сравнение всех налоговых режимов при одинаковой базе."""

    profit_before_tax_usd: float = Field(default=10_000_000.0)
    ai_revenue_usd: float = Field(default=0.0, ge=0)
    mining_revenue_usd: float = Field(default=0.0, ge=0)
    miners_energy_kwh_year: float = Field(default=0.0, ge=0)
    labor_usd_year: float = Field(default=0.0, ge=0)
    fx_rate_kgs_per_usd: float | None = Field(default=None, gt=0, le=1000)
    pe_risk_share: float | None = Field(
        default=None, ge=0, le=1, description="Доля прибыли КЗ-юрлица, относимая к КР (риск ПП)"
    )
