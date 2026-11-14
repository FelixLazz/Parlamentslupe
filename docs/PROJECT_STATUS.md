# Projektstand

Stand: **2026-11-14** · Version **0.3.1**.
Vergleichspipeline, Datenqualitätsprüfung, amtliche Belegarchivierung und lokale
Web-Endpunkte implementiert und geprüft.

## Aktuelle Fortsetzung – Gemeinsame Webauswahl

### Nachtrag: Datenabruf, Serverstände und leichte Titelauswahl

- Fehler lokal reproduziert: Der laufende alte Webserver lieferte die neuen
  Assets, aber `/api/choices` mit HTTP 404. Mehrere alte Webserverprozesse waren
  parallel aktiv. Die betreffenden lokalen Server wurden beendet und mit dem
  aktuellen Code neu gestartet; keine externen Importe ausgelöst.
- `/api/catalog` liefert `web_api_version: 1`. Die Oberfläche prüft den Vertrag
  vor den abhängigen Anfragen. Fehlende/abweichende Version zeigt einen
  konkreten Neustart-Hinweis und blockiert die initialen Hauptbedienelemente,
  statt einen allgemeinen Datenbank-/Abruffehler vorzutäuschen.
- `LoopbackHTTPServer` deaktiviert Port-Wiederverwendung und verwendet auf
  Windows `SO_EXCLUSIVEADDRUSE`. Ein zweiter Server auf demselben Port wird
  abgewiesen; nicht mehr mehrere aktive Listener für denselben lokalen Dienst.
- `vote_import_status` prüft Anzahl und archivierte ID-Menge ohne vollständige
  Stimmen-/Mandats-Payloads. Titelauswahl und Auswahlvalidierung nutzen diesen
  leichten Pfad; die bisherige Vollständigkeitssemantik bleibt erhalten.
- Rein lokale Messung für 162 Poll-Titel: vorher **20,585 Sekunden**, danach
  **0,275 Sekunden** im Dienst und **0,421 Sekunden** für den Browserabruf.
  Das sind Einzelmessungen des vorhandenen Bestands, keine allgemeine Garantie.
- HTTP-Antwortversand fängt zusätzlich `ConnectionAbortedError` ab, passend zum
  beobachteten Windows-Fehler 10053 bei abgebrochener Clientverbindung.
- **240 Offline-Tests erfolgreich**. Neue Prüfungen: Webvertrag, Titelauswahl
  ohne Detailauswertung, ID-Mengenwechsel und exklusive Portbindung; die
  Abbruchtests umfassen nun auch AbortedError für Header/Body.
- Browser: lokale Titelroute HTTP 200 mit 162 Titeln/20 Programmen; Auswahl
  wird wieder aufgebaut. Versionsprüfung akzeptiert den aktuellen Stand und
  meldet den fehlenden Vertrag verständlich. Zweiter lokaler Port-Bindversuch
  tatsächlich blockiert. Keine neuen API- oder PDF-Downloads durchgeführt.

### Nachtrag: Clientabbrüche und Relevanzprotokoll

- HTTP-Antworten fangen `ConnectionResetError` und `BrokenPipeError` jetzt
  auch beim Header-Versand ab, nicht erst beim Body. Ein abgebrochener Client
  schließt die Verbindung ohne diesen Request-Traceback; daraus wird kein
  Beleg für die Ursache eines gesamten Prozessendes abgeleitet.
- CLI-Relevanzimporte speichern `import_selection` im JSON-Bericht:
  vollständige Rangliste, tatsächlich ausgewählte Poll-IDs, Metadaten- und
  Stimmenimportprotokoll. Die Auswahl bleibt ausdrücklich ungeprüft und ist
  kein Richtungsurteil. Der zuvor offene `selection_export`-Befund ist behoben.
- Prüfung dieses Nachtrags: **238 Offline-Tests erfolgreich**, einschließlich
  vier simulierten Verbindungsabbrüchen (Header/Body, Reset/Broken Pipe) und
  CLI-Auswahlprotokoll mit HTTP-Mocks. Kein erneuter Live-Import.

Implementiert:

- Einmalige, nicht vorausgewählte Freigabe für abhängige Auswahldaten während
  dieses Seitenaufrufs. Parlamente, Perioden, Fraktionen, Programm-Metadaten und
  vollständige Poll-Metadaten; noch keine Mandate, Stimmen oder PDFs.
- Lokale Titel-/Programmauswahl vor der Untersuchung. Durchsuchbarer aufklappbarer
  Mehrfachauswahlbereich, separate Option „Alle Abstimmungen“. Alle benötigt eine
  gegen API-Anzahl und ID-Menge vollständige lokale Titelliste.
- „Auswahl laden & untersuchen“ bündelt nach einer Bestätigung die gewählten
  fehlenden/unvollständigen Stimmen mit historischen Mandaten und optional die
  ausgewählte PDF samt unmittelbar erstelltem Vergleich. Ohne Programm nur Analyse.
- Vollständige Stimmenimporte und lokale PDFs wiederverwenden, Auswahl erhalten,
  Vergleich auch beim lokalen Filtern nicht verwerfen. Gewählte Poll-IDs begrenzen
  den Bericht; die Abdeckung der ganzen Legislatur bleibt separat ausgewiesen.
- Neue Routen `/api/choices` (lokal), `/api/prepare` und `/api/run` (bestätigt,
  serialisiert, Token-/Origin-geschützt). Bestehende Stichprobenrouten unverändert
  auf fünf begrenzt; die neue bewusst ausgewählte/Alle-Aktion darf größer sein.
- Auswahldatenantworten direkt nutzen, kein erneutes Katalog-/Auswahl-Laden nach
  erfolgreichem gemeinsamem Start. Pro Kombination eine Vorbereitung je Seite.

Geprüft:

- **229 Offline-Tests erfolgreich**, darunter 25 neue Auswahltests: nur Metadaten,
  explizite Teil-/Alle-Auswahl, Fraktions-/Perioden-/Programmprüfung vor Netzabruf,
  gezielter Stimmenimport mit `current_on=all`, PDF und Vergleich in einer Aktion,
  Wiederverwendung und Erweiterung, Scoped-Berichte auch nach Folgeaktionen,
  Fehler/Teildaten, Bestätigung, Token/Origin und Online-Lock.
- Ruff-Prüfung aller geänderten Python-Dateien und projektweite Formatprüfung
  erfolgreich. Projektweites `ruff check .` meldet weiterhin den schon zuvor
  dokumentierten Befund `selection_export` in `cli.py:355`; CLI nicht geändert.
- Echte Browserprüfung mit temporärem Server und ausschließlich synthetischen
  HTTP-Mocks: Auswahldatenfreigabe, einzelne/alle Polls, Programmvergleich,
  erhaltene Auswahl, Titelsuche ohne Häkchenverlust, nur ein Run-POST auch bei
  doppeltem Aufruf sowie erhaltener Vergleich nach lokalem Filtern.
- Browser zeigt bei der ersten Vorbereitung genau drei lokale POSTs, bei erneuter
  Vorbereitung derselben Kombination keinen weiteren Online-POST. Gemeinsamer
  Start benötigt nur einen Run-POST, keine anschließenden Katalog-GETs.
- JavaScript im Browser geladen, keine Konsolenfehler; Desktop-Screenshot und
  DOM ohne horizontale Seitenüberbreite geprüft. Keine Mobilgeräte-Sichtprüfung.
  Keine echten API-Importe oder Programm-Downloads für diese Prüfung.

Grenzen/nächste Schritte: Große Importe bleiben synchron ohne Live-Fortschritt
oder Hintergrundjob. Fehler führen nicht zu automatischen Wiederholungen;
gespeicherte Teildaten bleiben erhalten. Große reale Importe wurden nicht
ausgeführt; bewusst möglichst 22–6 Uhr starten. Nach Backendänderung Webserver
neu starten. Entscheidung und Folgearbeit: ADR 0006.

## Ziel

Lokale, nachvollziehbare Erschließung der abgeordnetenwatch-API als Grundlage
für belegte Programm-/Abstimmungsvergleiche und explizit geprüfte Richtungszuordnungen.

## Fortsetzung am 14.11.2026 – Methodenstand v3

### Vertiefte Programmanalyse und weitere Quellen

Der gemeinsame Vergleichsbericht enthält `program_analysis` mit Textseiten,
indexierten Passagen, Kandidaten und deren erkannten Mengen-/Jahres-/Bedingungs-
und Verneinungsmerkmalen. Das Kandidateninventar enthält jetzt den vorherigen
und nächsten Satz sowie deren gesonderte Prüfmerkmale.
Die Website bietet unter „Programm genauer untersuchen“ Textsuche, Merkmalsfilter
und jeweils 20 weitere Einträge. Kandidaten ohne lokalen Top-Treffer lassen
sich gezielt untersuchen. Der Markdown-Bericht enthält die Übersicht, JSON das
vollständige Inventar. Die ursprüngliche Satzheuristik bleibt die Grundlage.

Ein echter lokaler CLI-Lauf wurde unter
`data/exports/gruene-programmanalyse/` erstellt. Das vorhandene Grünen-Programm
370 umfasst **272 Textseiten**, **3770 indexierte Passagen** und **570 ungeprüfte
Kandidaten**. Davon enthalten 17 erkannte Mengenangaben, 22 Jahreszahlen,
7 Bedingungen im Zitat und 26 Bedingungen im Satzkontext. Gruppen können sich
überschneiden. Zu 7 Kandidaten bestehen lokale Top-Treffer innerhalb der
11 detaillierten Polls. Diese Zählung beschreibt den erkannten Bestand.

**203 Offline-Tests erfolgreich**, einschließlich Inventar ohne Abstimmungstreffer,
leerer Textseiten, Originalkontext und Ausgabe über den Web-Endpunkt.
Ruff-Prüfung der geänderten Python-Dateien und projektweite Formatprüfung
erfolgreich. JavaScript-Syntax und isolierte Renderlogik mit simulierten
DOM-Elementen geprüft, einschließlich Nachladen, Suche ohne Ergebnis und
Bedingungsfilter über den Satzkontext. Eine echte Browserprüfung bleibt offen.
Der Browserzugriff meldete einen nicht verfügbaren Browser-Host.
Der zuvor dokumentierte projektweite Ruff-Befund in `cli.py` besteht fort.

Weitere Primärquellen sind in `PROGRAM_SOURCES.md` dokumentiert. Hohenheim liefert
konkrete Programmchecks, Polidoc historische und regionale Texte, Real-O-Mat
begründete Vorgangspositionierungen. Koalitionsstudien und der Koalitionstracker
haben unterschiedliche Auswahlmengen. Wahl-O-Mat nennt besondere Nutzungsbedingungen.
Die Quellen wurden recherchiert, zusätzliche Importadapter sind offen.

Implementiert sind ergänzte Bezugsgrößen in JSON, Markdown und Webanzeige.
Ja/Nein-Anteil, Teilnahme einschließlich Enthaltungen und Anteil der
Ja-/Nein-Mehrheitsrichtung werden auf alle dokumentierten Fraktionseinträge
bezogen. Geprüfte Richtungszuordnungen enthalten zusätzlich den Richtungsanteil
an Ja/Nein sowie an allen Einträgen mit absoluten Nennern. Leere Nenner bleiben
`null`. Die Freigabe der Richtungsdaten erfolgt weiterhin separat.

Die Vorgangs- und Versprechenzusammenfassung erhält die Häufigkeiten sämtlicher
Einzelergebniskategorien. Nicht auswertbare Zuordnungen verhindern, dass eine
weitere auswertbare Mehrheit den gesamten Vorgang als auswertbar erscheinen
lässt. Explizite Widersprüche bleiben `mixed`. Versprechen mit und ohne
geprüfte Links sowie Links und Prüfvorhaben werden getrennt gezählt.
Die Methodenversion lautet `bm25-context-evidence-v3`.

Geprüft wurden **202 Offline-Tests**, einschließlich neuer Regressionen für
die Zusammenfassung offener Ergebnisse, leere Nenner, Teilnahme und den
Unterschied zwischen Ja/Nein-Anteil und Anteil an allen Einträgen.
Die vorhandene `.venv` wurde direkt verwendet, da `uv` in dieser Sitzung
nicht im Suchpfad lag. Ruff-Prüfung aller geänderten Python-Dateien und die
projektweite Formatprüfung sind erfolgreich. Projektweites `ruff check .`
meldet eine bestehende ungenutzte Variable `selection_export` in `cli.py:355`.
Die CLI wurde in dieser Fortsetzung nicht geändert.

Ein echter rein lokaler Vergleich über den CLI-Einstieg wurde erstellt und
gegen den JSON-Bericht geprüft. Ausgabe unter
`data/exports/gruene-auswertung-v3/` mit **162 Poll-Metadaten**, **11 vollständigen
Stimmenimporten** und **11 detaillierten Polls**. Eine neue Browser-Sichtprüfung
der ergänzten Textanzeige ist offen.

Die fortgesetzte Quellenrecherche zu DIP, Manifesto Project und Comparative
Pledges Project steht mit Primärquellen in `API_RESEARCH.md`. Insbesondere
verweist die DIP-Dokumentation auf einen veröffentlichten gültigen Schlüssel.
Zusätzliche Quellenadapter und gemessene Retrieval-Evaluierungen sind offen.
`METHODOLOGY.md` enthält den Arbeitsplan mit versioniertem Prüfsatz, unabhängigen
Relevanzurteilen und Precision@k/Recall. In diesem Schritt wurden die vorhandenen
lokalen Daten ausgewertet.

## Neu in 0.3.1: Relevanzsteuerung und API-Ergebnis

- **Poll-Metadaten vollständig, Stimmen gezielt:** `compare --online
  --relevant-polls N` lädt zuerst alle Poll-Metadaten einer Legislatur und
  importiert danach nur die Stimmen der N lexikalisch relevantesten, noch nicht
  vollständigen Abstimmungen. Das erhöht die nutzbare Abdeckung ohne einen
  ungeprüften Massenimport aller Stimmen.
- **Nachvollziehbare Rangliste:** Titelstamm-Treffer vor BM25-Score, danach
  Datum und ID; jeder Kandidat enthält Zitat, Seite, Trefferbegriffe und den
  Hinweis `program_relevance_bm25_not_political_direction`. Die Rangliste ist
  keine politische Richtung und keine Bewertung.
- **Getrennte Abdeckung:** `local_polls` zählt alle lokalen Poll-Metadaten,
  `reported_polls` die im Bericht detaillierten Polls, `polls_with_local_votes`
  die Polls mit lokalen Stimmen und `polls_with_complete_votes` die vollständigen
  Stimmenimporte. `report_scope.only_with_votes` hält die Begrenzung fest.
- **API-Ergebnis:** `field_accepted` wird als `api_outcome`
  (`accepted`/`rejected`/`unknown`) ausgewiesen, getrennt für Poll und
  Qualitätszusammenfassung. Es ist ausdrücklich keine Umsetzungs- oder
  Erfüllungsaussage.
- **Gezielter Stimmenimport:** `Importer.import_votes` lädt Stimmen nur für
  bereits lokal vorhandene Polls derselben Legislatur, validiert Poll-Verweis,
  Mandat und Stimmwert und schreibt ein Importprotokoll mit `votes_only`.
- **Fraktionshistorie präzisiert:** Deckt die von der API gelieferte
  `fraction_membership` das Abstimmungsdatum nicht ab (bei Fraktionswechslern
  teils nur der neueste Eintrag), gilt das als **nicht prüfbar**, nicht als
  Widerspruch. Nur eine tatsächlich abdeckende, abweichende Fraktion blockiert.
- **Berichtsumfang:** `compare --only-with-votes` begrenzt auch einen lokalen
  Bericht ausdrücklich auf Polls mit importierten Stimmen.

### Prüfung von 0.3.1

- `uv run pytest`: **193 Tests erfolgreich**, vollständig offline. Neu geprüft:
  `field_accepted`/`api_outcome` inklusive unbekanntem Ergebnis, Begrenzung des
  Berichtsumfangs mit erhaltenen Metadaten, Relevanzrangliste, Auswahlregeln,
  gezielter Stimmenimport ohne erneuten Poll-Abruf, Abbruch bei doppelten oder
  unbekannten Poll-IDs sowie nicht abgedeckte Fraktionshistorie als
  `uncheckable` statt `mismatch`.
- `uv run ruff check .` und `uv run ruff format --check .`: erfolgreich.
- Bewusster Live-Lauf `--relevant-polls 10` (14.11.2026, außerhalb des
  empfohlenen 22–6-Fensters, aber begrenzt): **162 Poll-Metadaten** vollständig,
  **10 neue Stimmenimporte**, zusammen **11 Polls / 7347 Stimmen**. Alle 11
  Stimmenimporte sind gegenüber der API vollständig und ID-mengengeprüft; alle
  11 sind nach der Korrektur als Richtungsdaten nutzbar, **0 blockierende
  Datenprobleme**. Bericht: `data/exports/gruene-relevant-v031-final/report.md`.
- Der bereits amtlich geprüfte Poll 5957 bleibt in diesem Lauf enthalten:
  **112 Ja / 1 Nein / 0 Enthaltungen / 4 nicht abgegeben** bei den Grünen.
- Die Gesamtabdeckung bleibt **11 von 162 Polls**; ein vollständiger Import
  aller Stimmen wurde nicht ausgeführt.

## Neu in 0.3.0: belastbarere Auswertung

- **Suche:** BM25-Ranking mit deutschem Snowball-Stemming, offengelegten
  Suchkonzepten (z. B. Windkraft/Solar → erneuerbare Energien) und Gewichtung
  nach Titel, API-Beschreibung, amtlichem Kontext und Themen/Ausschüssen.
- **Originalkontext:** Treffer enthalten den vorherigen und nächsten Satz derselben
  PDF-Seite. Bedingungen, Verneinungen, Jahre und Mengen werden nur als
  Prüfhinweise ausgewiesen, nicht automatisch interpretiert.
- **Doppelte Belege:** identische Sätze über mehrere PDF-Seiten werden einmal
  indexiert. Suchkonzepte allein können keinen Treffer ohne belastbare
  Textüberschneidung erzeugen.
- **Datenintegrität:** Prüfung von Poll-Datum, Legislaturgrenzen, doppelten
  Mandatsstimmen, Mandatszeitraum, historischen Fraktionsmitgliedschaften und
  unbekannten Stimmwerten. Abweichende Ja-/Nein-Stimmen und Nichtteilnahme
  bleiben getrennt sichtbar.
- **Identitätsprüfung:** importierte Poll- und Vote-IDs werden als Mengen
  protokolliert und beim Abgleich erneut geprüft. Gleiche Anzahl allein genügt
  nicht mehr als Vollständigkeitsnachweis.
- **Amtliche Belege:** `enrich-period` und die Webaktion „Amtliche Belege ergänzen“
  laden standardmäßig höchstens drei verlinkte Bundestagsseiten/-drucksachen
  (Web fest auf drei begrenzt, CLI bewusst bis 20), archivieren sie
  mit SHA-256 und prüfen veröffentlichte Gesamt- und Fraktionssummen gegen die
  lokalen API-Stimmen. Die Verknüpfung bleibt ausdrücklich eine Kontextzuordnung,
  keine automatisch geprüfte Identität der Abstimmungsfassung.
- **Qualitätsdimensionen:** getrennte Angaben zu API-Abdeckung, Datenproblemen,
  Quellenlage, Summenabgleich, Prüfbedarf und ausdrücklich `overall_score: null`.
  Kein Programmtreue- oder Erfüllungsscore.
- **Geprüfte Auswahl:** mehrere Polls mit derselben `procedure_id` zählen als ein
  Prüfvorhaben; jedes Versprechen wird höchstens einmal gezählt. `partial` und
  `mixed` werden nicht als Zustimmung ausgegeben.
- **Ungeprüfte Kandidaten:** Das gesamte Programm wird als Kandidateninventar
  ausgewiesen. Ein fehlender lokaler Treffer ist kein Beleg für Untätigkeit und
  kein gültiger Score-Nenner.

### Prüfung von 0.3.0

- `uv sync --dev`: erfolgreich; neue lokale Abhängigkeit `snowballstemmer`.
- `uv run pytest`: **187 Tests erfolgreich**, vollständig offline. Neu geprüft:
  amtliche URL-Begrenzung, HTML-/PDF-Belege, manipulierte Archive, Summenkonflikte,
  begrenzte Belegrecherche, historische Fraktionsverläufe, ID-Mengenabgleich,
  Kandidatenzählung und Stemming-Treffer.
- `uv run ruff check .`, `uv run ruff format --check .` und `uv build`: erfolgreich.
- Echter Probelauf Poll **5957** (Schuldenbremse, 18.03.2025):
  amtliche Bundestagsseite `?id=951` archiviert, Gesamtsummen **512 Ja / 206 Nein /
  0 Enthaltungen / 15 nicht abgegeben** und Grünen-Summen **112 / 1 / 0 / 4**
  stimmen mit der lokalen API-Ableitung überein.
- Der Summenabgleich bestätigt nur veröffentlichte Aggregate; er ersetzt keine
  Prüfung der endgültigen Gesetzesfassung oder der politischen Wirkungsrichtung.
- Neuer Bericht: `data/exports/gruene-evidenz-v03-final/report.md`. Geladen wurden
  nur die ausdrücklich ausgewählte Bundestagsseite und die von ihr verlinkten
  Drucksachen; keine freie Websuche und keine weiteren Quellenhosts.
- Die Abdeckung bleibt **1 von 162 API-Polls**. Die Verbesserung der Methode
  behebt diese Datenlücke nicht. Seit 0.3.1 kann sie mit
  `--relevant-polls` schrittweise und nachvollziehbar verkleinert werden.

## Lokale Weboberfläche

### Webname und Logo: Parlamentslupe

- Sichtbarer Name in Seitenkopf, Seitentitel, Startseiten-Link und Fußzeile:
  **Parlamentslupe**. Logo und Browser-Icon zeigen eine Lupe mit großem „P“
  im Glas als SVG. Der Markenblock ist für schmale Seitenleisten gestapelt.
- Technischer Paketname, CLI, Datenpfade und Schnittstellen bleiben unverändert.
- Prüfung: **204 Offline-Tests erfolgreich**; Ruff- und Formatprüfung der
  geänderten Testdatei erfolgreich. Neuer Regressionstest für Namen und beide SVGs.
- Browser-DOM bei 800 Pixeln ohne horizontale Seitenüberbreite; Markenbeschriftung
  passt in den Markenblock. Desktop-Screenshot geprüft. Keine neue
  Mobilgeräte-Sichtprüfung und keine Online-Importe ausgeführt.

- Start mit `uv run parteihack web`, optional `--port`; ausschließlich Loopback.
- Responsive Oberfläche ohne zusätzliche Abhängigkeiten, Node-Build, CDN oder Cloud.
- Abhängige Auswahl **Parlament → Wahlperiode → Fraktion**, ohne automatische
  Fraktionsvorwahl. Bundestag und API-Landesparlamente verwenden dieselbe Logik;
  Optionen stammen aus lokalen Entitäten oder ausdrücklich geladenen Stammdaten.
- Lokale Titel-/Datumsfilter, paginierte Abstimmungen, Fraktionszählungen,
  Einzelstimmen, Quellenlinks, technische API-Abdeckung und JSON-Download.
- Wahlpartei/Programm separat auswählen; Programme zur vorhergehenden Wahl
  unabhängig vom Stimmenimport nachladen. Ausgewählte Original-PDF bei Bedarf
  nach Bestätigung laden, archivieren und lokal pro PDF-Seite extrahieren.
- Extrahierten Text seitenweise lesen; „Vergleich starten“ im Programm- und
  eigenen Vergleichsbereich: Originalzitate, Fraktionsstimmen, Quellen,
  Datenabdeckung und separater JSON-Export. Keine Richtungsbewertung.
- Bestätigte Online-Aktionen: Auswahldaten und gemeinsam ausdrücklich gewählte
  oder bewusst alle angebotenen Polls samt Stimmen und historischen Mandaten.
  Alte Stichproben-Endpunkte bleiben auf höchstens fünf Polls begrenzt.
- Keine automatischen Netzabfragen beim Start oder bei lokalen GET-Abfragen;
  PDF-Downloads nur gezielt für das ausgewählte Programm nach Bestätigung.
- Pro Webprozess serialisierte Online-Aktionen; Mindestabstand auch zwischen
  Aktionen. Host-/Origin-/Token-Schutz, feste Asset-Routen und CSP.

### Nachbesserung: Typografie

- Natürliche Buchstabenabstände für Überschriften, Markentext und Kennzahlen;
  reduzierte Sperrung kleiner Großbuchstaben-Beschriftungen.
- Kleine Hinweise und Bedienelemente vergrößert; Schaltflächen und Kennzahlen
  können bei Platzmangel umbrechen. Wortabstände nicht durch Laufweite ersetzen.
- Navigationsbeschriftungen jeweils in einem Textcontainer; Logo als SVG statt
  überlappender Buchstaben. Anzahl und Prozentwert mit echtem Textzwischenraum.
- Seitenaufteilung und Quelldaten unverändert.
- Desktop-Screenshots vor/nach der Änderung und Browser-DOM bei 1496 Pixeln
  geprüft: keine horizontale Seitenüberbreite, sichtbare Schaltflächen ohne
  Textüberlauf, natürliche Überschriften-Laufweite und getrennte Prozentangaben.
  Keine neue Mobilgeräte-Sichtprüfung.
- `uv run --no-sync pytest tests/test_typography.py`: **2 Tests erfolgreich**.
  Ruff-Prüfung und Formatprüfung dieser Testdatei erfolgreich.
- Gesamttestlauf zum Prüfzeitpunkt blockiert: `snowballstemmer` fehlt für
  zwischenzeitlich geänderte Backendmodule. Projektweite Ruff-Prüfungen melden
  zusätzlich Befunde in diesen anderen Dateien; sie wurden für die
  Typografiekorrektur nicht verändert. Keine neue Gesamtfreigabe behauptet.

### Nachbesserung: Programmabruf und Vergleich

Ursache des gemeldeten Fehlers: Der erste Webstand bot nur lokale PDF-Belege.
Programm-Metadaten aus einem Stimmenimport waren noch kein PDF-Download. Bei
fehlender Datei brach die Webroute vor der Textextraktion ab; eine echte sichtbare
Vergleichsaktion fehlte. Das ist durch die oben beschriebenen Abläufe ersetzt.

- `uv run pytest`: **148 Tests erfolgreich**, darunter **64 Web-Tests**.
  Vollständig offline: separate Programm-Metadaten, bestätigter gezielter
  PDF-Download, echte synthetische PDF-Extraktion und Seitenansicht, HTTP-/Scan-
  Fehler, Host-/Token-Schutz, Vergleich für synthetischen Landtag und eine Partei
  ohne CLI-Alias, begrenztes Stimmen-Nachladen sowie unveränderte Prüfsummen.
- `uv run ruff check .`, `uv run ruff format --check .` und `uv build`: erfolgreich.
  Aktuelle Vergleichsoberfläche im Wheel geprüft; keine Laufzeitdaten im Source-Archiv.
- Fehlende PDF bei vorhandenem Manifest kann nach Bestätigung mit identischer
  SHA-256 wiederhergestellt werden. Veränderte lokale Dateien oder andere
  Remote-Versionen werden nicht still ersetzt.
- CLI und Website verwenden denselben Vergleichsbericht-Kern.
- Browser-DOM-Prüfung mit bestehendem Programm 370: 272 PDF-Seiten,
  583.903 extrahierte Textzeichen, Zitat auf PDF-Seite 91 neben 112 Ja,
  1 Nein und 4 Nichtteilnahmen. Vergleichs-JSON aktiviert.
- Bestätigte Web-POST-Abläufe mit vorhandenem Original geprüft, Auswahl und
  Bedienbarkeit bleiben erhalten. Fehlendes Programm 367 öffnet gezielten
  Download-Bestätigungsdialog; für diese Prüfung nicht heruntergeladen.
- Keine neuen externen API-Importe oder PDF-Downloads für diese Prüfung gestartet.
  Neue Downloads und Fehlerfälle sind über kontrollierte HTTP-Mocks geprüft.
- Lokaler Webserver nach Backendänderung neu gestartet. Browserseite für die
  neue Oberfläche neu laden.

### Frühere Prüfung der ersten Web-Erweiterung

- `uv run pytest`: **124 Tests erfolgreich**, darunter **40 Web-Tests**;
  vollständig offline, einschließlich synthetischer Landtagsauswahl, Datenlücken,
  PDF-Originalbelegen, Importgrenzen, CSRF/Host-Schutz und Aktionsdrosselung.
- `uv run ruff check .` und `uv run ruff format --check .`: erfolgreich.
- `uv build`: Source-Distribution und Wheel erfolgreich; HTML/CSS/JS im Wheel
  enthalten. Source-Archiv enthält nur die vorgesehenen Datenordner-READMEs,
  keine Laufzeitdaten oder `.venv`.
- `uv run parteihack web --help`: erfolgreich.
- Lokaler Server und Browser-DOM geprüft: vorhandene Bundestagsperiode 132,
  Fraktion 321, Poll 5957 mit 112 Ja, 1 Nein und 4 Nichtteilnahmen; separate
  Programmauswahl 370 mit lokalem Originalbeleg auf PDF-Seite 91.
- Keine neuen API-Importe oder PDF-Downloads für diese Prüfung ausgelöst.
- Keine abgeschlossene Screenshot-/Mobilgeräte-Sichtprüfung: Screenshotwerkzeug
  hatte kein sichtbares Browserfenster. Responsive CSS vorhanden, nicht als
  umfassend visuell geprüft ausgewiesen.

### Grenzen der Website

- Kein öffentlicher Produktivserver, Login oder Mehrbenutzerbetrieb.
- Keine prozessübergreifende Importdrosselung; nicht parallel per CLI importieren.
- Keine Hintergrundjobs, automatische Importfortsetzung oder
  Versprechenprüfungsformulare. Bewusst vollständige Stimmenimporte sind nun auch
  per Alle-Auswahl möglich; geprüfte Richtungsberichte weiterhin über die CLI.
- Landesparlament-/Perioden-/Fraktionspfade offline synthetisch geprüft, nicht
  für jedes Landesparlament live validiert; tatsächliches Angebot hängt von der API ab.
- Ein Nachladeangebot garantiert keine Quellenverfügbarkeit: fehlende API-Links,
  HTTP-Fehler, externe PDF-Hosts oder Scans ohne Textschicht bleiben ausdrückliche
  Fehler. Keine OCR. Externe Originaldateien können per CLI eingebunden werden.
- Die amtliche Belegrecherche ist derzeit auf konkrete Bundestagsseiten und
  -drucksachen begrenzt. Landesparlamente haben noch keinen eigenen amtlichen
  Quellenadapter; deren Links bleiben im Bericht als offene Prüfaufgabe sichtbar.
- Archivierte HTML-/PDF-Belege werden nicht stillschweigend ersetzt. Ändert sich
  der Inhalt, wird der gespeicherte Stand als verändert gemeldet.
- Der Summenabgleich bestätigt weder Einzelstimmen noch die Identität der
  endgültigen Beschlussfassung. Er ist kein Beweis für oder gegen ein Versprechen.
- Der gemeinsame Webstart begrenzt den Vergleich auf die ausdrücklich ausgewählten
  Poll-IDs; bestehende Vergleichsrouten ohne IDs umfassen alle lokalen Polls.
  Titel-/Datumsfilter der Übersicht beeinflussen nicht den Vergleich.
  Worttreffer bleiben ungeprüft.

Bedienung: `../README.md`; Architekturentscheidungen: ADR 0003, 0004 und 0005.

## Neu in 0.2.0

- `compare "Bundestag 2021 bis 2025 Grüne"`: deterministische deutsche Anfrage,
  eindeutige Perioden-/Programm-/Fraktionsauswahl.
- `--online`: begrenzter Import inklusive Stimmen und ausgewählter Original-PDF.
  `--all-polls` ermöglicht ausdrücklich den vollständigen verfügbaren API-Import.
- Programm-PDF, SHA-256, Herkunft und PDF-Seiten unter `data/programs/`.
- Lexikalische Zitatvorschläge mit nachvollziehbaren Suchwörtern. Automatische
  Treffer bleiben ungeprüft und enthalten keine Richtungs-/Erfüllungsbewertung.
- JSON-Prüfdateien: Originalzitat, Seite, Prüfsumme und Pflichtfelder validieren;
  Richtungsvergleich nur mit expliziter Nutzerprüfung, nicht unabhängig verifiziert.
- Markdown, JSON und `promises.template.json` in einem neuen Ausgabeordner.
- Atomare Speicherung pro API-Seite beschleunigt größere Stimmenimporte.

### Prüfung von 0.2.0

- `uv sync --dev`: erfolgreich; zusätzliche lokale PDF-Abhängigkeit `pypdf`.
- `uv run pytest`: **84 Tests erfolgreich**, vollständig offline.
- `uv run ruff check .` und `uv run ruff format --check .`: erfolgreich.
- `uv build`: Source-Distribution und Wheel erfolgreich.
- Lange deutsche Beispielanfrage mit `--online --max-polls 1`: erfolgreich.
- Tatsächlich ausgewählt: Wahlprogramm-ID **370**, Partei-ID **5**, Wahl-ID **128**,
  Fraktions-ID **321**, Legislatur **132**.
- Originalprogramm: **272 PDF-Seiten**, SHA-256
  `96e2c2125af4b32c94e3f32af67a998d76f22246412193c5819f0ba5a7d6a432`.
- Belegter Treffer zur Schuldenbremse: PDF-Seite **91**, Poll **5957**;
  Grünen-Fraktion **112 Ja, 1 Nein, 0 Enthaltungen, 4 Nichtteilnahmen**.
- Anschließend rein offline geprüft und als Bericht exportiert:
  `data/exports/gruene-2021-2025-vergleich/report.md`.
- Der Echtbestand ist weiterhin **1 von 162 API-Polls**. Kein vollständiger
  Stimmen-Massenimport wurde für die Entwicklung gestartet.
- Es wurden keine realen Zuordnungen als nutzergeprüft fingiert. Der echte
  Bericht enthält Zitatvorschläge, keine behauptete Erfüllung oder Verletzung.

Details und Bedienung: `COMPARISON.md`.

## Bereits im Grundgerüst implementiert

- Installierbares Python-Paket im `src`-Layout, lokale `.venv`, `uv.lock`.
- CLI: `doctor`, `init-db`, `periods`, `sync-period`, `polls`, `votes`, `summary`,
  `status`; alternativ `python -m partei_hack`.
- Synchroner API-Client: mindestens 2,1 Sekunden Abstand, maximal vier Versuche,
  `Retry-After`, 24-Stunden-Cache, Range-Pagination und Konsistenzprüfungen.
- SQLite-Schema 1, Rohantworten, Quellen-URLs, UTC-Abrufzeitpunkte und Importläufe.
- Historische Mandate mit `current_on=all`, Fraktionsmetadaten, begrenzte oder
  vollständige API-Poll-Listen, optionale Stimmen und Wahlprogramm-Metadaten.
- Lokale Titel-/Zeitraum-/Themenfilter; Unicode-Titelsuche, Stimmenfilter,
  Fraktionszählungen und technische Prüfung der Stimmenabdeckung.
- JSON-/CSV-Export; keine stillen Dateiüberschreibungen, CSV-Formelschutz.
- `AGENTS.md` als zentraler Einstieg, Verweise für Claude, Gemini und Copilot,
  Ordner-READMEs, Architektur, API-Recherche, Methodik und Architekturentscheidung.

## Frühere Prüfung von 0.1.0

Unter Windows mit Python **3.14.6** und uv **0.11.24**:

- `uv sync --dev`: erfolgreich, Umgebung und Lockdatei erzeugt.
- `uv run pytest`: **41 Tests erfolgreich**, vollständig offline.
- `uv run ruff check .`: erfolgreich.
- `uv run ruff format --check .`: erfolgreich.
- `uv run parteihack --help`: erfolgreich.
- `uv build`: Source-Distribution und Wheel erfolgreich erzeugt. Archivprüfung:
  keine SQLite-Dateien, keine `.venv` und keine Laufzeitdaten im Source-Archiv.
- Kleiner Live-Import:
  `uv run parteihack sync-period 132 --max-polls 1 --with-votes`.
  Ergebnis: **772 Mandate**, **9 Fraktionseinträge**, **1 von 162 Polls**,
  **733 Einzelstimmen**, **20 Wahlprogramm-Metadaten**, 2 Periodenentitäten.
- Lokale Fraktionszählung zu Poll **5957**: 733 lokale Stimmen, gemeldete
  Quellanzahl 733; technische Abdeckung positiv.
- Separater Live-Paginationstest mit Seitengröße 1 und maximal 2 Polls:
  IDs **5957**, **5871**, Total jeweils 162. Zweiter Poll nur im Antwortcache/
  Roharchiv, nicht als Entität importiert.

Der erste Mehrseitentest erkannte eine falsche Interpretation von `range_end`
und brach kontrolliert ab. Nach Korrektur und neuem Regressionstest war der
Live-Test erfolgreich. Details in `API_RESEARCH.md`.

Die vorhandenen Laufzeitdaten sind ausdrücklich **eine Stichprobe**. Der aktuelle
lokale Datenstand wird durch `uv run parteihack status` ermittelt; diese Markdown-
Datei ist kein automatisch aktualisierter Datenbankbericht.

Python 3.12/3.13 sind laut Paketanforderung vorgesehen, hier aber nicht getestet.

## Nicht implementiert

OCR, historische Partei-Zeitreihe, semantische Zuordnung, separate Interviews/
Reden als Versprechensquellen, KI-Provider und automatische
Wahlversprechen-Erfüllungsbewertungen.

## Bekannte Grenzen

- Erneuter Import ist idempotent und nutzt Cache, hat aber keinen gespeicherten
  seitenweisen Fortschrittscursor. Harte Abbrüche können `running` zurücklassen.
- Keine automatische Bereinigung von an der Quelle gelöschten Datensätzen.
- Kein Snapshot-Token für gleichzeitig veränderte API-Listen.
- API-Abdeckung ist nicht gegen sämtliche amtlichen Abstimmungen validiert.
- Noch kein eigenständiger Import vollständiger Politikerprofile/Kandidaturen
  oder eine Abfrage aller Stimmen einer Person über mehrere Polls.
- Kein allgemeines Schema-Migrationssystem, kein Mehrbenutzerbetrieb und keine
  über mehrere Prozesse koordinierte API-Drosselung.
- Noch kein Git-Repository, Remote, CI-Dienst oder Code-Veröffentlichungslizenz.
- Freitextsyntax derzeit Bundestag, zwei Jahre und genau eine bekannte Partei.
- Lexikalische Suche mit Stämmen und wenigen offengelegten Suchkonzepten; keine
  allgemeine Semantik, keine vollständige Synonymabdeckung und keine logische
  Prüfung von Bedingungen oder Verneinungen.
- Amtliche Belege sind nur für den Bundestag automatisiert abrufbar; andere
  Parlamente benötigen weitere geprüfte Quellenadapter.
- Nutzerprüfungen werden auf Beleg-/Datenkonsistenz, nicht auf inhaltliche Wahrheit
  oder Prüferidentität geprüft. Zweitprüfung und Gegenquellen sind optionale
  Pflichtfelder der Prüfdatei, keine unabhängige Verifikation.

## Empfohlene nächste Schritte

1. Einen bewusst angeforderten vollständigen Import außerhalb der Stoßzeiten
   durchführen; keine automatischen Massenabrufe starten. Erst danach werden
   Qualitäts- und Abdeckungszahlen aussagekräftiger.
2. API-Abdeckung und Quellenverweise mit amtlichen Daten vergleichen; die
   ID-Mengenprüfung aus 0.3.0 dafür nutzen.
3. Ein kleines Referenzset tatsächlich prüfen: Zitat, Vorlage, Wirkungsrichtung,
   Gegenquelle und Zweitprüfung. Ungeprüfte Kandidaten nicht als Nenner verwenden.
4. Amtliche Quellenadapter für weitere Parlamente ergänzen, sofern belastbare
   öffentliche Originalquellen verfügbar sind.
5. Personenabfragen und historische Wahlpartei-Zuordnung ergänzen.
6. Suchqualität systematisch evaluieren; semantische Suche nur mit unveränderter
   Beleg- und Prüfpflicht.
