# Architektur

## Datenfluss

```text
Typer CLI / lokale Website (`web`)
  ├─ lokale Abfragen ────────────────────────────┐
  └─ Import-Service                             │
       └─ API-Client                            │
            ├─ SQLite-Antwortcache               │
            └─ httpx → abgeordnetenwatch API     │
                 └─ JSON-Roharchiv              │
       └─ validierte Entitäten → SQLite ←───────┘
                                      └─ JSON / CSV / Fraktionszählungen
```

## Dateikarte

| Datei | Zuständigkeit |
| --- | --- |
| `src/partei_hack/config.py` | Pfade, API-Basisadresse, konservative Standardwerte |
| `src/partei_hack/models.py` | Mindestvalidierung ohne Verlust unbekannter Felder |
| `src/partei_hack/api/client.py` | HTTP, Drosselung, Retry, Pagination, begrenzte amtliche Downloads |
| `src/partei_hack/api/official.py` | Allowlist kanonischer Bundestagsquellen |
| `src/partei_hack/storage/database.py` | Schema, Cacheindex, Entitäten, Importläufe |
| `src/partei_hack/storage/archive.py` | Archivierung erfolgreicher JSON-Antworten |
| `src/partei_hack/services/importer.py` | Import einer Legislatur mit begrenzter Auswahl |
| `src/partei_hack/services/queries.py` | Ausschließlich lokale, parametrisierte Abfragen |
| `src/partei_hack/services/requests.py` | Deutsche Anfrage und eindeutige Auswahl |
| `src/partei_hack/services/programs.py` | Ausgewählte PDF, SHA-256 und Seitentext |
| `src/partei_hack/services/language.py` | Deutsche Stämme, Suchkonzepte, Prüfmerkmale |
| `src/partei_hack/services/matching.py` | BM25-Suche mit Originalkontext, ohne Richtungsurteil |
| `src/partei_hack/services/promises.py` | Geprüfte Zitate, Links, Vorgangs- und Stimmrichtung |
| `src/partei_hack/services/quality.py` | Datenintegrität, Vorgangsflags, getrennte Zählung |
| `src/partei_hack/services/evidence.py` | Amtliche Belege, SHA-256, Summenabgleich |
| `src/partei_hack/services/selection.py` | Lexikalische Poll-Relevanz für gezielte Stimmenimporte |
| `src/partei_hack/services/comparison.py` | Quellen, Abdeckung, Qualität und Vergleichsdaten |
| `src/partei_hack/services/reports.py` | Markdown-/JSON-Berichte und Prüfungsvorlage |
| `src/partei_hack/services/workspace.py` | Webkatalog, lokale Auswahlauswertung und Textbelege |
| `src/partei_hack/cli.py` | Befehle, Fehleranzeige und Exporte |
| `src/partei_hack/web/server.py` | Loopback-HTTP, Asset-/JSON-Routen, bestätigte Online-Aktionen |
| `src/partei_hack/web/index.html`, `app.css`, `app.js` | Responsive Oberfläche ohne Build oder externe Assets |

## Grundentscheidungen

- Synchroner Client: Ein zentraler Abstand zwischen Netzrequests ist verständlicher
  und sicherer als parallele Abrufe unter dem engen API-Limit.
- Cache und Roharchiv sind getrennt: Der Cache kann veralten, archivierte Antworten
  bleiben als Beobachtung mit Abrufzeitpunkt erhalten.
- SQLite enthält die neueste importierte Fassung jeder Entität. Historische
  Rohantworten bleiben im Archiv, nicht als vollständiges relationales Versionsmodell.
- Eine generische Entitätstabelle erhält das vollständige JSON; lokale SQL-Abfragen
  verwenden SQLite-JSON-Funktionen. Das vermeidet verfrühte, verlustbehaftete Normalisierung.
- Die Titelsuche verwendet Unicode-Casefolding, damit auch deutsche Umlaute
  unabhängig von Groß-/Kleinschreibung gefunden werden.
- Ein Import ist pro Entität idempotent. Ein fehlgeschlagener Lauf kann bereits
  gespeicherte Teilergebnisse enthalten und wird als fehlgeschlagen markiert.
- Importseiten werden vollständig validiert und dann in einer SQLite-Transaktion
  geschrieben; kein langsamer Commit pro Einzelstimme.
- Poll- und Vote-Identitäten werden als ID-Mengen protokolliert. Eine bloß gleiche
  Anzahl genügt nicht als Vollständigkeitsnachweis.
- Amtliche Belege werden nur über eine feste Host-/Pfad-Allowlist geladen,
  mit derselben Drosselung wie die API und ohne Redirects. Rohinhalt, SHA-256 und
  Abrufzeitpunkt bleiben getrennt von der Interpretation.
- Daten werden nicht automatisch gelöscht, wenn sie in einer neuen Antwort fehlen.
  Vollständigkeitsprüfungen erkennen abweichende Anzahlen, ersetzen aber keinen
  ausgearbeiteten Abgleich gelöschter oder korrigierter Quellobjekte.

## Erweiterungspunkte

1. Robuste historische Partei-/Kandidaturzuordnung mit Quellen.
2. Dokumentversionierung und externe Versprechenquellen über das Programm hinaus.
3. Persistenter Prüfworkflow statt ausschließlich portabler JSON-Prüfdateien.
4. Amtliche Quellenadapter für weitere Parlamente.
5. Lokalen Web-Prüfworkflow über die bestehende JSON-Dateiprüfung hinaus ergänzen.

Kein LLM-Provider, Vektorspeicher oder zusätzliches Webframework wird benötigt.
Die vorhandene Vergleichspipeline verwendet lokale PDF-Texte, Wortsuche und
explizite JSON-Prüfdateien. Details: `COMPARISON.md` und ADR 0002.

## Lokale Website

`parteihack web` startet einen `ThreadingHTTPServer` der Python-Standardbibliothek
auf `127.0.0.1`. Pro Anfrage wird eine eigene SQLite-Verbindung verwendet.
Die Oberfläche liest zuerst nur lokale Daten; Online-Aktionen benötigen eine
Bestätigung, JSON und ein zufälliges Sitzungstoken. Host-/Origin-Prüfung und
restriktive Content-Security-Policy begrenzen fremde Browserzugriffe.
Es gibt keine CORS-Freigabe und keine allgemeine Dateiauslieferung.

Ein prozessweiter Lock verhindert parallele Webimporte. Der bestehende API-Client
bleibt für Cache, Roharchiv, Retry und Drosselung zuständig. Zwischen Webaktionen
gilt zusätzlich der Mindestabstand. CLI-Prozesse sind weiterhin nicht koordiniert.
Keine Hintergrundjobs, kein öffentlicher Hostingbetrieb. Entscheidung: ADR 0003.

Programm-Metadaten können unabhängig von Mandaten/Abstimmungen nachgeladen werden.
Die lesenden Programm-/Vergleichsrouten bleiben offline; eine fehlende PDF ergibt
einen strukturierten `program_missing`-Hinweis. Bestätigte POST-Aktionen können
genau die ausgewählte PDF über den bestehenden `prepare_program`-Dienst laden.
Bei fehlender Datei trotz Manifest wird nur das Original mit passender SHA-256
wiederhergestellt; Änderungen werden nicht überschrieben. Siehe ADR 0004.

CLI und Website teilen `build_selected_comparison`: die CLI löst vorher ihre
Freitextanfrage auf, die Website verwendet explizit gewählte API-IDs. Wahl,
Parlament, Programm, Fraktion und Dokument müssen konsistent verknüpft sein.
Es werden keine Parteialiases für Landesparlamente geraten. Die Programmpartei
und Fraktion bleiben unabhängige Auswahlen. Vergleichsberichte enthalten
ungeprüfte Worttreffer neben Stimmen und Quellen, keine automatische Bewertung.

Der gemeinsame Bericht ergänzt `program_analysis` und ein Kandidateninventar
mit Satzkontext. Die Website filtert dieses Inventar lokal nach Text und
Prüfmerkmalen und zeigt schrittweise weitere Einträge. Hierfür entstehen keine
zusätzlichen HTTP-Routen oder Netzabfragen.

Die Webaktion `/api/evidence` nutzt denselben Kern `enrich_period` wie die CLI:
höchstens fünf lokale Poll-Kontexte und drei amtliche Belege pro Lauf. Sie ist
bestätigungspflichtig, serialisiert und mit derselben Host-/Origin-/Token-Prüfung
geschützt. Amtliche Belege dürfen ausschließlich über die Allowlist in
`api/official.py` geladen werden; es gibt keine frei eingebbare Download-URL.
Entscheidung: ADR 0005.

Die gemeinsame Webauswahl trennt Auswahldaten und teure Detailimporte:
`GET /api/choices` bleibt lokal; `POST /api/prepare` ergänzt nach ausdrücklicher
Freigabe Fraktionen, Programm-Metadaten und die vollständige Poll-Titelliste,
ohne Mandate/Stimmen/PDFs. `Importer.import_poll_metadata` protokolliert die
abgerufene ID-Menge und API-Anzahl. Der Browser bereitet jede Kombination
einmal pro Seitenaufruf vor; der HTTP-Cache bleibt zusätzlich wirksam.
`POST /api/run` prüft Fraktion, Programm und Poll-Auswahl vor dem Online-Client.
Nur unvollständige gewählte Stimmen werden mit historischen Mandaten nachgeladen.
Optional wird die ausgewählte PDF geladen und unmittelbar verglichen. Alle
Teilaktionen nutzen denselben Client und Online-Lock. Die IDs begrenzen Analyse
und Vergleich, während die Abdeckung der gesamten Legislatur sichtbar bleibt.
Die ausdrückliche Alle-Auswahl benötigt eine vollständige lokale Titelliste.
Kein Hintergrundjob, keine Live-Fortschrittsanzeige und keine automatische
Wiederholung nach Fehlern; erfolgreich gespeicherte Teildaten bleiben erhalten.
Entscheidung: ADR 0006.
