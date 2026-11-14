"""Amtliche Belege gezielt archivieren, zuordnen und lokal nachprüfen."""

import hashlib
import json
import re
from collections import deque
from datetime import UTC, datetime
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from uuid import uuid4

from partei_hack.api.client import APIClient, APIError
from partei_hack.api.official import document_number, official_url
from partei_hack.services.matching import plain_text
from partei_hack.services.programs import pdf_pages
from partei_hack.services.requests import local_entities, normalize, party_keys
from partei_hack.storage.database import Database, utc_now

VOTE_KEYS = ("yes", "no", "abstain", "no_show")
COUNTS_PATTERN = r"(\d+)\s+ja\s+(\d+)\s+nein\s+(\d+)\s+enthalten\s+(\d+)\s+nicht\s+abg\.?"
MONTHS = {
    "Januar": 1,
    "Februar": 2,
    "März": 3,
    "April": 4,
    "Mai": 5,
    "Juni": 6,
    "Juli": 7,
    "August": 8,
    "September": 9,
    "Oktober": 10,
    "November": 11,
    "Dezember": 12,
}


def numeric_id(value: str) -> int:
    return int(hashlib.sha256(value.encode()).hexdigest()[:15], 16) or 1


def data_root(database: Database) -> Path:
    path = Path(database.connection.execute("PRAGMA database_list").fetchone()["file"])
    return path.parent.parent if path.parent.name == "processed" else path.parent


class LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            value = dict(attrs).get("href")
            if value:
                self.links.append(value)


def source_links(poll: dict[str, Any]) -> list[str]:
    parser = LinkParser()
    parser.feed(poll.get("field_intro") or "")
    return list(
        dict.fromkeys(
            [item.get("uri", "") for item in poll.get("field_related_links") or []] + parser.links
        )
    )


def parse_official(content: bytes, url: str) -> dict[str, Any]:
    if content.startswith(b"%PDF-"):
        pages = pdf_pages(content)
        first = pages[0]["text"]
        kind = next(
            (
                label
                for label in (
                    "Beschlussempfehlung",
                    "Änderungsantrag",
                    "Entschließungsantrag",
                    "Gesetzentwurf",
                    "Antrag",
                )
                if label in first[:1500]
            ),
            "Parlamentsdokument",
        )
        return {
            "format": "pdf",
            "title": f"{kind} {document_number(url) or ''}".strip(),
            "pages": pages,
            "links": [],
            "official_vote": None,
            "document_number": document_number(url),
            "document_type_hint": kind,
        }
    html = content.decode("utf-8", errors="strict")
    main = re.search(r"<main\b[^>]*>(.*?)</main>", html, flags=re.IGNORECASE | re.DOTALL)
    body = main[1] if main else html
    title = re.search(r"<h1\b[^>]*>(.*?)</h1>", body, flags=re.IGNORECASE | re.DOTALL)
    text = plain_text(body)
    if len(text) < 80 or not re.search(r"<(?:html|main|article)\b", html, re.IGNORECASE):
        raise ValueError("Amtliche Quelle enthält keinen lesbaren HTML-Beleg.")
    parser = LinkParser()
    parser.feed(body)
    dates = set()
    for day, month, year in re.findall(
        r"\b(\d{1,2})\.\s+(" + "|".join(MONTHS) + r")\s+(\d{4})\b", text
    ):
        try:
            dates.add(datetime(int(year), MONTHS[month], int(day)).date().isoformat())
        except ValueError:
            continue
    totals = re.search(
        r"Gesamtergebnis,\s*(\d+)\s+Mitglieder.{0,300}?" + COUNTS_PATTERN, text, re.IGNORECASE
    )
    official_vote = None
    if totals:
        groups = []
        for heading, segment in re.findall(
            r"<h4\b[^>]*>(.*?)</h4>(.*?)(?=<h[1-6]\b|\Z)",
            body,
            flags=re.IGNORECASE | re.DOTALL,
        ):
            full = plain_text(heading + " " + segment)
            counts = re.search(COUNTS_PATTERN, full, re.IGNORECASE)
            members = re.search(r"(\d+)\s+Mitglieder", full)
            if counts and members:
                label = re.sub(r"\s*\d+\s+Mitglieder.*", "", plain_text(heading))
                groups.append(
                    {
                        "label": label.strip(),
                        "members": int(members[1]),
                        "counts": dict(zip(VOTE_KEYS, map(int, counts.groups()), strict=True)),
                    }
                )
        official_vote = {
            "members": int(totals[1]),
            "counts": dict(zip(VOTE_KEYS, map(int, totals.groups()[1:]), strict=True)),
            "fractions": groups,
            "dates_in_source": sorted(dates),
            "verification_scope": "published_aggregate_counts_not_individual_roll_call",
        }
    return {
        "format": "html",
        "title": plain_text(title[1]) if title else "Amtlicher Bundestagsbeleg",
        "pages": [{"number": 1, "text": text}],
        "links": list(dict.fromkeys(urljoin(url, link) for link in parser.links)),
        "official_vote": official_vote,
        "document_number": None,
        "document_type_hint": "official_vote_page" if official_vote else "official_context_page",
    }


def load_source(database: Database, payload: dict[str, Any]) -> dict[str, Any]:
    url = official_url(payload["url"])
    digest = payload.get("sha256", "")
    if not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise ValueError("Ungültige Prüfsumme des amtlichen Belegs.")
    extension = "pdf" if payload["format"] == "pdf" else "html"
    path = data_root(database) / "evidence" / f"{digest}.{extension}"
    content = path.read_bytes()
    if hashlib.sha256(content).hexdigest() != digest:
        raise ValueError("Archivierter amtlicher Beleg wurde verändert.")
    return {**payload, **parse_official(content, url)}


def fetch_source(client: APIClient, database: Database, url: str) -> tuple[dict[str, Any], bool]:
    url = official_url(url)
    entity_id = numeric_id(url)
    row = database.connection.execute(
        """SELECT payload, fetched_at FROM entities
        WHERE resource='evidence-documents' AND entity_id=?""",
        (entity_id,),
    ).fetchone()
    if row and not client.refresh:
        age = (datetime.now(UTC) - datetime.fromisoformat(row["fetched_at"])).total_seconds()
        if 0 <= age < 86400:
            return load_source(database, json.loads(row["payload"])), False
    content, content_type = client.download_official(url)
    parsed = parse_official(content, url)
    digest = hashlib.sha256(content).hexdigest()
    directory = data_root(database) / "evidence"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{digest}.{parsed['format']}"
    if not path.exists():
        with path.open("xb") as handle:
            handle.write(content)
    elif path.read_bytes() != content:
        raise ValueError("Belegdatei am Prüfsummenpfad stimmt nicht überein.")
    record = {
        "id": entity_id,
        "label": parsed["title"],
        "url": url,
        "sha256": digest,
        "fetched_at": utc_now(),
        "content_type": content_type,
        "authority": "Deutscher Bundestag",
        **parsed,
    }
    database.save_entity("evidence-documents", record, url, record["fetched_at"])
    return record, True


def link_source(database: Database, poll_id: int, source: dict[str, Any], via: str) -> None:
    payload = {
        "id": numeric_id(f"{poll_id}:{source['url']}"),
        "label": source["title"],
        "poll_id": poll_id,
        "source_id": source["id"],
        "url": source["url"],
        "linking_method": via,
        "identity_review_status": "context_link_not_independently_verified",
    }
    database.save_entity("evidence-links", payload, source["url"], utc_now())


def evidence_for_poll(database: Database, poll_id: int) -> tuple[list[dict[str, Any]], list[str]]:
    sources = []
    errors = []
    for row in database.connection.execute(
        """SELECT d.payload, l.payload AS link_payload FROM entities l JOIN entities d
        ON d.resource='evidence-documents'
            AND d.entity_id=json_extract(l.payload, '$.source_id')
        WHERE l.resource='evidence-links' AND json_extract(l.payload, '$.poll_id')=?""",
        (poll_id,),
    ):
        record = json.loads(row["payload"])
        try:
            source = load_source(database, record)
        except (ValueError, OSError, UnicodeError) as exc:
            errors.append(f"{record.get('url')}: {exc}")
            continue
        sources.append({**source, "association": json.loads(row["link_payload"])})
    return sorted(sources, key=lambda item: item["url"]), errors


def crosscheck_counts(
    sources: list[dict[str, Any]],
    poll: dict[str, Any],
    total_counts: dict[str, int],
    *,
    fraction: dict[str, Any] | None = None,
    fraction_counts: dict[str, int] | None = None,
) -> dict[str, Any]:
    results = []
    for source in sources:
        official = source.get("official_vote")
        if official is None:
            continue
        date_matches = poll.get("field_poll_date") in official["dates_in_source"]
        counts_match = official["counts"] == {key: total_counts.get(key, 0) for key in VOTE_KEYS}
        sum_matches = sum(official["counts"].values()) == official["members"]
        fraction_match = None
        if fraction is not None and fraction_counts is not None:
            name = fraction.get("short_name") or fraction["label"].split(" (")[0]
            keys = party_keys(name)
            matches = [
                group
                for group in official["fractions"]
                if (keys and party_keys(group["label"]) == keys)
                or normalize(group["label"]).removeprefix("gruppe ") == normalize(name)
            ]
            if len(matches) == 1:
                fraction_match = matches[0]["counts"] == {
                    key: fraction_counts.get(key, 0) for key in VOTE_KEYS
                }
        comparable = date_matches and sum_matches
        conflict = comparable and (not counts_match or fraction_match is False)
        results.append(
            {
                "url": source["url"],
                "status": (
                    "conflict"
                    if conflict
                    else "aggregate_counts_match"
                    if comparable and counts_match
                    else "identity_unverified"
                ),
                "date_matches": date_matches,
                "counts_match": counts_match,
                "selected_fraction_counts_match": fraction_match,
                "published_counts": official["counts"],
                "scope": (
                    "aggregate_only; event identity and individual votes not independently verified"
                ),
            }
        )
    return {
        "status": (
            "conflict"
            if any(item["status"] == "conflict" for item in results)
            else "aggregate_counts_match"
            if any(item["status"] == "aggregate_counts_match" for item in results)
            else "not_checked"
        ),
        "sources": results,
    }


def enrich_period(
    client: APIClient,
    database: Database,
    period_id: int,
    *,
    max_polls: int = 5,
    max_documents: int = 3,
    poll_id: int | None = None,
    official_sources: list[str] | None = None,
) -> dict[str, Any]:
    if not 1 <= max_polls <= 50 or not 0 <= max_documents <= 20:
        raise ValueError("Belegrecherche: 1–50 Polls, 0–20 amtliche Dokumente.")
    polls = [
        item
        for item in local_entities(database, "polls")
        if (item.get("field_legislature") or {}).get("id") == period_id
        and (poll_id is None or item["id"] == poll_id)
    ]
    if not polls:
        raise ValueError("Keine passenden lokalen Polls. Zuerst Abstimmungen importieren.")
    period = next(
        (
            item
            for item in local_entities(database, "parliament-periods")
            if item["id"] == period_id and item.get("type") == "legislature"
        ),
        None,
    )
    if period is None:
        raise ValueError("Die angefragte Legislatur ist nicht lokal geprüft vorhanden.")
    if official_sources and poll_id is None:
        raise ValueError("Zusätzliche Quellen benötigen eine ausdrücklich angegebene Poll-ID.")
    explicit = [official_url(url) for url in official_sources or []]
    polls.sort(key=lambda item: (item.get("field_poll_date") or "", item["id"]), reverse=True)
    stats: dict[str, Any] = {
        "polls_examined": 0,
        "api_context_entities": 0,
        "documents_downloaded": 0,
        "documents_cached": 0,
        "document_limit": max_documents,
        "errors": [],
        "scope": "selected_relevant_context_not_all_api_resources",
    }
    seen_api: set[tuple[str, int]] = set()
    used_documents = 0
    for poll in polls[:max_polls]:
        stats["polls_examined"] += 1
        committees = poll.get("field_committees") or []
        if isinstance(committees, dict):
            committees = [committees]
        references = [("topics", ref) for ref in poll.get("field_topics") or []]
        references += [("committees", ref) for ref in committees]
        for resource, ref in references:
            key = (resource, ref.get("id"))
            if key in seen_api or len(seen_api) >= 30 or not key[1]:
                continue
            seen_api.add(key)
            try:
                response = client.get_entity(resource, key[1])
                if (
                    resource == "committees"
                    and (response.payload["data"].get("field_legislature") or {}).get("id")
                    != period_id
                ):
                    raise ValueError("Ausschuss gehört zu einer anderen Legislatur.")
                database.save_entity(
                    resource, response.payload["data"], response.source_url, response.fetched_at
                )
                stats["api_context_entities"] += 1
            except (APIError, ValueError) as exc:
                stats["errors"].append(f"{resource}/{key[1]}: {exc}")
        queue = deque([(url, "explicit_attachment") for url in explicit])
        queue.extend((url, "api_reference") for url in source_links(poll))
        seen_urls = set()
        while queue and used_documents < max_documents:
            url, via = queue.popleft()
            try:
                url = official_url(url)
            except ValueError:
                continue  # Nichtamtliche/interne Referenzen bleiben im originalen Poll erhalten.
            if url in seen_urls:
                continue
            seen_urls.add(url)
            used_documents += 1
            try:
                source, downloaded = fetch_source(client, database, url)
                link_source(database, poll["id"], source, via)
                stats["documents_downloaded" if downloaded else "documents_cached"] += 1
                if source["format"] == "html":
                    # Vorrang für die beim amtlichen Abstimmungsobjekt verlinkten Fassungen.
                    # Auch diese bleiben Kontextlinks, keine automatisch geprüfte Bindung.
                    queue.extendleft(
                        (url, "official_page_context_link") for url in reversed(source["links"])
                    )
            except (APIError, ValueError, OSError, UnicodeError) as exc:
                stats["errors"].append(f"{url}: {exc}")
    stats["api_context_limit_reached"] = len(seen_api) >= 30
    stats["document_budget_used"] = used_documents
    record = {
        "id": numeric_id(uuid4().hex),
        "label": f"Belegrecherche Legislatur {period_id}",
        "period_id": period_id,
        "finished_at": utc_now(),
        **stats,
    }
    database.save_entity(
        "enrichment-runs", record, f"local:enrichment:{period_id}", record["finished_at"]
    )
    return stats
