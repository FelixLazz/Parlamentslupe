# Beispielabläufe

Alle Befehle aus dem Projektwurzelverzeichnis ausführen. IDs sind recherchierte
Beispiele, keine Garantie für einen unveränderlichen aktuellen Datenbestand.

## Kleiner Einstieg

Direkter Programmvergleich (neuer Ausgabeordner):

```powershell
uv run parteihack compare "Bundestag 2021 bis 2025 Grüne" --online --output data/exports/mein-vergleich
```

Standardmäßig eine Stichprobe mit bis zu fünf Polls. Für alle verfügbaren:
`--all-polls`. Ohne `--online` bleibt der Vergleich offline. Anleitung und
Versprechenprüfung: `docs/COMPARISON.md`.

Amtliche Belege zu einem bereits importierten Poll ergänzen:

```powershell
uv run parteihack enrich-period 132 --poll 5957 --max-polls 1 --max-documents 3 `
  --source "https://www.bundestag.de/parlament/plenum/abstimmung/abstimmung?id=951"
```

Der Lauf ist auf konkrete Bundestagsseiten/-drucksachen begrenzt, archiviert
Originale mit SHA-256 und liefert nur einen Summenabgleich, keine
Erfüllungsbewertung.

Gezielte Datenabfragen:

```powershell
uv run parteihack periods --parliament 5
uv run parteihack sync-period 132 --max-polls 2 --with-votes
uv run parteihack polls --period 132
uv run parteihack status
```

Danach eine tatsächlich ausgegebene Abstimmungs-ID verwenden:

```powershell
uv run parteihack votes --poll 5957 --vote no
uv run parteihack summary --poll 5957
uv run parteihack votes --poll 5957 --format csv --output data/exports/votes.csv
```

`summary` gruppiert **Fraktionen**, nicht historische Parteien. Auch bei
vollständigem Import bleibt die Aussage auf die Daten des Anbieters begrenzt.

## Wiederholbarer Offline-Zugriff

Nach dem Import benötigen `polls`, `votes`, `summary` und `status` kein Netzwerk.
`periods` und `sync-period` können Netzwerkrequests auslösen, sofern der Cache
fehlt oder abgelaufen ist.
