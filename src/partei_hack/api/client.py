"""Konservativer, synchroner Client für die öffentliche abgeordnetenwatch-API."""

import re
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import httpx
from pydantic import ValidationError

from partei_hack import __version__
from partei_hack.api.official import official_url
from partei_hack.config import (
    API_BASE_URL,
    CACHE_TTL_SECONDS,
    MIN_REQUEST_INTERVAL,
    PAGE_SIZE,
)
from partei_hack.models import validate_entity
from partei_hack.storage.archive import archive_response
from partei_hack.storage.database import Database, utc_now


class APIError(RuntimeError):
    """Nicht erfolgreich oder nicht zuverlässig interpretierbare API-Antwort."""


@dataclass(frozen=True)
class Response:
    payload: dict[str, Any]
    source_url: str
    fetched_at: str


@dataclass(frozen=True)
class Page:
    items: list[dict[str, Any]]
    total: int
    source_url: str
    fetched_at: str


class APIClient:
    def __init__(
        self,
        database: Database,
        raw_dir: Path,
        *,
        refresh: bool = False,
        http_client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        page_size: int = PAGE_SIZE,
    ):
        if not 1 <= page_size <= 1000:
            raise ValueError("page_size muss zwischen 1 und 1000 liegen.")
        self.database = database
        self.raw_dir = raw_dir
        self.refresh = refresh
        self.page_size = page_size
        self._sleep = sleep
        self._clock = clock
        self._last_request: float | None = None
        self._owns_http = http_client is None
        self._http = http_client or httpx.Client(
            timeout=30.0,
            follow_redirects=False,
            headers={
                "User-Agent": f"ParteiHack/{__version__} (local research; fair-use client)",
                "Accept": "application/json",
            },
        )

    def __enter__(self) -> "APIClient":
        return self

    def __exit__(self, *_: object) -> None:
        if self._owns_http:
            self._http.close()

    def _throttle(self) -> None:
        if self._last_request is not None:
            remaining = MIN_REQUEST_INTERVAL - (self._clock() - self._last_request)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request = self._clock()

    @staticmethod
    def _retry_delay(response: httpx.Response, attempt: int) -> float:
        delay = 60.0 if response.status_code == 429 else float(2**attempt)
        header = response.headers.get("Retry-After")
        if header:
            try:
                parsed = float(header)
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(header)
                    if retry_at.tzinfo is None:
                        retry_at = retry_at.replace(tzinfo=UTC)
                    parsed = (retry_at - datetime.now(UTC)).total_seconds()
                except (TypeError, ValueError, OverflowError):
                    parsed = 0.0
            delay = max(delay, parsed)
        return delay

    def _request(self, url: str) -> httpx.Response:
        for attempt in range(4):
            self._throttle()
            try:
                response = self._http.get(url)
            except httpx.TransportError as exc:
                if attempt == 3:
                    raise APIError(f"Netzwerkfehler nach vier Versuchen: {url}") from exc
                self._sleep(float(2**attempt))
                continue
            if response.status_code in {429, 500, 502, 503, 504} and attempt < 3:
                self._sleep(self._retry_delay(response, attempt))
                continue
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                raise APIError(f"HTTP {response.status_code}: {url}") from exc
            return response
        raise AssertionError("Unreachable")

    def get(self, resource: str, params: dict[str, Any] | None = None) -> Response:
        if not re.fullmatch(r"[a-z-]+(?:/[1-9][0-9]*)?", resource):
            raise ValueError("Nur relative Ressourcen und positive IDs sind erlaubt.")
        query = httpx.QueryParams(sorted((params or {}).items()))
        url = str(httpx.URL(API_BASE_URL + resource, params=query))
        if not self.refresh:
            cached = self.database.get_cached(url, CACHE_TTL_SECONDS)
            if cached is not None:
                return Response(cached[0], url, cached[1])
        response = self._request(url)
        try:
            payload = response.json()
        except ValueError as exc:
            raise APIError(f"Keine gültige JSON-Antwort: {url}") from exc
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("meta"), dict)
            or payload["meta"].get("status") != "ok"
            or not isinstance(payload.get("data"), (dict, list))
        ):
            raise APIError(f"Unerwartetes Antwortformat oder API-Fehler: {url}")
        fetched_at = utc_now()
        archive_response(self.raw_dir, payload)
        self.database.cache_response(url, payload, fetched_at)
        return Response(payload, url, fetched_at)

    def get_entity(self, resource: str, entity_id: int) -> Response:
        response = self.get(f"{resource}/{entity_id}")
        payload = response.payload["data"]
        try:
            validate_entity(payload)
        except (ValidationError, TypeError) as exc:
            raise APIError(f"Ungültige Einzelentität: {response.source_url}") from exc
        if payload["id"] != entity_id:
            raise APIError("API lieferte eine andere ID als angefordert.")
        return response

    def download_program(self, url: str) -> bytes:
        """Nur explizit ausgewählte, bei abgeordnetenwatch gehostete Original-PDFs."""
        parsed = httpx.URL(url)
        if (
            parsed.scheme != "https"
            or parsed.host != "www.abgeordnetenwatch.de"
            or parsed.port not in (None, 443)
            or parsed.username
            or parsed.password
            or not parsed.path.startswith("/sites/default/files/")
        ):
            raise ValueError(
                "Automatischer Download nur von abgeordnetenwatch.de/sites/default/files/. "
                "Andere Quellen bitte als lokale PDF mit --program-file angeben."
            )
        response = self._request(str(parsed))
        if len(response.content) > 50 * 1024 * 1024:
            raise ValueError("Programm-PDF überschreitet 50 MiB.")
        if not response.content.startswith(b"%PDF-"):
            raise ValueError("Programmquelle lieferte keine PDF-Datei.")
        return response.content

    def download_official(self, url: str) -> tuple[bytes, str]:
        """Explizite amtliche Belege, gleiche Drosselung/Retry, keine Redirects."""
        canonical = official_url(url)
        response = self._request(canonical)
        if len(response.content) > 15 * 1024 * 1024:
            raise ValueError("Amtlicher Einzelbeleg überschreitet 15 MiB.")
        return response.content, response.headers.get("Content-Type", "")

    def iter_pages(
        self,
        resource: str,
        params: dict[str, Any] | None = None,
        *,
        max_items: int | None = None,
    ) -> Iterator[Page]:
        if max_items is not None and max_items < 1:
            raise ValueError("max_items muss positiv sein.")
        offset = 0
        seen: set[int] = set()
        initial_total: int | None = None
        while True:
            size = self.page_size
            if max_items is not None:
                size = min(size, max_items - offset)
            query = dict(params or {})
            # Trotz des Namens ist range_end die Anzahl, nicht offset + Anzahl.
            query.update(range_start=offset, range_end=size)
            response = self.get(resource, query)
            data = response.payload["data"]
            result = response.payload["meta"].get("result")
            if not isinstance(data, list) or not isinstance(result, dict):
                raise APIError("Listenantwort ohne gültige Daten oder Pagination.")
            total, count = result.get("total"), result.get("count")
            if (
                type(total) is not int
                or total < 0
                or type(count) is not int
                or count != len(data)
                or len(data) > size
                or offset + len(data) > total
                or result.get("range_start", offset) != offset
            ):
                raise APIError(
                    "Inkonsistente Pagination; Import wird nicht als vollständig gewertet."
                )
            if initial_total is not None and total != initial_total:
                raise APIError("Ergebnisanzahl hat sich während der Pagination verändert.")
            initial_total = total
            if not data and offset < total:
                raise APIError("Leere Seite vor dem gemeldeten Ende.")
            for item in data:
                try:
                    validate_entity(item)
                except (ValidationError, TypeError) as exc:
                    raise APIError("Ungültige Entität in Listenantwort.") from exc
                if item["id"] in seen:
                    raise APIError("Wiederholte ID während der Pagination.")
                seen.add(item["id"])
            yield Page(data, total, response.source_url, response.fetched_at)
            offset += len(data)
            if offset >= total or (max_items is not None and offset >= max_items):
                return
