from pathlib import Path

import httpx
import pytest

from partei_hack.api.client import APIClient, APIError
from partei_hack.storage.database import Database
from tests.conftest import Clock, envelope


def client_for(database: Database, tmp_path: Path, clock: Clock, handler, **kwargs) -> APIClient:
    return APIClient(
        database,
        tmp_path / "raw",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=clock.sleep,
        clock=clock.monotonic,
        **kwargs,
    )


def test_cache_preserves_timestamp_and_does_not_duplicate_archive(database, tmp_path, clock):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=envelope([]))

    client = client_for(database, tmp_path, clock, handler)
    first = client.get("polls", {"range_end": 1, "range_start": 0})
    second = client.get("polls", {"range_start": 0, "range_end": 1})
    assert first == second
    assert len(calls) == 1
    assert len(list((tmp_path / "raw").glob("*.json"))) == 1
    assert clock.sleeps == []


def test_refresh_bypasses_cache(database, tmp_path, clock):
    client = client_for(
        database, tmp_path, clock, lambda req: httpx.Response(200, json=envelope([])), refresh=True
    )
    client.get("polls")
    client.get("polls")
    assert len(list((tmp_path / "raw").glob("*.json"))) == 2
    assert clock.sleeps == pytest.approx([2.1])


def test_pagination_uses_ranges_and_validates_total(database, tmp_path, clock):
    requests = []

    def handler(request):
        requests.append(request)
        start = int(request.url.params["range_start"])
        items = [
            {"id": item, "label": f"Test {item}"} for item in range(start + 1, min(start + 3, 4))
        ]
        return httpx.Response(200, json=envelope(items, total=3, start=start))

    client = client_for(database, tmp_path, clock, handler, page_size=2)
    pages = list(client.iter_pages("polls"))
    assert [item["id"] for page in pages for item in page.items] == [1, 2, 3]
    assert [dict(req.url.params) for req in requests] == [
        {"range_end": "2", "range_start": "0"},
        {"range_end": "2", "range_start": "2"},
    ]
    assert clock.sleeps == pytest.approx([2.1])


def test_range_end_is_page_size_even_when_offset_is_nonzero(database, tmp_path, clock):
    def handler(request):
        start = int(request.url.params["range_start"])
        size = int(request.url.params["range_end"])
        items = [{"id": item + 1, "label": "Test"} for item in range(start, start + size)]
        return httpx.Response(200, json=envelope(items, total=3, start=start))

    client = client_for(database, tmp_path, clock, handler, page_size=1)
    pages = list(client.iter_pages("polls", max_items=2))
    assert [item["id"] for page in pages for item in page.items] == [1, 2]


def test_max_items_limits_actual_request(database, tmp_path, clock):
    urls = []

    def handler(request):
        urls.append(request.url)
        return httpx.Response(200, json=envelope([{"id": 1, "label": "Test"}], total=50))

    client = client_for(database, tmp_path, clock, handler)
    pages = list(client.iter_pages("polls", max_items=1))
    assert len(pages) == 1
    assert urls[0].params["range_end"] == "1"
    assert pages[0].total == 50


@pytest.mark.parametrize(
    "payload",
    [
        envelope([], total=3),
        {"meta": {"status": "ok", "result": {"count": 2, "total": 2}}, "data": []},
        {"meta": {"status": "ok", "result": {"count": 0, "total": "0"}}, "data": []},
        envelope([{"id": "1", "label": "Test"}]),
        envelope([{"id": 1}]),
    ],
)
def test_invalid_pages_fail(database, tmp_path, clock, payload):
    client = client_for(database, tmp_path, clock, lambda req: httpx.Response(200, json=payload))
    with pytest.raises(APIError):
        list(client.iter_pages("polls"))


def test_repeated_ids_fail(database, tmp_path, clock):
    def handler(request):
        start = int(request.url.params["range_start"])
        return httpx.Response(
            200, json=envelope([{"id": 1, "label": "Test"}], total=2, start=start)
        )

    client = client_for(database, tmp_path, clock, handler, page_size=1)
    with pytest.raises(APIError, match="Wiederholte"):
        list(client.iter_pages("polls"))


def test_changing_total_fails(database, tmp_path, clock):
    def handler(request):
        start = int(request.url.params["range_start"])
        return httpx.Response(
            200,
            json=envelope([{"id": start + 1, "label": "Test"}], total=2 + start, start=start),
        )

    client = client_for(database, tmp_path, clock, handler, page_size=1)
    with pytest.raises(APIError, match="verändert"):
        list(client.iter_pages("polls"))


def test_429_respects_retry_after(database, tmp_path, clock):
    responses = iter(
        [
            httpx.Response(429, headers={"Retry-After": "70"}),
            httpx.Response(200, json=envelope([])),
        ]
    )
    client = client_for(database, tmp_path, clock, lambda req: next(responses))
    client.get("polls")
    assert clock.sleeps == [70.0]


def test_repeated_server_error_is_finite_and_not_cached(database, tmp_path, clock):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(503)

    client = client_for(database, tmp_path, clock, handler)
    with pytest.raises(APIError, match="503"):
        client.get("polls")
    assert len(calls) == 4
    assert database.connection.execute("SELECT COUNT(*) FROM http_cache").fetchone()[0] == 0
    assert not (tmp_path / "raw").exists()


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, text="<html>Not JSON</html>"),
        httpx.Response(200, json={"meta": {"status": "error"}, "data": []}),
        httpx.Response(200, json=[]),
        httpx.Response(404),
    ],
)
def test_invalid_responses_are_not_cached(database, tmp_path, clock, response):
    client = client_for(database, tmp_path, clock, lambda req: response)
    with pytest.raises(APIError):
        client.get("polls")
    assert database.connection.execute("SELECT COUNT(*) FROM http_cache").fetchone()[0] == 0


def test_resource_cannot_escape_api_host(database, tmp_path, clock):
    client = client_for(database, tmp_path, clock, lambda req: pytest.fail("Unexpected request"))
    with pytest.raises(ValueError):
        client.get("https://invalid.example")


def test_single_entity_id_is_checked(database, tmp_path, clock):
    client = client_for(
        database,
        tmp_path,
        clock,
        lambda req: httpx.Response(200, json=envelope({"id": 2, "label": "Wrong"})),
    )
    with pytest.raises(APIError, match="andere ID"):
        client.get_entity("polls", 1)
