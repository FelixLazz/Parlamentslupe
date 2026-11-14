"""Begrenzte, deterministische deutsche Suchsyntax; kein allgemeines Sprachmodell."""

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from partei_hack.api.client import APIClient
from partei_hack.storage.database import Database

PARTIES = {
    "gruene": ("grüne", "grünen", "gruene", "gruenen", "bündnis 90 die grünen"),
    "spd": ("spd", "sozialdemokratische partei deutschlands"),
    "fdp": ("fdp", "freie demokraten"),
    "afd": ("afd", "alternative für deutschland"),
    "linke": ("die linke", "linke", "linkspartei"),
    "cdu": ("cdu", "christlich demokratische union deutschlands"),
    "csu": ("csu", "christlich soziale union in bayern"),
}


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKC", value).casefold().replace("\xad", "")
    for original, replacement in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        value = value.replace(original, replacement)
    return " ".join(re.findall(r"[a-z0-9]+", value))


def party_keys(value: str) -> set[str]:
    text = f" {normalize(value)} "
    return {
        key
        for key, aliases in PARTIES.items()
        if any(f" {normalize(alias)} " in text for alias in aliases)
    }


@dataclass(frozen=True)
class ComparisonRequest:
    parliament: str
    start_year: int
    end_year: int
    party: str

    def __post_init__(self) -> None:
        if not 1949 <= self.start_year < self.end_year <= 2100:
            raise ValueError("Bitte eine Wahlperiode mit Startjahr < Endjahr angeben.")
        if self.party not in PARTIES:
            raise ValueError("Unbekannte Partei.")


def parse_request(text: str) -> ComparisonRequest:
    years = re.findall(r"(?<!\d)(?:19|20)\d{2}(?!\d)", text)
    parties = party_keys(text)
    if "bundestag" not in normalize(text).split():
        raise ValueError("Die Freitextsyntax unterstützt derzeit den Bundestag.")
    if len(years) != 2 or len(parties) != 1:
        raise ValueError(
            'Bitte eindeutig formulieren, z. B. "Bundestag 2021 bis 2025 Grüne". '
            "Genau zwei Jahreszahlen und eine Partei sind erforderlich."
        )
    return ComparisonRequest("Bundestag", int(years[0]), int(years[1]), parties.pop())


def local_entities(database: Database, resource: str) -> list[dict[str, Any]]:
    import json

    return [
        json.loads(row["payload"])
        for row in database.connection.execute(
            "SELECT payload FROM entities WHERE resource=? ORDER BY entity_id", (resource,)
        )
    ]


def discover_periods(client: APIClient, database: Database, parliament: str) -> None:
    matches = []
    for page in client.iter_pages("parliaments"):
        for item in page.items:
            if normalize(item["label"]) == normalize(parliament):
                matches.append(item)
                database.save_entity("parliaments", item, page.source_url, page.fetched_at)
    if len(matches) != 1:
        raise ValueError("Parlament konnte nicht eindeutig über die API aufgelöst werden.")
    parliament_id = matches[0]["id"]
    for page in client.iter_pages("parliament-periods", {"parliament": parliament_id}):
        for item in page.items:
            if (item.get("parliament") or {}).get("id") != parliament_id:
                raise ValueError("API lieferte eine Periode eines anderen Parlaments.")
            database.save_entity("parliament-periods", item, page.source_url, page.fetched_at)


def resolve_period(database: Database, request: ComparisonRequest) -> dict[str, Any]:
    candidates = []
    for period in local_entities(database, "parliament-periods"):
        parliament = period.get("parliament") or {}
        start = str(period.get("start_date_period") or "")[:4]
        end = str(period.get("end_date_period") or "")[:4]
        if (
            period.get("type") == "legislature"
            and normalize(parliament.get("label", "")) == normalize(request.parliament)
            and start == str(request.start_year)
            and end == str(request.end_year)
        ):
            candidates.append(period)
    if len(candidates) != 1:
        raise ValueError(
            "Wahlperiode nicht eindeutig lokal vorhanden. --online verwenden oder "
            "zunächst periods/sync-period ausführen. Es wird keine andere Periode geraten."
        )
    return candidates[0]


def resolve_targets(
    database: Database,
    period: dict[str, Any],
    party: str,
    program_id: int | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    election_id = (period.get("previous_period") or {}).get("id")
    elections = [
        item
        for item in local_entities(database, "parliament-periods")
        if item["id"] == election_id
        and item.get("type") == "election"
        and (item.get("parliament") or {}).get("id") == (period.get("parliament") or {}).get("id")
    ]
    if len(elections) != 1:
        raise ValueError("Zugehörige Wahl nicht geprüft vorhanden; Legislatur zuerst importieren.")
    programs = [
        item
        for item in local_entities(database, "election-program")
        if (item.get("parliament_period") or {}).get("id") == election_id
        and party in party_keys((item.get("party") or {}).get("label", ""))
        and (program_id is None or item["id"] == program_id)
    ]
    fractions = []
    for item in local_entities(database, "fractions"):
        if (item.get("legislature") or {}).get("id") != period["id"]:
            continue
        name = item.get("short_name") or item["label"].split(" (")[0]
        if party in party_keys(name):
            fractions.append(item)
    if len(programs) != 1:
        options = ", ".join(f"{item['id']}: {item['label']}" for item in programs) or "keine"
        raise ValueError(
            f"Programm nicht eindeutig. Passende Programme: {options}. "
            "Bei mehreren Treffern --program-id verwenden."
        )
    if len(fractions) != 1:
        raise ValueError("Fraktion der angefragten Legislatur ist nicht eindeutig vorhanden.")
    return programs[0], fractions[0]
