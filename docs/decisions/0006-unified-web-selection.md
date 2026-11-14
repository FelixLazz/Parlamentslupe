# ADR 0006: Auswahldaten vor Details, gemeinsamer bestätigter Webstart

- Datum: 2026-11-14
- Status: umgesetzt
- Ergänzt ADR 0003/0004: Die dortige Fünf-Poll-Grenze gilt für die alten
  Stichprobenrouten, nicht für die neue ausdrückliche Poll-Auswahl.

## Anlass

Mehrere Ladebestätigungen zwischen Dropdowns, ein nachträglicher Stimmenimport
und die separate Programmvorbereitung erschweren eine einzige Untersuchung.
Abstimmungen sollen schon anhand ihrer Titel gezielt auswählbar sein.

## Entscheidung

Der Seitenstart bleibt offline. Ein nicht voreingestelltes Kontrollkästchen
erlaubt für diese Seite das Nachladen der abhängigen Auswahldaten: Parlamente,
Perioden, Fraktionen, Programm-Metadaten und vollständige Poll-Metadaten.
Keine Mandate, Stimmen oder PDFs in diesem Schritt. Der Browser serialisiert
diese Schritte, bereitet jede Kombination einmal vor und nutzt den API-Cache.

Die Person wählt Fraktion, optional Programm sowie einzelne Polls oder bewusst
alle Polls. „Alle“ setzt eine gegen API-Anzahl und ID-Menge vollständige
Titelliste voraus. Titel können durchsucht werden, ohne Häkchen zu verlieren.
Eine gemeinsame Bestätigung nennt Umfang, PDF-Quelle und Zeitfenster 22–6 Uhr.
Erst danach werden fehlende/unvollständige Stimmen mit historischen Mandaten
geladen, die ausgewählte PDF bei Bedarf vorbereitet und der Vergleich erstellt.
Eine explizite Teilmenge begrenzt den Bericht, nicht die Legislaturabdeckung.

Serverseitige Auswahlprüfung erfolgt vor dem Online-Client. Token, Origin,
Online-Lock, Rate-Limit, Archivierung und bestehende ID-Mengenprüfung bleiben
verbindlich. Die POST-Größe ist auf 64 KiB begrenzt, explizite ID-Listen auf 5000.

## Alternativen und Grenzen

- Stille Netzabfragen beim Seitenstart: verletzen die explizite Freigabe.
- Weiter nur fünf zufällige API-Polls: erfüllt keine gezielte Titelauswahl.
- PDFs aller Programme vorladen: unnötig und nicht erlaubt.
- Neue Hintergrundjobplattform: nicht erforderlich für diesen lokalen Ablauf.

Lange Importe bleiben synchron an den lokalen Server gebunden. Keine
Fortschrittsjobs, keine automatische Fehlerwiederholung oder prozessübergreifende
Drosselung. Gespeicherte Teildaten bleiben bei Fehlern nutzbar; vollständige
Stimmenimporte und vorhandene PDFs werden wiederverwendet. Ein API-vollständiger
Import ist keine amtlich vollständige Abdeckung und kein Erfüllungsbeweis.
