"""Explizit nutzergeprüfte Versprechen und Richtungszuordnungen mit Originalbelegen."""

from datetime import date
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StrictInt

from partei_hack.services.programs import clean_text

Nonempty = Annotated[str, Field(min_length=3)]


class ReviewedLink(BaseModel):
    model_config = ConfigDict(extra="forbid")

    poll_id: Annotated[StrictInt, Field(gt=0)]
    aligned_vote: Literal["yes", "no"]
    rationale: Annotated[str, Field(min_length=20)]
    source_url: HttpUrl
    reviewed_by: Nonempty
    reviewed_at: date
    procedure_id: Nonempty | None = None
    relationship: Literal["direct", "partial", "mixed", "unclear", "unspecified"] = "unspecified"
    conditions_checked: bool | None = None
    package_reviewed: bool | None = None
    second_reviewer: Nonempty | None = None
    counter_sources: list[HttpUrl] = Field(default_factory=list)


class Promise(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: Nonempty
    title: Nonempty
    page: Annotated[StrictInt, Field(gt=0)]
    quote: Annotated[str, Field(min_length=30)]
    links: list[ReviewedLink] = Field(default_factory=list)


class PromiseFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    program_id: Annotated[StrictInt, Field(gt=0)]
    document_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    promises: list[Promise]


def load_promises(path: Path, document: dict[str, Any]) -> PromiseFile:
    data = PromiseFile.model_validate_json(path.read_text(encoding="utf-8"))
    if data.program_id != document["program_id"] or data.document_sha256 != document["sha256"]:
        raise ValueError("Versprechendatei gehört nicht zu dieser Programmversion/Prüfsumme.")
    pages = {page["number"]: page["text"] for page in document["pages"]}
    seen = set()
    for promise in data.promises:
        if promise.id in seen:
            raise ValueError(f"Doppelte Versprechen-ID: {promise.id}")
        seen.add(promise.id)
        if promise.page not in pages or clean_text(promise.quote) not in pages[promise.page]:
            raise ValueError(
                f"Zitat von {promise.id} ist auf PDF-Seite {promise.page} nicht nachweisbar."
            )
        poll_ids = [link.poll_id for link in promise.links]
        if len(poll_ids) != len(set(poll_ids)):
            raise ValueError(f"Doppelte Abstimmungszuordnung bei {promise.id}.")
        if any(link.reviewed_at > date.today() for link in promise.links):
            raise ValueError("Ein Prüfdatum darf nicht in der Zukunft liegen.")
    return data


def compare_direction(
    counts: dict[str, int], aligned_vote: str, *, complete: bool
) -> dict[str, Any]:
    """Nur Stimmrichtung vergleichen, ausdrücklich keine Umsetzung/Erfüllung bewerten."""
    opposite = "no" if aligned_vote == "yes" else "yes"
    aligned = counts.get(aligned_vote, 0)
    opposed = counts.get(opposite, 0)
    decisive = aligned + opposed
    recorded = sum(counts.values())
    participating = decisive + counts.get("abstain", 0)
    if not complete or counts.get("unknown", 0):
        result = "insufficient_data"
    elif decisive == 0:
        result = "not_assessable"
    elif aligned == opposed:
        result = "split"
    elif aligned > opposed:
        result = "majority_aligned"
    else:
        result = "majority_opposed"
    return {
        "result": result,
        "aligned_vote": aligned_vote,
        "aligned": aligned,
        "opposed": opposed,
        "abstain": counts.get("abstain", 0),
        "no_show": counts.get("no_show", 0),
        "unknown": counts.get("unknown", 0),
        "aligned_share_of_yes_no": round(aligned / decisive, 4) if decisive else None,
        "decisive_votes": decisive,
        "recorded_votes": recorded,
        "aligned_share_of_recorded_votes": round(aligned / recorded, 4) if recorded else None,
        "participating_votes": participating,
        "participation_share_of_recorded_votes": (
            round(participating / recorded, 4) if recorded else None
        ),
        "shares_scope": "observed_entries_only; completeness_and_integrity_via_result",
        "denominator": "yes + no; Enthaltung und Nichtteilnahme separat",
        "fulfillment": "not_assessed",
    }


def promise_template(report: dict[str, Any]) -> dict[str, Any]:
    """Zitate vorfüllen, aber niemals menschliche Richtungsprüfung fingieren."""
    candidates = {}
    for poll in report["polls"]:
        for passage in poll["program_matches"]:
            if passage["kind"] == "promise_candidate":
                candidates.setdefault(
                    (passage["page"], passage["quote"]),
                    {
                        "id": f"pruefen-{len(candidates) + 1}",
                        "title": "Ungeprüfter Kandidat – bitte konkret benennen",
                        "page": passage["page"],
                        "quote": passage["quote"],
                        "links": [],
                    },
                )
    return {
        "schema_version": 1,
        "program_id": report["program"]["id"],
        "document_sha256": report["program"]["sha256"],
        "promises": list(candidates.values()),
    }
