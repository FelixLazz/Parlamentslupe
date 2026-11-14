# ADR 0001: Python, uv und SQLite als Ausgangspunkt

- Datum: 2026-11-14
- Status: angenommen für das Grundgerüst

## Anlass

Zunächst werden öffentliche politische Daten lokal erschlossen und geprüft.
Eine installierte Python-/uv-Umgebung ist vorhanden. Ein Webbetrieb oder
Mehrbenutzerbetrieb ist noch nicht gefordert.

## Entscheidung

Python-Paket im `src`-Layout, Typer-CLI, synchroner httpx-Client, SQLite und
JSON-Roharchiv. Abhängigkeiten werden mit `uv.lock` reproduzierbar festgehalten.

## Alternativen

- PostgreSQL: sinnvoll bei mehreren Nutzern, derzeit zusätzlicher Betriebsaufwand.
- Node.js/Weboberfläche: möglich, aber ohne derzeitigen fachlichen Mehrwert.
- Reine JSON-Dateien: gut als Archiv, unpraktisch für wiederholbare lokale Joins.
- Vollständig normalisierte Fachtabellen: später sinnvoll, nach besserer
  Validierung von Historie und Quellen; zunächst vollständige JSON-Entitäten.

## Konsequenzen

Kein Server nötig. Spätere Migration bleibt möglich. SQLite-JSON-Abfragen sind
bewusst Bestandteil des lokalen Modells. Datenvolumen und komplexere Analysen
sollen vor einem Architekturwechsel gemessen werden.
