"""Datenkonsistenz, explizite Nenner und begrenzte Aussagekraft prüfen."""

from copy import deepcopy

import pytest

from partei_hack.services.importer import Importer
from partei_hack.services.quality import procedural_context, review_summary, vote_diagnostics
from partei_hack.services.queries import poll_coverage, vote_summary
from partei_hack.storage.database import utc_now


def context(database, dataset):
    for resource, items in dataset.items():
        database.save_entities(resource, items, "synthetic", utc_now())
    period = {
        **dataset["parliament-periods"][0],
        "start_date_period": "2021-01-01",
        "end_date_period": "2025-12-31",
    }
    mandates = {item["id"]: deepcopy(item) for item in dataset["candidacies-mandates"]}
    return period, dataset["polls"][0], mandates


def test_absence_not_dissent_and_missing_membership_not_invented(database, dataset):
    period, poll, mandates = context(database, dataset)
    result = vote_diagnostics(database, period, poll, 9031, mandates)
    assert result["decisive_votes"] == 0
    assert result["dissenting_votes"] == []
    assert result["yes_share_of_yes_no"] is None
    assert result["membership_history_uncheckable"] == 1
    assert result["blocking_issue_count"] == 0


def test_duplicate_mandate_vote_and_wrong_timeline_block(database, dataset):
    period, poll, mandates = context(database, dataset)
    duplicate = {**dataset["votes"][0], "id": 99999}
    database.save_entity("votes", duplicate, "synthetic", utc_now())
    mandates[9011]["end_date"] = "2023-01-01"
    result = vote_diagnostics(database, period, poll, 9031, mandates)
    codes = {issue["code"] for issue in result["issues"] if issue["blocking"]}
    assert "duplicate_mandate_votes" in codes
    assert "vote_outside_mandate" in codes


def test_membership_starting_after_poll_is_uncheckable_not_a_mismatch(database, dataset):
    period, poll, mandates = context(database, dataset)
    mandates[9011]["fraction_membership"] = [
        {
            "fraction": {"id": 320},
            "valid_from": "2024-07-09",
            "valid_until": "2025-12-31",
        }
    ]
    result = vote_diagnostics(database, period, poll, 9031, mandates)
    assert result["membership_history_checked"] == 0
    assert result["membership_history_uncheckable"] == 1
    assert not any(issue["code"] == "fraction_history_mismatch" for issue in result["issues"])
    assert result["blocking_issue_count"] == 0


def test_current_fraction_cannot_replace_historical_membership(database, dataset):
    period, poll, mandates = context(database, dataset)
    mandates[9011]["fraction_membership"] = [
        {
            "fraction": {"id": 9999},
            "valid_from": "2021-01-01",
            "valid_until": "2025-12-31",
        }
    ]
    result = vote_diagnostics(database, period, poll, 9031, mandates)
    assert result["membership_history_checked"] == 1
    assert any(issue["code"] == "fraction_history_mismatch" for issue in result["issues"])


def test_procedural_context_uses_api_outcome_without_claiming_implementation(dataset):
    accepted = procedural_context(dataset["polls"][1])
    assert accepted["api_accepted"] is True
    assert accepted["outcome_source"] == "abgeordnetenwatch field_accepted"
    assert accepted["outcome_is_not_implementation"] is True
    assert "api_outcome_unknown" not in accepted["flags"]

    rejected = procedural_context(dataset["polls"][0])
    assert rejected["api_accepted"] is False

    unknown = dict(dataset["polls"][0])
    unknown.pop("field_accepted")
    missing = procedural_context(unknown)
    assert missing["api_accepted"] is None
    assert missing["outcome_source"] == "not_available"
    assert "api_outcome_unknown" in missing["flags"]


def test_same_count_with_wrong_vote_identity_is_not_complete(database, dataset_client):
    client, _ = dataset_client
    Importer(client, database).sync_period(9001, max_polls=1, with_votes=True)
    assert vote_summary(database, 9041)["identity_set_verified"] is True
    database.connection.execute("UPDATE entities SET entity_id=9999 WHERE resource='votes'")
    # Payload ebenfalls ändern: keine abweichenden IDs in zwei Repräsentationen verstecken.
    row = database.connection.execute(
        "SELECT payload FROM entities WHERE resource='votes'"
    ).fetchone()
    import json

    payload = json.loads(row["payload"])
    payload["id"] = 9999
    database.connection.execute("DELETE FROM entities WHERE resource='votes'")
    database.connection.commit()
    database.save_entity("votes", payload, "synthetic", utc_now())
    assert vote_summary(database, 9041)["local_votes"] == 1
    assert vote_summary(database, 9041)["complete_against_api"] is False


def test_same_count_wrong_poll_identity_is_not_complete(database):
    run = database.start_import(9001, {})
    database.finish_import(run, {"polls_available": 1, "polls_complete": True, "poll_ids": [9041]})
    coverage = poll_coverage(database, 9001, [9999])
    assert coverage["poll_list_complete_against_api"] is False


def test_multiple_related_votes_are_flagged_not_merged():
    result = procedural_context(
        {
            "label": "Änderungsantrag zur Abschaffung einer Regel",
            "field_intro": "Ebenfalls namentlich wurde über ein anderes Gesetz abgestimmt.",
        }
    )
    assert result["motion_kind_hint"] == "amendment"
    assert "reverse_direction_possible" in result["flags"]
    assert "description_may_cover_multiple_votes" in result["flags"]
    assert result["binding_version_verified"] is False


def test_many_votes_do_not_count_as_many_promises():
    comparisons = [
        {
            "poll_id": poll,
            "procedure_id": "test-law",
            "relationship": "direct",
            "direction_comparison": {"result": "majority_aligned"},
        }
        for poll in (1, 2, 3)
    ]
    result = review_summary([{"id": "test-promise", "comparisons": comparisons}])
    assert result["reviewed_promises"] == 1
    assert len(result["cases"]) == 1
    assert result["cases"][0]["poll_comparisons"] == 3
    assert result["categories"]["aligned_in_reviewed_cases"] == 1
    assert result["fulfillment"] == "not_assessed"


def test_unspecified_or_mixed_relationship_is_not_program_support():
    result = review_summary(
        [
            {
                "id": "test",
                "comparisons": [
                    {
                        "poll_id": 1,
                        "relationship": "mixed",
                        "direction_comparison": {"result": "majority_aligned"},
                    }
                ],
            }
        ]
    )
    assert result["categories"] == {"mixed": 1}


def test_split_is_reported_as_split_not_unassessable():
    result = review_summary(
        [
            {
                "id": "test",
                "comparisons": [
                    {
                        "poll_id": 1,
                        "relationship": "direct",
                        "direction_comparison": {"result": "split"},
                    }
                ],
            }
        ]
    )
    assert result["categories"] == {"split_in_reviewed_cases": 1}
    assert result["cases"][0]["result"] == "split"


@pytest.mark.parametrize("same_procedure", [True, False])
@pytest.mark.parametrize("unresolved", ["not_assessable", "insufficient_data"])
def test_unresolved_comparison_remains_visible(same_procedure, unresolved):
    comparisons = [
        {
            "poll_id": number,
            "procedure_id": "test-law" if same_procedure else None,
            "relationship": "direct",
            "direction_comparison": {"result": result},
        }
        for number, result in enumerate(["majority_aligned", unresolved], start=1)
    ]
    result = review_summary([{"id": "promise", "comparisons": comparisons}])
    assert result["categories"] == {unresolved: 1}
    assert result["poll_comparisons"] == 2
    assert result["procedure_cases"] == (1 if same_procedure else 2)
    if same_procedure:
        assert result["cases"][0]["result_counts"] == {
            "majority_aligned": 1,
            unresolved: 1,
        }


def test_empty_review_links_are_counted_separately():
    result = review_summary([{"id": "candidate", "comparisons": []}])
    assert result["promises_with_reviewed_links"] == 0
    assert result["promises_without_reviewed_links"] == 1
    assert result["procedure_cases"] == 0
    assert result["categories"] == {"not_assessable": 1}


def test_vote_diagnostics_show_small_decisive_share(database, dataset):
    period, poll, mandates = context(database, dataset)
    vote = dataset["votes"][0]
    for number, value in enumerate(["yes", "no", "abstain", "no_show"], start=1):
        database.save_entity(
            "votes", {**vote, "id": 99000 + number, "vote": value}, "test", utc_now()
        )
    result = vote_diagnostics(database, period, poll, 9031, mandates)
    assert result["selected_fraction_events"] == 5  # plus existing no_show
    assert result["decisive_share_of_recorded_members"] == 0.4
    assert result["participation_share_of_recorded_members"] == 0.6
    assert result["majority_share_of_recorded_members"] is None  # tie
