# Lokale Daten

Dieser Ordner ist bis auf die README-Dateien von Git ausgeschlossen.
Die Software legt fehlende Laufzeitverzeichnisse selbst an.

- `raw/`: archivierte erfolgreiche API-Antworten.
- `processed/`: SQLite-Datenbank mit Cache, Entitäten und Importstatus.
- `exports/`: ausdrücklich angeforderte JSON-/CSV-Exporte.
- `programs/`: ausgewählte Originalprogramme, SHA-256 und Seitenmetadaten.
- `evidence/`: ausgewählte amtliche HTML-/PDF-Belege, benannt nach SHA-256.

Keine fingierten Beispieldaten als echte API-Antworten ablegen. Backups und
Löschung liegen beim Nutzer; die Anwendung löscht diesen Ordner nicht automatisch.
