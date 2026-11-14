"""Eng begrenzte amtliche Quellen; keine freie URL-/Dateiabrufschnittstelle."""

import re
from urllib.parse import parse_qs, urlsplit, urlunsplit


def official_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError as exc:
        raise ValueError("Ungültige amtliche Quellen-URL.") from exc
    if (
        parts.scheme != "https"
        or parts.username
        or parts.password
        or port not in (None, 443)
        or any(char in url for char in ("\n", "\r", "\\", "\x00"))
        or "%" in parts.path
    ):
        raise ValueError("Nur direkte amtliche HTTPS-Quellen ohne Zugangsdaten sind erlaubt.")
    host = parts.hostname
    path = parts.path
    if host in {"dip21.bundestag.de", "dipbt.bundestag.de"}:
        path = path.removeprefix("/dip21")
        host = "dserver.bundestag.de"
    if host == "dserver.bundestag.de":
        if not re.fullmatch(r"/(?:btd/\d{2}/\d{3}/\d{7}|btp/\d{2}/\d{5})\.pdf", path):
            raise ValueError("Nur konkrete Bundestagsdrucksachen/-protokolle werden geladen.")
        if parts.query:
            raise ValueError("PDF-Quellen dürfen keine Queryparameter enthalten.")
    elif host == "www.bundestag.de":
        if path == "/parlament/plenum/abstimmung/abstimmung":
            query = parse_qs(parts.query, keep_blank_values=True)
            if set(query) != {"id"} or len(query["id"]) != 1 or not query["id"][0].isdigit():
                raise ValueError("Amtliche Abstimmung benötigt genau eine numerische ID.")
        elif not re.fullmatch(r"/dokumente/textarchiv/[a-zA-Z0-9/_-]+", path) or parts.query:
            raise ValueError("Nur konkrete Abstimmungs- oder Textarchivseiten werden geladen.")
    else:
        raise ValueError(
            "Dieser Quellenhost ist noch nicht als amtlicher Abrufadapter unterstützt."
        )
    return urlunsplit(("https", host, path, parts.query, ""))


def document_number(url: str) -> str | None:
    match = re.search(r"/btd/(\d{2})/\d{3}/(\d{7})\.pdf$", url)
    if match and match[2][:2] == match[1]:
        return f"{int(match[1])}/{int(match[2][2:])}"
    return None
