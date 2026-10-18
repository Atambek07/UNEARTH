"""Синтетический рынок (BTC / аренда GPU) + ML-прогноз доходности.

В MVP нет реальных рыночных лент (ТЗ: «синтетические рыночные данные»):
  * BTC — ансамбль путей GBM с редкими крэшами (смесь режимов);
  * аренда GPU — процесс Орнштейна–Уленбека вокруг 2 $/GPU·ч;
  * RandomForestRegressor + HistGradientBoostingRegressor (бустинг из состава
    scikit-learn) обучаются предсказывать форвардную доходность BTC на 3 мес
    по фичам моментума/волатильности/ренты;
  * прогноз → множитель маржи майнинга для Smart Grid балансировщика;
  * simulate_future_markets() → траектории для Монте-Карло в финансовом блоке.

Обучение — при первом обращении, кэшируется lru_cache по seed (детерминизм).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

import numpy as np
from sklearn.ensemble import HistGradientBoostingRegressor, RandomForestRegressor

from app import config as cfg


@dataclass(frozen=True)
class MarketParams:
    seed: int = 42
    n_paths: int = 48          # путей в обучающем ансамбле
    months: int = 132          # длина каждого пути, мес
    btc_start: float = cfg.BTC_PRICE_DEFAULT
    drift_year: float = 0.35   # дрейф GBM, год
    vol_year: float = 0.55     # волатильность GBM, год
    crash_prob_month: float = 0.03
    crash_return: float = -0.28
    gpu_rent_mean: float = cfg.GPU_RENT_DEFAULT
    gpu_rent_floor: float = 0.5
    gpu_rent_vol: float = 0.08
    difficulty_growth_month: float = 0.02  # рост сложности сети BTC, мес


def _simulate_history(p: MarketParams) -> tuple[np.ndarray, np.ndarray]:
    """Исторический ансамбль: btc [n_paths, months], rent [n_paths, months]."""
    rng = np.random.default_rng(p.seed)
    shape = (p.n_paths, p.months)

    r = rng.normal(p.drift_year / 12.0, p.vol_year / math.sqrt(12.0), size=shape)
    crash = rng.random(shape) < p.crash_prob_month
    r = np.where(crash, p.crash_return + rng.normal(0.0, 0.05, size=shape), r)
    btc = p.btc_start * np.cumprod(1.0 + r, axis=1)

    rent = np.empty(shape)
    rent[:, 0] = p.gpu_rent_mean
    shocks = rng.normal(0.0, p.gpu_rent_vol, size=p.months)
    for t in range(1, p.months):
        rent[:, t] = np.clip(
            rent[:, t - 1] + 0.15 * (p.gpu_rent_mean - rent[:, t - 1]) + shocks[t],
            p.gpu_rent_floor,
            None,
        )
    return btc, rent


def _features(px: np.ndarray, rent: np.ndarray) -> list[float]:
    """8 фич состояния рынка из истории цены и ренты."""
    px1 = float(px[-1])
    ret = lambda n: px1 / float(px[-1 - n]) - 1.0 if len(px) > n else 0.0
    vol6 = float(np.std(np.diff(np.log(px[-7:])), ddof=1)) if len(px) >= 8 else 0.0
    ma12 = float(np.mean(px[-12:]))
    hi12 = float(np.max(px[-12:]))
    rent_mean = float(np.mean(rent))
    return [
        ret(1),
        ret(3),
        ret(12),
        vol6,
        px1 / ma12 if ma12 > 0 else 1.0,
        px1 / hi12 - 1.0 if hi12 > 0 else 0.0,
        float(rent[-1] / rent[-2] - 1.0) if len(rent) >= 2 else 0.0,
        float(rent[-1] / rent_mean) if rent_mean > 0 else 1.0,
    ]


class MarketModel:
    """ML-модель ожидаемой доходности BTC (ансамбль RF + HistGB)."""

    def __init__(self, p: MarketParams):
        self.params = p
        btc, rent = _simulate_history(p)

        X: list[list[float]] = []
        y: list[float] = []
        for i in range(p.n_paths):
            for t in range(12, p.months - 3):
                X.append(_features(btc[i, : t + 1], rent[i, : t + 1]))
                y.append(float(btc[i, t + 3] / btc[i, t] - 1.0))
        Xa = np.asarray(X, dtype=float)
        ya = np.asarray(y, dtype=float)

        self.rf = RandomForestRegressor(
            n_estimators=300,
            max_depth=6,
            min_samples_leaf=20,
            random_state=p.seed,
            n_jobs=-1,
        )
        self.rf.fit(Xa, ya)
        self.hgb = HistGradientBoostingRegressor(
            max_iter=200, max_depth=4, learning_rate=0.08, random_state=p.seed
        )
        self.hgb.fit(Xa, ya)
        self._reference_btc = btc
        self._reference_rent = rent

    def features_for_state(self, btc_price: float, gpu_rent: float) -> list[float]:
        """Фичи текущего состояния: референсный путь масштабируется к заданной цене."""
        px_ref = self._reference_btc[-1]
        rent_ref = self._reference_rent[-1]
        px = px_ref * (btc_price / px_ref[-1])
        rn = rent_ref * (gpu_rent / rent_ref[-1]) if rent_ref[-1] > 0 else rent_ref
        return _features(px, rn)

    def predict_return_3m(self, btc_price: float, gpu_rent: float) -> float:
        """Ожидаемая доходность BTC на 3 мес (ансамбль), ограничена ±35 %."""
        x = np.asarray([self.features_for_state(btc_price, gpu_rent)], dtype=float)
        pred = (float(self.rf.predict(x)[0]) + float(self.hgb.predict(x)[0])) / 2.0
        return float(np.clip(pred, -0.35, 0.35))

    def miner_margin_multiplier(self, predicted_return: float) -> float:
        """Риск-дисконт майнинга: 1 + 0.5·E[ret_3m], диапазон [0.25, 1.5]."""
        return float(np.clip(1.0 + 0.5 * predicted_return, 0.25, 1.5))


@lru_cache(maxsize=8)
def get_market_model(seed: int = 42) -> MarketModel:
    """Кэшированная модель рынка (детерминирована по seed)."""
    return MarketModel(MarketParams(seed=seed))


def simulate_future_markets(
    seed: int,
    horizon_months: int,
    btc_start: float = cfg.BTC_PRICE_DEFAULT,
    n_sims: int = 400,
) -> tuple[np.ndarray, np.ndarray]:
    """Будущие траектории для Монте-Карло: btc [n_sims, months], rent [n_sims, months]."""
    p = MarketParams(seed=seed, btc_start=btc_start)
    rng = np.random.default_rng(seed + 1)
    shape = (n_sims, horizon_months)

    r = rng.normal(p.drift_year / 12.0, p.vol_year / math.sqrt(12.0), size=shape)
    crash = rng.random(shape) < p.crash_prob_month
    r = np.where(crash, p.crash_return + rng.normal(0.0, 0.05, size=shape), r)
    btc = p.btc_start * np.cumprod(1.0 + r, axis=1)

    rent = np.empty(shape)
    rent[:, 0] = p.gpu_rent_mean
    shocks = rng.normal(0.0, p.gpu_rent_vol, size=horizon_months)
    for t in range(1, horizon_months):
        rent[:, t] = np.clip(
            rent[:, t - 1] + 0.15 * (p.gpu_rent_mean - rent[:, t - 1]) + shocks[t],
            p.gpu_rent_floor,
            None,
        )
    return btc, rent
