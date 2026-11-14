import hashlib
import io
import json
from pathlib import Path

import httpx
import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from partei_hack.api.client import APIError
from partei_hack.services.programs import load_program, pdf_pages, prepare_program
from tests.test_api_client import client_for

TEST_TEXT = (
    "Wir wollen den öffentlichen Verkehr ausbauen und die Mobilität durch zuverlässige "
    "Busse verbessern. Wir werden erneuerbare Energie stärken und Windkraft sowie "
    "Solaranlagen gezielt fördern."
)


def make_pdf(*pages: str) -> bytes:
    """Kleine echte PDF mit eindeutig synthetischem Text."""
    writer = PdfWriter()
    for text in pages:
        page = writer.add_blank_page(width=600, height=800)
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
                NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})}
        )
        stream = DecodedStreamObject()
        text = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        stream.set_data(f"BT /F1 12 Tf 10 700 Td ({text}) Tj ET".encode("cp1252"))
        page[NameObject("/Contents")] = stream
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()


@pytest.fixture
def program():
    return {
        "id": 9071,
        "label": "Synthetisches Testprogramm",
        "party": {"id": 9081, "label": "BÜNDNIS 90/DIE GRÜNEN"},
        "parliament_period": {"id": 9002},
        "file": "https://www.abgeordnetenwatch.de/sites/default/files/test.pdf",
    }


def test_pdf_extraction_uses_real_page_numbers():
    pages = pdf_pages(make_pdf(TEST_TEXT, "Synthetische zweite Seite"))
    assert pages[0]["text"] == TEST_TEXT
    assert pages[1]["number"] == 2


@pytest.mark.parametrize("content", [b"not pdf", make_pdf("")])
def test_invalid_or_scanned_pdf_fails(content):
    with pytest.raises(ValueError):
        pdf_pages(content)


def test_local_document_provenance_and_cache_are_verified(tmp_path, program):
    path = tmp_path / "original.pdf"
    content = make_pdf(TEST_TEXT)
    path.write_bytes(content)
    document = prepare_program(tmp_path, program, local_file=path)
    assert document["sha256"] == hashlib.sha256(content).hexdigest()
    assert document["origin"] == "local_file"
    assert load_program(tmp_path, program)["pages"][0]["text"] == TEST_TEXT
    manifest = tmp_path / "programs" / "9071" / f"{document['sha256']}.json"
    cached = json.loads(manifest.read_text(encoding="utf-8"))
    cached["pages"][0]["text"] = "Manipulierter Textcache"
    manifest.write_text(json.dumps(cached), encoding="utf-8")
    assert load_program(tmp_path, program)["pages"][0]["text"] == TEST_TEXT
    Path(document["pdf_path"]).write_bytes(b"Changed")
    with pytest.raises(ValueError, match="verändert"):
        load_program(tmp_path, program)


def test_missing_program_has_actionable_error(tmp_path, program):
    with pytest.raises(ValueError, match="--online"):
        prepare_program(tmp_path, program)


def test_selected_hosted_pdf_can_be_downloaded_and_reused(database, tmp_path, clock, program):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, content=make_pdf(TEST_TEXT))

    client = client_for(database, tmp_path, clock, handler)
    first = prepare_program(tmp_path, program, client=client)
    second = prepare_program(tmp_path, program, client=client)
    assert first["sha256"] == second["sha256"]
    assert len(calls) == 1


@pytest.mark.parametrize(
    "url",
    [
        "http://www.abgeordnetenwatch.de/sites/default/files/test.pdf",
        "https://invalid.example/test.pdf",
        "https://www.abgeordnetenwatch.de/other/test.pdf",
        "https://attacker@www.abgeordnetenwatch.de/sites/default/files/test.pdf",
        "https://www.abgeordnetenwatch.de:1234/sites/default/files/test.pdf",
    ],
)
def test_document_download_rejects_external_or_unsafe_urls(database, tmp_path, clock, url):
    client = client_for(database, tmp_path, clock, lambda req: pytest.fail("Unexpected request"))
    with pytest.raises(ValueError):
        client.download_program(url)


def test_document_redirect_is_not_followed(database, tmp_path, clock, program):
    client = client_for(
        database,
        tmp_path,
        clock,
        lambda req: httpx.Response(302, headers={"Location": "https://invalid.example/"}),
    )
    with pytest.raises(APIError, match="302"):
        client.download_program(program["file"])


def test_document_download_rejects_html(database, tmp_path, clock, program):
    client = client_for(database, tmp_path, clock, lambda req: httpx.Response(200, text="HTML"))
    with pytest.raises(ValueError, match="keine PDF"):
        client.download_program(program["file"])
