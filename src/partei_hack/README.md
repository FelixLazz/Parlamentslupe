# Python-Paket `partei_hack`

- `config.py`: Konfiguration und Pfade.
- `models.py`: Mindestvalidierung von API-Objekten.
- `cli.py`: Typer-Befehle und Export.
- `api/`: Kommunikation mit dem Anbieter.
- `storage/`: lokale Persistenz und Provenienz.
- `services/`: Anwendungsabläufe und lokale Abfragen.
- `web/`: lokaler HTTP-Server und Oberfläche; Start mit `parteihack web`.

Fachlogik bleibt von CLI und HTTP getrennt. `python -m partei_hack` ist ein
alternativer Einstieg zum installierten Befehl `parteihack`.
