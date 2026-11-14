# API-Zugriff

`client.py` besitzt als einzige Produktionskomponente HTTP-Zugriff.
Alle Netzrequests laufen sequenziell mit mindestens 2,1 Sekunden Abstand.
Cache-Treffer benötigen keinen künstlichen Abstand.
`download_program` verwendet dieselbe Drosselung und akzeptiert nur ausgewählte
HTTPS-PDFs aus dem Dateiarchiv von abgeordnetenwatch. Keine externen Redirects.
`download_official` lädt ausschließlich über die Allowlist in `official.py`
konkrete Bundestagsseiten und -drucksachen, ebenfalls ohne Redirects.

Pagination prüft Metadaten und doppelte IDs; unbekannte Felder bleiben erhalten.
Tests verwenden `httpx.MockTransport` und eine künstliche Uhr statt echte Wartezeit.
Keine parallelen zusätzlichen Clients einsetzen, die gemeinsam das IP-Limit
überschreiten könnten.
