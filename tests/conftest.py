"""Synthetische Fixtures; jeder unbeabsichtigte externe Netzwerkzugriff scheitert."""

import socket
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from partei_hack.api.client import APIClient
from partei_hack.storage.database import Database


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Netzwerkzugriff in Offline-Test blockiert.")

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)


@pytest.fixture
def database(tmp_path: Path) -> Iterator[Database]:
    with Database(tmp_path / "test.sqlite3") as db:
        yield db


def envelope(
    data: dict[str, Any] | list[dict[str, Any]], *, total: int | None = None, start: int = 0
) -> dict[str, Any]:
    result = (
        {"count": len(data), "total": len(data) if total is None else total, "range_start": start}
        if isinstance(data, list)
        else {"entity_id": str(data["id"])}
    )
    return {"meta": {"status": "ok", "result": result}, "data": data}


class Clock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        self.now += seconds


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def dataset() -> dict[str, list[dict[str, Any]]]:
    """Bewusst fiktive Namen und IDs; keine tatsächlichen politischen Aussagen."""
    return {
        "parliament-periods": [
            {
                "id": 9001,
                "label": "Test-Legislatur",
                "type": "legislature",
                "parliament": {"id": 999},
                "previous_period": {"id": 9002},
            },
            {
                "id": 9002,
                "label": "Test-Wahl",
                "type": "election",
                "parliament": {"id": 999},
            },
        ],
        "candidacies-mandates": [
            {
                "id": 9011,
                "label": "Testperson Alpha – Test-Legislatur",
                "type": "mandate",
                "parliament_period": {"id": 9001},
                "politician": {"id": 9021, "label": "Testperson Alpha"},
                "end_date": "2024-05-01",
            }
        ],
        "fractions": [
            {"id": 9031, "label": "Testfraktion", "legislature": {"id": 9001}},
        ],
        "polls": [
            {
                "id": 9041,
                "label": "Test: Öffentlicher Verkehr",
                "field_legislature": {"id": 9001},
                "field_poll_date": "2024-01-01",
                "field_accepted": False,
                "field_topics": [{"id": 9061}],
            },
            {
                "id": 9042,
                "label": "Test: Energie",
                "field_legislature": {"id": 9001},
                "field_poll_date": "2024-02-01",
                "field_accepted": True,
                "field_topics": [],
            },
        ],
        "votes": [
            {
                "id": 9051,
                "label": "Teststimme Alpha",
                "poll": {"id": 9041},
                "mandate": {"id": 9011},
                "fraction": {"id": 9031, "label": "Testfraktion"},
                "vote": "no_show",
                "reason_no_show": "fell_ill",
            },
            {
                "id": 9052,
                "label": "Teststimme Beta",
                "poll": {"id": 9042},
                "mandate": {"id": 9011},
                "fraction": {"id": 9031, "label": "Testfraktion"},
                "vote": "yes",
            },
        ],
        "election-program": [
            {
                "id": 9071,
                "label": "Testprogramm",
                "parliament_period": {"id": 9002},
                "party": {"id": 9081},
                "file": "https://invalid.example/synthetic.pdf",
            }
        ],
    }


@pytest.fixture
def dataset_client(database: Database, tmp_path: Path, clock: Clock, dataset: dict):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        parts = request.url.path.removeprefix("/api/v2/").split("/")
        resource = parts[0]
        if len(parts) == 2:
            data = next(item for item in dataset[resource] if item["id"] == int(parts[1]))
            return httpx.Response(200, json=envelope(data))
        data = dataset[resource]
        if resource == "votes":
            data = [item for item in data if item["poll"]["id"] == int(request.url.params["poll"])]
        start = int(request.url.params.get("range_start", 0))
        end = start + int(request.url.params.get("range_end", 1000))
        return httpx.Response(200, json=envelope(data[start:end], total=len(data), start=start))

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        with APIClient(
            database,
            tmp_path / "raw",
            http_client=http,
            sleep=clock.sleep,
            clock=clock.monotonic,
        ) as client:
            yield client, requests
