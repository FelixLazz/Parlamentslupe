"""Relevanzgesteuerte Auswahl: alle Poll-Metadaten nutzen, Stimmen gezielt laden."""

from typing import Any

from partei_hack.services.matching import PassageMatcher
from partei_hack.services.queries import vote_summary
from partei_hack.services.requests import local_entities
from partei_hack.storage.database import Database


def rank_polls_for_program(
    database: Database,
    period_id: int,
    document: dict[str, Any],
) -> list[dict[str, Any]]:
    """Poll-Metadaten gegen das Programm ranken, ohne eine Richtung zu behaupten."""
    matcher = PassageMatcher(document["pages"])
    polls = [
        poll
        for poll in local_entities(database, "polls")
        if (poll.get("field_legislature") or {}).get("id") == period_id
    ]
    ranking = []
    for poll in polls:
        matches = matcher.match(poll, limit=1)
        if not matches:
            continue
        top = matches[0]
        summary = vote_summary(database, poll["id"])
        ranking.append(
            {
                "poll_id": poll["id"],
                "label": poll["label"],
                "date": poll.get("field_poll_date"),
                "api_accepted": poll.get("field_accepted")
                if isinstance(poll.get("field_accepted"), bool)
                else None,
                "score": top["lexical_score"],
                "title_stem_matches": len(top["matched_title_stems"]),
                "matched_terms": top["matched_terms"],
                "matched_concepts": top["matched_concepts"],
                "page": top["page"],
                "quote": top["quote"],
                "review_flags": top["review_flags"],
                "votes_complete": summary["complete_against_api"],
                "local_votes": summary["local_votes"],
                "selection_method": "program_relevance_bm25_not_political_direction",
            }
        )
    ranking.sort(
        key=lambda item: (
            -item["title_stem_matches"],
            -item["score"],
            item["date"] or "",
            item["poll_id"],
        )
    )
    return ranking


def relevant_poll_ids(
    ranking: list[dict[str, Any]], limit: int, *, skip_complete: bool = True
) -> list[int]:
    if not 1 <= limit <= 50:
        raise ValueError("Relevanzauswahl: 1 bis 50 Polls erlaubt.")
    candidates = (
        [item for item in ranking if not item["votes_complete"]] if skip_complete else ranking
    )
    if not candidates:
        candidates = ranking
    return [item["poll_id"] for item in candidates[:limit]]
