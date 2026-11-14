"""Gemeinsame Webauswahl ausschließlich mit synthetischen Daten und HTTP-Mocks."""

import json

import pytest

from partei_hack.storage.database import Database, utc_now
from tests import test_web as fixtures
from tests.test_web import get_json, request

workspace = fixtures.workspace
web = fixtures.web
program_client = fixtures.program_client


def run_payload(**overrides):
    return {
        "period": 9001,
        "fraction": 9031,
        "poll_ids": [9041],
        "program": 9071,
        "confirm_online": True,
        **overrides,
    }


def test_catalog_declares_web_contract_before_new_selection_requests(web, program_client):
    from partei_hack.web.server import WEB_API_VERSION

    calls, _ = program_client
    result = get_json(web, "/api/catalog")
    assert result["web_api_version"] == WEB_API_VERSION == 1
    assert result["token"] == web.token
    assert calls == []
    source = request(web, "/app.js").body.decode("utf-8")
    assert f"const WEB_API_VERSION = {WEB_API_VERSION};" in source


def test_choices_are_local_and_available_before_fraction_or_vote_import(web, program_client):
    calls, _ = program_client
    with Database(web.settings.database_path) as db:
        db.connection.execute("DELETE FROM entities WHERE resource IN ('votes', 'fractions')")
        db.connection.commit()
    result = get_json(web, "/api/choices?period=9001")
    assert {poll["id"] for poll in result["polls"]} == {9041, 9042}
    assert all("votes" not in poll for poll in result["polls"])
    assert all(not poll["complete_against_api"] for poll in result["polls"])
    assert result["programs"][0]["id"] == 9071
    assert calls == []
    assert request(web, "/api/choices?period=9002").status == 400


def test_choices_do_not_load_vote_or_mandate_details(web, monkeypatch):
    def unexpected(*args, **kwargs):
        raise AssertionError("Die Titelauswahl darf keine Einzelstimmen auswerten.")

    monkeypatch.setattr("partei_hack.services.queries.list_votes", unexpected)
    monkeypatch.setattr("partei_hack.services.workspace.vote_summary", unexpected)
    result = get_json(web, "/api/choices?period=9001")
    assert len(result["polls"]) == 2


def test_id_only_coverage_matches_full_summary_and_detects_changed_id_set(web):
    from partei_hack.services.queries import vote_import_status, vote_summary

    with Database(web.settings.database_path) as db:
        db.mark_vote_coverage(9041, 1, complete=True)
        db.save_entity(
            "vote-import-manifests",
            {"id": 9041, "label": "Synthetischer ID-Satz", "vote_ids": [9051]},
            "https://invalid.example",
            utc_now(),
        )
        status = vote_import_status(db, 9041)
        summary = vote_summary(db, 9041)
        assert status["complete_against_api"] is True
        assert all(summary[key] == value for key, value in status.items())
        db.connection.execute(
            "UPDATE entities SET entity_id=99999 WHERE resource='votes' AND entity_id=9051"
        )
        db.connection.commit()
        assert vote_import_status(db, 9041)["complete_against_api"] is False


def test_loopback_server_disallows_shared_port_and_enables_windows_exclusive_bind(monkeypatch):
    from partei_hack.web import server

    calls = []
    monkeypatch.setattr(server.socket, "SO_EXCLUSIVEADDRUSE", 12345, raising=False)
    monkeypatch.setattr(
        server.ThreadingHTTPServer, "server_bind", lambda self: calls.append("bind")
    )

    class FakeSocket:
        def setsockopt(self, *args):
            calls.append(args)

    instance = object.__new__(server.LoopbackHTTPServer)
    instance.socket = FakeSocket()
    instance.server_bind()
    assert calls == [(server.socket.SOL_SOCKET, 12345, 1), "bind"]
    assert instance.allow_reuse_address is False
    assert instance.allow_reuse_port is False


def test_prepare_loads_only_choices_with_verified_full_title_coverage(web, program_client):
    calls, _ = program_client
    with Database(web.settings.database_path) as db:
        db.connection.execute(
            "DELETE FROM entities WHERE resource NOT IN ('parliaments', 'parliament-periods')"
        )
        db.connection.commit()
    response = request(web, "/api/prepare", payload={"period": 9001, "confirm_online": True})
    assert response.status == 200, response.body
    result = json.loads(response.body)
    assert len(result["catalog"]["fractions"]) == 1
    assert len(result["choices"]["programs"]) == 1
    assert len(result["choices"]["polls"]) == 2
    assert result["choices"]["coverage"]["poll_list_complete_against_api"] is True
    assert {call.url.path.rsplit("/", 1)[-1] for call in calls} == {
        "fractions",
        "9002",
        "election-program",
        "polls",
    }
    assert not (web.settings.data_dir / "programs").exists()
    with Database(web.settings.database_path) as db:
        assert (
            db.connection.execute(
                "SELECT COUNT(*) FROM entities WHERE resource IN ('votes','candidacies-mandates')"
            ).fetchone()[0]
            == 0
        )


def test_one_action_imports_only_selected_votes_downloads_pdf_and_compares(web, program_client):
    calls, _ = program_client
    with Database(web.settings.database_path) as db:
        db.connection.execute(
            "DELETE FROM entities WHERE resource IN ('votes','candidacies-mandates')"
        )
        db.connection.commit()
    response = request(web, "/api/run", payload=run_payload())
    assert response.status == 200, response.body
    result = json.loads(response.body)
    assert result["selected_poll_ids"] == [9041]
    assert result["reused_polls"] == 0
    assert [poll["id"] for poll in result["analysis"]["polls"]] == [9041]
    report = result["comparison"]
    assert [poll["id"] for poll in report["polls"]] == [9041]
    assert report["report_scope"]["poll_ids"] == [9041]
    assert report["coverage"]["local_polls"] == 2
    assert report["coverage"]["reported_polls"] == 1
    assert report["fulfillment"] == "not_assessed"
    assert result["analysis"]["programs"][0]["local_document_present"] is True
    assert report["vote_totals"]["no_show"] == 1
    vote_calls = [call for call in calls if call.url.path.endswith("/votes")]
    assert [call.url.params["poll"] for call in vote_calls] == ["9041"]
    mandates = next(call for call in calls if call.url.path.endswith("/candidacies-mandates"))
    assert mandates.url.params["current_on"] == "all"
    assert sum(call.url.path.endswith(".pdf") for call in calls) == 1
    assert not any(call.url.path.endswith("/polls") for call in calls)


def test_repeat_selection_reuses_complete_votes_and_local_pdf(web, program_client, monkeypatch):
    from partei_hack.web import server

    calls, _ = program_client
    assert request(web, "/api/run", payload=run_payload()).status == 200
    calls.clear()
    monkeypatch.setattr(server.time, "sleep", lambda _: None)
    result = request(web, "/api/run", payload=run_payload())
    assert result.status == 200, result.body
    assert json.loads(result.body)["reused_polls"] == 1
    assert calls == []


def test_extending_selection_fetches_only_the_still_missing_poll(web, program_client, monkeypatch):
    from partei_hack.web import server

    calls, _ = program_client
    assert request(web, "/api/run", payload=run_payload()).status == 200
    calls.clear()
    monkeypatch.setattr(server.time, "sleep", lambda _: None)
    response = request(web, "/api/run", payload=run_payload(poll_ids=[9041, 9042]))
    assert response.status == 200, response.body
    result = json.loads(response.body)
    assert result["reused_polls"] == 1
    assert result["import"]["poll_ids"] == [9042]
    assert [call.url.params["poll"] for call in calls if call.url.path.endswith("/votes")] == [
        "9042"
    ]


def test_prepare_without_linked_election_still_offers_titles_and_fractions(web, program_client):
    with Database(web.settings.database_path) as db:
        db.connection.execute(
            "UPDATE entities SET payload=json_remove(payload, '$.previous_period') "
            "WHERE resource='parliament-periods' AND entity_id=9001"
        )
        db.connection.commit()
    response = request(web, "/api/prepare", payload={"period": 9001, "confirm_online": True})
    assert response.status == 200, response.body
    result = json.loads(response.body)
    assert result["notice"]
    assert len(result["choices"]["polls"]) == 2
    assert result["choices"]["programs"] == []


def test_all_polls_requires_complete_title_list_and_no_ambiguous_selection(web, program_client):
    calls, _ = program_client
    payload = run_payload(poll_ids=None, all_polls=True, program=None)
    assert request(web, "/api/run", payload=payload).status == 400
    assert calls == []
    with Database(web.settings.database_path) as db:
        run = db.start_import(9001, {"metadata_only": True})
        db.finish_import(
            run, {"polls_available": 2, "polls_complete": True, "poll_ids": [9041, 9042]}
        )
    assert request(web, "/api/run", payload=run_payload(all_polls=True)).status == 400
    response = request(web, "/api/run", payload=payload)
    assert response.status == 200, response.body
    result = json.loads(response.body)
    assert set(result["selected_poll_ids"]) == {9041, 9042}
    assert result["comparison"] is None
    assert result["analysis"]["coverage"]["filtered_polls_with_complete_votes"] == 2
    assert not any(call.url.path.endswith(".pdf") for call in calls)


@pytest.mark.parametrize(
    "override",
    [
        {"poll_ids": []},
        {"poll_ids": [9041, 9041]},
        {"poll_ids": [True]},
        {"poll_ids": "9041"},
        {"poll_ids": [9999]},
        {"poll_ids": [9041], "all_polls": "yes"},
        {"period": 9002},
        {"fraction": 9999},
        {"program": 9999},
        {"confirm_online": False},
    ],
)
def test_invalid_combined_selection_never_starts_network(web, program_client, override):
    calls, _ = program_client
    assert request(web, "/api/run", payload=run_payload(**override)).status == 400
    assert calls == []


def test_foreign_period_poll_is_rejected_before_network(web, program_client):
    calls, _ = program_client
    with Database(web.settings.database_path) as db:
        db.save_entity(
            "polls",
            {"id": 9997, "label": "Fremd", "field_legislature": {"id": 42}},
            "https://invalid.example",
            utc_now(),
        )
    assert request(web, "/api/run", payload=run_payload(poll_ids=[9997])).status == 400
    assert calls == []


@pytest.mark.parametrize("path", ["/api/run", "/api/prepare"])
def test_new_online_routes_keep_token_origin_and_lock_protection(web, program_client, path):
    calls, _ = program_client
    payload = run_payload()
    assert request(web, path, payload=payload, headers={"X-ParteiHack-Token": ""}).status == 403
    assert (
        request(web, path, payload=payload, headers={"Origin": "https://invalid.example"}).status
        == 403
    )
    web.online_lock.acquire()
    try:
        assert request(web, path, payload=payload).status == 409
    finally:
        web.online_lock.release()
    assert calls == []


def test_selected_scope_is_kept_in_offline_analysis_and_comparison(web, program_client):
    calls, _ = program_client
    assert request(web, "/api/run", payload=run_payload()).status == 200
    calls.clear()
    report = get_json(web, "/api/analysis?period=9001&fraction=9031&polls=9041")
    comparison = get_json(web, "/api/compare?period=9001&fraction=9031&program=9071&polls=9041")
    assert [poll["id"] for poll in report["polls"]] == [9041]
    assert [poll["id"] for poll in comparison["polls"]] == [9041]
    assert report["coverage"]["local_polls"] == comparison["coverage"]["local_polls"] == 2
    assert calls == []


@pytest.mark.parametrize("path", ["/api/compare", "/api/evidence"])
def test_later_online_actions_keep_explicit_report_scope(web, program_client, monkeypatch, path):
    from partei_hack.web import server

    assert request(web, "/api/run", payload=run_payload()).status == 200
    monkeypatch.setattr(server.time, "sleep", lambda _: None)
    monkeypatch.setattr(server, "enrich_period", lambda *args, **kwargs: {"test": True})
    response = request(web, path, payload=run_payload(load_votes=False))
    assert response.status == 200, response.body
    report = json.loads(response.body)
    assert [poll["id"] for poll in report["polls"]] == [9041]
    assert report["report_scope"]["poll_ids"] == [9041]


def test_metadata_filter_failure_does_not_claim_completeness(web, program_client, workspace):
    calls, _ = program_client
    workspace[1]["polls"][1]["field_legislature"] = {"id": 42}
    response = request(web, "/api/prepare", payload={"period": 9001, "confirm_online": True})
    assert response.status == 502
    assert not get_json(web, "/api/choices?period=9001")["coverage"][
        "poll_list_complete_against_api"
    ]


def test_failed_pdf_keeps_imported_votes_and_releases_online_lock(web, program_client):
    calls, behavior = program_client
    behavior["status"] = 404
    response = request(web, "/api/run", payload=run_payload())
    assert response.status == 502
    assert not web.online_lock.locked()
    result = get_json(web, "/api/choices?period=9001")
    assert next(poll for poll in result["polls"] if poll["id"] == 9041)["complete_against_api"]
    assert not (web.settings.data_dir / "programs").exists()
