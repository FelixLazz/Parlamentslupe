"""Deutsches BM25-Retrieval mit Stämmen, Suchkonzepten und Originalkontext."""

import math
import re
from collections import Counter
from html.parser import HTMLParser
from typing import Any

from partei_hack.services.language import concepts, statement_features, stem
from partei_hack.services.programs import clean_text
from partei_hack.services.requests import normalize

STOPWORDS = set(
    "aber alle allein als also am an andere auch auf aus bei bis dabei dadurch daher "
    "damit dann das dass dem den der des die dies diese diesem diesen dieser dieses "
    "doch dort du durch ein eine einem einen einer eines er es fuer gegen haben hat "
    "hier im in ist ja jede jeder jedes kann koennen mehr mit muss nach nicht noch "
    "nur oder ohne pro schon sehr sein seine sich sie sind so sowie statt ueber um "
    "und uns unser unsere unseren unserer unter vom von vor war werden wie wieder "
    "will wir wird wollen wurde wurden zu zum zur zwischen deutschland deutschen "
    "bundesregierung bundestag fraktion fraktionen antrag gesetzentwurf gesetz "
    "beziehungsweise koalition regierung fordern fordert soll sollen koennen "
    "moechten setzen setzt dafuer bereich rahmen menschen weitere weiteren euro "
    "milliarden millionen prozent prozentpunkte buendnis gruene gruenen spd cdu csu "
    "fdp afd linke linkspartei bundestagswahlprogramm wahlprogramm kapitel einleitung "
    "ebenfalls dagegen aenderung aenderungen reform reformieren lockerung einfuehrung "
    "abschaffung aufhebung verlaengerung regelung regelungen neue neuen foerderung".split()
)


class PlainText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.ignored = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in {"script", "style"}:
            self.ignored += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self.ignored = max(0, self.ignored - 1)

    def handle_data(self, data: str) -> None:
        if not self.ignored:
            self.parts.append(data)


def plain_text(html: str) -> str:
    parser = PlainText()
    parser.feed(html)
    return clean_text(" ".join(parser.parts))


def tokens(text: str) -> set[str]:
    return {
        word
        for word in normalize(text).split()
        if len(word) >= 4 and any(char.isalpha() for char in word) and word not in STOPWORDS
    }


def passages(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    results = []
    seen = set()
    for page in pages:
        sentences = re.split(r"(?<=[.!?])\s+(?=[A-ZÄÖÜ„“])", page["text"])
        for index, sentence in enumerate(sentences):
            if not 50 <= len(sentence) <= 1600:
                continue
            key = normalize(sentence)
            if key in seen or len(tokens(sentence)) < 2:
                continue
            seen.add(key)
            features = statement_features(sentence)
            results.append(
                {
                    "page": page["number"],
                    "quote": sentence,
                    "kind": (
                        "promise_candidate" if features["promise_markers"] else "program_passage"
                    ),
                    "context_before": sentences[index - 1][-1200:] if index else "",
                    "context_after": (
                        sentences[index + 1][:1200] if index + 1 < len(sentences) else ""
                    ),
                    "statement_features": features,
                }
            )
    return results


class PassageMatcher:
    def __init__(self, pages: list[dict[str, Any]]):
        self.passages = passages(pages)
        self.terms = [tokens(item["quote"]) for item in self.passages]
        self.stems = [Counter(stem(word) for word in terms) for terms in self.terms]
        self.concepts = [concepts(terms) for terms in self.terms]
        frequencies = Counter(term for terms in self.stems for term in terms)
        size = len(self.terms)
        self.weights = {
            term: math.log(1 + (size - frequency + 0.5) / (frequency + 0.5))
            for term, frequency in frequencies.items()
        }
        self.average_length = sum(sum(terms.values()) for terms in self.stems) / max(size, 1)

    def match(self, poll: dict[str, Any], limit: int = 3) -> list[dict[str, Any]]:
        title_terms = tokens(poll["label"])
        topics = " ".join(item.get("label", "") for item in poll.get("field_topics") or [])
        committees = poll.get("field_committees") or []
        if isinstance(committees, dict):
            committees = [committees]
        context = " ".join(item.get("label", "") for item in committees)
        body_terms = tokens(plain_text(poll.get("field_intro") or ""))
        source_terms = tokens(poll.get("source_context") or "")
        api_terms = tokens(topics + " " + context + " " + (poll.get("api_context") or ""))
        query = title_terms | body_terms | source_terms | api_terms
        title_stems = {stem(word) for word in title_terms}
        query_stems = {stem(word) for word in query}
        strong_stems = {stem(word) for word in title_terms | body_terms | source_terms}
        body_stems = {stem(word) for word in body_terms}
        source_stems = {stem(word) for word in source_terms}
        title_concepts = concepts(title_terms)
        source_features = statement_features(plain_text(poll.get("field_intro") or ""))
        ranked = []
        for index, (passage, terms) in enumerate(zip(self.passages, self.terms, strict=True)):
            frequency = self.stems[index]
            common_stems = query_stems & frequency.keys()
            shared_title_stems = title_stems & frequency.keys()
            shared_concepts = title_concepts & self.concepts[index]
            common = query & terms
            if len(common_stems & strong_stems) < 2 or (
                not shared_title_stems and not shared_concepts
            ):
                continue
            title_common = common & title_terms
            length = sum(frequency.values())
            norm = 1.2 * (0.25 + 0.75 * length / max(self.average_length, 1))
            score = sum(
                self.weights[word]
                * (frequency[word] * 2.2 / (frequency[word] + norm))
                * (
                    3
                    if word in shared_title_stems
                    else 1
                    if word in body_stems
                    else 0.5
                    if word in source_stems
                    else 0.25
                )
                for word in common_stems
            ) + 0.5 * len(shared_concepts)
            flags = []
            if passage["statement_features"]["conditions"]:
                flags.append("conditional_statement")
            neighbor_features = statement_features(
                passage["context_before"] + " " + passage["context_after"]
            )
            if neighbor_features["conditions"]:
                flags.append("condition_in_neighbor_context")
            if neighbor_features["negations"]:
                flags.append("negation_in_neighbor_context")
            if passage["statement_features"]["negations"] or source_features["negations"]:
                flags.append("negation_requires_direction_review")
            if not shared_title_stems:
                flags.append("concept_expansion_only_title_anchor")
            ranked.append(
                {
                    **passage,
                    "lexical_score": round(score, 4),
                    "matched_terms": sorted(common),
                    "matched_title_terms": sorted(title_common),
                    "matched_stems": sorted(common_stems),
                    "matched_title_stems": sorted(shared_title_stems),
                    "matched_concepts": sorted(shared_concepts),
                    "retrieval_method": "bm25-german-stems-concepts-v2",
                    "evidence_fields": {
                        "title": sorted(terms & title_terms),
                        "api_description": sorted(terms & body_terms),
                        "official_context": sorted(terms & source_terms),
                        "topics_committees": sorted(terms & api_terms),
                    },
                    "review_flags": flags,
                    "review_status": "unreviewed",
                    "assessment": "not_assessable",
                }
            )
        ranked.sort(
            key=lambda item: (
                -len(item["matched_title_stems"]),
                -item["lexical_score"],
                item["page"],
                item["quote"],
            )
        )
        return ranked[:limit]
