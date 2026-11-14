import json
import sqlite3
from datetime import UTC, datetime, timedelta

import pytest

from partei_hack.storage.archive import archive_response
from partei_hack.storage.database import Database, utc_now


def test_entity_upsert_is_idempotent_and_preserves_unknown_fields(database):
    entity = {"id": 1, "label": "Test", "unknown": {"nested": [1, 2]}}
    database.save_entity("polls", entity, "https://invalid.example/old", utc_now())
    entity["label"] = "Updated"
    database.save_entity("polls", entity, "https://invalid.example/new", utc_now())
    rows = database.connection.execute("SELECT * FROM entities").fetchall()
    assert len(rows) == 1
    assert json.loads(rows[0]["payload"]) == entity
    assert rows[0]["source_url"].endswith("/new")


def test_cache_expiry(database):
    old = (datetime.now(UTC) - timedelta(days=2)).isoformat()
    database.cache_response("https://invalid.example", {"data": []}, old)
    assert database.get_cached("https://invalid.example", 86400) is None


def test_archive_is_unique_and_json_content_is_preserved(tmp_path):
    payload = {"html": "<p>Änderung</p>", "unknown": None}
    first = archive_response(tmp_path, payload)
    second = archive_response(tmp_path, payload)
    assert first != second
    assert json.loads(first.read_text(encoding="utf-8")) == payload


def test_import_failure_is_recorded(database):
    run = database.start_import(1, {"max_polls": 1})
    database.finish_import(run, {"polls_complete": False}, "Testfehler")
    row = database.connection.execute("SELECT * FROM import_runs").fetchone()
    assert row["status"] == "failed"
    assert row["error"] == "Testfehler"
    assert row["finished_at"]


def test_unknown_schema_is_not_overwritten(tmp_path):
    path = tmp_path / "future.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version=99")
    with pytest.raises(RuntimeError, match="99"):
        Database(path)


def test_page_write_rolls_back_as_a_unit(database):
    with pytest.raises(KeyError):
        database.save_entities(
            "polls",
            [{"id": 1, "label": "Synthetic"}, {"label": "Missing ID"}],
            "https://invalid.example",
            utc_now(),
        )
    assert database.connection.execute("SELECT COUNT(*) FROM entities").fetchone()[0] == 0
