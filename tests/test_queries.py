from partei_hack.services.importer import Importer
from partei_hack.services.queries import list_polls, list_votes, vote_summary
from partei_hack.storage.database import utc_now


def test_poll_filters_are_local_and_combinable(database, dataset_client):
    client, requests = dataset_client
    Importer(client, database).sync_period(9001)
    count = len(requests)
    matches = list_polls(
        database,
        period_id=9001,
        search="Verkehr",
        since="2024-01-01",
        until="2024-01-31",
        topic_id=9061,
    )
    assert [item["id"] for item in matches] == [9041]
    assert [item["id"] for item in list_polls(database, search="ÖFFENTLICHER")] == [9041]
    assert list_polls(database, search="' OR 1=1 --") == []
    assert list_polls(database, period_id=9999) == []
    assert len(requests) == count


def test_votes_join_mandate_without_using_current_party(database, dataset_client):
    client, _ = dataset_client
    Importer(client, database).sync_period(9001, with_votes=True)
    rows = list_votes(database, 9041, vote="no_show", fraction_id=9031)
    assert len(rows) == 1
    assert rows[0]["politician"] == "Testperson Alpha"
    assert rows[0]["reason_no_show"] == "fell_ill"
    assert list_votes(database, 9041, vote="no") == []


def test_summary_keeps_absence_and_abstention_separate(database, dataset_client):
    client, _ = dataset_client
    Importer(client, database).sync_period(9001, with_votes=True)
    result = vote_summary(database, 9041)
    fraction = result["fractions"][0]
    assert fraction["no_show"] == 1
    assert fraction["no"] == fraction["abstain"] == 0
    assert result["complete_against_api"] is True


def test_unimported_poll_is_not_marked_complete(database):
    result = vote_summary(database, 99999)
    assert result["local_votes"] == 0
    assert result["complete_against_api"] is False
    assert result["expected_api_votes"] is None


def test_extra_stale_vote_breaks_coverage_claim(database, dataset_client):
    client, _ = dataset_client
    Importer(client, database).sync_period(9001, with_votes=True)
    database.save_entity(
        "votes",
        {"id": 99999, "label": "Stale synthetic", "poll": {"id": 9041}, "vote": "abstain"},
        "https://invalid.example",
        utc_now(),
    )
    result = vote_summary(database, 9041)
    assert result["complete_against_api"] is False
    assert result["local_votes"] == 2
    assert result["fractions"][0]["fraction"]
