"""SQLite-Ablage; Schema und Schreiboperationen an einem Ort."""

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(path)
        self.connection.row_factory = sqlite3.Row
        self.connection.create_function(
            "unicode_casefold",
            1,
            lambda value: value.casefold() if isinstance(value, str) else value,
            deterministic=True,
        )
        version = self.connection.execute("PRAGMA user_version").fetchone()[0]
        if version not in (0, 1):
            self.close()
            raise RuntimeError(f"Nicht unterstützte Datenbankschemaversion: {version}")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS entities (
                resource TEXT NOT NULL,
                entity_id INTEGER NOT NULL,
                payload TEXT NOT NULL,
                source_url TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                PRIMARY KEY (resource, entity_id)
            );
            CREATE TABLE IF NOT EXISTS http_cache (
                url TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                fetched_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS import_runs (
                id INTEGER PRIMARY KEY,
                period_id INTEGER NOT NULL,
                started_at TEXT NOT NULL,
                finished_at TEXT,
                status TEXT NOT NULL,
                options TEXT NOT NULL,
                stats TEXT,
                error TEXT
            );
            CREATE TABLE IF NOT EXISTS vote_coverage (
                poll_id INTEGER PRIMARY KEY,
                expected_count INTEGER,
                complete INTEGER NOT NULL,
                checked_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS entities_poll
                ON entities(resource, json_extract(payload, '$.poll.id'));
            CREATE INDEX IF NOT EXISTS entities_period
                ON entities(resource, json_extract(payload, '$.field_legislature.id'));
            PRAGMA user_version = 1;
            """
        )

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "Database":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def save_entity(
        self, resource: str, payload: dict[str, Any], source_url: str, fetched_at: str
    ) -> None:
        self.save_entities(resource, [payload], source_url, fetched_at)

    def save_entities(
        self, resource: str, payloads: list[dict[str, Any]], source_url: str, fetched_at: str
    ) -> None:
        """Eine vollständig validierte API-Seite atomar speichern statt Commit pro Stimme."""
        with self.connection:
            self.connection.executemany(
                """INSERT INTO entities VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(resource, entity_id) DO UPDATE SET
                    payload=excluded.payload,
                    source_url=excluded.source_url,
                    fetched_at=excluded.fetched_at""",
                (
                    (resource, payload["id"], json.dumps(payload), source_url, fetched_at)
                    for payload in payloads
                ),
            )

    def get_cached(self, url: str, ttl_seconds: float) -> tuple[dict[str, Any], str] | None:
        row = self.connection.execute(
            "SELECT payload, fetched_at FROM http_cache WHERE url=?", (url,)
        ).fetchone()
        if row is None:
            return None
        age = (datetime.now(UTC) - datetime.fromisoformat(row["fetched_at"])).total_seconds()
        if age < 0 or age >= ttl_seconds:
            return None
        return json.loads(row["payload"]), row["fetched_at"]

    def cache_response(self, url: str, payload: dict[str, Any], fetched_at: str) -> None:
        with self.connection:
            self.connection.execute(
                """INSERT INTO http_cache VALUES (?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    payload=excluded.payload, fetched_at=excluded.fetched_at""",
                (url, json.dumps(payload), fetched_at),
            )

    def start_import(self, period_id: int, options: dict[str, Any]) -> int:
        with self.connection:
            cursor = self.connection.execute(
                """INSERT INTO import_runs(period_id, started_at, status, options)
                VALUES (?, ?, 'running', ?)""",
                (period_id, utc_now(), json.dumps(options)),
            )
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    def finish_import(self, run_id: int, stats: dict[str, Any], error: str | None = None) -> None:
        with self.connection:
            self.connection.execute(
                """UPDATE import_runs SET finished_at=?, status=?, stats=?, error=?
                WHERE id=?""",
                (
                    utc_now(),
                    "failed" if error else "completed",
                    json.dumps(stats),
                    error,
                    run_id,
                ),
            )

    def mark_vote_coverage(
        self, poll_id: int, expected_count: int | None, *, complete: bool
    ) -> None:
        with self.connection:
            self.connection.execute(
                """INSERT INTO vote_coverage VALUES (?, ?, ?, ?)
                ON CONFLICT(poll_id) DO UPDATE SET expected_count=excluded.expected_count,
                    complete=excluded.complete, checked_at=excluded.checked_at""",
                (poll_id, expected_count, int(complete), utc_now()),
            )
