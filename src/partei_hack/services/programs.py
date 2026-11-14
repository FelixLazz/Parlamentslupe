"""Original-PDF, Prüfsumme und extrahierte PDF-Seiten ohne Cloud oder OCR."""

import hashlib
import io
import json
import re
from pathlib import Path
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from partei_hack.api.client import APIClient
from partei_hack.storage.database import utc_now


class ProgramFileMissingError(ValueError):
    def __init__(self, path: Path, sha256: str):
        super().__init__(f"Programmdatei fehlt lokal: {path}")
        self.sha256 = sha256


def clean_text(text: str) -> str:
    text = text.replace("\xad", "")
    text = re.sub(r"(?<=\w)[ \t]*-\s*\n\s*(?=\w)", "", text)
    return " ".join(text.split())


def pdf_pages(content: bytes) -> list[dict[str, Any]]:
    if not content.startswith(b"%PDF-") or len(content) > 50 * 1024 * 1024:
        raise ValueError("Keine gültige Programm-PDF oder größer als 50 MiB.")
    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            raise ValueError("Verschlüsselte Programme werden nicht unterstützt.")
        if len(reader.pages) > 1000:
            raise ValueError("PDF hat mehr als 1000 Seiten.")
        pages = [
            {"number": number, "text": clean_text(page.extract_text() or "")}
            for number, page in enumerate(reader.pages, 1)
        ]
    except (PyPdfError, KeyError, RecursionError) as exc:
        raise ValueError("Programm-PDF konnte nicht zuverlässig gelesen werden.") from exc
    if sum(len(page["text"]) for page in pages) < 80:
        raise ValueError("PDF enthält zu wenig lesbaren Text. OCR ist noch nicht implementiert.")
    return pages


def program_directory(data_dir: Path, program_id: int) -> Path:
    return data_dir / "programs" / str(program_id)


def load_program(data_dir: Path, program: dict[str, Any]) -> dict[str, Any] | None:
    directory = program_directory(data_dir, program["id"])
    if not directory.exists():
        return None
    documents = []
    for manifest in directory.glob("*.json"):
        document = json.loads(manifest.read_text(encoding="utf-8"))
        if (
            not isinstance(document, dict)
            or document.get("schema_version") != 1
            or document.get("origin") not in {"local_file", "api_hosted_pdf"}
            or not isinstance(document.get("imported_at"), str)
            or "source_url" not in document
        ):
            raise ValueError(f"Ungültige Programm-Metadaten: {manifest}")
        digest = document.get("sha256", "")
        if not re.fullmatch(r"[a-f0-9]{64}", digest):
            raise ValueError(f"Ungültige Programm-Prüfsumme: {manifest}")
        if (
            document.get("program_id") != program["id"]
            or document.get("election_id") != (program.get("parliament_period") or {}).get("id")
            or document.get("party_id") != (program.get("party") or {}).get("id")
        ):
            raise ValueError(f"Programm-Metadaten passen nicht zur API-Auswahl: {manifest}")
        pdf = directory / f"{digest}.pdf"
        if not pdf.exists():
            raise ProgramFileMissingError(pdf, digest)
        if hashlib.sha256(pdf.read_bytes()).hexdigest() != digest:
            raise ValueError(f"Programmdatei wurde verändert: {pdf}")
        # Textcache ist keine Quelle: Seiten erneut aus dem geprüften Original lesen.
        document["pages"] = pdf_pages(pdf.read_bytes())
        document["pdf_path"] = str(pdf.resolve())
        documents.append(document)
    if len(documents) > 1:
        raise ValueError(
            "Mehrere lokale Dokumentversionen. Gewünschte Original-PDF mit --program-file wählen."
        )
    return documents[0] if documents else None


def prepare_program(
    data_dir: Path,
    program: dict[str, Any],
    *,
    client: APIClient | None = None,
    local_file: Path | None = None,
) -> dict[str, Any]:
    missing_digest = None
    if local_file is None:
        try:
            cached = load_program(data_dir, program)
        except ProgramFileMissingError as exc:
            if client is None:
                raise
            cached = None
            missing_digest = exc.sha256
        if cached is not None:
            return cached
        if client is None:
            raise ValueError(
                "Programmtext fehlt lokal. --online lädt die ausgewählte API-PDF, "
                "alternativ --program-file ORIGINAL.pdf."
            )
        source_url = program.get("file")
        if not source_url:
            raise ValueError("Kein PDF-Download in der API. --program-file ORIGINAL.pdf verwenden.")
        content = client.download_program(source_url)
    else:
        if local_file.stat().st_size > 50 * 1024 * 1024:
            raise ValueError("Programm-PDF überschreitet 50 MiB.")
        content = local_file.read_bytes()
        source_url = program.get("file")
    pages = pdf_pages(content)
    digest = hashlib.sha256(content).hexdigest()
    if missing_digest is not None and digest != missing_digest:
        raise ValueError(
            "Die Quelle liefert eine andere PDF-Version als das lokale Manifest. "
            "Die fehlende Originalversion wird nicht stillschweigend ersetzt."
        )
    directory = program_directory(data_dir, program["id"])
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{digest}.pdf"
    if not path.exists():
        with path.open("xb") as handle:
            handle.write(content)
    elif path.read_bytes() != content:
        raise ValueError("Datei am Prüfsummenpfad stimmt nicht mit dem Original überein.")
    document = {
        "schema_version": 1,
        "extractor": "pypdf",
        "program_id": program["id"],
        "election_id": (program.get("parliament_period") or {}).get("id"),
        "party_id": (program.get("party") or {}).get("id"),
        "sha256": digest,
        "source_url": source_url,
        "origin": "local_file" if local_file is not None else "api_hosted_pdf",
        "original_local_file": str(local_file.resolve()) if local_file else None,
        "imported_at": utc_now(),
        "pdf_path": str(path.resolve()),
        "pages": pages,
    }
    manifest = directory / f"{digest}.json"
    if not manifest.exists():
        with manifest.open("x", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
    if missing_digest is not None:
        restored = load_program(data_dir, program)
        if restored is None:
            raise ValueError("Die wiederhergestellte Original-PDF konnte nicht geprüft werden.")
        return restored
    return document
