# Anwendungslogik

- `importer.py`: Legislatur prüfen; Mandate, Fraktionen und ausgewählte Polls
  importieren; optional Einzelstimmen und verknüpfte Wahlprogramm-Metadaten.
  Separater protokollierter Poll-Metadatenimport ohne Mandate/Stimmen; gezielter
  Stimmenimport kann historische Mandate vorab aktualisieren.
- `queries.py`: lokale Listen und Fraktionszählungen, ohne HTTP.
  `vote_import_status` prüft Importanzahl/ID-Mengen ohne Stimmen-/Mandatsdetails
  und wird für leichte Webauswahldaten verwendet.
- `requests.py`: deutsche Anfrage, Perioden-/Partei-/Fraktionsauswahl.
- `programs.py`: ausgewählte Original-PDF und SHA-256, Text pro PDF-Seite;
  fehlende Originaldateien nur mit erwarteter Prüfsumme wiederherstellen.
- `matching.py`: BM25-Treffer, deutsche Stämme/Suchkonzepte, Originalkontext;
  immer ungeprüft.
- `language.py`: lokale Stemming- und Prüfmerkmale (Bedingungen, Verneinungen,
  Jahre, Mengen), keine logische Bedeutungsprüfung.
- `promises.py`: Originalzitate und explizit geprüfte Richtungszuordnungen.
- `quality.py`: Datenintegrität, Vorgangsflags und getrennte, begrenzte Zählung.
  Gruppierte Prüfvorhaben behalten Einzelergebnis-Häufigkeiten und offene
  Auswertbarkeit. Stimmanteile nennen ihre dokumentierten Bezugsgrößen.
- `evidence.py`: begrenzte amtliche Belege mit SHA-256 und Summenabgleich.
- `comparison.py`: Quellen, Abdeckung und Stimmen zusammenführen; gemeinsame
  Berichtserstellung für CLI-Anfragen und explizite Webauswahlen.
  `program_analysis` beschreibt Textumfang und Kandidatenmerkmale. Das vollständige
  Kandidateninventar enthält Satzkontext und dessen gesonderte Prüfmerkmale.
- `reports.py`: Markdown, JSON und Zitatvorlage exportieren.
- `workspace.py`: Webauswahl für beliebige API-Parlamente/Legislaturen/Fraktionen,
  lokale Datenübersicht, Einzelstimmen und ungeprüfte lokale Programmbelege;
  expliziter Stammdaten-/Programmabruf mit Filterprüfung, PDF-Textansicht
  und Vergleichsaktion mit gezieltem Nachladen fehlender Originale.
  `choices`/`prepare_choices` trennen leichte Auswahldaten vom Stimmenimport.
  `run_selection` bündelt ausdrücklich ausgewählte Stimmen und optionalen
  Programmvergleich; vollständige Stimmenimporte werden wiederverwendet.

Ein begrenzter Import ist kein vollständiger Datensatz. Jeder Lauf protokolliert
seinen Umfang. Keine Partei-Zeitreihen oder automatische Erfüllungsbewertung.
Der Richtungsvergleich setzt nutzergeprüfte Begründungen voraus; `docs/COMPARISON.md`.
