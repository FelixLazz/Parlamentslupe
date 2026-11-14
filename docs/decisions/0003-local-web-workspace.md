# ADR 0003: Lokale Website statt separater Cloud-/Frontend-Plattform

- Datum: 2026-11-14
- Status: umgesetzt

Ergänzt durch ADR 0004: Die unten dokumentierte Beschränkung auf bereits lokale
PDF-Dateien wurde durch gezielte, bestätigte Downloads des ausgewählten Programms
ersetzt. Die ursprüngliche Entscheidung bleibt zur Nachvollziehbarkeit erhalten.
ADR 0006 ergänzt die gemeinsame Webauswahl: freigegebene Auswahldaten und
ausdrücklich gewählte oder bewusst alle Polls statt pauschaler Fünf-Poll-Grenze.

## Anlass

Gewünscht ist ein Benutzerinterface mit Auswahl von Bundestag/Landesparlament,
Wahlperiode und Fraktion. Die Python-/SQLite-Dienste sind bereits vorhanden.

## Entscheidung

Eine paketierte HTML-/CSS-/JavaScript-Oberfläche wird über die
Python-Standardbibliothek auf Loopback bereitgestellt. `parteihack web` startet
sie; CLI und Website teilen dieselben Daten und Anwendungsdienste.
Kein Node-Toolchain-Zwang, CDN, Login, KI-Provider oder Cloud-Dienst.

Parlamente, Perioden und Fraktionen kommen aus importierten API-Entitäten, nicht
aus geratenen ID-Listen. Ein Stammdatenabruf ist ausdrücklich bestätigt.
Abfragen bleiben lokal; bewusste Stimmenimporte sind auf höchstens fünf Polls
pro Webaktion begrenzt. Vollständige Importe bleiben explizite CLI-Aufgaben.
PDFs werden nicht über die Website heruntergeladen. Lokal archivierte
Original-PDFs können erneut geprüft und nach ungeprüften Worttreffern durchsucht
werden. Programmpartei und historische Fraktion bleiben getrennte Auswahlen.

## Alternativen

- Ein separates React-/API-Projekt mit Build und zusätzlichem Backendframework:
  aktuell unnötige Installations-/Deploymentkomplexität.
- Eine rein statische Demo mit fiktiven Ergebnissen: kein funktionales Interface
  zum bestehenden Werkzeug und fachlich unzulässiger Datenersatz.
- Öffentlicher Webdienst: benötigt Authentifizierung, Jobverwaltung und
  prozessübergreifende API-Drosselung; nicht Teil dieser Anforderung.

## Konsequenzen

Der lokale Server ist kein öffentlicher Produktivserver. Host-/Origin-/Token-
Prüfung, feste Asset-Routen und CSP schützen den lokalen Browserzugriff.
Online-Aktionen werden innerhalb dieses Prozesses serialisiert; andere CLI-
oder Serverprozesse dürfen nicht gleichzeitig importieren.
Lange Importe bleiben an den laufenden Server gebunden. Es gibt keine
Benutzerverwaltung oder Wiederaufnahme von Hintergrundjobs.
