import json

import pytest

from partei_hack.api.client import APIError
from partei_hack.services.importer import Importer
from partei_hack.services.queries import poll_coverage, project_status, vote_summary


def test_sample_import_is_explicit_and_loads_historical_mandates(database, dataset_client):
    client, requests = dataset_client
    stats = Importer(client, database).sync_period(9001, max_polls=1, with_votes=True)
    assert stats["polls"] == 1
    assert stats["polls_available"] == 2
    assert stats["polls_complete"] is False
    assert stats["programs"] == 1
    assert stats["votes"] == 1
    mandate_request = next(req for req in requests if "candidacies-mandates" in req.url.path)
    assert mandate_request.url.params["current_on"] == "all"
    assert vote_summary(database, 9041)["complete_against_api"] is True
    assert vote_summary(database, 9042)["complete_against_api"] is False
    assert not any("invalid.example" in str(req.url) for req in requests)


def test_full_import_and_reimport_are_idempotent(database, dataset_client):
    client, _ = dataset_client
    importer = Importer(client, database)
    stats = importer.sync_period(9001, max_polls=None, with_votes=True)
    assert stats["polls_complete"] is True
    counts = project_status(database)["entity_counts"]
    importer.sync_period(9001, max_polls=None, with_votes=True)
    assert project_status(database)["entity_counts"] == counts
    assert len(project_status(database)["recent_imports"]) == 2


def test_without_votes_makes_no_vote_requests(database, dataset_client):
    client, requests = dataset_client
    Importer(client, database).sync_period(9001)
    assert not any(req.url.path.endswith("/votes") for req in requests)
    assert vote_summary(database, 9041)["complete_against_api"] is False


def test_wrong_period_filter_fails_and_marks_run(database, dataset_client, dataset):
    dataset["polls"][0]["field_legislature"]["id"] = 123
    client, _ = dataset_client
    with pytest.raises(APIError, match="Filterprüfung"):
        Importer(client, database).sync_period(9001)
    run = project_status(database)["recent_imports"][0]
    assert run["status"] == "failed"
    assert "Filterprüfung" in run["error"]


def test_unknown_vote_value_is_not_silently_reinterpreted(database, dataset_client, dataset):
    dataset["votes"][0]["vote"] = "mystery"
    client, _ = dataset_client
    with pytest.raises(APIError, match="Unbekannter Stimmenwert"):
        Importer(client, database).sync_period(9001, with_votes=True)
    assert vote_summary(database, 9041)["complete_against_api"] is False


def test_votes_can_be_loaded_for_already_known_polls_only(database, dataset_client):
    client, requests = dataset_client
    Importer(client, database).sync_period(9001, max_polls=None, with_votes=False)
    assert vote_summary(database, 9042)["complete_against_api"] is False
    before = len(requests)
    stats = Importer(client, database).import_votes(9001, [9042])
    later = requests[before:]
    assert stats["votes"] == 1
    assert stats["poll_ids"] == [9042]
    assert stats["vote_polls_complete"] == 1
    assert vote_summary(database, 9042)["complete_against_api"] is True
    assert [req.url.path for req in later if req.url.path.endswith("/votes")] == ["/api/v2/votes"]
    assert next(req for req in later if "votes" in req.url.path).url.params["poll"] == "9042"
    assert not any(req.url.path.endswith("/polls") for req in later)
    run = project_status(database)["recent_imports"][0]
    assert run["stats"]["votes_only"] is True
    assert run["stats"]["poll_ids"] == [9042]
    coverage = poll_coverage(database, 9001, [9041, 9042])
    assert coverage["available_api_polls"] == 2
    assert coverage["poll_list_complete_against_api"] is True
    assert coverage["identity_set_verified"] is True


def test_votes_only_import_rejects_duplicates_and_unknown_polls(database, dataset_client):
    client, _ = dataset_client
    importer = Importer(client, database)
    with pytest.raises(ValueError, match="eindeutig"):
        importer.import_votes(9001, [9042, 9042])
    importer.sync_period(9001, max_polls=1, with_votes=False)
    with pytest.raises(APIError, match="nicht lokal vorhanden"):
        importer.import_votes(9001, [9042])
    assert vote_summary(database, 9042)["complete_against_api"] is False


def test_election_is_rejected_as_import_target(database, dataset_client):
    client, _ = dataset_client
    with pytest.raises(APIError, match="Legislatur-ID"):
        Importer(client, database).sync_period(9002)
    row = database.connection.execute("SELECT stats FROM import_runs").fetchone()
    assert json.loads(row["stats"])["polls_complete"] is False
