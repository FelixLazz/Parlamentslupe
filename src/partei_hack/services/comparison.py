"""Belegte Gegenüberstellung einer Legislaturfraktion mit einem Wahlprogramm."""

import hashlib
from dataclasses import asdict
from pathlib import Path
from typing import Any

from partei_hack import __version__
from partei_hack.services.evidence import crosscheck_counts, evidence_for_poll, source_links
from partei_hack.services.language import statement_features
from partei_hack.services.matching import PassageMatcher, plain_text
from partei_hack.services.promises import compare_direction, load_promises
from partei_hack.services.quality import procedural_context, review_summary, vote_diagnostics
from partei_hack.services.queries import poll_coverage, vote_summary
from partei_hack.services.requests import (
    ComparisonRequest,
    local_entities,
    party_keys,
    resolve_targets,
)
from partei_hack.storage.database import Database, utc_now


def build_comparison(
    database: Database,
    request: ComparisonRequest,
    period: dict[str, Any],
    program: dict[str, Any],
    fraction: dict[str, Any],
    document: dict[str, Any],
    *,
    promises_file: Path | None = None,
    matches_per_poll: int = 3,
    only_with_votes: bool = False,
) -> dict[str, Any]:
    if not 1 <= matches_per_poll <= 10:
        raise ValueError("Pro Abstimmung sind 1 bis 10 Texttreffer erlaubt.")
    verified_program, verified_fraction = resolve_targets(
        database, period, request.party, program["id"]
    )
    if (
        verified_program["id"] != document["program_id"]
        or verified_fraction["id"] != fraction["id"]
    ):
        raise ValueError("Programm oder Fraktion passt nicht zur Anfrage.")
    return build_selected_comparison(
        database,
        period,
        program,
        fraction,
        document,
        request=asdict(request),
        promises_file=promises_file,
        matches_per_poll=matches_per_poll,
        only_with_votes=only_with_votes,
    )


def build_selected_comparison(
    database: Database,
    period: dict[str, Any],
    program: dict[str, Any],
    fraction: dict[str, Any],
    document: dict[str, Any],
    *,
    request: dict[str, Any] | None = None,
    promises_file: Path | None = None,
    matches_per_poll: int = 3,
    only_with_votes: bool = False,
    poll_ids: list[int] | None = None,
) -> dict[str, Any]:
    """Explizite Auswahl ohne Freitext-/Parteialias-Beschränkung, auch für Landtage."""
    if not 1 <= matches_per_poll <= 10:
        raise ValueError("Pro Abstimmung sind 1 bis 10 Texttreffer erlaubt.")
    election_id = (period.get("previous_period") or {}).get("id")
    election = next(
        (
            item
            for item in local_entities(database, "parliament-periods")
            if item["id"] == election_id and item.get("type") == "election"
        ),
        None,
    )
    if (
        period.get("type") != "legislature"
        or election is None
        or not (period.get("parliament") or {}).get("id")
        or (election.get("parliament") or {}).get("id")
        != (period.get("parliament") or {}).get("id")
        or (program.get("parliament_period") or {}).get("id") != election_id
        or (fraction.get("legislature") or {}).get("id") != period["id"]
        or document.get("program_id") != program["id"]
        or document.get("election_id") != election_id
        or document.get("party_id") != (program.get("party") or {}).get("id")
    ):
        raise ValueError("Programm, Dokument, Wahl oder Fraktion passt nicht zur Legislatur.")
    matcher = PassageMatcher(document["pages"])
    mandates = {item["id"]: item for item in local_entities(database, "candidacies-mandates")}
    topic_catalog = {item["id"]: item for item in local_entities(database, "topics")}
    committee_catalog = {item["id"]: item for item in local_entities(database, "committees")}
    all_polls = [
        item
        for item in local_entities(database, "polls")
        if (item.get("field_legislature") or {}).get("id") == period["id"]
    ]
    all_polls.sort(key=lambda item: (item.get("field_poll_date") or "", item["id"]))
    if poll_ids is not None:
        if not poll_ids or len(set(poll_ids)) != len(poll_ids):
            raise ValueError("Abstimmungsauswahl muss eindeutig und nicht leer sein.")
        if not set(poll_ids) <= {poll["id"] for poll in all_polls}:
            raise ValueError("Abstimmung gehört nicht zur ausgewählten Wahlperiode.")
    summaries = {poll["id"]: vote_summary(database, poll["id"]) for poll in all_polls}
    polls = [
        poll
        for poll in all_polls
        if (poll_ids is None or poll["id"] in poll_ids)
        and (not only_with_votes or summaries[poll["id"]]["local_votes"] > 0)
    ]
    coverage = poll_coverage(database, period["id"], [poll["id"] for poll in all_polls])
    available = coverage["available_api_polls"]
    polls_complete = coverage["poll_list_complete_against_api"]
    complete_votes = sum(summary["complete_against_api"] for summary in summaries.values())
    result_polls = []
    totals = dict.fromkeys(("yes", "no", "abstain", "no_show", "unknown"), 0)
    for poll in polls:
        summary = summaries[poll["id"]]
        group = next(
            (item for item in summary["fractions"] if item["fraction_id"] == fraction["id"]), {}
        )
        counts = {key: group.get(key, 0) for key in totals}
        for key in totals:
            totals[key] += counts[key]
        diagnostics = vote_diagnostics(database, period, poll, fraction["id"], mandates)
        sources, source_errors = evidence_for_poll(database, poll["id"])
        all_counts = {
            key: sum(group.get(key, 0) for group in summary["fractions"]) for key in totals
        }
        crosscheck = crosscheck_counts(
            sources,
            poll,
            all_counts,
            fraction=fraction,
            fraction_counts=counts,
        )
        source_diagnostics = []
        for source in sources:
            source_diagnostics.append(
                {
                    key: source[key]
                    for key in (
                        "id",
                        "url",
                        "sha256",
                        "title",
                        "format",
                        "fetched_at",
                        "document_number",
                        "document_type_hint",
                        "association",
                    )
                }
            )
        source_context = " ".join(
            source["pages"][0]["text"][:1500]
            for source in sources
            if source["format"] == "pdf" and source["pages"]
        )
        topics = [topic_catalog.get(ref["id"], ref) for ref in poll.get("field_topics") or []]
        committee_refs = poll.get("field_committees") or []
        if isinstance(committee_refs, dict):
            committee_refs = [committee_refs]
        committees = [committee_catalog.get(ref["id"], ref) for ref in committee_refs]
        contextual_topics = list(topics)
        for committee in committees:
            contextual_topics.extend(committee.get("field_topics") or [])
        api_context = " ".join(
            plain_text(topic.get("description") or "")
            + " "
            + (topic.get("parent") or {}).get("label", "")
            for topic in topics
        )
        retrieval_poll = {
            **poll,
            "source_context": source_context,
            "api_context": api_context,
            "field_topics": contextual_topics,
            "field_committees": committees,
        }
        procedure = procedural_context(poll)
        quality = {
            "api_votes_complete": summary["complete_against_api"],
            "api_outcome": (
                "accepted"
                if procedure["api_accepted"] is True
                else "rejected"
                if procedure["api_accepted"] is False
                else "unknown"
            ),
            "data_integrity": (
                "issues_detected"
                if diagnostics["blocking_issue_count"]
                else "no_blocking_issue_found"
            ),
            "membership_history": (
                "partly_uncheckable" if diagnostics["membership_history_uncheckable"] else "checked"
            ),
            "official_aggregate_crosscheck": crosscheck["status"],
            "original_official_documents": len(sources),
            "source_integrity_errors": source_errors,
            "binding_vote_object_verified": False,
            "political_direction": "requires_explicit_review",
            "implementation": "not_assessed",
        }
        review_allowed = bool(
            summary["complete_against_api"]
            and diagnostics["blocking_issue_count"] == 0
            and crosscheck["status"] != "conflict"
            and not source_errors
        )
        result_polls.append(
            {
                "id": poll["id"],
                "title": poll["label"],
                "date": poll.get("field_poll_date"),
                "accepted": poll.get("field_accepted"),
                "source_url": poll.get("abgeordnetenwatch_url") or poll.get("api_url"),
                "description": plain_text(poll.get("field_intro") or ""),
                "related_links": poll.get("field_related_links") or [],
                "votes": counts,
                "fraction_votes": sum(counts.values()),
                "all_votes_complete_against_api": summary["complete_against_api"],
                "votes_checked_at": summary["checked_at"],
                "vote_id_set_verified": summary["identity_set_verified"],
                "program_matches": matcher.match(retrieval_poll, limit=matches_per_poll),
                "topics": topics,
                "committees": committees,
                "api_source_links": source_links(poll),
                "official_sources": source_diagnostics,
                "official_crosscheck": crosscheck,
                "procedure_context": procedure,
                "vote_diagnostics": diagnostics,
                "quality": quality,
                "direction_data_usable": review_allowed,
            }
        )
    reviewed = []
    if promises_file is not None:
        promise_file = load_promises(promises_file, document)
        poll_map = {poll["id"]: poll for poll in result_polls}
        for promise in promise_file.promises:
            comparisons = []
            for link in promise.links:
                if link.poll_id not in poll_map:
                    raise ValueError(
                        f"Geprüfte Zuordnung verweist auf nicht importierten Poll {link.poll_id}. "
                        "Passende Abstimmung importieren; es wird keine Bewertung ausgelassen."
                    )
                poll = poll_map[link.poll_id]
                comparisons.append(
                    {
                        **link.model_dump(mode="json"),
                        "review_status": "user_reviewed_not_independently_verified",
                        "direction_comparison": compare_direction(
                            poll["votes"],
                            link.aligned_vote,
                            complete=poll["direction_data_usable"],
                        ),
                        "remaining_checks": [
                            check
                            for check, unresolved in (
                                ("relationship_not_explicit", link.relationship == "unspecified"),
                                ("conditions_not_confirmed", link.conditions_checked is not True),
                                ("package_not_confirmed", link.package_reviewed is not True),
                                ("no_second_reviewer", not link.second_reviewer),
                                ("data_integrity_block", not poll["direction_data_usable"]),
                            )
                            if unresolved
                        ],
                    }
                )
            reviewed.append(
                {
                    **promise.model_dump(mode="json", exclude={"links"}),
                    "comparisons": comparisons,
                    "fulfillment": "not_assessed",
                }
            )
    warnings = [
        "Fraktionsverhalten ist nicht identisch mit historischer Parteimitgliedschaft.",
        "Texttreffer nutzen BM25, deutsche Wortstämme und Suchkonzepte; keine Logikprüfung.",
        "Ohne explizite Richtungsprüfung wird kein Widerspruch oder Einklang behauptet.",
        "Keine Aussage zur tatsächlichen Umsetzung oder Erfüllung eines Wahlversprechens.",
        "API-Ergebnis (angenommen/abgelehnt) belegt nicht die Umsetzung eines Versprechens.",
        "PDF-Seitenzählung beginnt bei 1 und kann von gedruckten Seitenzahlen abweichen.",
        "Auch vollständige API-Daten sind nicht gegen alle amtlichen Abstimmungen geprüft.",
    ]
    if party_keys((program.get("party") or {}).get("label", "")) & {"cdu", "csu"} and party_keys(
        fraction.get("short_name") or fraction["label"]
    ) & {"cdu", "csu"}:
        warnings.append("CDU/CSU-Fraktion gemeinsam; Programm nur der ausgewählten Partei.")
    if request is None:
        warnings.append(
            "Programmpartei und Fraktion wurden unabhängig ausdrücklich ausgewählt. "
            "Eine historische Parteizugehörigkeit wird daraus nicht abgeleitet."
        )
    if not polls:
        warnings.insert(0, "Keine lokalen Abstimmungen. Für einen Vergleich Abstimmungen laden.")
    if not polls_complete:
        warnings.insert(
            0, "STICHPROBE: Die lokale Abstimmungsliste ist nicht als vollständig belegt."
        )
    if complete_votes < len(polls):
        warnings.insert(
            0, "Einzelstimmen fehlen oder sind nicht für alle Abstimmungen vollständig."
        )
    if document["origin"] == "local_file":
        warnings.append(
            "Lokale PDF zugeordnet; Identität mit der verlinkten API-Datei nicht verifiziert."
        )
    candidate_inventory = []
    for passage in matcher.passages:
        if passage["kind"] != "promise_candidate":
            continue
        matched_polls = [
            poll["id"]
            for poll in result_polls
            if any(
                match["page"] == passage["page"] and match["quote"] == passage["quote"]
                for match in poll["program_matches"]
            )
        ]
        candidate_inventory.append(
            {
                "candidate_id": hashlib.sha256(
                    f"{document['sha256']}:{passage['page']}:{passage['quote']}".encode()
                ).hexdigest()[:20],
                "page": passage["page"],
                "quote": passage["quote"],
                "context_before": passage["context_before"],
                "context_after": passage["context_after"],
                "context_features": statement_features(
                    passage["context_before"] + " " + passage["context_after"]
                ),
                "statement_features": passage["statement_features"],
                "matched_poll_ids": matched_polls,
                "status": "unreviewed",
                "meaning_of_no_match": "not_found_in_local_top_matches_not_a_broken_promise",
            }
        )
    program_analysis = {
        "method": "lexical-statement-inventory-v1",
        "pdf_pages": len(document["pages"]),
        "pages_with_text": sum(bool(page["text"].strip()) for page in document["pages"]),
        "pages_without_text": [
            page["number"] for page in document["pages"] if not page["text"].strip()
        ],
        "indexed_passages": len(matcher.passages),
        "candidate_count": len(candidate_inventory),
        "candidate_feature_counts": {
            feature: sum(bool(item["statement_features"][feature]) for item in candidate_inventory)
            for feature in ("quantities", "years", "conditions", "negations")
        },
        "candidates_with_context_conditions": sum(
            bool(item["context_features"]["conditions"]) for item in candidate_inventory
        ),
        "candidates_with_top_matches": sum(
            bool(item["matched_poll_ids"]) for item in candidate_inventory
        ),
        "retrieval_scope": "top_matches_of_reported_polls_only",
        "review_status": "unreviewed",
        "fulfillment": "not_assessed",
    }
    quality_summary = {
        "polls_with_blocking_data_issues": sum(
            poll["vote_diagnostics"]["blocking_issue_count"] > 0 for poll in result_polls
        ),
        "polls_with_official_sources": sum(bool(poll["official_sources"]) for poll in result_polls),
        "polls_with_matching_official_aggregates": sum(
            poll["official_crosscheck"]["status"] == "aggregate_counts_match"
            for poll in result_polls
        ),
        "polls_with_official_conflicts": sum(
            poll["official_crosscheck"]["status"] == "conflict" for poll in result_polls
        ),
        "polls_with_uncheckable_membership_history": sum(
            poll["quality"]["membership_history"] == "partly_uncheckable" for poll in result_polls
        ),
        "polls_accepted_by_api": sum(
            poll["quality"]["api_outcome"] == "accepted" for poll in result_polls
        ),
        "polls_rejected_by_api": sum(
            poll["quality"]["api_outcome"] == "rejected" for poll in result_polls
        ),
        "polls_outcome_unknown": sum(
            poll["quality"]["api_outcome"] == "unknown" for poll in result_polls
        ),
        "promise_candidates": len(candidate_inventory),
        "candidates_without_retrieved_poll": sum(
            not candidate["matched_poll_ids"] for candidate in candidate_inventory
        ),
        "unreviewed_candidates_are_not_a_valid_score_denominator": True,
        "overall_score": None,
    }
    return {
        "schema_version": 1,
        "method_version": "bm25-context-evidence-v3",
        "application_version": __version__,
        "generated_at": utc_now(),
        "request": request
        or {
            "parliament": period["parliament"].get("label"),
            "period_id": period["id"],
            "fraction_id": fraction["id"],
            "program_id": program["id"],
            "party": (program.get("party") or {}).get("label"),
            "selection_mode": "explicit_independent",
        },
        "period": {
            "id": period["id"],
            "label": period["label"],
            "start": period.get("start_date_period"),
            "end": period.get("end_date_period"),
        },
        "fraction": {"id": fraction["id"], "label": fraction["label"]},
        "program": {
            "id": program["id"],
            "label": program["label"],
            "party": program.get("party"),
            "election_id": document["election_id"],
            "sha256": document["sha256"],
            "source_url": document["source_url"],
            "origin": document["origin"],
            "imported_at": document["imported_at"],
            "pdf_path": document["pdf_path"],
            "pdf_pages": len(document["pages"]),
        },
        "coverage": {
            "local_polls": len(all_polls),
            "reported_polls": len(result_polls),
            "polls_with_local_votes": sum(
                summary["local_votes"] > 0 for summary in summaries.values()
            ),
            "available_api_polls": available,
            "poll_list_complete_against_api": polls_complete,
            "polls_with_complete_votes": complete_votes,
            "complete_against_api": polls_complete and complete_votes == len(all_polls),
            "poll_id_set_verified": coverage["identity_set_verified"],
            "polls_with_verified_vote_id_sets": sum(
                summary["identity_set_verified"] is True for summary in summaries.values()
            ),
        },
        "report_scope": {
            **({"poll_ids": sorted(poll_ids)} if poll_ids is not None else {}),
            "only_with_votes": only_with_votes,
            "reported_polls": len(result_polls),
            "local_polls": len(all_polls),
        },
        "vote_totals": totals,
        "vote_totals_unit": (
            "Stimmereignisse über lokale Polls, keine Anzahl verschiedener Personen"
        ),
        "program_passages_indexed": len(matcher.passages),
        "polls_with_text_matches": sum(bool(poll["program_matches"]) for poll in result_polls),
        "warnings": warnings,
        "polls": result_polls,
        "reviewed_promises": reviewed,
        "reviewed_summary": review_summary(reviewed),
        "promise_candidates": candidate_inventory,
        "program_analysis": program_analysis,
        "quality_summary": quality_summary,
        "fulfillment": "not_assessed",
    }
