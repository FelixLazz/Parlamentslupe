"""Ausschließlich synthetische amtliche Testantworten, keine echten politischen Aussagen."""

import json

import httpx
import pytest

from partei_hack.api.client import APIError
from partei_hack.api.official import document_number, official_url
from partei_hack.services.evidence import (
    crosscheck_counts,
    enrich_period,
    evidence_for_poll,
    fetch_source,
    link_source,
    parse_official,
)
from partei_hack.storage.database import utc_now
from tests.conftest import envelope
from tests.test_api_client import client_for
from tests.test_programs import TEST_TEXT, make_pdf

PAGE = "https://www.bundestag.de/parlament/plenum/abstimmung/abstimmung?id=999999"
PDF = "https://dserver.bundestag.de/btd/20/999/2099999.pdf"


def html(yes=1, no=0, group_yes=None, day="1. Januar 2024"):
    group_yes = yes if group_yes is None else group_yes
    return (
        f"<html><main><p>{day}</p><h1>Synthetischer Testvorgang – keine reale Bewertung</h1>"
        f"<h3>Gesamtergebnis, {yes + no} Mitglieder</h3>"
        f"<ul><li>{yes} ja</li><li>{no} nein</li><li>0 enthalten</li><li>0 nicht abg.</li></ul>"
        "<h4>Testfraktion</h4>"
        f"<p>{yes + no} Mitglieder</p><ul><li>{group_yes} ja</li>"
        f"<li>{yes + no - group_yes} nein</li><li>0 enthalten</li><li>0 nicht abg.</li></ul>"
        f'<p>Ausdrücklich synthetischer Testtext.</p><a href="{PDF}">Testdrucksache</a>'
        "</main></html>"
    ).encode()


@pytest.mark.parametrize(
    "url",
    [
        "http://www.bundestag.de/parlament/plenum/abstimmung/abstimmung?id=1",
        "https://127.0.0.1/file.pdf",
        "https://www.bundestag.de.evil.example/file.pdf",
        "https://user@www.bundestag.de/parlament/plenum/abstimmung/abstimmung?id=1",
        "https://www.bundestag.de:22/parlament/plenum/abstimmung/abstimmung?id=1",
        "https://dserver.bundestag.de/btd/20/999/2099999.pdf?redirect=x",
        "https://dserver.bundestag.de/%2e%2e/secret.pdf",
        "https://www.bundestag.de/parlament/plenum/abstimmung/abstimmung?id=1&x=",
    ],
)
def test_unsafe_sources_rejected(url):
    with pytest.raises(ValueError):
        official_url(url)


def test_legacy_pdf_host_is_explicitly_normalized():
    assert official_url("https://dipbt.bundestag.de/dip21/btp/20/20214.pdf#P.27741") == (
        "https://dserver.bundestag.de/btp/20/20214.pdf"
    )
    assert document_number(PDF) == "20/99999"


def test_html_extracts_total_fraction_date_and_document_links():
    parsed = parse_official(html(), PAGE)
    vote = parsed["official_vote"]
    assert vote["counts"] == {"yes": 1, "no": 0, "abstain": 0, "no_show": 0}
    assert vote["fractions"][0]["label"] == "Testfraktion"
    assert vote["dates_in_source"] == ["2024-01-01"]
    assert PDF in parsed["links"]


def test_aggregate_crosscheck_requires_date_and_checks_target_fraction():
    parsed = parse_official(html(yes=1, no=1, group_yes=0), PAGE)
    source = {**parsed, "url": PAGE}
    poll = {"field_poll_date": "2024-01-01"}
    counts = {"yes": 1, "no": 1, "abstain": 0, "no_show": 0}
    result = crosscheck_counts(
        [source],
        poll,
        counts,
        fraction={"label": "Testfraktion"},
        fraction_counts=counts,
    )
    assert result["status"] == "conflict"
    assert result["sources"][0]["selected_fraction_counts_match"] is False
    assert crosscheck_counts([source], {"field_poll_date": "2024-02-01"}, counts)["status"] == (
        "not_checked"
    )
    assert crosscheck_counts([source], poll, counts)["status"] == "aggregate_counts_match"


def test_archives_are_reused_but_changed_originals_are_rejected(database, tmp_path, clock):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=html(), headers={"Content-Type": "text/html"})

    client = client_for(database, tmp_path, clock, handler)
    source, downloaded = fetch_source(client, database, PAGE)
    assert downloaded
    assert fetch_source(client, database, PAGE)[1] is False
    assert len(calls) == 1
    link_source(database, 9041, source, "explicit_attachment")
    sources, errors = evidence_for_poll(database, 9041)
    assert not errors and sources[0]["sha256"] == source["sha256"]
    artifact = tmp_path / "evidence" / f"{source['sha256']}.html"
    artifact.write_bytes(b"Modified")
    sources, errors = evidence_for_poll(database, 9041)
    assert sources == [] and errors
    assert len(calls) == 1  # Keine stillschweigende Reparatur/manipulierte Ersetzung.


def test_metadata_cannot_forge_counts_without_changing_original(database, tmp_path, clock):
    client = client_for(database, tmp_path, clock, lambda req: httpx.Response(200, content=html()))
    source, _ = fetch_source(client, database, PAGE)
    source["official_vote"]["counts"]["yes"] = 999
    database.save_entity("evidence-documents", source, PAGE, utc_now())
    link_source(database, 9041, source, "explicit_attachment")
    sources, _ = evidence_for_poll(database, 9041)
    assert sources[0]["official_vote"]["counts"]["yes"] == 1


def test_bounded_enrichment_imports_context_and_official_pdf(database, tmp_path, clock, dataset):
    other_pdf = "https://dserver.bundestag.de/btd/20/999/2099998.pdf"
    dataset["polls"][0]["field_intro"] = f'<a href="{other_pdf}">Andere Vorlage</a>'
    for resource in ("parliament-periods", "polls"):
        database.save_entities(resource, dataset[resource], "synthetic", utc_now())
    calls = []

    def handler(request):
        calls.append(str(request.url))
        if request.url.path.endswith("/topics/9061"):
            return httpx.Response(200, json=envelope({"id": 9061, "label": "Testverkehr"}))
        if request.url.host == "www.bundestag.de":
            return httpx.Response(200, content=html())
        if request.url.host == "dserver.bundestag.de":
            return httpx.Response(
                200, content=make_pdf("Synthetischer Gesetzentwurf. " + TEST_TEXT)
            )
        pytest.fail(f"Unexpected request: {request.url}")

    client = client_for(database, tmp_path, clock, handler)
    result = enrich_period(
        client,
        database,
        9001,
        poll_id=9041,
        max_documents=2,
        official_sources=[PAGE],
    )
    assert result["api_context_entities"] == 1
    assert result["documents_downloaded"] == 2
    assert result["errors"] == []
    assert len(calls) == 3
    assert other_pdf not in calls  # Amtlicher Direktkontext hat Vorrang vor weiteren API-Verweisen.
    sources, _ = evidence_for_poll(database, 9041)
    assert len(sources) == 2
    assert any(source["document_number"] == "20/99999" for source in sources)
    assert (
        database.connection.execute(
            "SELECT COUNT(*) FROM entities WHERE resource='enrichment-runs'"
        ).fetchone()[0]
        == 1
    )


def test_source_failures_do_not_become_successful_evidence(database, tmp_path, clock, dataset):
    for resource in ("parliament-periods", "polls"):
        data = json.loads(json.dumps(dataset[resource]))
        if resource == "polls":
            data[0]["field_topics"] = []
        database.save_entities(resource, data, "synthetic", utc_now())
    client = client_for(database, tmp_path, clock, lambda req: httpx.Response(404))
    result = enrich_period(client, database, 9001, poll_id=9041, official_sources=[PAGE])
    assert result["errors"]
    assert result["documents_downloaded"] == 0
    assert evidence_for_poll(database, 9041)[0] == []


def test_official_redirects_are_not_followed(database, tmp_path, clock):
    client = client_for(
        database,
        tmp_path,
        clock,
        lambda req: httpx.Response(302, headers={"Location": "http://127.0.0.1/private"}),
    )
    with pytest.raises(APIError, match="302"):
        client.download_official(PAGE)


def test_amendment_is_not_mislabeled_as_the_original_bill():
    parsed = parse_official(
        make_pdf("Synthetischer Änderungsantrag zu einem Gesetzentwurf. " + TEST_TEXT), PDF
    )
    assert parsed["document_type_hint"] == "Änderungsantrag"
