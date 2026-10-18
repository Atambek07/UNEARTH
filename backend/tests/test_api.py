"""Smoke-тесты REST API (TestClient, без запуска uvicorn)."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert "prophet_available" in data


def test_forecast_endpoint() -> None:
    r = client.post("/api/forecast", json={"horizon_years": 5})
    assert r.status_code == 200
    data = r.json()
    assert len(data["annual"]) == 5
    assert len(data["monthly"]) == 60
    assert data["annual"][0]["avg_power_mw"] > 0
    assert data["summary"]["year1_avg_power_mw"] > 0
    assert data["meta"]["model"] in {"builtin-seasonal-ar1", "prophet"}


def test_optimize_endpoint_auto_and_manual() -> None:
    r = client.post("/api/optimize", json={"available_mw": 3.0, "mode": "auto"})
    assert r.status_code == 200
    data = r.json()
    assert not data["overcommitted"]
    assert len(data["allocation"]) == 2

    r2 = client.post(
        "/api/optimize",
        json={"available_mw": 3.0, "mode": "manual", "manual_miners": 100, "manual_ai_servers": 50},
    )
    assert r2.status_code == 200
    assert r2.json()["manual"]


def test_maintenance_endpoint() -> None:
    r = client.post(
        "/api/maintenance", json={"installed_mw": 5.0, "ch4_m3_month": 2_000_000.0, "h2s_ppm": 45.0}
    )
    assert r.status_code == 200
    data = r.json()
    assert data["genset_count"] == 5
    assert data["scrubber"]["life_months"] > 0
    assert data["opex_monthly_usd"]["total_usd"] > 0


def test_sectors_endpoint() -> None:
    r = client.post("/api/sectors", json={"ch4_m3_delivered_month": 1_500_000.0, "month": 10})
    assert r.status_code == 200
    data = r.json()
    assert len(data["sectors"]) == data["rows"] * data["cols"] == 48
    statuses = {s["status"] for s in data["sectors"]}
    assert statuses <= {"green", "amber", "red", "depleted"}
    assert sum(data["summary"].values()) == 48


def test_simulation_run_aggregator() -> None:
    r = client.post("/api/simulation/run", json={"horizon_years": 5})
    assert r.status_code == 200
    data = r.json()
    assert {"forecast", "optimize", "maintenance", "finance", "sectors"} <= set(data)
    assert data["finance"]["capex_total_usd"] > 0
    assert len(data["finance"]["annual"]) == 5


def test_validation_errors() -> None:
    r = client.post("/api/optimize", json={"available_mw": -1})
    assert r.status_code == 422
    r = client.post(
        "/api/finance",
        json={
            "horizon_years": 2,
            "monthly_power_mw": [1.0] * 24,
            "monthly_ch4_m3_delivered": [1.0] * 12,
            "miners_count": 0,
            "ai_servers_count": 0,
        },
    )
    assert r.status_code == 422
