"""Карта секторов полигона: поток газа, H2S, статусы.

Легенда (PDF + ТЗ): свежие сектора — зелёные (газа много и он стабильный),
старые — серые (выработаны); оранжевый/красный — высокое содержание
сероводорода, требующее усиленной фильтрации (риск №1 PDF).

Нестабильность секторов предсказывает RandomForestClassifier (scikit-learn):
фичи — календарный месяц, индекс влажности, H2S, возраст, поток газа.
Модель обучается на латентных правилах (осенний пик бахчевых + высокий H2S)
при первом обращении и кэшируется по seed.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np
from sklearn.ensemble import RandomForestClassifier

from app import config as cfg
from app.engines.seasonal import SeasonalParams, moisture_index

AGE_CLASSES = ("fresh", "mid", "old")
CLASS_WEIGHT = {"fresh": 1.6, "mid": 1.0, "old": 0.55}
H2S_BASE = {"fresh": 38.0, "mid": 28.0, "old": 16.0}

STATUS_NOTES = {
    "green": "Стабильная подача газа",
    "amber": "Повышенное содержание H2S — усиленная фильтрация",
    "red": "Высокий H2S / нестабильность — приоритет очистки, узлы могут отключаться",
    "depleted": "Старый сектор: генерация газа практически выработана",
}


@lru_cache(maxsize=8)
def get_sector_model(seed: int = 42) -> RandomForestClassifier:
    """Классификатор нестабильности секторов (детерминирован по seed)."""
    rng = np.random.default_rng(seed + 7)
    n = 6000
    month = rng.integers(1, 13, n).astype(float)
    moisture = np.asarray([moisture_index(int(m), SeasonalParams()) for m in month])
    h2s = np.clip(rng.lognormal(np.log(30.0), 0.45, n), 2.0, 200.0)
    age = rng.uniform(1.0, 54.0, n)
    flux = rng.lognormal(np.log(120.0), 0.6, n)

    latent = (
        (h2s > 55.0)
        & (month >= 8.0)
        & (month <= 11.0)
        & (rng.random(n) < 0.75)
    ) | ((moisture > 1.08) & (rng.random(n) < 0.45))

    X = np.column_stack([month, moisture, h2s, age, flux])
    clf = RandomForestClassifier(
        n_estimators=200, max_depth=8, random_state=seed
    )
    clf.fit(X, latent)
    return clf


def build_sectors(
    ch4_m3_delivered_month: float,
    month: int,
    rows: int = cfg.SECTOR_ROWS,
    cols: int = cfg.SECTOR_COLS,
    seed: int = 42,
) -> dict:
    """Карта rows×cols: доли массы через Dirichlet с весами возрастных классов.

    ch4_m3_delivered_month — CH4, отбираемый из секторов за месяц (после
    учёта collection efficiency), поэтому повторно не масштабируется.
    """
    clf = get_sector_model(seed)
    rng = np.random.default_rng(seed + 8)
    n = rows * cols

    classes = rng.choice(np.asarray(AGE_CLASSES), size=n, p=[0.25, 0.40, 0.35])
    weights = np.asarray([CLASS_WEIGHT[c] for c in classes])
    shares = rng.dirichlet(np.ones(n) * 3.0) * weights
    shares = shares / shares.sum()

    flux = shares * ch4_m3_delivered_month / 730.0  # м³/ч

    moisture_mult = 1.0 + 0.35 * (moisture_index(month, SeasonalParams()) - 1.0)
    h2s = np.asarray(
        [
            float(
                rng.lognormal(np.log(H2S_BASE[c]), 0.35)
            )
            for c in classes
        ]
    ) * moisture_mult
    h2s = np.clip(h2s, 2.0, 200.0)

    age_years = np.asarray(
        [
            rng.uniform(1.0, 6.0) if c == "fresh" else (rng.uniform(6.0, 20.0) if c == "mid" else rng.uniform(20.0, 54.0))
            for c in classes
        ]
    )

    X = np.column_stack(
        [
            np.full(n, float(month)),
            np.full(n, moisture_index(month, SeasonalParams())),
            h2s,
            age_years,
            np.clip(flux, 1e-6, None),
        ]
    )
    proba = clf.predict_proba(X)[:, 1]

    sectors: list[dict] = []
    summary = {"green": 0, "amber": 0, "red": 0, "depleted": 0}
    for i in range(n):
        if flux[i] < cfg.SECTOR_DEPLETED_FLUX_M3H:
            status = "depleted"
        elif h2s[i] > cfg.SECTOR_H2S_RED_PPM or proba[i] > 0.7:
            status = "red"
        elif h2s[i] > cfg.SECTOR_H2S_AMBER_PPM or proba[i] > 0.4:
            status = "amber"
        else:
            status = "green"
        summary[status] += 1
        sectors.append(
            {
                "id": f"S{i + 1:02d}",
                "row": i // cols,
                "col": i % cols,
                "age_class": str(classes[i]),
                "ch4_flux_m3_h": round(float(flux[i]), 1),
                "h2s_ppm": round(float(h2s[i]), 1),
                "instability_proba": round(float(proba[i]), 2),
                "status": status,
                "note": STATUS_NOTES[status],
            }
        )

    return {
        "rows": rows,
        "cols": cols,
        "month": month,
        "sectors": sectors,
        "summary": summary,
    }
