"""Lokale Daten für die Weboberfläche; keine impliziten Netzabfragen."""

import json
from datetime import date
from pathlib import Path
from typing import Any

from partei_hack.api.client import APIClient
from partei_hack.services.comparison import build_selected_comparison
from partei_hack.services.importer import Importer, require_reference
from partei_hack.services.matching import PassageMatcher, plain_text
from partei_hack.services.programs import (
    ProgramFileMissingError,
    load_program,
    prepare_program,
    program_directory,
)
from partei_hack.services.queries import (
    list_polls,
    list_votes,
    poll_coverage,
    vote_import_status,
    vote_summary,
)
from partei_hack.services.requests import local_entities
from partei_hack.storage.database import Database, utc_now

VOTE_KEYS = ("yes", "no", "abstain", "no_show", "unknown")


class ProgramMissingError(ValueError):
    """Ein bewusster Online-Abruf kann die fehlende lokale Quelle ergänzen."""


def entity(database: Database, resource: str, entity_id: int) -> dict[str, Any]:
    row = database.connection.execute(
        "SELECT payload FROM entities WHERE resource=? AND entity_id=?", (resource, entity_id)
    ).fetchone()
    if row is None:
        raise ValueError("Die Auswahl ist lokal noch nicht vorhanden. Bitte Stammdaten laden.")
    return json.loads(row["payload"])


def selection(
    database: Database, period_id: int, fraction_id: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    period = entity(database, "parliament-periods", period_id)
    fraction = entity(database, "fractions", fraction_id)
    if period.get("type") != "legislature":
        raise ValueError("Bitte eine Legislaturperiode auswählen, keine Wahl.")
    if (fraction.get("legislature") or {}).get("id") != period_id:
        raise ValueError("Die Fraktion gehört nicht zur ausgewählten Wahlperiode.")
    return period, fraction


def catalog(database: Database) -> dict[str, Any]:
    periods = local_entities(database, "parliament-periods")
    parliaments = {item["id"]: item for item in local_entities(database, "parliaments")}
    # Bereits importierte Perioden enthalten echte Parlamentsreferenzen.
    for period in periods:
        ref = period.get("parliament") or {}
        if ref.get("id") and ref.get("label"):
            parliaments.setdefault(ref["id"], ref)
    return {
        "parliaments": sorted(parliaments.values(), key=lambda item: item["label"]),
        "periods": sorted(
            (item for item in periods if item.get("type") == "legislature"),
            key=lambda item: (item.get("start_date_period") or "", item["id"]),
            reverse=True,
        ),
        "fractions": sorted(local_entities(database, "fractions"), key=lambda item: item["label"]),
    }


def refresh_catalog(
    client: APIClient, database: Database, scope: str, parent_id: int | None
) -> dict[str, Any]:
    if scope == "parliaments":
        resource, params, reference = "parliaments", {}, None
    elif scope == "periods" and parent_id is not None:
        if not any(item["id"] == parent_id for item in catalog(database)["parliaments"]):
            raise ValueError("Das Parlament ist lokal noch nicht vorhanden.")
        resource, params, reference = "parliament-periods", {"parliament": parent_id}, "parliament"
    elif scope == "fractions" and parent_id is not None:
        period = entity(database, "parliament-periods", parent_id)
        if period.get("type") != "legislature":
            raise ValueError("Fraktionen benötigen eine Legislaturperiode.")
        resource, params, reference = "fractions", {"legislature": parent_id}, "legislature"
    elif scope == "programs" and parent_id is not None:
        period = entity(database, "parliament-periods", parent_id)
        if period.get("type") != "legislature":
            raise ValueError("Programme benötigen eine Legislaturperiode.")
        election_id = (period.get("previous_period") or {}).get("id")
        if not isinstance(election_id, int) or election_id < 1:
            raise ValueError("Die API verknüpft keine vorhergehende Wahl mit dieser Legislatur.")
        response = client.get_entity("parliament-periods", election_id)
        election = response.payload["data"]
        if election.get("type") != "election":
            raise ValueError("Die vorhergehende Periode ist keine Wahl; keine Programme geraten.")
        parliament_id = (period.get("parliament") or {}).get("id")
        if parliament_id is None:
            raise ValueError("Legislatur ohne geprüfte Parlamentsreferenz.")
        require_reference(election, "parliament", parliament_id)
        database.save_entity(
            "parliament-periods", election, response.source_url, response.fetched_at
        )
        resource = "election-program"
        params = {"parliament_period": election_id}
        reference, parent_id = "parliament_period", election_id
    else:
        raise ValueError("Unbekannte Stammdaten-Auswahl oder fehlende übergeordnete ID.")
    for page in client.iter_pages(resource, params):
        if reference is not None:
            for item in page.items:
                require_reference(item, reference, parent_id)
        database.save_entities(resource, page.items, page.source_url, page.fetched_at)
    return catalog(database)


def programs_for_period(database: Database, period: dict[str, Any]) -> list[dict[str, Any]]:
    election_id = (period.get("previous_period") or {}).get("id")
    election = next(
        (
            item
            for item in local_entities(database, "parliament-periods")
            if item["id"] == election_id
            and item.get("type") == "election"
            and (item.get("parliament") or {}).get("id")
            == (period.get("parliament") or {}).get("id")
        ),
        None,
    )
    return [
        item
        for item in local_entities(database, "election-program")
        if election is not None and (item.get("parliament_period") or {}).get("id") == election_id
    ]


def selected_program(
    database: Database, period_id: int, fraction_id: int, program_id: int
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    period, fraction = selection(database, period_id, fraction_id)
    program = next(
        (p for p in programs_for_period(database, period) if p["id"] == program_id), None
    )
    if program is None:
        raise ValueError(
            "Das Programm gehört nicht zur zugehörigen, lokal geprüften Wahl. "
            "Bei fehlenden Metadaten zuerst die Programmliste online laden."
        )
    return period, fraction, program


def selected_document(
    database: Database,
    data_dir: Path,
    period_id: int,
    fraction_id: int,
    program_id: int,
    *,
    client: APIClient | None = None,
) -> dict[str, Any]:
    _, _, program = selected_program(database, period_id, fraction_id, program_id)
    try:
        document = load_program(data_dir, program)
    except ProgramFileMissingError:
        document = None
    if document is None:
        if client is None:
            raise ProgramMissingError(
                "Die Programm-Metadaten sind vorhanden, aber die Original-PDF fehlt lokal. "
                "„Programm laden & Text anzeigen“ oder „Vergleich starten“ verwenden "
                "und den gezielten Download bestätigen."
            )
        document = prepare_program(data_dir, program, client=client)
    return document


def analysis(
    database: Database,
    period_id: int,
    fraction_id: int,
    *,
    search: str = "",
    since: str = "",
    until: str = "",
    poll_ids: list[int] | None = None,
) -> dict[str, Any]:
    period, fraction = selection(database, period_id, fraction_id)
    for value in (since, until):
        if value and date.fromisoformat(value).isoformat() != value:
            raise ValueError("Datum bitte im Format YYYY-MM-DD angeben.")
    if since and until and since > until:
        raise ValueError("Das Startdatum muss vor dem Enddatum liegen.")
    all_polls = list_polls(database, period_id=period_id)
    filtered = list_polls(
        database, period_id=period_id, search=search, since=since or None, until=until or None
    )
    if poll_ids is not None:
        filtered = [poll for poll in filtered if poll["id"] in poll_ids]
    totals = dict.fromkeys(VOTE_KEYS, 0)
    polls = []
    for poll in filtered:
        summary = vote_summary(database, poll["id"])
        group = next(
            (item for item in summary["fractions"] if item["fraction_id"] == fraction_id), {}
        )
        counts = {key: group.get(key, 0) for key in VOTE_KEYS}
        for key, value in counts.items():
            totals[key] += value
        original = entity(database, "polls", poll["id"])
        polls.append(
            {
                **poll,
                "public_url": original.get("abgeordnetenwatch_url"),
                "votes": counts,
                "fraction_votes": sum(counts.values()),
                "complete_against_api": summary["complete_against_api"],
                "expected_api_votes": summary["expected_api_votes"],
                "local_votes": summary["local_votes"],
            }
        )
    coverage = poll_coverage(database, period_id, [poll["id"] for poll in all_polls])
    available = coverage["available_api_polls"]
    complete = coverage["poll_list_complete_against_api"]
    programs = programs_for_period(database, period)
    return {
        "generated_at": utc_now(),
        "period": period,
        "fraction": fraction,
        "filters": {"search": search, "since": since, "until": until, "poll_ids": poll_ids},
        "coverage": {
            "local_polls": len(all_polls),
            "available_api_polls": available,
            "poll_list_complete_against_api": complete,
            "filtered_polls": len(polls),
            "filtered_polls_with_complete_votes": sum(p["complete_against_api"] for p in polls),
        },
        "vote_totals": totals,
        "vote_totals_unit": "Stimmereignisse in den gefilterten Abstimmungen, nicht Personen",
        "polls": polls,
        "programs": programs,
        "notice": (
            "Fraktionen sind keine Parteien. Fehlende Stimmen sind keine Nichtteilnahmen. "
            "Auch vollständige API-Listen sind nicht amtlich vollständig geprüft. "
            "Keine Bewertung der Erfüllung von Wahlversprechen."
        ),
    }


def poll_detail(
    database: Database, period_id: int, fraction_id: int, poll_id: int
) -> dict[str, Any]:
    selection(database, period_id, fraction_id)
    poll = entity(database, "polls", poll_id)
    if (poll.get("field_legislature") or {}).get("id") != period_id:
        raise ValueError("Die Abstimmung gehört nicht zur ausgewählten Wahlperiode.")
    return {
        "poll": poll,
        "description": plain_text(poll.get("field_intro") or ""),
        "votes": list_votes(database, poll_id, fraction_id=fraction_id),
        "coverage": vote_summary(database, poll_id),
    }


def program_passages(
    database: Database,
    data_dir: Path,
    period_id: int,
    fraction_id: int,
    program_id: int,
    *,
    page: int = 1,
    document: dict[str, Any] | None = None,
) -> dict[str, Any]:
    report = analysis(database, period_id, fraction_id)
    _, _, program = selected_program(database, period_id, fraction_id, program_id)
    if document is None:
        document = selected_document(database, data_dir, period_id, fraction_id, program_id)
    if not 1 <= page <= len(document["pages"]):
        raise ValueError("PDF-Seite außerhalb des Dokuments.")
    matcher = PassageMatcher(document["pages"])
    return {
        "program": program,
        "sha256": document["sha256"],
        "source_url": document["source_url"],
        "pdf_pages": len(document["pages"]),
        "origin": document["origin"],
        "imported_at": document["imported_at"],
        "page": page,
        "pages": document["pages"][page - 1 : page],
        "text_characters": sum(len(p["text"]) for p in document["pages"]),
        "notice": (
            "Ungeprüfte Worttreffer, keine Richtungs- oder Erfüllungsbewertung. "
            "Die Wahlpartei des Programms und die ausgewählte Fraktion sind getrennte Auswahlen."
        ),
        "polls": [
            {
                "id": poll["id"],
                "label": poll["label"],
                "matches": matcher.match(entity(database, "polls", poll["id"])),
            }
            for poll in report["polls"]
        ],
    }


def comparison(
    database: Database,
    data_dir: Path,
    period_id: int,
    fraction_id: int,
    program_id: int,
    *,
    client: APIClient | None = None,
    poll_ids: list[int] | None = None,
) -> dict[str, Any]:
    period, fraction, program = selected_program(database, period_id, fraction_id, program_id)
    document = selected_document(
        database, data_dir, period_id, fraction_id, program_id, client=client
    )
    return build_selected_comparison(
        database, period, program, fraction, document, poll_ids=poll_ids
    )


def choices(database: Database, data_dir: Path, period_id: int) -> dict[str, Any]:
    """Leichte lokale Auswahl ohne Fraktionsstimmen oder PDF-Extraktion."""
    period = entity(database, "parliament-periods", period_id)
    if period.get("type") != "legislature":
        raise ValueError("Bitte eine Legislaturperiode auswählen.")
    polls = list_polls(database, period_id=period_id)
    return program_options(
        data_dir,
        {
            "period": period,
            "programs": programs_for_period(database, period),
            "polls": [
                {
                    "id": poll["id"],
                    "label": poll["label"],
                    "date": poll["date"],
                    "complete_against_api": vote_import_status(database, poll["id"])[
                        "complete_against_api"
                    ],
                }
                for poll in polls
            ],
            "coverage": poll_coverage(database, period_id, [poll["id"] for poll in polls]),
        },
    )


def prepare_choices(
    client: APIClient, database: Database, data_dir: Path, period_id: int
) -> dict[str, Any]:
    """Nach Freigabe nur Fraktionen, Programm-Metadaten und Poll-Titel ergänzen."""
    period = entity(database, "parliament-periods", period_id)
    if period.get("type") != "legislature":
        raise ValueError("Bitte eine Legislaturperiode auswählen.")
    refresh_catalog(client, database, "fractions", period_id)
    program_notice = None
    if (period.get("previous_period") or {}).get("id"):
        refresh_catalog(client, database, "programs", period_id)
    else:
        program_notice = "Keine vorhergehende Wahl verknüpft; nur Abstimmungen auswählbar."
    Importer(client, database).import_poll_metadata(period_id)
    return {
        "catalog": catalog(database),
        "choices": choices(database, data_dir, period_id),
        "notice": program_notice,
    }


def run_selection(
    client: APIClient,
    database: Database,
    data_dir: Path,
    period_id: int,
    fraction_id: int,
    poll_ids: list[int],
    program_id: int | None,
) -> dict[str, Any]:
    """Bestätigte Auswahl gemeinsam laden; vollständige Stimmen nicht erneut abrufen."""
    pending = [
        poll_id
        for poll_id in poll_ids
        if not vote_import_status(database, poll_id)["complete_against_api"]
    ]
    imported = None
    if pending:
        imported = Importer(client, database).import_votes(
            period_id, pending, refresh_mandates=True
        )
    result = {
        "analysis": program_options(
            data_dir, analysis(database, period_id, fraction_id, poll_ids=poll_ids)
        ),
        "comparison": None,
        "import": imported,
        "selected_poll_ids": poll_ids,
        "reused_polls": len(poll_ids) - len(pending),
    }
    if program_id is not None:
        result["comparison"] = comparison(
            database,
            data_dir,
            period_id,
            fraction_id,
            program_id,
            client=client,
            poll_ids=poll_ids,
        )
        # Der Dateihinweis wird nach einem eventuellen PDF-Download aktualisiert.
        program_options(data_dir, result["analysis"])
    return result


def program_options(data_dir: Path, report: dict[str, Any]) -> dict[str, Any]:
    """Dateihinweis, keine vorgetäuschte Prüfsummen- oder Extraktionsprüfung."""
    for program in report["programs"]:
        directory = program_directory(data_dir, program["id"])
        program["local_document_present"] = any(
            path.with_suffix(".pdf").is_file() for path in directory.glob("*.json")
        )
    return report
