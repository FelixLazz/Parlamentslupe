"""Getrennte Qualitätsdimensionen statt eines irreführenden Gesamtscores."""

from collections import Counter
from datetime import date
from typing import Any

from partei_hack.services.queries import list_votes
from partei_hack.services.requests import normalize


def valid_date(value: Any) -> str | None:
    try:
        return date.fromisoformat(value).isoformat() if isinstance(value, str) else None
    except ValueError:
        return None


def vote_diagnostics(
    database: Any,
    period: dict[str, Any],
    poll: dict[str, Any],
    fraction_id: int,
    mandates: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    votes = list_votes(database, poll["id"])
    selected = [item for item in votes if item["fraction_id"] == fraction_id]
    counts = Counter(item["vote"] for item in selected)
    decisive = counts["yes"] + counts["no"]
    total = len(selected)
    majority = (
        "yes" if counts["yes"] > counts["no"] else "no" if counts["no"] > counts["yes"] else None
    )
    issues: list[dict[str, Any]] = []
    poll_date = valid_date(poll.get("field_poll_date"))
    start = valid_date(period.get("start_date_period"))
    end = valid_date(period.get("end_date_period"))
    if not poll_date:
        issues.append({"code": "poll_date_missing_or_invalid", "blocking": True})
    elif (start and poll_date < start) or (end and poll_date > end):
        issues.append({"code": "poll_outside_legislature", "blocking": True})
    mandate_counts = Counter(item["mandate_id"] for item in votes if item["mandate_id"])
    for mandate_id, count in mandate_counts.items():
        if count > 1:
            issues.append(
                {
                    "code": "duplicate_mandate_votes",
                    "mandate_id": mandate_id,
                    "count": count,
                    "blocking": True,
                }
            )
    membership_checked = 0
    membership_unknown = 0
    for vote in votes:
        mandate = mandates.get(vote["mandate_id"])
        if mandate is None:
            issues.append(
                {
                    "code": "missing_mandate",
                    "vote_id": vote["id"],
                    "blocking": True,
                }
            )
            continue
        if (mandate.get("parliament_period") or {}).get("id") != period["id"]:
            issues.append(
                {
                    "code": "mandate_other_legislature",
                    "vote_id": vote["id"],
                    "blocking": True,
                }
            )
        mandate_start = valid_date(mandate.get("start_date")) or start
        mandate_end = valid_date(mandate.get("end_date")) or end
        if poll_date and (
            (mandate_start and poll_date < mandate_start)
            or (mandate_end and poll_date > mandate_end)
        ):
            issues.append(
                {
                    "code": "vote_outside_mandate",
                    "vote_id": vote["id"],
                    "blocking": True,
                }
            )
        memberships = mandate.get("fraction_membership") or []
        if isinstance(memberships, dict):
            memberships = [memberships]
        if not memberships or not poll_date:
            membership_unknown += 1
            continue
        active_ids = []
        checkable = True
        covered = False
        for membership in memberships:
            since = valid_date(membership.get("valid_from")) or mandate_start
            until = valid_date(membership.get("valid_until")) or mandate_end
            if not since or not until:
                checkable = False
                continue
            if since <= poll_date <= until:
                covered = True
                active_ids.append((membership.get("fraction") or {}).get("id"))
        if not checkable or not covered:
            # Keine Angabe deckt das Abstimmungsdatum ab. Das kann an einer
            # unvollständigen Historie liegen (die API liefert bei
            # Fraktionswechslern teils nur den neuesten Eintrag) und ist
            # deshalb kein bewiesener Widerspruch.
            membership_unknown += 1
        else:
            membership_checked += 1
            if vote["fraction_id"] not in active_ids:
                issues.append(
                    {
                        "code": "fraction_history_mismatch",
                        "vote_id": vote["id"],
                        "blocking": True,
                    }
                )
            elif len(set(active_ids)) > 1:
                issues.append(
                    {
                        "code": "overlapping_membership_intervals",
                        "vote_id": vote["id"],
                        "blocking": False,
                    }
                )
    unknown = sum(
        count
        for key, count in counts.items()
        if key
        not in {
            "yes",
            "no",
            "abstain",
            "no_show",
        }
    )
    if unknown:
        issues.append({"code": "unknown_vote_values", "count": unknown, "blocking": True})
    return {
        "selected_fraction_events": total,
        "decisive_votes": decisive,
        "majority_vote_among_yes_no": majority,
        "yes_share_of_yes_no": round(counts["yes"] / decisive, 4) if decisive else None,
        "decisive_share_of_recorded_members": round(decisive / total, 4) if total else None,
        "majority_share_of_recorded_members": (
            round(max(counts["yes"], counts["no"]) / total, 4) if total and majority else None
        ),
        "participation_share_of_recorded_members": (
            round((decisive + counts["abstain"]) / total, 4) if total else None
        ),
        "denominators": {
            "direction": "yes + no",
            "participation": "recorded fraction vote entries including no_show; not inferred seats",
        },
        "dissenting_votes": [
            {key: item[key] for key in ("id", "mandate_id", "politician_id", "politician", "vote")}
            for item in selected
            if majority and item["vote"] in {"yes", "no"} and item["vote"] != majority
        ],
        "nonparticipation_reasons": dict(
            Counter(
                item["reason_no_show"] or "unspecified"
                for item in selected
                if item["vote"] == "no_show"
            )
        ),
        "membership_history_checked": membership_checked,
        "membership_history_uncheckable": membership_unknown,
        "issues": issues,
        "blocking_issue_count": sum(issue["blocking"] for issue in issues),
    }


def procedural_context(poll: dict[str, Any]) -> dict[str, Any]:
    title = normalize(poll["label"])
    text = normalize(poll.get("field_intro") or "")
    accepted = poll.get("field_accepted")
    accepted_known = isinstance(accepted, bool)
    kind = next(
        (
            kind
            for marker, kind in (
                ("aenderungsantrag", "amendment"),
                ("entschliessungsantrag", "resolution"),
                ("gesetzentwurf", "bill"),
                ("antrag", "motion"),
            )
            if marker in title
        ),
        "unspecified",
    )
    flags = []
    if kind == "amendment":
        flags.append("amendment_not_final_law")
    if kind == "resolution":
        flags.append("resolution_not_implementation")
    if any(word in title for word in ("abschaffung", "aufhebung", "verhindern", "streichen")):
        flags.append("reverse_direction_possible")
    if any(
        phrase in text
        for phrase in (
            "ebenfalls namentlich",
            "im kontext der abstimmung",
            "aenderungsantrag",
        )
    ):
        flags.append("description_may_cover_multiple_votes")
    if any(phrase in text for phrase in ("geandert", "geaendert", "ausschussfassung")):
        flags.append("amended_version_must_be_identified")
    if not accepted_known:
        flags.append("api_outcome_unknown")
    return {
        "motion_kind_hint": kind,
        "api_accepted": accepted if accepted_known else None,
        "outcome_source": (
            "abgeordnetenwatch field_accepted" if accepted_known else "not_available"
        ),
        "outcome_is_not_implementation": True,
        "flags": flags,
        "adoption_is_not_implementation": True,
        "binding_version_verified": False,
    }


def review_summary(promises: list[dict[str, Any]]) -> dict[str, Any]:
    tallies = Counter()
    cases = []
    for promise in promises:
        groups: dict[str, list[str]] = {}
        for comparison in promise["comparisons"]:
            key = comparison.get("procedure_id") or f"poll:{comparison['poll_id']}"
            result = comparison["direction_comparison"]["result"]
            if comparison.get("relationship") == "mixed":
                result = "mixed"
            elif comparison.get("relationship") not in {"direct", "partial"}:
                result = "not_assessable"
            elif comparison.get("relationship") == "partial" and result in {
                "majority_aligned",
                "majority_opposed",
            }:
                result = "partial"
            groups.setdefault(key, []).append(result)
        results = []
        for key, values in groups.items():
            known = set(values)
            result = (
                "mixed"
                if "mixed" in known or {"majority_aligned", "majority_opposed"} <= known
                else "insufficient_data"
                if "insufficient_data" in known
                else "not_assessable"
                if "not_assessable" in known
                else "partial"
                if "partial" in known
                else "split"
                if "split" in known
                else "majority_aligned"
                if "majority_aligned" in known
                else "majority_opposed"
                if "majority_opposed" in known
                else "not_assessable"
            )
            results.append(result)
            cases.append(
                {
                    "promise_id": promise["id"],
                    "procedure_key": key,
                    "poll_comparisons": len(values),
                    "result_counts": dict(Counter(values)),
                    "result": result,
                }
            )
        if "mixed" in results or ("majority_aligned" in results and "majority_opposed" in results):
            category = "mixed"
        elif "insufficient_data" in results:
            category = "insufficient_data"
        elif "not_assessable" in results:
            category = "not_assessable"
        elif "partial" in results:
            category = "partial_relationship_only"
        elif "split" in results:
            category = "split_in_reviewed_cases"
        elif results and all(value == "majority_aligned" for value in results):
            category = "aligned_in_reviewed_cases"
        elif results and all(value == "majority_opposed" for value in results):
            category = "opposed_in_reviewed_cases"
        else:
            category = "not_assessable"
        tallies[category] += 1
    return {
        "reviewed_promises": len(promises),
        "promises_with_reviewed_links": sum(bool(item["comparisons"]) for item in promises),
        "promises_without_reviewed_links": sum(not item["comparisons"] for item in promises),
        "poll_comparisons": sum(len(item["comparisons"]) for item in promises),
        "procedure_cases": len(cases),
        "categories": dict(tallies),
        "cases": cases,
        "grouping": "explicit procedure_id only; otherwise separate poll, no overall score",
        "unit": "each promise once; not a representative sample of all election promises",
        "fulfillment": "not_assessed",
    }
