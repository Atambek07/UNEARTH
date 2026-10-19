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
    assert {
        "forecast",
        "optimize",
        "maintenance",
        "finance",
        "sectors",
        "plan",
        "carbon",
    } <= set(data)
    assert data["finance"]["capex_total_usd"] > 0
    assert data["finance"]["fiscal"]["regime"] == "kr_htp"
    assert len(data["finance"]["annual"]) == 5
    assert data["carbon"]["totals"]["net_credits_t"] > 0
    assert data["plan"]["months"] == 12


def test_currency_endpoint() -> None:
    r = client.post("/api/currency", json={"annual_usd": [1_000_000.0], "usd_kgs_rate": 87.4})
    assert r.status_code == 200
    data = r.json()
    assert data["annual"][0]["kgs_received"] > 0
    assert data["totals"]["net_usd"] < 1_000_000.0
    assert data["totals"]["conversion_cost_usd"] == 15_000.0


def test_fiscal_compare_endpoint() -> None:
    r = client.post(
        "/api/fiscal/compare",
        json={
            "profit_before_tax_usd": 10_000_000,
            "ai_revenue_usd": 14_000_000,
            "mining_revenue_usd": 4_000_000,
            "miners_energy_kwh_year": 8_760_000,
            "labor_usd_year": 140_000,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert {row["regime"] for row in data["regimes"]} == {
        "none",
        "kr_general",
        "kr_htp",
        "kz_aifc",
    }
    assert data["best_regime"] in {"kr_htp", "kz_aifc"}
    assert data["assumptions"]["tariff_usd_per_kwh"] > 0
    assert "kz_pe_profit_share" in data["assumptions"]


def test_finance_has_fx_block() -> None:
    r = client.post(
        "/api/finance",
        json={
            "horizon_years": 3,
            "monthly_power_mw": [13.0] * 36,
            "monthly_ch4_m3_delivered": [1_500_000.0] * 36,
            "miners_count": 10,
            "ai_servers_count": 5,
            "fiscal_regime": "kz_aifc",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["fx"]["annual"][0]["kgs_received"] > 0
    assert data["fiscal"]["regime"] == "kz_aifc"


def test_scenario_stores_full_payload() -> None:
    created = client.post(
        "/api/scenarios",
        json={"name": "payload-test", "notes": "", "inputs": {"horizon_years": 3}, "run": True},
    )
    assert created.status_code == 201, created.text
    sid = created.json()["id"]
    try:
        full = client.get(f"/api/scenarios/{sid}").json()
        payload = full["results"]["payload"]
        assert payload["forecast"]["summary"]["year1_avg_power_mw"] > 0
        assert payload["carbon"]["totals"]["net_credits_t"] > 0
        assert payload["plan"]["months"] == 12
        assert payload["finance"]["fiscal"]["regime"] == "kr_htp"
    finally:
        client.delete(f"/api/scenarios/{sid}")


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


# ----------------------------------------------------------------------------
# v0.2: рынок, путь, карбон, финансы с фискальным блоком, сценарии
# ----------------------------------------------------------------------------


def test_market_current_synthetic() -> None:
    r = client.get("/api/market/current?provider=synthetic")
    assert r.status_code == 200
    data = r.json()
    assert data["source"] == "synthetic"
    assert data["btc_price_usd"] > 0
    assert data["disclaimer"]


def test_market_current_invalid_provider() -> None:
    assert client.get("/api/market/current?provider=darkweb").status_code == 422


def test_optimize_includes_market_source() -> None:
    r = client.post("/api/optimize", json={"available_mw": 3.0, "mode": "auto"})
    assert r.status_code == 200
    market = r.json()["market"]
    assert market["source"] == "synthetic"
    assert "notes" in market


def test_optimize_path_endpoint() -> None:
    r = client.post(
        "/api/optimize/path",
        json={"monthly_power_mw": [13.0] * 12, "monthly_btc_price": [65000.0] * 12},
    )
    assert r.status_code == 200
    data = r.json()
    assert len(data["plan"]) == 12
    assert data["totals"]["improvement_usd"] >= 0
    assert data["disclaimer"]


def test_carbon_endpoint() -> None:
    r = client.post("/api/carbon", json={"monthly_ch4_m3_delivered": [1_600_000.0] * 12})
    assert r.status_code == 200
    data = r.json()
    assert data["totals"]["net_credits_t"] > 0
    assert {"p10", "p50", "p90"} <= set(data["scenarios"])
    assert data["disclaimer"]


def test_finance_includes_fiscal_and_disclaimer() -> None:
    r = client.post(
        "/api/finance",
        json={
            "horizon_years": 5,
            "monthly_power_mw": [13.0] * 60,
            "monthly_ch4_m3_delivered": [1_600_000.0] * 60,
            "miners_count": 2480,
            "ai_servers_count": 500,
            "fiscal_regime": "kr_htp",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["fiscal"]["regime"] == "kr_htp"
    assert len(data["fiscal"]["years"]) == 5
    assert (
        data["fiscal"]["totals"]["net_profit_after_fiscal_usd"]
        < data["totals"]["net_profit_p50_usd"]
    )
    assert data["disclaimer"]


def test_scenarios_crud_and_compare(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("UNEARTH_DB_PATH", str(tmp_path / "api_scenarios.db"))
    monkeypatch.delenv("UNEARTH_DB_URL", raising=False)

    first = client.post("/api/scenarios", json={"name": "Базовый", "inputs": {}})
    assert first.status_code == 201
    id1 = first.json()["id"]

    second = client.post(
        "/api/scenarios",
        json={"name": "Бычий рынок", "inputs": {"btc_price": 90000.0}, "notes": "BTC up"},
    )
    assert second.status_code == 201
    id2 = second.json()["id"]

    listing = client.get("/api/scenarios").json()
    assert listing["count"] >= 2

    got = client.get(f"/api/scenarios/{id1}").json()
    assert got["name"] == "Базовый"
    assert got["results"]["digest"]["capex_total_usd"] > 0

    comparison = client.post("/api/scenarios/compare", json={"ids": [id1, id2]}).json()
    assert len(comparison["comparison"]) == 2
    assert comparison["best"]["capex_total_usd"] in {id1, id2}

    assert client.delete(f"/api/scenarios/{id2}").json()["deleted"] == id2
    assert client.get(f"/api/scenarios/{id2}").status_code == 404


def test_scenarios_compare_requires_existing(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("UNEARTH_DB_PATH", str(tmp_path / "api_scenarios2.db"))
    monkeypatch.delenv("UNEARTH_DB_URL", raising=False)
    r = client.post("/api/scenarios/compare", json={"ids": [424242, 424243]})
    assert r.status_code == 422
