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
    btc_price: float = Field(default=cfg.BTC_PRICE_DEFAULT, gt=0)
    gpu_rent_usd_per_gpu_hour: float = Field(default=cfg.GPU_RENT_DEFAULT, gt=0)
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
