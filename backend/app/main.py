"""UNEARTH — точка входа FastAPI.

Запуск: uvicorn app.main:app --reload --port 8000  (из папки backend/)
Документация: http://localhost:8000/docs
"""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router

app = FastAPI(
    title="UNEARTH — Smart LFG-to-Energy & Computational Grid Simulator",
    version="0.1.0",
    description=(
        "MVP-симулятор Бишкекского полигона: LandGEM + ML-прогноз метана, "
        "Smart Grid балансировщик, предиктивное обслуживание ГПУ по H2S, "
        "финансовая модель и Green Tracker (CO2, Фонд озеленения)."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://unearth-le7z.onrender.com/", "https://unearth-ruddy.vercel.app", "http://localhost:8000"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/")
def root() -> dict:
    return {"service": "UNEARTH", "version": app.version, "docs": "/docs", "health": "/api/health"}
