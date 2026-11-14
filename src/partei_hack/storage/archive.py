"""Archivierung dekodierter JSON-Antworten, unabhängig vom Antwortcache."""

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4


def archive_response(directory: Path, payload: dict[str, Any]) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    path = directory / f"{stamp}_{uuid4().hex}.json"
    with path.open("x", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return path
