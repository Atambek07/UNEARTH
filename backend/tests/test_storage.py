"""Тесты хранилища сценариев (SQLite, временная БД)."""
import pytest

from app import storage


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    monkeypatch.setenv("UNEARTH_DB_PATH", str(tmp_path / "scenarios.db"))
    monkeypatch.delenv("UNEARTH_DB_URL", raising=False)
    return tmp_path


def test_save_list_get_delete(temp_db):
    saved = storage.save_scenario(
        name="Базовый", notes="дефолт Бишкека", inputs={"h2s_ppm": 30}, results={"digest": {"capex_total_usd": 1}}
    )
    assert saved["id"] >= 1
    assert saved["created_at"]

    items = storage.list_scenarios()
    assert any(item["id"] == saved["id"] and item["name"] == "Базовый" for item in items)

    full = storage.get_scenario(saved["id"])
    assert full is not None
    assert full["inputs"]["h2s_ppm"] == 30
    assert full["results"]["digest"]["capex_total_usd"] == 1

    assert storage.delete_scenario(saved["id"]) is True
    assert storage.get_scenario(saved["id"]) is None
    assert storage.delete_scenario(saved["id"]) is False


def test_persistence_across_calls(temp_db):
    first = storage.save_scenario("A", "", {"x": 1}, {"digest": {}})
    second = storage.save_scenario("B", "", {"x": 2}, {"digest": {}})
    assert second["id"] > first["id"]
    names = [item["name"] for item in storage.list_scenarios()]
    assert names[:2] == ["B", "A"]  # новые сверху


def test_missing_scenario_returns_none(temp_db):
    assert storage.get_scenario(999_999) is None
