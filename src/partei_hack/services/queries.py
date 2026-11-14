"""Parametrisierte lokale Abfragen. Keine Netzwerkzugriffe oder Bewertungen."""

import json
from typing import Any

from partei_hack.storage.database import Database


def list_polls(
    database: Database,
    *,
    period_id: int | None = None,
    search: str | None = None,
    since: str | None = None,
    until: str | None = None,
    topic_id: int | None = None,
) -> list[dict[str, Any]]:
    conditions = ["resource = 'polls'"]
    values: list[Any] = []
    if period_id is not None:
        conditions.append("json_extract(payload, '$.field_legislature.id') = ?")
        values.append(period_id)
    if search:
        # Literal-Suche statt unerwarteter SQL-LIKE-Platzhalter.
        conditions.append(
            "instr(unicode_casefold(json_extract(payload, '$.label')), unicode_casefold(?)) > 0"
        )
        values.append(search)
    if since:
        conditions.append("json_extract(payload, '$.field_poll_date') >= ?")
        values.append(since)
    if until:
        conditions.append("json_extract(payload, '$.field_poll_date') <= ?")
        values.append(until)
    if topic_id is not None:
        conditions.append(
            """EXISTS (SELECT 1 FROM json_each(entities.payload, '$.field_topics')
            WHERE json_extract(value, '$.id') = ?)"""
        )
        values.append(topic_id)
    rows = database.connection.execute(
        f"""SELECT payload, source_url, fetched_at FROM entities
        WHERE {" AND ".join(conditions)}
        ORDER BY json_extract(payload, '$.field_poll_date') DESC, entity_id DESC""",
        values,
    )
    results = []
    for row in rows:
        item = json.loads(row["payload"])
        results.append(
            {
                "id": item["id"],
                "label": item["label"],
                "date": item.get("field_poll_date"),
                "accepted": item.get("field_accepted"),
                "period_id": (item.get("field_legislature") or {}).get("id"),
                "source_url": row["source_url"],
                "fetched_at": row["fetched_at"],
            }
        )
    return results


def list_votes(
    database: Database, poll_id: int, *, vote: str | None = None, fraction_id: int | None = None
) -> list[dict[str, Any]]:
    conditions = ["v.resource='votes'", "json_extract(v.payload, '$.poll.id')=?"]
    values: list[Any] = [poll_id]
    if vote:
        conditions.append("json_extract(v.payload, '$.vote')=?")
        values.append(vote)
    if fraction_id is not None:
        conditions.append("json_extract(v.payload, '$.fraction.id')=?")
        values.append(fraction_id)
    rows = database.connection.execute(
        f"""SELECT v.payload, v.source_url, v.fetched_at, m.payload AS mandate_payload
        FROM entities v
        LEFT JOIN entities m ON m.resource='candidacies-mandates'
            AND m.entity_id=json_extract(v.payload, '$.mandate.id')
        WHERE {" AND ".join(conditions)} ORDER BY v.entity_id""",
        values,
    )
    results = []
    for row in rows:
        item = json.loads(row["payload"])
        mandate = json.loads(row["mandate_payload"]) if row["mandate_payload"] else {}
        politician = mandate.get("politician") or {}
        fraction = item.get("fraction") or {}
        results.append(
            {
                "id": item["id"],
                "poll_id": poll_id,
                "mandate_id": (item.get("mandate") or {}).get("id"),
                "politician_id": politician.get("id"),
                "politician": politician.get("label"),
                "fraction_id": fraction.get("id"),
                "fraction": fraction.get("label"),
                "vote": item.get("vote"),
                "reason_no_show": item.get("reason_no_show"),
                "source_url": row["source_url"],
                "fetched_at": row["fetched_at"],
            }
        )
    return results


def vote_summary(database: Database, poll_id: int) -> dict[str, Any]:
    votes = list_votes(database, poll_id)
    fractions: dict[int | None, dict[str, Any]] = {}
    for vote in votes:
        key = vote["fraction_id"]
        if key not in fractions:
            fractions[key] = {
                "fraction_id": key,
                "fraction": vote["fraction"] or "Nicht zugeordnet",
                "yes": 0,
                "no": 0,
                "abstain": 0,
                "no_show": 0,
                "unknown": 0,
            }
        value = vote["vote"]
        field = value if value in {"yes", "no", "abstain", "no_show"} else "unknown"
        fractions[key][field] += 1
    return {
        **vote_import_status(database, poll_id, vote_ids=[vote["id"] for vote in votes]),
        "notice": "Fraktionen, nicht Parteien. Keine Bewertung von Wahlversprechen.",
        "fractions": sorted(fractions.values(), key=lambda item: str(item["fraction"])),
    }


def vote_import_status(
    database: Database, poll_id: int, *, vote_ids: list[int] | None = None
) -> dict[str, Any]:
    """Importabdeckung nur anhand IDs prüfen, ohne Stimmen-/Mandats-Payloads zu laden."""
    if vote_ids is None:
        vote_ids = [
            row["entity_id"]
            for row in database.connection.execute(
                "SELECT entity_id FROM entities WHERE resource='votes' "
                "AND json_extract(payload, '$.poll.id')=?",
                (poll_id,),
            )
        ]
    coverage = database.connection.execute(
        "SELECT * FROM vote_coverage WHERE poll_id=?", (poll_id,)
    ).fetchone()
    expected = coverage["expected_count"] if coverage else None
    complete = bool(coverage and coverage["complete"] and expected == len(vote_ids))
    manifest = database.connection.execute(
        "SELECT payload FROM entities WHERE resource='vote-import-manifests' AND entity_id=?",
        (poll_id,),
    ).fetchone()
    ids_verified = None
    if manifest:
        expected_ids = json.loads(manifest["payload"]).get("vote_ids")
        ids_verified = (
            isinstance(expected_ids, list)
            and len(expected_ids) == expected
            and sorted(vote_ids) == sorted(expected_ids)
        )
        complete = complete and ids_verified
    return {
        "poll_id": poll_id,
        "local_votes": len(vote_ids),
        "expected_api_votes": expected,
        "complete_against_api": complete,
        "identity_set_verified": ids_verified,
        "validation_level": "retrieved_id_set_and_count" if manifest else "count_only_legacy",
        "checked_at": coverage["checked_at"] if coverage else None,
    }


def poll_coverage(database: Database, period_id: int, local_ids: list[int]) -> dict[str, Any]:
    runs = database.connection.execute(
        """SELECT stats FROM import_runs WHERE period_id=? AND status='completed'
        ORDER BY id DESC""",
        (period_id,),
    )
    latest = next(
        (
            stats
            for stats in (json.loads(row["stats"]) for row in runs if row["stats"])
            if stats.get("polls_available") is not None
        ),
        {},
    )
    available = latest.get("polls_available")
    expected_ids = latest.get("poll_ids")
    ids_verified = (
        sorted(expected_ids) == sorted(local_ids) if isinstance(expected_ids, list) else None
    )
    complete = bool(
        latest.get("polls_complete") and available == len(local_ids) and ids_verified is not False
    )
    return {
        "available_api_polls": available,
        "poll_list_complete_against_api": complete,
        "identity_set_verified": ids_verified,
        "validation_level": (
            "retrieved_id_set_and_count" if expected_ids is not None else "count_only_legacy"
        ),
    }


def project_status(database: Database) -> dict[str, Any]:
    counts = {
        row["resource"]: row["count"]
        for row in database.connection.execute(
            "SELECT resource, COUNT(*) AS count FROM entities GROUP BY resource ORDER BY resource"
        )
    }
    runs = []
    for row in database.connection.execute("SELECT * FROM import_runs ORDER BY id DESC LIMIT 10"):
        run = dict(row)
        run["options"] = json.loads(run["options"])
        run["stats"] = json.loads(run["stats"]) if run["stats"] else None
        runs.append(run)
    return {"entity_counts": counts, "recent_imports": runs}
