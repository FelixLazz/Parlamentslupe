# ParteiHack

Lokales Recherchewerkzeug für die [abgeordnetenwatch-API](https://www.abgeordnetenwatch.de/api).
Quellenbasierte Gegenüberstellung von Wahlprogramm und Abstimmungsverhalten:
deutsche Rechercheanfragen, Programmzitate mit PDF-Seiten und Fraktionsstimmen.
Textvorschläge bleiben ungeprüft; nur explizit geprüfte Zuordnungen erlauben
einen Richtungsvergleich. Keine automatische Erfüllungsbewertung.

**KI-/Agenten-Einstieg:** [`AGENTS.md`](AGENTS.md)  
**Aktueller Stand:** [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md)

## Projektstruktur

```text
ParteiHack/
├── AGENTS.md              # Zentrale Regeln und Einstieg für KI-Agenten
├── CLAUDE.md / GEMINI.md  # Verweise auf die zentrale Anleitung
├── .github/              # Copilot-Einstieg, keine aktive CI
├── docs/                 # Stand, Architektur, API, Datenmodell und Methodik
├── src/partei_hack/       # Installierbare Anwendung
│   ├── api/              # HTTP, Cache, Retry und Pagination
│   ├── storage/          # SQLite und Roharchiv
│   ├── web/              # Lokaler Webserver und responsive Oberfläche
│   └── services/         # Importabläufe und lokale Abfragen
├── tests/                # Synthetische, vollständig netzwerkfreie Tests
├── examples/             # Befehle für typische Abläufe
├── data/                 # Lokale Daten; Inhalte nicht für Git vorgesehen
├── pyproject.toml        # Paket, Abhängigkeiten und Qualitätswerkzeuge
├── uv.lock               # Festgehaltene Abhängigkeitsversionen
└── .venv/                # Lokal erzeugte Python-Umgebung
```

Ordner-READMEs erklären den jeweiligen Kontext. `docs/ARCHITECTURE.md` enthält
die Dateikarte. Die KI-Einstiegsdateien verweisen auf eine gemeinsame Quelle;
ob ein bestimmtes Werkzeug sie automatisch liest, hängt vom Werkzeug ab.

## Voraussetzungen und Einrichtung

Windows/PowerShell, Python ab 3.12 und [uv](https://docs.astral.sh/uv/).
Die lokale Entwicklungsumgebung verwendet Python 3.14.

```powershell
uv sync --dev
uv run parteihack --help
uv run parteihack doctor
uv run parteihack init-db
```

Falls PowerShell Umlaute falsch darstellt, kann für die Sitzung
`$env:PYTHONUTF8 = "1"` gesetzt werden.

`uv.lock` hält die aufgelösten Abhängigkeiten fest. Kein API-Schlüssel, Node.js,
Docker oder externer Datenbankserver erforderlich.

## Erste Schritte

### Website als Benutzeroberfläche

Die Website heißt **Parlamentslupe**. Ihr Logo zeigt eine Lupe mit einem
vergrößerten „P“ im Glas. Paketname, CLI-Befehle und Datenpfade bleiben unverändert.

```powershell
uv run parteihack web
```

Anschließend **http://127.0.0.1:8000** öffnen. Beenden mit `Strg+C`.
Alternativer Port: `uv run parteihack web --port 8080`.
Ein anderes Datenverzeichnis steht davor:
`uv run parteihack --data-dir "D:\ParteiHack\data" web`.

- **Einmal Auswahldaten freigeben:** „Auswahldaten beim Auswählen online ergänzen“
  aktivieren. Danach werden Parlamente, Perioden und zur gewählten Legislatur
  Fraktionen, Programm-Metadaten und Abstimmungstitel sequenziell ergänzt.
  Noch keine Mandate, Einzelstimmen oder PDFs. Jede Auswahlkombination wird pro
  Seitenaufruf nur einmal vorbereitet; der API-Client nutzt zusätzlich seinen Cache.
- **Alles vorab auswählen:** Parlament → Wahlperiode → Fraktion, optional das
  Programm der Wahlpartei und im aufklappbaren Titelfeld mehrere Abstimmungen.
  Die Titelsuche filtert nur die Anzeige, nicht die bereits gesetzten Häkchen.
  „Alle Abstimmungen“ ist eine gesonderte Auswahl und setzt eine gegen die API
  vollständige lokale Titelliste voraus. Fraktion und Programm werden nicht geraten.
- **Auswahl laden & untersuchen:** eine gemeinsame Bestätigung, danach nur die
  fehlenden/unvollständigen gewählten Stimmen einschließlich historischer Mandate
  laden. Falls ein Programm gewählt ist, wird nur dessen PDF bei Bedarf geladen,
  extrahiert und unmittelbar der Vergleich erstellt. Die Auswahl bleibt erhalten.
  Vollständige Stimmenimporte und vorhandene PDFs werden wiederverwendet.
  Bewusst alle oder viele Stimmen können lange dauern; möglichst 22–6 Uhr starten.
  Ohne Programm entsteht nur die Stimmenübersicht. „Nur lokale Daten anzeigen“
  bleibt ohne Online-Abruf verfügbar.
- **Abstimmungen:** lokale Titel-/Datumsfilter, Stimmenverteilung, Einzelstimmen,
  Quellenlinks, technische Importabdeckung und JSON-Download.
- **Wahlprogramme:** „Programmliste online laden“ ruft nur Metadaten zur
  vorhergehenden Wahl ab, unabhängig vom Abstimmungsimport. Programm separat
  wählen und „Programm laden & Text anzeigen“ verwenden: fehlt die Original-PDF,
  wird ihr gezielter Download nach Bestätigung angeboten. Extrahierten Text
  seitenweise lesen; SHA-256, Herkunft und lokalen Dateistatus einsehen.
- **Vergleich starten:** unter „Wahlprogramme“ oder im eigenen Bereich „Vergleich“.
  Programmzitate mit PDF-Seiten stehen neben Fraktionsstimmen, Quellen und
   Importabdeckung. Der gemeinsame Start nutzt die ausdrücklich gewählten
   Abstimmungen, unabhängig von Übersichtssuchfiltern. Vergleichs-JSON separat herunterladen.
  Zitate enthalten Satzkontext, Suchkonzepte und Prüfhinweise zu Bedingungen und
  Verneinungen. Datenprobleme, historische Fraktionsverläufe und amtliche
  Summenabgleiche werden getrennt ausgewiesen.
  Zusätzlich zeigt der Vergleich Teilnahme und Ja-/Nein-Anteile mit allen
  dokumentierten Fraktionseinträgen als explizitem Nenner.
  Unter „Programm genauer untersuchen“ lassen sich alle erkannten Kandidaten
  durchsuchen und nach Mengenangaben, Jahreszahlen oder Bedingungen filtern.
  Originalzitat, PDF-Seite und Satzkontext bleiben sichtbar.
- **Amtliche Belege ergänzen:** lädt begrenzt Themen-/Ausschussdaten und höchstens
  drei verlinkte Bundestagsoriginale, archiviert sie mit SHA-256 und prüft
  veröffentlichte Gesamtsummen. Keine freie Websuche, kein Erfüllungsurteil.
- **Gezielt online:** fehlende Parlamente, Perioden oder Fraktionen nach
  Bestätigung laden. „Daten importieren“ lädt ausdrücklich eine Stichprobe von
  ein bis fünf Polls samt Stimmen, historischen Mandaten und Programm-Metadaten.

Beim Start und bei lokalen Untersuchungen gibt es **keine automatischen
Netzabfragen**. Erst die ausdrückliche Freigabe erlaubt das automatische Ergänzen
der Auswahldaten; die einzelnen Online-Schaltflächen bleiben als Alternative.
Für neuere/andere Wahlperioden muss der zugehörige Datenbestand erst importiert
werden; die Oberfläche ersetzt fehlende Daten nicht durch Beispieldaten.

Fehlende Quellen lassen sich in der Website bewusst nachladen, ohne auf lokale
Vorarbeiten per CLI angewiesen zu sein. Beim Vergleich kann zusätzlich eine
ausdrückliche Abstimmungsauswahl angefordert werden. Vorhandene PDFs
werden wiederverwendet; es gibt keine PDF-Sammeldownloads. Eine entfernte PDF
mit noch vorhandenem Manifest lässt sich nur mit identischer Prüfsumme
wiederherstellen; veränderte lokale Dateien werden nicht überschrieben.

Die Quelle muss die Daten tatsächlich anbieten: fehlende PDF-Links, HTTP-Fehler,
externe Downloadhosts oder Scans ohne Textschicht werden mit einem konkreten
Fehler gemeldet, nicht als leere erfolgreiche Analyse. Externe Originaldateien
können weiterhin per CLI mit `--program-file` eingebunden werden.
Worttreffer sind keine geprüften Übereinstimmungen/Widersprüche.
Explizit geprüfte Richtungsvergleiche bleiben CLI-Funktionen.
Die Webaktion „Alle Abstimmungen“ lädt bewusst sämtliche angebotenen Stimmen,
keine Vollständigkeitsgarantie gegenüber amtlichen Quellen. Der Server bindet ausschließlich
an `127.0.0.1`, ist kein öffentlicher Mehrbenutzer-/Produktivserver und sollte
nicht parallel zu anderen CLI-Importen laufen. Keine zusätzliche Installation,
kein Node-Build und keine Cloud notwendig.

Nach Änderungen am Python-Backend den laufenden Webserver mit `Strg+C` beenden,
mit `uv run parteihack web` neu starten und die Browserseite neu laden.
Oberfläche und Server prüfen beim Start einen gemeinsamen Web-API-Stand.
Bei einem Neustart-Hinweis muss der alte Server vollständig beendet werden.
Ein zweiter Server auf demselben Port wird ausdrücklich abgewiesen.

### Dein Beispiel als direkte Anfrage

```powershell
uv run parteihack compare "Bundestag 2021 bis 2025 Grüne" --online --output data/exports/gruene-probe
```

Der Online-Einstieg importiert höchstens fünf Polls samt Stimmen, lädt nur das
ausgewählte Programm und erstellt Markdown, JSON und eine Versprechenvorlage.
Für alle verfügbaren Abstimmungen:

```powershell
uv run parteihack compare "Bundestag 2021 bis 2025 Grüne" --online --all-polls --output data/exports/gruene-komplett
```

Das ist ein bewusster größerer Import. Ausgabeordner müssen neu sein.
Zwischenstufe für größere Abdeckung ohne vollständigen Massenimport:

```powershell
uv run parteihack compare "Bundestag 2021 bis 2025 Grüne" --online --relevant-polls 10 --output data/exports/gruene-relevant
```

Dabei werden zuerst **alle Poll-Metadaten** der Legislatur geladen und lokal
gegen das Programm gerankt; anschließend werden nur die Stimmen der N
relevantesten Abstimmungen importiert. Der Bericht enthält dann nur Polls mit
lokalen Stimmen, weist die übrige Metadatenabdeckung aber getrennt aus. Die
Rangliste ist eine lexikalische Relevanzhilfe, keine politische Richtung und
keine Bewertung. `--relevant-polls` und `--all-polls` schließen sich aus.
`--only-with-votes` begrenzt auch einen rein lokalen Bericht auf Polls mit
importierten Stimmen; die Metadatenabdeckung wird weiterhin getrennt ausgewiesen.
Bei `--relevant-polls` enthält der JSON-Bericht zusätzlich `import_selection`:
die vollständige Rangliste, tatsächlich ausgewählte Poll-IDs und Importprotokolle.

Für lokale Daten: `uv run parteihack compare "Bundestag 2021 bis 2025 Grüne"`.
Anleitung zur [Versprechenprüfung](docs/COMPARISON.md).

Begrenzte amtliche Belege für einen bereits importierten Poll ergänzen:

```powershell
uv run parteihack enrich-period 132 --poll 5957 --max-polls 1 --max-documents 3 `
  --source "https://www.bundestag.de/parlament/plenum/abstimmung/abstimmung?id=951"
```

Alternativ beim Online-Vergleich `--enrich-sources` verwenden. Unterstützt sind
nur konkrete Bundestagsseiten und -drucksachen; Originale werden mit SHA-256
archiviert. Der Summenabgleich ist kein Erfüllungs- oder Richtungsurteil.

### Daten gezielt abfragen

```powershell
# Kleine Online-Abfrage: Wahl- und Legislaturperioden des Bundestags
uv run parteihack periods --parliament 5

# Begrenzter Probeimport: Stammdaten und bis zu fünf Abstimmungen, keine Einzelstimmen
uv run parteihack sync-period 132

# Dieselbe Auswahl inklusive Einzelstimmen
uv run parteihack sync-period 132 --with-votes

# Lokale Abfragen; lösen keine API-Aufrufe aus
uv run parteihack polls --period 132
uv run parteihack polls --period 132 --search Schulden
uv run parteihack votes --poll 5957
uv run parteihack summary --poll 5957
uv run parteihack status

# CSV-Export der tatsächlich lokal vorhandenen Abstimmungen
uv run parteihack polls --period 132 --format csv --output data/exports/polls.csv
```

Die standardmäßig importierten Abstimmungen sind eine **technische Stichprobe in
API-Reihenfolge**, keine repräsentative Auswahl. Welche IDs enthalten sind, zeigt
`polls`. Nicht davon ausgehen, dass Abstimmung 5957 in jeder Stichprobe vorkommt.

### Bewusst vollständiger Import

```powershell
uv run parteihack sync-period 132 --all-polls --with-votes
```

Dieser Befehl kann mehrere Minuten dauern und viele Daten abrufen. Möglichst
zwischen 22 und 6 Uhr ausführen. Es werden nur die vom Anbieter verfügbaren Daten
importiert, nicht garantiert sämtliche Abstimmungen des Parlaments.

Erfolgreiche Antworten werden standardmäßig 24 Stunden gecacht. Wiederholtes
Ausführen nutzt diesen Cache und aktualisiert Datensätze idempotent. Nach einem
Abbruch kann derselbe Import erneut gestartet werden; es gibt noch keinen
seitenweisen Fortschrittscursor. `--refresh` umgeht den Cache:

```powershell
uv run parteihack sync-period 132 --max-polls 2 --refresh
```

### Datenverzeichnis

Standard ist `./data` relativ zum Arbeitsverzeichnis. Alternativ:

```powershell
uv run parteihack --data-dir "D:\ParteiHack\data" status
# Oder für die aktuelle PowerShell-Sitzung:
$env:PARTEIHACK_DATA_DIR = "D:\ParteiHack\data"
```

`.env.example` dient als Vorlage; `.env` wird **nicht automatisch eingelesen**.
Die globale Option `--data-dir` steht vor dem Unterbefehl.

## Daten und Grenzen

- SQLite: `data/processed/parteihack.sqlite3`
- Archivierte API-Antworten: `data/raw/`
- Exporte: `data/exports/`
- Ausgewählte Originalprogramme und Prüfsummen: `data/programs/`
- API-Antworten: CC0 1.0. Verlinkte Dokumente können andere Rechte haben.
- Importprotokolle unterscheiden Stichproben, vollständige API-Listen und Fehler.
- Lokale Auswertungen zeigen nur vorhandene Daten und kennzeichnen den
  Vollständigkeitsstatus des Einzelstimmenimports.
- Keine automatische historische Partei-Zuordnung und kein Wahlversprechen-Score.
- Automatische Texttreffer sind keine geprüften Versprechen oder Widersprüche.

Beim Aufbau wurde eine echte Stichprobe der Legislatur 132 importiert:
ein Poll mit 733 Einzelstimmen, 772 Mandate, neun Fraktionseinträge und
20 Wahlprogramm-Verweise. Den jeweils aktuellen lokalen Umfang zeigt `status`.

## Entwicklung

```powershell
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Tests sind vollständig offline. Live-Abfragen werden nicht beim Teststart oder
bei der Installation ausgelöst.

## Weitere Dokumentation

- [Architektur und Dateikarte](docs/ARCHITECTURE.md)
- [API-Recherche und Fallstricke](docs/API_RESEARCH.md)
- [Datenmodell](docs/DATA_MODEL.md)
- [Methodik und Bewertungsgrenzen](docs/METHODOLOGY.md)
- [Weitere Programmchecks und Recherchequellen](docs/PROGRAM_SOURCES.md)
- [Wahlprogrammvergleich und Versprechenprüfung](docs/COMPARISON.md)
- [Entwicklungsleitfaden](CONTRIBUTING.md)
- [Beispielabläufe](examples/README.md)
