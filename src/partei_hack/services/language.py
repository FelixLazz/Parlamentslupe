"""Lokale deutsche Suchmerkmale; ausdrücklich keine logische Bedeutungsprüfung."""

import re
import threading
from functools import lru_cache
from typing import Any

import snowballstemmer

from partei_hack.services.requests import normalize

_LOCAL = threading.local()
CONCEPTS = {
    "erneuerbare": {"erneuerbar", "windkraft", "windenergie", "solarenergie", "photovoltaik"},
    "nahverkehr": {"nahverkehr", "oepnv", "busverkehr", "regionalverkehr"},
    "klima": {"klimaschutz", "klimaneutral", "klimaneutralitaet", "dekarbonisierung"},
    "mindestlohn": {"mindestlohn", "lohnuntergrenze"},
    "kohlekraft": {"kohlekraft", "kohleverstromung", "kohleausstieg"},
    "mieten": {"mietpreisbremse", "mietendeckel", "mietbegrenzung"},
}


@lru_cache(maxsize=20000)
def stem(word: str) -> str:
    if not hasattr(_LOCAL, "stemmer"):
        _LOCAL.stemmer = snowballstemmer.stemmer("german")
    return _LOCAL.stemmer.stemWord(word)


CONCEPT_STEMS = {name: {stem(word) for word in words} for name, words in CONCEPTS.items()}


def concepts(words: set[str]) -> set[str]:
    stems = {stem(word) for word in words}
    return {name for name, aliases in CONCEPT_STEMS.items() if stems & aliases}


def statement_features(text: str) -> dict[str, Any]:
    """Merkmale für die Prüfung, keine automatische Einstufung als verbindliche Zusage."""
    normalized = normalize(text)
    markers = [
        phrase
        for phrase in (
            "wir wollen",
            "wir werden",
            "werden wir",
            "wir fordern",
            "wir schaffen",
            "wir setzen",
            "unser ziel",
            "wir sorgen",
            "wir machen",
        )
        if phrase in normalized
    ]
    conditions = [
        phrase
        for phrase in ("wenn", "sofern", "soweit", "falls", "unter der bedingung")
        if re.search(rf"\b{phrase}\b", normalized)
    ]
    negations = [
        word
        for word in ("nicht", "kein", "keine", "keinen", "ohne", "niemals")
        if re.search(rf"\b{word}\b", normalized)
    ]
    years = sorted(set(re.findall(r"\b(?:19|20)\d{2}\b", text)))
    quantities = re.findall(
        r"\b\d+(?:[.,]\d+)*\s*(?:Prozent|%|Euro|Milliarden|Millionen|Jahre?|Monate?|Tage?)",
        text,
        flags=re.IGNORECASE,
    )
    return {
        "promise_markers": markers,
        "conditions": conditions,
        "negations": negations,
        "years": years,
        "quantities": quantities,
        "specificity_hint": (
            "quantified_candidate"
            if markers and (years or quantities)
            else "goal_candidate"
            if markers
            else "context_passage"
        ),
        "review_required": True,
    }
