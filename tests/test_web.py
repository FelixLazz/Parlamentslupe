"""Web-Endpunkte ohne Sockets oder echte API-Aufrufe prüfen."""

import json
from copy import deepcopy

import httpx
import pytest
from typer.testing import CliRunner

from partei_hack.api.client import APIClient
from partei_hack.cli import app
from partei_hack.config import Settings
from partei_hack.services.programs import prepare_program
from partei_hack.services.workspace import analysis, catalog, refresh_catalog
from partei_hack.storage.database import Database, utc_now
from partei_hack.web.server import SECURITY_HEADERS, WebApplication, positive_id
from tests.conftest import envelope
from tests.test_programs import TEST_TEXT, make_pdf


@pytest.fixture
def workspace(tmp_path, dataset):
    settings = Settings.resolve(tmp_path)
    data = deepcopy(dataset)
    parliament = {"id": 999, "label": "Synthetischer Test-Landtag"}
    data["parliaments"] = [parliament]
    for period in data["parliament-periods"]:
        period["parliament"] = parliament
    data["parliament-periods"][0]["start_date_period"] = "2021-01-01"
    data["parliament-periods"][0]["end_date_period"] = "2026-01-01"
    with Database(settings.database_path) as database:
        for resource, items in data.items():
            database.save_entities(resource, items, "https://invalid.example/api", utc_now())
    return settings, data


@pytest.fixture
def web(workspace):
    return WebApplication(workspace[0], 8000)


def request(web, path, *, payload=None, headers=None, method=None):
    fields = {"Host": "127.0.0.1:8000"}
    if payload is not None:
        fields.update(
            {
                "Content-Type": "application/json",
                "X-ParteiHack-Token": web.token,
                "Origin": "http://127.0.0.1:8000",
            }
        )
    fields.update(headers or {})
    return web.handle(
        method or ("POST" if payload is not None else "GET"),
        path,
        fields,
        json.dumps(payload).encode() if payload is not None else b"",
    )


def get_json(web, path):
    response = request(web, path)
    assert response.status == 200, response.body
    return json.loads(response.body)


def test_empty_workspace_returns_no_fabricated_choices(tmp_path):
    web = WebApplication(Settings.resolve(tmp_path), 8000)
    payload = get_json(web, "/api/catalog")
    assert payload == {
        "parliaments": [],
        "periods": [],
        "fractions": [],
        "token": web.token,
        "web_api_version": 1,
    }


def test_catalog_supports_landtags_and_only_legislatures(web):
    payload = get_json(web, "/api/catalog")
    assert payload["parliaments"][0]["label"] == "Synthetischer Test-Landtag"
    assert [period["id"] for period in payload["periods"]] == [9001]
    assert payload["fractions"][0]["id"] == 9031


def test_catalog_can_use_real_imported_parliament_references(workspace):
    with Database(workspace[0].database_path) as database:
        database.connection.execute("DELETE FROM entities WHERE resource='parliaments'")
        database.connection.commit()
        assert catalog(database)["parliaments"][0]["id"] == 999


def test_analysis_distinguishes_missing_votes_from_no_show(web):
    payload = get_json(web, "/api/analysis?period=9001&fraction=9031")
    assert payload["vote_totals"] == {"yes": 1, "no": 0, "abstain": 0, "no_show": 1, "unknown": 0}
    assert payload["coverage"]["available_api_polls"] is None
    assert payload["coverage"]["poll_list_complete_against_api"] is False
    assert payload["coverage"]["filtered_polls_with_complete_votes"] == 0
    assert len(payload["programs"]) == 1
    with Database(web.settings.database_path) as database:
        database.connection.execute("DELETE FROM entities WHERE resource='votes'")
        database.connection.commit()
    payload = get_json(web, "/api/analysis?period=9001&fraction=9031")
    assert payload["vote_totals"]["no_show"] == 0
    assert all(poll["fraction_votes"] == 0 for poll in payload["polls"])


def test_filters_only_affect_visible_polls_not_period_coverage(web):
    payload = get_json(
        web, "/api/analysis?period=9001&fraction=9031&search=VERKEHR&until=2024-01-31"
    )
    assert [poll["id"] for poll in payload["polls"]] == [9041]
    assert payload["coverage"]["local_polls"] == 2
    assert payload["vote_totals"]["no_show"] == 1
    assert payload["vote_totals"]["yes"] == 0
    assert get_json(web, "/api/analysis?period=9001&fraction=9031&search=%25")["polls"] == []


def test_verified_api_coverage_is_not_an_assumption(web):
    with Database(web.settings.database_path) as database:
        run = database.start_import(9001, {"max_polls": None})
        database.finish_import(run, {"polls_available": 2, "polls_complete": True})
        database.mark_vote_coverage(9041, 1, complete=True)
        database.mark_vote_coverage(9042, 2, complete=True)  # Falsche Anzahl bleibt unvollständig.
        payload = analysis(database, 9001, 9031)
    assert payload["coverage"]["poll_list_complete_against_api"] is True
    assert payload["coverage"]["filtered_polls_with_complete_votes"] == 1


@pytest.mark.parametrize(
    "query",
    [
        "period=9002&fraction=9031",  # Wahl statt Legislatur.
        "period=9001&fraction=9999",
        "period=9001&fraction=9031&since=2024-02-31",
        "period=9001&fraction=9031&since=2025-01-01&until=2024-01-01",
        "period=9001&fraction=9031&period=9002",
        "period=-1&fraction=9031",
        "period=9001&fraction=9031&search=" + "x" * 201,
    ],
)
def test_invalid_selections_and_filters_are_rejected(web, query):
    assert request(web, "/api/analysis?" + query).status == 400


def test_fraction_and_poll_must_belong_to_selected_period(web):
    with Database(web.settings.database_path) as database:
        database.save_entity(
            "fractions",
            {"id": 9998, "label": "Fremde Testfraktion", "legislature": {"id": 42}},
            "https://invalid.example",
            utc_now(),
        )
        database.save_entity(
            "polls",
            {"id": 9997, "label": "Fremder Testpoll", "field_legislature": {"id": 42}},
            "https://invalid.example",
            utc_now(),
        )
    assert request(web, "/api/analysis?period=9001&fraction=9998").status == 400
    assert request(web, "/api/poll?period=9001&fraction=9031&poll=9997").status == 400


def test_detail_exposes_filtered_votes_and_plain_text_only(web):
    payload = get_json(web, "/api/poll?period=9001&fraction=9031&poll=9041")
    assert len(payload["votes"]) == 1
    assert payload["votes"][0]["vote"] == "no_show"
    assert payload["votes"][0]["politician"] == "Testperson Alpha"


def test_missing_program_pdf_does_not_download(web):
    response = request(web, "/api/program?period=9001&fraction=9031&program=9071")
    assert response.status == 409
    assert "Original-PDF fehlt lokal" in json.loads(response.body)["error"]
    assert json.loads(response.body)["code"] == "program_missing"
    assert not (web.settings.data_dir / "programs").exists()
    assert request(web, "/api/program?period=9001&fraction=9031&program=9999").status == 400


def test_program_passages_use_original_pdf_and_remain_unreviewed(web):
    with Database(web.settings.database_path) as database:
        program = json.loads(
            database.connection.execute(
                "SELECT payload FROM entities WHERE resource='election-program'"
            ).fetchone()["payload"]
        )
        database.connection.execute(
            """UPDATE entities SET payload=json_set(payload, '$.label', ?)
            WHERE resource='polls' AND entity_id=9041""",
            ("Synthetischer Test: Verkehr und Mobilität",),
        )
        database.connection.commit()
    pdf = web.settings.data_dir / "synthetic.pdf"
    pdf.write_bytes(make_pdf(TEST_TEXT))
    document = prepare_program(web.settings.data_dir, program, local_file=pdf)
    payload = get_json(web, "/api/program?period=9001&fraction=9031&program=9071")
    assert payload["sha256"] == document["sha256"]
    matches = [match for poll in payload["polls"] for match in poll["matches"]]
    assert matches
    assert all(match["review_status"] == "unreviewed" for match in matches)
    assert all(match["assessment"] == "not_assessable" for match in matches)
    assert all(match["page"] == 1 for match in matches)


@pytest.mark.parametrize("path", ["/", "/app.css", "/app.js"])
def test_packaged_assets_are_served_without_external_dependencies(web, path):
    response = request(web, path)
    assert response.status == 200
    assert response.body
    if path == "/":
        assert b'lang="de"' in response.body
        assert b"https://fonts" not in response.body
    assert request(web, "/../config.py").status == 404
    assert "frame-ancestors 'none'" in SECURITY_HEADERS["Content-Security-Policy"]


@pytest.mark.parametrize(
    "headers",
    [
        {"Host": "attacker.example:8000"},
        {"Host": "127.0.0.1:9999"},
        {"X-ParteiHack-Token": ""},
        {"Origin": "https://attacker.example"},
        {"Sec-Fetch-Site": "cross-site"},
    ],
)
def test_online_actions_reject_dns_rebinding_and_csrf(web, headers):
    response = request(
        web,
        "/api/refresh",
        payload={"scope": "parliaments", "confirm_online": True},
        headers=headers,
    )
    assert response.status == 403


def test_online_actions_require_json_and_confirmation(web):
    assert request(web, "/api/refresh", payload={"scope": "parliaments"}).status == 400
    assert (
        request(
            web,
            "/api/refresh",
            payload={"scope": "parliaments", "confirm_online": True},
            headers={"Content-Type": "text/plain"},
        ).status
        == 415
    )
    assert (
        request(
            web, "/api/import", payload={"period": 9001, "max_polls": 6, "confirm_online": True}
        ).status
        == 400
    )
    assert (
        request(
            web, "/api/import", payload={"period": 9002, "max_polls": 1, "confirm_online": True}
        ).status
        == 400
    )
    assert (
        request(web, "/api/refresh", payload={"scope": "unknown", "confirm_online": True}).status
        == 400
    )
    assert request(web, "/api/catalog", method="DELETE").status == 405
    assert (
        web.handle(
            "POST",
            "/api/import",
            {
                "Host": "127.0.0.1:8000",
                "X-ParteiHack-Token": web.token,
                "Content-Type": "application/json",
            },
            b"[]",
        ).status
        == 400
    )


def test_concurrent_online_action_is_rejected(web):
    web.online_lock.acquire()
    try:
        response = request(
            web, "/api/refresh", payload={"scope": "parliaments", "confirm_online": True}
        )
    finally:
        web.online_lock.release()
    assert response.status == 409


def test_mocked_web_import_uses_historical_mandates_and_bound(web, dataset_client, monkeypatch):
    client, calls = dataset_client
    monkeypatch.setattr("partei_hack.web.server.APIClient", lambda *args: client)
    response = request(
        web, "/api/import", payload={"period": 9001, "max_polls": 1, "confirm_online": True}
    )
    assert response.status == 200, response.body
    result = json.loads(response.body)
    assert result["polls"] == 1
    assert result["with_votes"] is True
    mandate_call = next(call for call in calls if "candidacies-mandates" in call.url.path)
    assert mandate_call.url.params["current_on"] == "all"
    assert len([call for call in calls if call.url.path.endswith("/votes")]) == 1


def test_refresh_rejects_wrong_parent_before_saving(database, dataset_client):
    client, _ = dataset_client
    database.save_entity(
        "parliaments",
        {"id": 998, "label": "Anderer Test-Landtag"},
        "https://invalid.example",
        utc_now(),
    )
    with pytest.raises(RuntimeError, match="Filterprüfung"):
        refresh_catalog(client, database, "periods", 998)
    assert catalog(database)["periods"] == []


def test_actions_keep_rate_limit_across_clients(web, monkeypatch):
    from partei_hack.web import server

    class FakeClient:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def iter_pages(self, *args):
            return iter([])

    sleeps = []
    monkeypatch.setattr(server, "APIClient", lambda *args: FakeClient())
    monkeypatch.setattr(server.time, "monotonic", lambda: 100)
    monkeypatch.setattr(server.time, "sleep", sleeps.append)
    payload = {"scope": "parliaments", "confirm_online": True}
    assert request(web, "/api/refresh", payload=payload).status == 200
    assert request(web, "/api/refresh", payload=payload).status == 200
    assert sleeps == [2.1]


def test_refresh_accepts_imported_parliament_reference_without_standalone_entity(
    web, dataset_client, monkeypatch
):
    client, _ = dataset_client
    monkeypatch.setattr("partei_hack.web.server.APIClient", lambda *args: client)
    with Database(web.settings.database_path) as database:
        database.connection.execute("DELETE FROM entities WHERE resource='parliaments'")
        database.connection.commit()
    response = request(
        web, "/api/refresh", payload={"scope": "periods", "parent": 999, "confirm_online": True}
    )
    assert response.status == 200, response.body


def test_failed_online_action_releases_lock_and_returns_actionable_error(web, monkeypatch):
    from partei_hack.api.client import APIError

    def failed(*args):
        raise APIError("Synthetischer API-Fehler")

    monkeypatch.setattr("partei_hack.web.server.APIClient", failed)
    response = request(
        web, "/api/refresh", payload={"scope": "parliaments", "confirm_online": True}
    )
    assert response.status == 502
    assert "Synthetischer API-Fehler" in json.loads(response.body)["error"]
    assert not web.online_lock.locked()
    assert web.last_online_end is not None


@pytest.mark.parametrize("value", [True, 0, -1, "1.2", "١", 2**63, None])
def test_web_ids_are_bounded_positive_ascii_integers(value):
    with pytest.raises(ValueError):
        positive_id(value)


def test_web_cli_exposes_port_and_has_no_implicit_network(tmp_path, monkeypatch):
    from partei_hack.web import server

    class FakeServer:
        server_port = 8123

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def serve_forever(self):
            raise KeyboardInterrupt

    def create(settings, port):
        assert port == 8123
        assert settings.data_dir == tmp_path
        return FakeServer()

    monkeypatch.setattr(server, "create_server", create)
    runner = CliRunner()
    result = runner.invoke(app, ["--data-dir", str(tmp_path), "web", "--port", "8123"])
    assert result.exit_code == 0
    assert "http://127.0.0.1:8123" in result.output
    assert not (tmp_path / "processed").exists()
    assert runner.invoke(app, ["web", "--port", "0"]).exit_code == 2


@pytest.fixture
def program_client(web, workspace, clock, monkeypatch, database):
    """Echte synthetische PDF, ausschließlich kontrollierter HTTP-Mock."""
    data = workspace[1]
    program = data["election-program"][0]
    program["file"] = "https://www.abgeordnetenwatch.de/sites/default/files/synthetic-program.pdf"
    program["party"]["label"] = "Synthetische Testpartei ohne CLI-Alias"
    data["polls"][0]["field_intro"] = "Verkehr und Mobilität durch zuverlässige Busse verbessern."
    with Database(web.settings.database_path) as db:
        db.save_entity("election-program", program, "https://invalid.example", utc_now())
        db.save_entity("polls", data["polls"][0], "https://invalid.example", utc_now())
    requests = []
    behavior = {"status": 200, "content": make_pdf(TEST_TEXT, "Synthetische zweite PDF-Seite.")}

    def handler(request):
        requests.append(request)
        if request.url.path.endswith(".pdf"):
            return httpx.Response(
                behavior["status"],
                content=behavior["content"],
                headers={"Location": "https://invalid.example/redirect.pdf"},
            )
        parts = request.url.path.removeprefix("/api/v2/").split("/")
        items = data[parts[0]]
        if len(parts) == 2:
            return httpx.Response(
                200, json=envelope(next(item for item in items if item["id"] == int(parts[1])))
            )
        if parts[0] == "votes":
            items = [
                item for item in items if item["poll"]["id"] == int(request.url.params["poll"])
            ]
        start = int(request.url.params.get("range_start", 0))
        size = int(request.url.params.get("range_end", 1000))
        return httpx.Response(
            200, json=envelope(items[start : start + size], total=len(items), start=start)
        )

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with APIClient(
            database,
            web.settings.raw_dir,
            http_client=http,
            sleep=clock.sleep,
            clock=clock.monotonic,
        ) as client:
            monkeypatch.setattr("partei_hack.web.server.APIClient", lambda *args: client)
            yield requests, behavior


def program_payload(**overrides):
    return {"period": 9001, "fraction": 9031, "program": 9071, "confirm_online": True, **overrides}


def test_program_list_can_load_without_importing_votes_or_pdfs(web, program_client):
    calls, _ = program_client
    with Database(web.settings.database_path) as db:
        db.connection.execute("DELETE FROM entities WHERE resource='election-program'")
        db.connection.execute(
            "DELETE FROM entities WHERE resource='parliament-periods' AND entity_id=9002"
        )
        db.connection.commit()
    response = request(
        web, "/api/refresh", payload={"scope": "programs", "parent": 9001, "confirm_online": True}
    )
    assert response.status == 200, response.body
    assert len(calls) == 2
    assert calls[0].url.path.endswith("/parliament-periods/9002")
    assert calls[1].url.params["parliament_period"] == "9002"
    payload = get_json(web, "/api/analysis?period=9001&fraction=9031")
    assert len(payload["programs"]) == 1
    assert payload["programs"][0]["local_document_present"] is False
    assert not (web.settings.data_dir / "programs").exists()


@pytest.mark.parametrize("mismatch", ["election", "program"])
def test_program_metadata_parent_validation_precedes_storage(
    web, program_client, workspace, mismatch
):
    calls, _ = program_client
    data = workspace[1]
    if mismatch == "election":
        data["parliament-periods"][1]["parliament"] = {"id": 42}
    else:
        data["election-program"][0]["parliament_period"] = {"id": 42}
    with Database(web.settings.database_path) as db:
        db.connection.execute("DELETE FROM entities WHERE resource='election-program'")
        db.connection.commit()
    response = request(
        web, "/api/refresh", payload={"scope": "programs", "parent": 9001, "confirm_online": True}
    )
    assert response.status == 502
    assert len(calls) == (1 if mismatch == "election" else 2)
    assert get_json(web, "/api/analysis?period=9001&fraction=9031")["programs"] == []


def test_confirmed_selected_pdf_is_downloaded_extracted_and_reusable_offline(web, program_client):
    calls, _ = program_client
    response = request(web, "/api/program", payload=program_payload())
    assert response.status == 200, response.body
    result = json.loads(response.body)
    assert len(calls) == 1 and calls[0].url.path.endswith("/synthetic-program.pdf")
    assert result["origin"] == "api_hosted_pdf"
    assert result["pdf_pages"] == 2
    assert result["text_characters"] >= 80
    assert result["pages"][0] == {"number": 1, "text": TEST_TEXT}
    assert len(result["sha256"]) == 64
    directory = web.settings.data_dir / "programs" / "9071"
    assert (directory / f"{result['sha256']}.pdf").is_file()
    second = get_json(web, "/api/program?period=9001&fraction=9031&program=9071&page=2")
    assert second["pages"][0]["number"] == 2
    assert "zweite PDF-Seite" in second["pages"][0]["text"]
    assert len(calls) == 1  # Lokales Blättern ruft die Quelle nicht erneut ab.
    assert request(web, "/api/program?period=9001&fraction=9031&program=9071&page=3").status == 400
    assert (
        get_json(web, "/api/analysis?period=9001&fraction=9031")["programs"][0][
            "local_document_present"
        ]
        is True
    )


@pytest.mark.parametrize("endpoint", ["/api/program", "/api/compare"])
def test_program_and_comparison_downloads_require_confirmation_and_valid_selection(
    web, program_client, endpoint
):
    calls, _ = program_client
    assert request(web, endpoint, payload=program_payload(confirm_online=False)).status == 400
    assert request(web, endpoint, payload=program_payload(program=123456)).status == 400
    assert request(web, endpoint, payload=program_payload(fraction=123456)).status == 400
    assert calls == []
    assert not (web.settings.data_dir / "programs").exists()


@pytest.mark.parametrize("source", [None, "https://invalid.example/not-allowed.pdf"])
def test_missing_or_external_pdf_source_has_clear_failure_without_request(
    web, program_client, source
):
    calls, _ = program_client
    with Database(web.settings.database_path) as db:
        db.connection.execute(
            "UPDATE entities SET payload=json_set(payload,'$.file',?) "
            "WHERE resource='election-program' AND entity_id=9071",
            (source,),
        )
        db.connection.commit()
    response = request(web, "/api/program", payload=program_payload())
    assert response.status == 400
    assert calls == []
    assert not (web.settings.data_dir / "programs").exists()


@pytest.mark.parametrize(
    ("status", "content", "expected_status", "message"),
    [
        (404, b"not found", 502, "HTTP 404"),
        (302, b"redirect", 502, "HTTP 302"),
        (200, b"<html>keine PDF</html>", 400, "keine PDF"),
        (200, make_pdf(""), 400, "OCR"),
    ],
)
def test_pdf_failures_are_not_misreported_as_success(
    web, program_client, status, content, expected_status, message
):
    calls, behavior = program_client
    behavior.update(status=status, content=content)
    response = request(web, "/api/program", payload=program_payload())
    assert response.status == expected_status, response.body
    assert message in json.loads(response.body)["error"]
    assert len(calls) == 1
    assert not (web.settings.data_dir / "programs").exists()


def test_comparison_get_is_offline_and_offers_missing_pdf_fallback(web, program_client):
    calls, _ = program_client
    response = request(web, "/api/compare?period=9001&fraction=9031&program=9071")
    assert response.status == 409
    assert json.loads(response.body)["code"] == "program_missing"
    assert calls == []


def test_web_comparison_supports_landtag_and_unknown_party_with_evidence(web, program_client):
    calls, _ = program_client
    response = request(web, "/api/compare", payload=program_payload(load_votes=False))
    assert response.status == 200, response.body
    report = json.loads(response.body)
    assert report["request"]["parliament"] == "Synthetischer Test-Landtag"
    assert report["request"]["selection_mode"] == "explicit_independent"
    assert report["program"]["party"]["label"] == "Synthetische Testpartei ohne CLI-Alias"
    assert report["coverage"]["local_polls"] == 2
    assert report["vote_totals"]["no_show"] == 1
    assert report["vote_totals"]["no"] == 0
    assert report["fulfillment"] == "not_assessed"
    assert report["reviewed_promises"] == []
    assert report["program_analysis"]["candidate_count"] == len(report["promise_candidates"])
    assert report["program_analysis"]["review_status"] == "unreviewed"
    assert all("context_features" in item for item in report["promise_candidates"])
    matches = [match for poll in report["polls"] for match in poll["program_matches"]]
    assert matches and all(match["review_status"] == "unreviewed" for match in matches)
    assert all(match["quote"] in TEST_TEXT for match in matches)
    assert len(calls) == 1  # Nur gewählte PDF; keine versteckten Stimmenimporte.
    cached = get_json(web, "/api/compare?period=9001&fraction=9031&program=9071")
    assert cached["program"]["sha256"] == report["program"]["sha256"]
    assert len(calls) == 1


def test_comparison_can_explicitly_fill_missing_votes_with_bounded_import(web, program_client):
    calls, _ = program_client
    with Database(web.settings.database_path) as db:
        db.connection.execute("DELETE FROM entities WHERE resource IN ('votes','polls')")
        db.connection.commit()
    response = request(web, "/api/compare", payload=program_payload(load_votes=True, max_polls=1))
    assert response.status == 200, response.body
    report = json.loads(response.body)
    assert report["coverage"]["local_polls"] == 1
    assert report["coverage"]["available_api_polls"] == 2
    assert report["coverage"]["polls_with_complete_votes"] == 1
    assert report["coverage"]["complete_against_api"] is False
    mandate = next(call for call in calls if call.url.path.endswith("/candidacies-mandates"))
    assert mandate.url.params["current_on"] == "all"
    vote_calls = [call for call in calls if call.url.path.endswith("/votes")]
    assert len(vote_calls) == 1
    assert vote_calls[0].url.params["poll"] == "9041"
    assert len([call for call in calls if call.url.path.endswith(".pdf")]) == 1


@pytest.mark.parametrize(
    "options",
    [
        {"load_votes": True, "max_polls": 6},
        {"load_votes": "false", "max_polls": 1},
        {"load_votes": True},
    ],
)
def test_comparison_never_silently_starts_unbounded_import(web, program_client, options):
    calls, _ = program_client
    response = request(web, "/api/compare", payload=program_payload(**options))
    assert response.status == 400
    assert calls == []


def test_comparison_with_no_polls_has_explicit_warning(web, program_client):
    with Database(web.settings.database_path) as db:
        db.connection.execute("DELETE FROM entities WHERE resource='polls'")
        db.connection.commit()
    response = request(web, "/api/compare", payload=program_payload(load_votes=False))
    assert response.status == 200, response.body
    report = json.loads(response.body)
    assert report["polls"] == []
    assert report["coverage"]["complete_against_api"] is False
    assert any("Keine lokalen Abstimmungen" in warning for warning in report["warnings"])


def test_missing_pdf_with_existing_manifest_can_be_restored_without_overwriting(
    web, program_client
):
    calls, _ = program_client
    first = request(web, "/api/program", payload=program_payload())
    assert first.status == 200
    document = json.loads(first.body)
    directory = web.settings.data_dir / "programs" / "9071"
    manifest = directory / f"{document['sha256']}.json"
    original_manifest = manifest.read_bytes()
    pdf = directory / f"{document['sha256']}.pdf"
    pdf.unlink()  # Ausschließlich im temporären synthetischen Testbestand.
    assert request(web, "/api/program?period=9001&fraction=9031&program=9071").status == 409
    web.last_online_end = None
    restored = request(web, "/api/program", payload=program_payload())
    assert restored.status == 200, restored.body
    assert len(calls) == 2
    assert pdf.exists()
    assert manifest.read_bytes() == original_manifest
    assert json.loads(restored.body)["sha256"] == document["sha256"]


@pytest.mark.parametrize("missing_file", [True, False])
def test_changed_local_or_remote_pdf_is_not_silently_replaced(web, program_client, missing_file):
    calls, behavior = program_client
    first = request(web, "/api/program", payload=program_payload())
    document = json.loads(first.body)
    pdf = web.settings.data_dir / "programs" / "9071" / f"{document['sha256']}.pdf"
    if missing_file:
        pdf.unlink()
        behavior["content"] = make_pdf(TEST_TEXT + " Synthetisch veränderte Quelle.")
    else:
        pdf.write_bytes(b"Synthetisch veraenderte lokale Datei")
    web.last_online_end = None
    response = request(web, "/api/program", payload=program_payload())
    assert response.status == 400
    if missing_file:
        assert "andere PDF-Version" in json.loads(response.body)["error"]
        assert not pdf.exists()
        assert len(calls) == 2
    else:
        assert "verändert" in json.loads(response.body)["error"]
        assert pdf.read_bytes() == b"Synthetisch veraenderte lokale Datei"
        assert len(calls) == 1


@pytest.mark.parametrize("endpoint", ["/api/program", "/api/compare"])
def test_selected_program_download_still_requires_local_session_token(
    web, program_client, endpoint
):
    calls, _ = program_client
    response = request(web, endpoint, payload=program_payload(), headers={"X-ParteiHack-Token": ""})
    assert response.status == 403
    assert calls == []
