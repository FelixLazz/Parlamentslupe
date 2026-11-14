"""Loopback-Webserver ohne Framework, externe Assets oder automatische Importe."""

import json
import logging
import secrets
import socket
import sqlite3
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlsplit

from partei_hack.api.client import APIClient, APIError
from partei_hack.config import MIN_REQUEST_INTERVAL, Settings
from partei_hack.services.evidence import enrich_period
from partei_hack.services.importer import Importer
from partei_hack.services.workspace import (
    ProgramMissingError,
    analysis,
    catalog,
    choices,
    comparison,
    entity,
    poll_detail,
    prepare_choices,
    program_options,
    program_passages,
    refresh_catalog,
    run_selection,
    selected_document,
    selected_program,
    selection,
)
from partei_hack.storage.database import Database

logger = logging.getLogger(__name__)
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}
SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; object-src 'none'; "
        "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
    ),
}
MAX_BODY_BYTES = 65536
WEB_API_VERSION = 1


class LoopbackHTTPServer(ThreadingHTTPServer):
    # Windows' SO_REUSEADDR kann mehrere aktive Listener auf demselben Port erlauben.
    allow_reuse_address = False
    allow_reuse_port = False

    def server_bind(self) -> None:
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


@dataclass
class Response:
    status: int
    body: bytes
    content_type: str = "application/json; charset=utf-8"


def json_response(payload: Any, status: int = 200) -> Response:
    return Response(status, json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def positive_id(value: Any) -> int:
    if isinstance(value, bool) or not str(value).isascii() or not str(value).isdigit():
        raise ValueError("Bitte eine positive ganzzahlige ID angeben.")
    number = int(value)
    if not 1 <= number <= 2**63 - 1:
        raise ValueError("ID außerhalb des zulässigen Bereichs.")
    return number


class WebApplication:
    def __init__(self, settings: Settings, port: int):
        self.settings = settings
        self.hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
        self.token = secrets.token_urlsafe(32)
        self.online_lock = threading.Lock()
        self.last_online_end: float | None = None

    def handle(self, method: str, target: str, headers: Any, body: bytes = b"") -> Response:
        host = headers.get("Host", "")
        if host not in self.hosts:
            return json_response({"error": "Nur lokaler Zugriff ist erlaubt."}, 403)
        if method not in {"GET", "POST"}:
            return json_response({"error": "Methode nicht erlaubt."}, 405)
        if method == "POST":
            origin = headers.get("Origin")
            if (
                headers.get("X-ParteiHack-Token") != self.token
                or (origin is not None and origin != f"http://{host}")
                or headers.get("Sec-Fetch-Site") == "cross-site"
            ):
                return json_response({"error": "Ungültige lokale Anfrage."}, 403)
            if headers.get("Content-Type", "").split(";")[0] != "application/json":
                return json_response({"error": "JSON-Anfrage erforderlich."}, 415)
        parsed = urlsplit(target)
        if method == "GET" and parsed.path in ASSETS:
            filename, content_type = ASSETS[parsed.path]
            return Response(200, Path(__file__).with_name(filename).read_bytes(), content_type)
        try:
            query = parse_qs(parsed.query, keep_blank_values=True, max_num_fields=12)
            if any(len(values) != 1 for values in query.values()):
                raise ValueError("Doppelte Abfrageparameter sind nicht erlaubt.")
            params = {key: values[0] for key, values in query.items()}
            if len(params.get("search", "")) > 200:
                raise ValueError("Suchtext bitte auf 200 Zeichen begrenzen.")
            with Database(self.settings.database_path) as database:
                if method == "GET":
                    return self._get(database, parsed.path, params)
                if len(body) > MAX_BODY_BYTES:
                    return json_response({"error": "Anfrage zu groß."}, 413)
                payload = json.loads(body)
                if not isinstance(payload, dict):
                    raise ValueError("JSON-Objekt erforderlich.")
                return self._post(database, parsed.path, payload)
        except ProgramMissingError as exc:
            return json_response({"error": str(exc), "code": "program_missing"}, 409)
        except (ValueError, TypeError, KeyError) as exc:
            return json_response({"error": str(exc)}, 400)
        except APIError as exc:
            return json_response({"error": str(exc)}, 502)
        except (OSError, sqlite3.Error, RuntimeError):
            logger.exception("Lokale Webanfrage fehlgeschlagen")
            return json_response(
                {"error": "Lokale Daten konnten nicht gelesen werden. Details im Terminal."}, 500
            )

    def _get(self, database: Database, path: str, params: dict[str, str]) -> Response:
        if path == "/api/catalog":
            return json_response(
                {**catalog(database), "token": self.token, "web_api_version": WEB_API_VERSION}
            )
        if path not in {
            "/api/analysis",
            "/api/poll",
            "/api/program",
            "/api/compare",
            "/api/choices",
        }:
            return json_response({"error": "Nicht gefunden."}, 404)
        period_id = positive_id(params.get("period"))
        if path == "/api/choices":
            return json_response(choices(database, self.settings.data_dir, period_id))
        fraction_id = positive_id(params.get("fraction"))
        poll_ids = (
            [positive_id(value) for value in params["polls"].split(",")]
            if params.get("polls")
            else None
        )
        if path == "/api/analysis":
            return json_response(
                program_options(
                    self.settings.data_dir,
                    analysis(
                        database,
                        period_id,
                        fraction_id,
                        search=params.get("search", ""),
                        since=params.get("since", ""),
                        until=params.get("until", ""),
                        poll_ids=poll_ids,
                    ),
                )
            )
        if path == "/api/poll":
            return json_response(
                poll_detail(database, period_id, fraction_id, positive_id(params.get("poll")))
            )
        if path == "/api/compare":
            return json_response(
                comparison(
                    database,
                    self.settings.data_dir,
                    period_id,
                    fraction_id,
                    positive_id(params.get("program")),
                    poll_ids=poll_ids,
                )
            )
        return json_response(
            program_passages(
                database,
                self.settings.data_dir,
                period_id,
                fraction_id,
                positive_id(params.get("program")),
                page=positive_id(params.get("page", 1)),
            )
        )

    def _post(self, database: Database, path: str, payload: dict[str, Any]) -> Response:
        if path not in {
            "/api/refresh",
            "/api/import",
            "/api/program",
            "/api/compare",
            "/api/evidence",
            "/api/prepare",
            "/api/run",
        }:
            return json_response({"error": "Nicht gefunden."}, 404)
        if payload.get("confirm_online") is not True:
            raise ValueError("Online-Abruf muss ausdrücklich bestätigt werden.")
        parent_id = None
        scope_poll_ids = None
        if path == "/api/prepare":
            period_id = positive_id(payload.get("period"))
            period = entity(database, "parliament-periods", period_id)
            if period.get("type") != "legislature":
                raise ValueError("Bitte eine Legislaturperiode auswählen.")
        elif path == "/api/run":
            period_id = positive_id(payload.get("period"))
            fraction_id = positive_id(payload.get("fraction"))
            selection(database, period_id, fraction_id)
            program_id = (
                positive_id(payload["program"]) if payload.get("program") is not None else None
            )
            if program_id is not None:
                selected_program(database, period_id, fraction_id, program_id)
            all_polls = payload.get("all_polls", False)
            if not isinstance(all_polls, bool):
                raise ValueError("all_polls muss ein Wahrheitswert sein.")
            available = choices(database, self.settings.data_dir, period_id)
            if all_polls:
                if payload.get("poll_ids") not in (None, []):
                    raise ValueError("Entweder alle oder einzelne Abstimmungen auswählen.")
                if not available["coverage"]["poll_list_complete_against_api"]:
                    raise ValueError("Für „Alle“ zuerst die vollständigen Auswahldaten laden.")
                poll_ids = [poll["id"] for poll in available["polls"]]
            else:
                raw_ids = payload.get("poll_ids")
                if not isinstance(raw_ids, list) or len(raw_ids) > 5000:
                    raise ValueError("Bitte eine Liste mit höchstens 5000 Abstimmungen auswählen.")
                poll_ids = [positive_id(value) for value in raw_ids]
            if not poll_ids or len(set(poll_ids)) != len(poll_ids):
                raise ValueError("Mindestens eine Abstimmung auswählen; keine doppelten IDs.")
            if not set(poll_ids) <= {poll["id"] for poll in available["polls"]}:
                raise ValueError("Abstimmung gehört nicht zur ausgewählten Wahlperiode.")
        elif path == "/api/refresh":
            scope = payload.get("scope")
            if scope not in {"parliaments", "periods", "fractions", "programs"}:
                raise ValueError("Unbekannte Stammdaten-Auswahl.")
            if scope != "parliaments":
                parent_id = positive_id(payload.get("parent"))
        elif path == "/api/import":
            period_id = positive_id(payload.get("period"))
            period = entity(database, "parliament-periods", period_id)
            if period.get("type") != "legislature":
                raise ValueError("Bitte eine Legislaturperiode auswählen.")
            max_polls = positive_id(payload.get("max_polls"))
            if max_polls > 5:
                raise ValueError("Die Stichprobenroute erlaubt höchstens fünf Polls pro Import.")
        else:
            period_id = positive_id(payload.get("period"))
            fraction_id = positive_id(payload.get("fraction"))
            program_id = positive_id(payload.get("program"))
            selected_program(database, period_id, fraction_id, program_id)
            if path in {"/api/compare", "/api/evidence"} and "poll_ids" in payload:
                raw_ids = payload["poll_ids"]
                if not isinstance(raw_ids, list) or not 1 <= len(raw_ids) <= 5000:
                    raise ValueError("Bitte eine nicht leere Abstimmungsauswahl angeben.")
                scope_poll_ids = [positive_id(value) for value in raw_ids]
                if len(set(scope_poll_ids)) != len(scope_poll_ids):
                    raise ValueError("Doppelte Abstimmungen sind nicht erlaubt.")
                for poll_id in scope_poll_ids:
                    poll = entity(database, "polls", poll_id)
                    if (poll.get("field_legislature") or {}).get("id") != period_id:
                        raise ValueError("Abstimmung gehört nicht zur ausgewählten Wahlperiode.")
            if path == "/api/evidence":
                max_polls = positive_id(payload.get("max_polls", 5))
                max_documents = positive_id(payload.get("max_documents", 3))
                if max_polls > 5 or max_documents > 3:
                    raise ValueError("Webrecherche: höchstens fünf Polls und drei amtliche Belege.")
            load_votes = payload.get("load_votes", False)
            if not isinstance(load_votes, bool):
                raise ValueError("load_votes muss ein Wahrheitswert sein.")
            if path == "/api/compare" and load_votes:
                max_polls = positive_id(payload.get("max_polls"))
                if max_polls > 5:
                    raise ValueError(
                        "Die Stichprobenroute erlaubt höchstens fünf Polls pro Import."
                    )
        if not self.online_lock.acquire(blocking=False):
            return json_response({"error": "Ein Online-Abruf läuft bereits. Bitte warten."}, 409)
        try:
            # Neue Clients dürfen das Limit auch zwischen zwei Aktionen nicht unterschreiten.
            if self.last_online_end is not None:
                remaining = MIN_REQUEST_INTERVAL - (time.monotonic() - self.last_online_end)
                if remaining > 0:
                    time.sleep(remaining)
            with APIClient(database, self.settings.raw_dir) as client:
                if path == "/api/prepare":
                    return json_response(
                        prepare_choices(client, database, self.settings.data_dir, period_id)
                    )
                if path == "/api/run":
                    return json_response(
                        run_selection(
                            client,
                            database,
                            self.settings.data_dir,
                            period_id,
                            fraction_id,
                            poll_ids,
                            program_id,
                        )
                    )
                if path == "/api/refresh":
                    return json_response(refresh_catalog(client, database, scope, parent_id))
                if path == "/api/evidence":
                    enrichment = enrich_period(
                        client,
                        database,
                        period_id,
                        max_polls=max_polls,
                        max_documents=max_documents,
                    )
                    result = comparison(
                        database,
                        self.settings.data_dir,
                        period_id,
                        fraction_id,
                        program_id,
                        poll_ids=scope_poll_ids,
                    )
                    return json_response({**result, "enrichment": enrichment})
                if path == "/api/program":
                    document = selected_document(
                        database,
                        self.settings.data_dir,
                        period_id,
                        fraction_id,
                        program_id,
                        client=client,
                    )
                    return json_response(
                        program_passages(
                            database,
                            self.settings.data_dir,
                            period_id,
                            fraction_id,
                            program_id,
                            document=document,
                        )
                    )
                if path == "/api/compare":
                    if load_votes:
                        Importer(client, database).sync_period(
                            period_id, max_polls=max_polls, with_votes=True
                        )
                    return json_response(
                        comparison(
                            database,
                            self.settings.data_dir,
                            period_id,
                            fraction_id,
                            program_id,
                            client=client,
                            poll_ids=scope_poll_ids,
                        )
                    )
                result = Importer(client, database).sync_period(
                    period_id, max_polls=max_polls, with_votes=True
                )
                return json_response(result)
        finally:
            self.last_online_end = time.monotonic()
            self.online_lock.release()


def create_server(settings: Settings, port: int = 8000) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            self.respond("GET")

        def do_POST(self) -> None:
            self.respond("POST")

        def respond(self, method: str) -> None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = -1
            if not 0 <= length <= MAX_BODY_BYTES or self.headers.get("Transfer-Encoding"):
                response = json_response({"error": "Ungültige Anfragegröße."}, 413)
            else:
                response = application.handle(
                    method, self.path, self.headers, self.rfile.read(length) if length else b""
                )
            try:
                self.send_response(response.status)
                self.send_header("Content-Type", response.content_type)
                self.send_header("Content-Length", str(len(response.body)))
                for name, value in SECURITY_HEADERS.items():
                    self.send_header(name, value)
                self.end_headers()
                self.wfile.write(response.body)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                self.close_connection = True

        def log_message(self, format: str, *args: Any) -> None:
            logger.info(format, *args)

    server = LoopbackHTTPServer(("127.0.0.1", port), Handler)
    application = WebApplication(settings, server.server_port)
    return server
