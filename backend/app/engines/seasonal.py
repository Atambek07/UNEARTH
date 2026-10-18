"""Модуль 1б — ML-слой поверх физики LandGEM: сезонность + AR(1) + доверительные интервалы.

Два полностью реализованных бэкенда:
  1) builtin-seasonal-ar1 (по умолчанию, работает без тяжёлых зависимостей):
     - синтетическая «история наблюдений» 48 мес: физический тренд × сезонный
       множитель × AR(1)-шум (seed фиксирован) — имитация мониторинга скважин;
     - декомпозиция: центральное MA-12 → тренд; средние детрендированного ряда
       по календарным месяцам → эмпирические сезонные индексы;
     - лог-остатки → оценка ρ (AR(1)) и σ инноваций методом моментов;
     - прогноз: физтренд × сезонный индекс × exp(ρ^h·ε_last + var_h/2);
       интервалы: ±1.96·σ·sqrt((1-ρ^{2h})/(1-ρ²)) в мультипликативной форме
       с медленным ростом неопределённости модели на длинном горизонте.
  2) prophet (подключается, если пакет установлен и use_prophet=True):
     годовая сезонность + мультипликативный регрессор «физический тренд»,
     интервалы от самой Prophet. Любая ошибка → откат на builtin.

Осенний скачок влажности (арбузы/дыни — PDF, риск №2) живёт в moisture_index:
пик в сентябре–октябре, волатильность генерации осенью умножается на
AUTUMN_VOL_MULT — именно её «видит» Smart Load Balancing.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from app import config as cfg
from app.engines.landgem import LandGEMInput, monthly_ch4_history, monthly_ch4_m3

HISTORY_MONTHS = 48


@dataclass(frozen=True)
class SeasonalParams:
    seed: int = 42
    amplitude: float = cfg.SEASONAL_AMPLITUDE
    summer_dip: float = cfg.SUMMER_DROUCH_DIP
    autumn_boost: float = cfg.AUTUMN_BOOST
    autumn_center: float = cfg.AUTUMN_CENTER_MONTH
    autumn_sigma: float = cfg.AUTUMN_SIGMA
    autumn_vol_mult: float = cfg.AUTUMN_VOL_MULT
    base_vol: float = cfg.BASE_VOL
    prior_rho: float = cfg.AR1_RHO


def moisture_index(month: int, p: SeasonalParams) -> float:
    """Индекс влажности массива: осенний пик (бахчевые) минус летняя засуха."""
    autumn = p.autumn_boost * math.exp(
        -((month - p.autumn_center) ** 2) / (2 * p.autumn_sigma**2)
    )
    summer = p.summer_dip * math.exp(-((month - 7) ** 2) / (2 * 2.0**2))
    return max(0.0, 1.0 + autumn - summer)


def seasonal_multiplier(month: int, p: SeasonalParams) -> float:
    """Мультипликатор генерации газа в календарный месяц (1..12)."""
    return (
        1.0
        + (moisture_index(month, p) - 1.0)
        + p.amplitude * math.sin(2 * math.pi * (month - 4) / 12.0)
    )


@dataclass
class SeasonalFit:
    seasonal_index: np.ndarray  # 12 значений, среднее = 1
    rho: float                  # AR(1)-коэффициент лог-остатков
    sigma_innov: float          # σ инноваций (лог-шкала)
    eps_last: float             # последний остаток — для AR-продолжения
    n_obs: int


def _synthetic_history(
    trend_hist: np.ndarray,
    months_hist: np.ndarray,
    p: SeasonalParams,
    rng: np.random.Generator,
) -> np.ndarray:
    """«Наблюдения» мониторинга: тренд × сезонность × AR(1)-шум (seed)."""
    eps = 0.0
    obs: list[float] = []
    for trend, m in zip(trend_hist, months_hist):
        vol = p.base_vol * (p.autumn_vol_mult if 8 <= int(m) <= 11 else 1.0)
        eps = p.prior_rho * eps + float(rng.normal(0.0, vol))
        obs.append(float(trend) * seasonal_multiplier(int(m), p) * (1.0 + eps))
    return np.asarray(obs, dtype=float)


def decompose(obs: np.ndarray, months: np.ndarray, p: SeasonalParams) -> SeasonalFit:
    """MA-12 декомпозиция + сезонные индексы + AR(1) по лог-остаткам."""
    n = len(obs)
    if n < 24:
        return SeasonalFit(np.ones(12), p.prior_rho, p.base_vol, 0.0, n)

    s = pd.Series(obs)
    trend = s.rolling(12, center=True, min_periods=6).mean().to_numpy()

    idx = np.ones(12)
    ratio = obs / trend
    for m in range(1, 13):
        mask = (months == m) & np.isfinite(ratio) & (trend > 0)
        if mask.any():
            idx[m - 1] = float(np.mean(ratio[mask]))
    if np.isfinite(idx.mean()) and idx.mean() > 0:
        idx = idx / idx.mean()
    idx = np.clip(idx, 0.5, 1.6)

    fitted = trend * idx[np.clip(months - 1, 0, 11)]
    with np.errstate(divide="ignore", invalid="ignore"):
        log_resid = np.log(np.where(fitted > 0, obs / fitted, np.nan))
    valid = np.isfinite(log_resid)
    e = log_resid[valid]
    if len(e) < 12:
        return SeasonalFit(idx, p.prior_rho, p.base_vol, 0.0, len(e))

    e_prev, e_curr = e[:-1], e[1:]
    denom = float(np.sum(e_prev**2))
    rho = float(np.sum(e_prev * e_curr) / denom) if denom > 0 else p.prior_rho
    rho = float(np.clip(rho, -0.95, 0.95))
    innov = e_curr - rho * e_prev
    sigma = float(np.std(innov, ddof=1)) if len(innov) > 1 else p.base_vol
    sigma = float(np.clip(sigma, 1e-4, 0.5))
    return SeasonalFit(idx, rho, sigma, float(e[-1]), len(e))


def forecast_builtin(
    trend_future: np.ndarray,
    months_future: np.ndarray,
    fit: SeasonalFit,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Прогноз builtin-модели: (point, ci_lower, ci_upper), м³ CH4/мес."""
    h = np.arange(1, len(trend_future) + 1, dtype=float)
    seas = fit.seasonal_index[np.clip(months_future - 1, 0, 11)]
    var_h = fit.sigma_innov**2 * (1.0 - fit.rho ** (2 * h)) / (1.0 - fit.rho**2)
    var_h = var_h * (1.0 + 0.02 * h)  # честный рост неопределённости с горизонтом
    # Логнормальное AR(1): медианная траектория + полпоправка к матожиданию
    point = trend_future * seas * np.exp(fit.rho**h * fit.eps_last + 0.5 * var_h)
    sd = np.sqrt(var_h)
    lower = point * np.exp(-1.96 * sd)
    upper = point * np.exp(1.96 * sd)
    return point, lower, upper


def forecast_prophet(
    dates_hist: list[date],
    obs_hist: np.ndarray,
    trend_hist: np.ndarray,
    dates_future: list[date],
    trend_future: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Prophet-бэкенд: годовая сезонность + мультипликативный регрессор физтренда."""
    from prophet import Prophet  # опциональная зависимость — импорт внутри

    df = pd.DataFrame(
        {
            "ds": pd.to_datetime(dates_hist),
            "y": obs_hist,
            "physics_trend": trend_hist,
        }
    )
    model = Prophet(
        yearly_seasonality=True,
        weekly_seasonality=False,
        daily_seasonality=False,
        seasonality_mode="multiplicative",
        interval_width=0.95,
        uncertainty_samples=300,
    )
    model.add_regressor("physics_trend", mode="multiplicative")
    model.fit(df)
    future = pd.DataFrame(
        {"ds": pd.to_datetime(dates_future), "physics_trend": trend_future}
    )
    fcst = model.predict(future)
    return (
        fcst["yhat"].to_numpy(dtype=float),
        fcst["yhat_lower"].to_numpy(dtype=float),
        fcst["yhat_upper"].to_numpy(dtype=float),
    )


@dataclass
class ForecastBundle:
    dates: list[date]
    months: list[int]
    landgem_ch4_m3: list[float]   # чистая физика без сезонности — базовая кривая
    forecast_ch4_m3: list[float]  # гибридный прогноз (физика × ML-сезонность)
    ci_lower: list[float]
    ci_upper: list[float]
    moisture_index: list[float]
    meta: dict


def run_hybrid_forecast(
    inp: LandGEMInput,
    params: SeasonalParams,
    start_month: date,
    use_prophet: bool = False,
) -> ForecastBundle:
    """Полный конвейер: физика → синтетическая история → декомпозиция → прогноз."""
    horizon_months = inp.horizon_years * 12
    dates_f = pd.date_range(pd.Timestamp(start_month), periods=horizon_months, freq="MS")
    dates_h = pd.date_range(
        dates_f[0] - pd.DateOffset(months=HISTORY_MONTHS),
        periods=HISTORY_MONTHS,
        freq="MS",
    )

    trend_f = np.asarray(monthly_ch4_m3(inp), dtype=float)
    trend_h = np.asarray(monthly_ch4_history(inp, HISTORY_MONTHS), dtype=float)
    months_f = np.asarray([d.month for d in dates_f], dtype=int)
    months_h = np.asarray([d.month for d in dates_h], dtype=int)

    rng = np.random.default_rng(params.seed)
    obs_h = _synthetic_history(trend_h, months_h, params, rng)
    fit = decompose(obs_h, months_h, params)

    notes: list[str] = []
    prophet_used = False
    if use_prophet:
        try:
            point, lower, upper = forecast_prophet(
                list(dates_h.date), obs_h, trend_h, list(dates_f.date), trend_f
            )
            prophet_used = True
        except Exception as exc:  # noqa: BLE001 — любой сбой Prophet → откат
            point, lower, upper = forecast_builtin(trend_f, months_f, fit)
            notes.append(
                f"Prophet недоступен ({type(exc).__name__}: {exc}); "
                "использован builtin-seasonal-ar1"
            )
    else:
        point, lower, upper = forecast_builtin(trend_f, months_f, fit)

    ci_lower = np.clip(lower, 0.0, None)
    ci_upper = np.clip(upper, None, trend_f * 3.0)  # санити-потолок интервала

    moisture = [moisture_index(int(m), params) for m in months_f]
    meta = {
        "model": "prophet" if prophet_used else "builtin-seasonal-ar1",
        "prophet_used": prophet_used,
        "history_months": HISTORY_MONTHS,
        "ar1_rho": round(float(fit.rho), 3),
        "sigma_innov": round(float(fit.sigma_innov), 4),
        "seasonal_index": [round(float(x), 3) for x in fit.seasonal_index],
        "seed": params.seed,
        "notes": notes,
    }
    return ForecastBundle(
        dates=[d.date() for d in dates_f],
        months=[int(m) for m in months_f],
        landgem_ch4_m3=trend_f.tolist(),
        forecast_ch4_m3=point.tolist(),
        ci_lower=ci_lower.tolist(),
        ci_upper=ci_upper.tolist(),
        moisture_index=moisture,
        meta=meta,
    )
