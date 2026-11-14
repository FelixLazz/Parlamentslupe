# Recherche: abgeordnetenwatch API

Recherche und kleine Live-Stichproben: **2026-11-14**. Beobachtete API-Version:
**2.10.0**. Werte und Verfügbarkeit können sich ändern.

## Quellen

- Grundlagen: https://www.abgeordnetenwatch.de/api
- Antwortformat: https://www.abgeordnetenwatch.de/api/response
- Perioden: https://www.abgeordnetenwatch.de/api/entitaeten/parliament-period
- Mandate: https://www.abgeordnetenwatch.de/api/entitaeten/candidacy-mandate
- Abstimmungen: https://www.abgeordnetenwatch.de/api/entitaeten/poll
- Einzelstimmen: https://www.abgeordnetenwatch.de/api/entitaeten/vote
- Fraktionen: https://www.abgeordnetenwatch.de/api/entitaeten/fraction
- Programme: https://www.abgeordnetenwatch.de/api/entitaeten/election-program

## Vertrag laut Dokumentation

- Basis: `https://www.abgeordnetenwatch.de/api/v2/`
- JSON, öffentlich lesbar; bei den getesteten Endpunkten keine Authentifizierung.
- API-Daten unter CC0 1.0; nicht pauschal auf externe PDFs übertragen.
- 30 Requests pro Minute/IP, höchstens ein Request pro Sekunde.
- Bei HTTP 429 drosseln und beispielsweise 60 Sekunden warten.
- Massenabrufe möglichst einmalig und zwischen 22 und 6 Uhr.
- Standardlisten: 100, maximal 1.000 Entitäten.
- `range_start` ist der Offset; `range_end` ist trotz des Namens die
  **Seitengröße**, nicht die absolute Endposition (auch live bestätigt).
  Alternativ `page` und `pager_limit`.
- Filteroperatoren unter anderem `eq`, `ne`, `gt`, `gte`, `lt`, `lte`, `cn`, `in`.
  Nicht jeder Operator funktioniert auf jedem Feld.
- Referenzfilter wie `politician[entity.party.entity.short_name]=SPD`.
- `related_data` ist auf maximal 1.000 Objekte begrenzt und nicht weiter filterbar.
  Deshalb Einzelstimmen über den Listenendpunkt paginieren.

## Relevante Endpunkte

| Ressource | Wichtige Filter / Verknüpfungen |
| --- | --- |
| `parliaments` | Bundestag: ID 5 |
| `parliament-periods` | `parliament`, `type=election` oder `legislature` |
| `candidacies-mandates` | `parliament_period`, `type=mandate`, `current_on=all` |
| `fractions` | `legislature` |
| `polls` | `field_legislature`, `field_poll_date`, `field_topics`, `field_accepted` |
| `votes` | `poll`, `mandate`, `vote` |
| `election-program` | Singular im Pfad! `parliament_period` verweist auf Wahl |

Stimmen referenzieren **Mandate**, nicht direkt Personen. `fraction` bei Stimmen
ist mit `poll` filterbar; keine Verkettung oder `in`/`notin` für diesen Filter.
Mandate enthalten zeitliche `fraction_membership`-Einträge. Die Partei auf einem
Politikerprofil ist die derzeitige Partei, keine historische Zeitreihe.

`field_accepted` ist ein boolesches Vorgangsergebnis (angenommen/abgelehnt) und
kein Beleg für Umsetzung oder Versprechenserfüllung. Fehlt das Feld, bleibt das
Ergebnis `unknown`; es wird nicht aus anderen Feldern geraten.

## Live beobachtet

| Beobachtung | Ergebnis |
| --- | --- |
| Bundestag Wahl 2021 / Legislatur 2021–2025 | IDs 128 / 132 |
| Bundestag Wahl 2025 / Legislatur ab 2025 | IDs 160 / 161 |
| `polls?field_legislature=132&range_end=1` | 1 Objekt, gemeldetes Total 162 |
| `votes?poll=5957&range_end=1` | 1 Objekt, gemeldetes Total 733 |
| `election-program?parliament_period=128&range_end=1` | Total 20, Beispiel mit PDF-URL |
| Periodenliste nur mit `pager_limit=8`, ohne `page` | 12 statt 8 Objekte |
| Poll-Liste mit `sort_by=id&sort_direction=asc` | HTTP 500 bei einem Test |
| Dieselbe Periodenfilterung ohne Sortierung | erfolgreich |
| Einzelne Poll-Entität | `entity_type` tatsächlich `node` |
| `field_accepted` im Poll-Payload | boolesch, z. B. `false` bei abgelehntem Antrag |
| `polls?field_legislature=132&range_start=1&range_end=2` | 2 Objekte ab Offset 1 |

Das sind Stichproben, keine abschließende Prüfung aller Filter, Sortierfelder
oder der Seitennummerierung. Der Client verwendet deshalb Range-Pagination,
prüft IDs/Metadaten und setzt kein `sort_by=id` voraus.

Ein erster paginierter Live-Probelauf behandelte `range_end` irrtümlich als
Endposition. Die Konsistenzprüfung stoppte ihn. Die Implementierung und ein
Regressionstest wurden auf die beobachtete Seitengrößen-Semantik korrigiert.

## Weitere Schutzmaßnahmen

- `count`, `total` und tatsächlich gelieferte Objekte prüfen.
- Leere Seiten vor dem gemeldeten Ende und wiederholte IDs als Fehler behandeln.
- Rückgabefilter im Import zusätzlich lokal gegen die angefragte Legislatur prüfen.
- API-Korrekturen während eines mehrseitigen Imports können trotzdem zu
  inkonsistenten Momentaufnahmen führen. Ein Snapshot-Token ist nicht bekannt.
- `field_intro` enthält HTML und kann mehrere verwandte Vorgänge beschreiben.
  Nicht ungeprüft als genau eine vollständige Gesetzesvorlage interpretieren.
- `field_related_links` kann neben HTTP-URLs auch interne `entity:node/...`-Verweise
  enthalten.
- `field_topics` und `field_committees` verweisen auf eigene Entitäten. Themen
  enthalten Beschreibung und Elternknoten; Ausschüsse sind einer Legislatur
  zugeordnet. Nur lokal aufgelöste oder ausdrücklich nachgeladene Details werden
  für Suche/Qualität verwendet.

## Amtliche Ergänzungsquellen

- Bundestag: `https://www.bundestag.de/parlament/plenum/abstimmung/abstimmung?id=…`
  veröffentlicht Abstimmungsergebnisse mit Gesamt- und Fraktionssummen sowie
  verlinkten Drucksachen.
- Drucksachen/Plenarprotokolle: `https://dserver.bundestag.de/btd/…` bzw. `btp/…`.
  Ältere `dip21`/`dipbt`-Adressen werden auf `dserver` kanonisiert.
- Diese Quellen sind **nicht** Teil der abgeordnetenwatch-API. Der Abruf ist auf
  eine Allowlist begrenzt, nutzt dieselbe Drosselung und folgt keinen Redirects.
- Eine Abstimmungsseite kann mehrere namentliche Abstimmungen und geänderte
  Ausschussfassungen beschreiben. Summengleichheit ist kein Beweis für die
  Identität der konkreten Vorlage.
- DIP-API des Bundestags benötigt einen gültigen Schlüssel und ist im Projekt
  bisher nicht konfiguriert. Zugangsmöglichkeiten siehe fortgesetzte Recherche.

## Fortgesetzte Quellenrecherche am 14.11.2026

Die weitere Recherche zu Hohenheim, Polidoc, Real-O-Mat, Koalitionsstudien und
Wahl-O-Mat ist mit Einsatzmöglichkeiten und offenen Prüfungen in
`PROGRAM_SOURCES.md` dokumentiert.

Die folgenden Dokumentationen wurden gelesen. Datenabrufe und Adapter für diese
zusätzlichen Angebote sind noch offen.

- **DIP** stellt Vorgänge, Vorgangspositionen, Aktivitäten, Personen, Drucksachen
  und Plenarprotokolle bereit. Die Kurzdokumentation verweist auch auf einen auf
  der Hilfeseite veröffentlichten gültigen API-Schlüssel. Ein persönlicher
  Schlüssel ist damit keine zwingende Voraussetzung. Für ParteiHack bleibt die
  ausdrückliche Freigabe zur Zugangskonfiguration erforderlich. Ein künftiger
  Adapter könnte Vorgangsverläufe und Fassungen erschließen. Eingebettete
  Referenzlisten können unvollständig sein und benötigen eigene Abfragen.
  [Bundestag, DIP-Kurzdokumentation](https://dip.bundestag.de/documents/informationsblatt_zur_dip_api.pdf)
- **Manifesto Project** bietet Programmtexte, Annotationen und versionierte
  Datensätze an. Texte und Annotationen erfordern laut API-Dokumentation einen
  Account und API-Schlüssel. Unser möglicher Einsatz wäre die Prüfung der
  Themenabdeckung und Segmentierung. Die Zuordnung zwischen Partei-, Wahl- und
  Dokument-IDs sowie die Originalsprache müssten einzeln geprüft werden.
  [Manifesto-API](https://manifesto.wzb.eu/information/documents/api)
- **Comparative Pledges Project** verlangt in seiner gemeinsamen
  Versprechensdefinition überprüfbare Zusagen und vergleichbare Belegstandards.
  Daraus leiten wir als Projektentscheidung ab, Ziele, Bedingungen, Zeitraum
  und messbare Kriterien vor einer späteren Umsetzungsbewertung zu erfassen.
  Die Website liefert hier einen methodischen Bezug, ein Importdatensatz
  wurde bei dieser Recherche nicht geprüft.
  [Comparative Pledges Project](https://comparativepledges.net/)

Bestehende amtliche HTML-/PDF-Adapter bilden den implementierten Zugang zu
parlamentarischen Zusatzbelegen.
