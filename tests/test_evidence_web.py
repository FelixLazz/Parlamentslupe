"""Neue Quellenaktionen bleiben begrenzt, bestätigt und ohne implizite Netzabfragen."""

import json

import pytest

from partei_hack.config import Settings
from partei_hack.storage.database import Database, utc_now
from partei_hack.web.server import WebApplication
from tests.test_web import request


@pytest.fixture
def evidence_web(tmp_path, dataset):
    settings = Settings.resolve(tmp_path)
    with Database(settings.database_path) as database:
        for resource, items in dataset.items():
            database.save_entities(resource, items, "synthetic", utc_now())
    return WebApplication(settings, 8000)


def payload(**extra):
    return {
        "period": 9001,
        "fraction": 9031,
        "program": 9071,
        "confirm_online": True,
        **extra,
    }


@pytest.mark.parametrize(
    "extra",
    [
        {"max_polls": 6},
        {"max_documents": 4},
        {"max_documents": 0},
        {"confirm_online": False},
    ],
)
def test_limits_and_confirmation_before_network(evidence_web, extra):
    result = request(evidence_web, "/api/evidence", payload=payload(**extra))
    assert result.status == 400


def test_evidence_action_uses_shared_core(evidence_web, monkeypatch):
    calls = []

    def enrich(client, database, period_id, **options):
        calls.append((period_id, options))
        return {"documents_downloaded": 0, "documents_cached": 0, "errors": []}

    monkeypatch.setattr("partei_hack.web.server.enrich_period", enrich)
    monkeypatch.setattr(
        "partei_hack.web.server.comparison",
        lambda *args, **kwargs: {"method_version": "synthetic", "polls": []},
    )
    result = request(evidence_web, "/api/evidence", payload=payload())
    assert result.status == 200
    assert calls == [(9001, {"max_polls": 5, "max_documents": 3})]
    assert json.loads(result.body)["enrichment"]["errors"] == []


def test_get_does_not_start_evidence_downloads(evidence_web):
    assert request(evidence_web, "/api/evidence").status == 404
