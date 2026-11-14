# ADR 0005: Amtliche Belege, Datenqualität und getrennte Aussagekraft

- Datum: 2026-11-14
- Status: umgesetzt
- Ergänzt ADR 0002 und 0004.

## Anlass

Der bisherige Vergleich konnte relevante Textstellen verpassen, weil nur exakte
Wörter verglichen wurden. Zugleich konnten gleiche Stimmenzahlen eine
Vollständigkeit vortäuschen, obwohl andere Poll- oder Vote-IDs importiert waren.
Amtliche Abstimmungsseiten enthalten nützliche Summen, aber oft mehrere
Abstimmungen, Ausschussfassungen und verlinkte Dokumente. Ein einzelner
Gesamtscore würde diese Unterschiede verdecken.

## Entscheidung

- **Retrieval:** BM25 mit deutschem Snowball-Stemming, wenigen offengelegten
  Suchkonzepten und Gewichtung nach Titel, API-Beschreibung, amtlichem Kontext
  sowie Themen/Ausschüssen. Suchkonzepte allein erzeugen keinen Treffer.
- **Kontext:** Jeder Treffer enthält den vorherigen und nächsten Satz derselben
  PDF-Seite. Bedingungen, Verneinungen, Jahre und Mengen sind Prüfhinweise,
  keine automatische Interpretation.
- **Identität:** Poll- und Vote-ID-Mengen werden protokolliert. Vollständigkeit
  verlangt übereinstimmende Mengen, nicht nur gleiche Anzahlen.
- **Amtliche Quellen:** Nur eine feste Allowlist konkreter Bundestagsseiten und
  -drucksachen ist abrufbar. Originale werden mit SHA-256 archiviert, nicht
  still ersetzt. Summen werden getrennt nach Gesamt und ausgewählter Fraktion
  geprüft; die Zuordnung bleibt eine Kontextverknüpfung.
- **Qualität:** Abdeckung, Datenintegrität, Quellenlage, Summenabgleich und
  Prüfbedarf bleiben getrennte Dimensionen. `overall_score` ist `null`.
- **Zählung:** Mehrere Polls mit gleicher expliziter `procedure_id` sind ein
  Prüfvorhaben. Jedes Versprechen wird höchstens einmal gezählt; `partial` und
  `mixed` gelten nicht als Zustimmung.

## Alternativen

- **Größerer Import als erste Maßnahme:** verbessert die Stichprobe, behebt aber
  keine falsche Zuordnung oder Datenintegritätsfehler.
- **Automatische semantische Ähnlichkeit oder LLM-Urteil:** schwer nachprüfbar,
  nicht lokal reproduzierbar und für Richtungsaussagen ungeeignet.
- **Gesamtscore aus Abdeckung, Treffern und Stimmen:** vermischt technische
  Qualität mit politischer Interpretation und suggeriert Erfüllung.

## Konsequenzen

- Der Bericht ist ausführlicher und nennt offene Prüfungen ausdrücklich.
- Ohne vollständigen Import bleibt die Abdeckung niedrig; die Methode behebt
  diese Datenlücke nicht.
- Amtliche Belege sind derzeit nur für den Bundestag automatisiert verfügbar.
- Ein Summenabgleich bestätigt weder Einzelstimmen noch die endgültige
  Gesetzesfassung oder die politische Wirkung eines Versprechens.
