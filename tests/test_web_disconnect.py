"""Clientabbrüche beim Header- und Bodyversand ohne Netzverbindung prüfen."""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from partei_hack.config import Settings
from partei_hack.web import server


@pytest.mark.parametrize("stage", ["headers", "body"])
@pytest.mark.parametrize("error", [ConnectionResetError, BrokenPipeError, ConnectionAbortedError])
def test_disconnect_closes_connection_without_traceback(tmp_path, monkeypatch, stage, error):
    def fake_server(address, handler):
        return SimpleNamespace(server_port=8000, RequestHandlerClass=handler)

    monkeypatch.setattr(server, "LoopbackHTTPServer", fake_server)
    monkeypatch.setattr(
        server.WebApplication, "handle", lambda *args: server.Response(200, b"test")
    )
    http = server.create_server(Settings.resolve(tmp_path))
    handler = object.__new__(http.RequestHandlerClass)
    handler.headers = {}
    handler.path = "/"
    handler.close_connection = False
    handler.send_response = Mock()
    handler.send_header = Mock()
    handler.end_headers = Mock(side_effect=error() if stage == "headers" else None)
    handler.wfile = SimpleNamespace(write=Mock(side_effect=error() if stage == "body" else None))

    handler.respond("GET")

    assert handler.close_connection is True
    if stage == "headers":
        handler.wfile.write.assert_not_called()
