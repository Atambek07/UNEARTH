"""Хранилище сценариев: SQLite по умолчанию, PostgreSQL опционально.

Выбор драйвера:
  * SQLite (по умолчанию): файл `backend/data/unearth.db`, путь переопределяется
    env `UNEARTH_DB_PATH`. Ноль настройки — для MVP и разработки.
  * PostgreSQL: env `UNEARTH_DB_URL=postgres://user:pass@host:5432/db`
    (psycopg3). DDL создаётся автоматически при первом обращении.

Нагрузка MVP (сохранение сценариев) для SQLite с WAL достаточна; Postgres —
готовый путь для прод-деплоя. API обоих драйверов идентичен.
"""
from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from app import config as cfg

# Дефолтный файл SQLite — относительно пакета (backend/data/unearth.db),
# независимо от рабочей директории процесса.
_DEFAULT_SQLITE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "unearth.db"
)

_TABLE = "scenarios"

_DDL_SQLITE = f"""
CREATE TABLE IF NOT EXISTS {_TABLE} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    inputs_json TEXT NOT NULL,
    results_json TEXT NOT NULL DEFAULT '{{}}'
)
"""

_DDL_POSTGRES = f"""
CREATE TABLE IF NOT EXISTS {_TABLE} (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    inputs_json TEXT NOT NULL,
    results_json TEXT NOT NULL DEFAULT '{{}}'
)
"""


class StorageError(RuntimeError):
    """Ошибка слоя хранения (драйвер/схема)."""


def _resolve_backend() -> tuple[str, str]:
    """(backend, target): 'postgres' при заданном UNEARTH_DB_URL, иначе sqlite."""
    url = os.environ.get("UNEARTH_DB_URL", "").strip()
    if url:
        if not url.startswith(("postgres://", "postgresql://")):
            raise StorageError("UNEARTH_DB_URL должен начинаться с postgres://")
        return "postgres", url
    path = os.environ.get("UNEARTH_DB_PATH", _DEFAULT_SQLITE_PATH)
    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    return "sqlite", path


@contextmanager
def _connect() -> Iterator[tuple[Any, str]]:
    backend, target = _resolve_backend()
    if backend == "postgres":
        try:
            import psycopg
            import psycopg.rows
        except ImportError as exc:  # pragma: no cover — среда без psycopg
            raise StorageError(
                "Для PostgreSQL установите: pip install 'psycopg[binary]'"
            ) from exc
        conn = psycopg.connect(target, row_factory=psycopg.rows.dict_row)
    else:
        conn = sqlite3.connect(target, timeout=15.0)
        conn.row_factory = sqlite3.Row
    try:
        yield conn, backend
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _ensure_table(conn: Any, backend: str) -> None:
    ddl = _DDL_POSTGRES if backend == "postgres" else _DDL_SQLITE
    conn.execute(ddl)


def _ph(backend: str) -> str:
    """Плейсхолдер параметров: ? у sqlite, %s у postgres."""
    return "%s" if backend == "postgres" else "?"


def save_scenario(name: str, notes: str, inputs: dict, results: dict) -> dict:
    """Сохраняет сценарий; возвращает {id, created_at, name}."""
    created_at = datetime.now(timezone.utc).isoformat()
    inputs_json = json.dumps(inputs, ensure_ascii=False)
    results_json = json.dumps(results, ensure_ascii=False)
    with _connect() as (conn, backend):
        _ensure_table(conn, backend)
        ph = _ph(backend)
        params = (name, notes, created_at, inputs_json, results_json)
        if backend == "postgres":
            row = conn.execute(
                f"INSERT INTO {_TABLE} (name, notes, created_at, inputs_json, results_json) "
                f"VALUES ({ph}, {ph}, {ph}, {ph}, {ph}) RETURNING id",
                params,
            ).fetchone()
            new_id = row["id"]
        else:
            cursor = conn.execute(
                f"INSERT INTO {_TABLE} (name, notes, created_at, inputs_json, results_json) "
                f"VALUES ({ph}, {ph}, {ph}, {ph}, {ph})",
                params,
            )
            new_id = cursor.lastrowid
    return {"id": int(new_id), "created_at": created_at, "name": name}


def list_scenarios(limit: int = 100) -> list[dict]:
    """Список сценариев (без тяжёлых результатов): id, имя, дата, заметки."""
    with _connect() as (conn, backend):
        _ensure_table(conn, backend)
        rows = conn.execute(
            f"SELECT id, name, notes, created_at FROM {_TABLE} ORDER BY id DESC LIMIT {int(limit)}"
        ).fetchall()
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "notes": row["notes"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def get_scenario(scenario_id: int) -> dict | None:
    """Полный сценарий: входы и сохранённые результаты."""
    with _connect() as (conn, backend):
        _ensure_table(conn, backend)
        row = conn.execute(
            f"SELECT id, name, notes, created_at, inputs_json, results_json "
            f"FROM {_TABLE} WHERE id = {_ph(backend)}",
            (scenario_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "id": row["id"],
        "name": row["name"],
        "notes": row["notes"],
        "created_at": row["created_at"],
        "inputs": json.loads(row["inputs_json"]),
        "results": json.loads(row["results_json"]),
    }


def delete_scenario(scenario_id: int) -> bool:
    """Удаляет сценарий; True, если он существовал."""
    with _connect() as (conn, backend):
        _ensure_table(conn, backend)
        cursor = conn.execute(
            f"DELETE FROM {_TABLE} WHERE id = {_ph(backend)}", (scenario_id,)
        )
        return bool(cursor.rowcount)
