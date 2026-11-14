# Offline-Tests

Die Daten sind **synthetische Testdaten**, keine echten Abgeordneten oder
Abstimmungen. `conftest.py` blockiert externe Socket-Verbindungen und stellt
temporäre Datenbanken sowie kontrollierte HTTP-Antworten bereit.

| Datei | Geprüfter Bereich |
| --- | --- |
| `test_api_client.py` | Cache, Rate-Limit, Retry, Pagination und Fehler |
| `test_storage.py` | Schema, idempotente Speicherung und Roharchiv |
| `test_importer.py` | Umfang, historische Mandate und Filterkontrolle |
| `test_queries.py` | lokale Filter, Joins, Kategorien und Abdeckung |
| `test_cli.py` | Bedienbarkeit, Validierung und sichere Exporte |
| `test_comparison.py` | Deutsche Anfragen, Auswahl, Zitate, Richtungen und Berichte |
| `test_retrieval.py` | Deutsche Stämme, Suchkonzepte, Originalkontext und Negations-/Bedingungsflags |
| `test_quality.py` | Datenintegrität, ID-Mengen, Vorgangsflags, offene Ergebnisse in Vorgangsgruppen, Teilnahme und begrenzte Versprechenzählung |
| `test_evidence.py` | Amtliche URL-Allowlist, HTML-/PDF-Belege, SHA-256, Summenabgleich und Budgetgrenzen |
| `test_evidence_web.py` | Bestätigungspflicht, Web-Budgetgrenzen und gemeinsamer Belegrecherche-Kern |
| `test_programs.py` | Echte synthetische PDFs, Downloadbegrenzung und Provenienz |
| `test_web.py` | Landtagsauswahl, Web-Endpunkte, Datenlücken, Filter, separate Programmlisten, gezielter PDF-Abruf, Extraktion/Seitenansicht, Vergleich, Originalwiederherstellung, CSRF/Host-Schutz, Importbestätigung und Aktionsdrosselung |
| `test_web_selection.py` | Lokale Titelauswahl vor Fraktions-/Stimmenimport, reine Metadatenvorbereitung, gemeinsamer Import mit PDF-Vergleich, ausdrückliche Alle-Auswahl, Wiederverwendung/Erweiterung, Auswahlvalidierung vor Netzabruf, Schutz und erhaltene Teilergebnisse |
| `test_web_disconnect.py` | Abbruch beim Header-/Bodyversand: Reset, Broken Pipe und Windows-AbortedError ohne Request-Traceback |
| `test_typography.py` | Natürliche Schriftabstände, umbrechende Schaltflächen, zusammenhängende Navigationsbeschriftungen sowie Webname und Lupenlogo einschließlich Browser-Icon, unabhängig von der Vergleichslogik |

Ausführung: `uv run pytest`. Keine Live-API-Tests in der Standardsuite ergänzen.
