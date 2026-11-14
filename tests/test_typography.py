"""Typografie der lokalen Assets prüfen, unabhängig von der Vergleichslogik."""

import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote
from xml.etree import ElementTree

WEB = Path(__file__).parents[1] / "src" / "partei_hack" / "web"


def test_typography_uses_natural_spacing_and_wrappable_controls():
    css = (WEB / "app.css").read_text(encoding="utf-8")
    typography = css.split("/* Lesbare Typografie:", 1)[1]
    assert not re.search(r"(?:letter|word)-spacing\s*:\s*-", typography)
    headings = re.search(r"h1,\s*h2,.*?\{([^}]+)\}", typography, re.DOTALL)
    assert headings is not None
    assert "letter-spacing: normal" in headings[1]
    controls = re.search(
        r"\.primary-button,\s*\.secondary-button\s*\{([^}]+)\}", typography, re.DOTALL
    )
    assert controls is not None
    assert "white-space: normal" in controls[1]
    assert "font-size: 12px" in controls[1]


def test_navigation_words_share_one_label_instead_of_separate_flex_items():
    class Labels(HTMLParser):
        def __init__(self):
            super().__init__()
            self.in_label = False
            self.labels = []

        def handle_starttag(self, tag, attrs):
            if tag == "span" and "nav-text" in dict(attrs).get("class", "").split():
                self.in_label = True
                self.labels.append("")

        def handle_endtag(self, tag):
            if tag == "span":
                self.in_label = False

        def handle_data(self, data):
            if self.in_label:
                self.labels[-1] += data

    parser = Labels()
    html = (WEB / "index.html").read_text(encoding="utf-8")
    parser.feed(html)
    assert parser.labels == ["Übersicht", "Wahlprogramme", "Vergleich", "Methodik & Quellen"]
    assert 'class="brand-mark" aria-hidden="true"><svg' in html


def test_web_brand_and_favicon_show_a_magnifying_glass_over_p():
    html = (WEB / "index.html").read_text(encoding="utf-8")
    assert "<title>Parlamentslupe · Parlament verstehen</title>" in html
    assert 'aria-label="Parlamentslupe Startseite"' in html
    assert "<span>Parlamentslupe<span" in html
    assert "Parlamentslupe <span" in html
    assert "ParteiHack" not in html

    logo = re.search(r'class="brand-mark"[^>]*>(<svg.*?</svg>)', html)
    favicon = re.search(r'rel="icon" href="data:image/svg\+xml,([^"]+)"', html)
    assert logo is not None
    assert favicon is not None
    for svg in (logo[1], unquote(favicon[1])):
        root = ElementTree.fromstring(svg)
        elements = {element.tag.rsplit("}", 1)[-1]: element for element in root.iter()}
        assert elements["circle"].attrib == {"cx": "17", "cy": "17", "r": "12"}
        assert elements["path"].attrib["d"] == "m26 26 9 9M13 24V10h5a5 5 0 0 1 0 10h-5"
