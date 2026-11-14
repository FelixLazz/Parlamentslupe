# Lokale Weboberfläche

**Parlamentslupe** ist der sichtbare Webname. Logo und Browser-Icon zeigen
eine Lupe über einem großen „P“; beide sind lokale SVG-Grafiken ohne externe Assets.
Der Markenblock ist gestapelt, damit der Name auch in der schmalen Seitenleiste passt.
Technische Paketnamen, CLI-Befehle und Datenpfade bleiben unverändert.

Start: `uv run parteihack web`, dann `http://127.0.0.1:8000`.
Optional `--port 8080`; das globale `--data-dir` steht vor `web`.

- `server.py`: Loopback-HTTP, feste Asset-Routen, lokale JSON-Endpunkte,
  Host-/Origin-/Token-Prüfung und serialisierte Online-Aktionen.
  Clientabbrüche beim Header- oder Bodyversand schließen die Verbindung ohne
  Request-Traceback für `ConnectionResetError`/`BrokenPipeError`.
- `index.html`, `app.css`, `app.js`: responsive deutsche Oberfläche, ohne
  Node-Build, CDN, externe Schriftarten, Telemetrie oder Cloud.
- Fachlogik in `services/workspace.py`, vorhandene Import-/Abfragedienste
  bleiben gemeinsam mit der CLI nutzbar.

Der abschließende Typografieabschnitt in `app.css` verwendet natürliche
Buchstabenabstände, gut lesbare Beschriftungen und umbrechende Bedienelemente.
Navigationsnamen bleiben jeweils ein Textcontainer. Diese Darstellungsregeln
ändern keine API-Bezeichnungen, Originalzitate oder extrahierten Quelltexte.
Änderungen an den Assets erfordern nur das Neuladen der Browserseite.
Bei Änderungen am Python-Backend hingegen den laufenden Server vollständig
beenden und neu starten. `/api/catalog` enthält dafür `web_api_version`; ein
unpassender Serverstand zeigt beim Seitenstart einen konkreten Neustart-Hinweis.
Der lokale Server bindet seinen Port exklusiv (Windows: `SO_EXCLUSIVEADDRUSE`);
ein zweiter Server auf demselben Port scheitert statt Anfragen auf alte und neue
Instanzen zu verteilen. Abgebrochene Clientverbindungen beim Antwortversand
(`BrokenPipeError`, `ConnectionResetError`, `ConnectionAbortedError`) schließen
die Verbindung ohne Request-Traceback.

Auswahl: Parlament → Legislaturperiode → historische Fraktion. Stammdaten
kommen ausschließlich aus lokalen Entitäten oder explizit bestätigten API-Abrufen.
„Auswahldaten beim Auswählen online ergänzen“ ist eine einmalige Freigabe für
diese Seite, keine gespeicherte Einwilligung und kein Import von Einzelstimmen/PDFs.
Die Vorbereitung läuft bei Auswahländerungen sequenziell, pro Auswahlkombination
einmal. `GET /api/choices?period=…` liefert ausschließlich lokale Programme,
Titel und Abdeckungsangaben, ohne Fraktionsauswahl oder Stimmenübertragung.
Die Importabdeckung wird dabei nur über Stimmen-IDs und Importmanifest geprüft,
nicht durch die teure vollständige Stimmen-/Mandatsauswertung.
`POST /api/prepare` ergänzt Fraktionen, Programme und vollständige Poll-Metadaten.
Die Titelauswahl ist ein durchsuchbarer, aufklappbarer Mehrfachauswahlbereich;
„Alle“ ist separat und nur mit vollständiger API-Titelliste verfügbar.
`POST /api/run` validiert die gesamte Auswahl vor dem Online-Client, importiert
nur unvollständige gewählte Stimmen mit historischen Mandaten (`current_on=all`)
und erstellt bei gewähltem Programm unmittelbar den PDF-basierten Vergleich.
Programm ist optional. Lokale Anzeige, Auswahlbeibehaltung und Wiederverwendung
vollständiger Stimmen bleiben möglich. Ein großer Import ist bewusst zu bestätigen.
Bestehende Stichproben-Endpunkte bleiben kompatibel; die neue Hauptaktion verwendet
keine automatische Stichprobengröße.
Landesparlamente werden nicht über erfundene IDs oder feste Listen angeboten.
Leere Datenbanken zeigen einen Einstieg zum bewussten Stammdatenabruf.

Abstimmungstitel-/Datumsfilter, Einzelstimmen, Quellen, Importabdeckung und
JSON-Download beziehen sich auf die Auswahl. Programm und Wahlpartei werden
separat gewählt. Programmlisten lassen sich unabhängig vom Stimmenimport über
`refresh`/Scope `programs` nachladen. `GET /api/program` zeigt den extrahierten
Text seitenweise; bei fehlender Originaldatei liefert es `409` mit
`code=program_missing`. Die Oberfläche bietet dann eine bestätigte
`POST /api/program`-Aktion an: nur die ausgewählte, API-verlinkte und beim
Anbieter gehostete PDF laden, archivieren und extrahieren. Lokale Quellen nutzen.

`GET /api/compare` erstellt lokal den gemeinsamen Vergleichsbericht aus
Programmzitaten und Fraktionsstimmen. `POST /api/compare` darf nach Bestätigung
die ausgewählte PDF und optional eine begrenzte Stimmenstichprobe nachladen.
Programm-/Wahl-/Fraktionsreferenzen werden vor dem Download validiert.
Der Vergleich unterstützt explizite API-Auswahlen auch bei Landesparlamenten
und ohne Parteialias in der CLI-Freitextsyntax. Keine Richtungsprüfungen im Web.
Die Stimmenansicht ergänzt Ja/Nein-Anteil, Teilnahme und Anteil der
Ja-/Nein-Mehrheitsrichtung mit allen dokumentierten Fraktionseinträgen als
explizitem Nenner. Leere Nenner werden als nicht berechenbar angezeigt.
„Programm genauer untersuchen“ erschließt alle erkannten Kandidaten mit
Textsuche, Mengen-/Jahres-/Bedingungsfilter, Originalzitaten und Satzkontext.
Die Anzeige lädt jeweils bis zu 20 weitere Kandidaten aus dem lokalen Bericht.
Ein Filter umfasst auch Kandidaten ohne Treffer unter den lokalen
Top-Zuordnungen. Die Liste enthält ausschließlich ungeprüfte Vorschläge.

`POST /api/evidence` ergänzt nach Bestätigung höchstens fünf lokale Poll-Kontexte
und drei amtliche Bundestagsbelege. Der gemeinsame Kern `enrich_period` archiviert
Originale mit SHA-256 und liefert einen neuen Vergleichsbericht zurück. Freie
Quellen-URLs sind nicht möglich; die Allowlist steht in `api/official.py`.

Online-Aktionen sind bestätigungspflichtig: Freigabe der Auswahldaten sowie
gemeinsamer Start mit ausgewählten oder ausdrücklich allen Polls und optional
der ausgewählten Programm-PDF. Alte Stichprobenrouten bleiben auf fünf begrenzt.
Mindestens 2,1 Sekunden Requestabstand
gelten auch zwischen Webaktionen. Keine parallelen CLI-Importe oder weiteren
Serverprozesse: die Drosselung koordiniert nur diesen Prozess.

Der Server ist ausschließlich für lokale Einzelnutzung gedacht, nicht als
öffentlich erreichbarer Produktivserver. Kein Login, keine Benutzerverwaltung,
keine Hintergrundjobs oder Importfortsetzung nach dem Schließen des Servers.
