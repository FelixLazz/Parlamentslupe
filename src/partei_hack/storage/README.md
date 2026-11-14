# Persistenz

- `database.py`: SQLite-Schema 1, Entitäten, HTTP-Cache, Importläufe und Abdeckung.
- `archive.py`: eindeutige, inhaltlich unveränderte JSON-Rohantworten.

SQLite-Verbindungen werden explizit geschlossen. JSON ist kein vertrauenswürdiger
SQL-Code; Werte immer parametrisieren. API-Daten oder Archivdateien nicht
automatisch bereinigen oder löschen.
