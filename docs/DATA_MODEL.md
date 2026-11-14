# Lokales Datenmodell – Schema 1

Datei: `data/processed/parteihack.sqlite3`. Schema in
`src/partei_hack/storage/database.py`; Version über SQLite `user_version`.
Unbekannte Schemaversionen werden abgelehnt.

## Tabellen

### `entities`

Primärschlüssel `(resource, entity_id)`, zusätzlich `payload` (JSON),
`source_url` und `fetched_at` (UTC).

Ressourcen: `parliament-periods`, `candidacies-mandates`, `fractions`, `polls`,
`votes`, `election-program`, `topics`, `committees`, `vote-import-manifests`,
`evidence-documents`, `evidence-links`, `enrichment-runs`. Die letzte importierte
Fassung ersetzt die vorherige Fassung derselben Entität; Archivdateien bleiben
erhalten. Politikerreferenzen kommen zunächst aus Mandaten; ein vollständiger
separater Politikerimport fehlt.

### `http_cache`

Exakte kanonische Request-URL, JSON-Antwort und Abrufzeitpunkt. Standard-TTL:
24 Stunden. Nur erfolgreiche, strukturell gültige JSON-Antworten werden gespeichert.
Ein Cache-Treffer erhält den ursprünglichen Abrufzeitpunkt und erzeugt kein
zusätzliches Roharchiv.

### `import_runs`

Beginn, Ende, Perioden-ID, Status (`running`, `completed`, `failed`), Optionen,
Statistiken und Fehlermeldung.

`completed` bedeutet **der angeforderte Umfang wurde ausgeführt**, nicht
automatisch eine vollständige Legislatur inklusive Stimmen.
`polls_complete` und `with_votes` in der Statistik separat beachten.
Bei hartem Prozessabbruch kann `running` stehen bleiben; ein erneuter Aufruf
startet einen neuen Lauf.

### `vote_coverage`

Pro Poll-ID: gemeldete Quellanzahl, erfolgreicher Abschluss des paginierten
Stimmenimports, Prüfzeitpunkt. Zusätzlich wird bei Abfragen die lokale Anzahl
verglichen. Ab Version 0.3.0 speichert `vote-import-manifests` außerdem die
tatsächlich abgerufenen Vote-IDs; Vollständigkeit verlangt übereinstimmende
ID-Mengen. Gleiche Anzahl ist eine technische Konsistenzprüfung, kein Beweis,
dass alle amtlichen Stimmen korrekt oder vollständig beim Anbieter vorliegen.

## Beziehungen

```text
Parliament ← ParliamentPeriod (legislature)
                 ├─ previous_period → ParliamentPeriod (election) → ElectionProgram → Party
                 ├─ CandidacyMandate → Politician
                 │       └─ FractionMembership (Zeitraum) → Fraction
                 └─ Poll ← Vote → CandidacyMandate
                              └─ Fraction
```

Eine vorherige Periode wird nur dann für Programme verwendet, wenn sie nach
Prüfung tatsächlich eine Wahl desselben Parlaments ist.

## Provenienz und Grenzen

Archivdateien unter `data/raw/` enthalten die dekodierte JSON-Antwort, nicht
byteidentische HTTP-Pakete. Dateiname und SQLite-Zeitstempel dokumentieren den
Abruf. API-Metadaten bleiben im JSON erhalten.

Kein automatisches Löschen veralteter Entitäten, kein vollständiges historisches
Versionsmodell und keine beweissichere Signierung. Dokumente und zukünftige
Interpretationen erhalten später eigene Provenienz statt die Quelle zu verändern.

## Programm- und Prüfdaten ab Version 0.2.0

Kein SQLite-Schemawechsel erforderlich. `data/programs/PROGRAMM_ID/` enthält
`SHA256.pdf` und `SHA256.json` mit Programm-/Wahl-/Partei-ID, Quelle, Herkunft,
Importzeitpunkt und extrahierten PDF-Seiten. Die Prüfsumme gehört zur Original-PDF,
nicht zum Textcache. Der Text wird vor Vergleichen erneut extrahiert.

Exportierte Berichte enthalten nur relevante Zitate, Stimmen und Provenienz,
nicht das vollständige PDF. JSON-Prüfdateien verknüpfen exakte Originalzitate
mit Poll-IDs, gewünschter Stimmrichtung, Begründung, Quelle und Nutzerprüfung.
Sie werden nicht in die ursprünglichen API-Entitäten eingemischt.
Validierung und Grenzen: `COMPARISON.md`.

## Amtliche Belegdaten ab Version 0.3.0

- `evidence-documents`: kanonische URL, SHA-256, Abrufzeitpunkt, Format,
  Seitentext und gegebenenfalls veröffentlichte Gesamt-/Fraktionssummen.
- `evidence-links`: Poll-ID, Dokument-ID, Verknüpfungsweg und ausdrücklicher
  Status `context_link_not_independently_verified`.
- `enrichment-runs`: Umfang, Fehler und Budget eines begrenzten Beleglaufs.
- `data/evidence/SHA256.pdf|html`: unveränderte Originalbytes. Der Inhalt wird
  vor jeder Nutzung erneut geprüft; Abweichungen werden als Fehler gemeldet.
- Die Zuordnung zu einer Abstimmung ist eine Kontextverknüpfung, keine
  automatisch bewiesene Identität der endgültigen Beschlussfassung.
