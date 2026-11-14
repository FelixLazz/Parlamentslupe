# ADR 0004: Gezielter PDF-Abruf und sichtbare Vergleichsaktion im Web

- Datum: 2026-11-14
- Status: umgesetzt
- Ergänzt ADR 0003; ersetzt dessen Beschränkung auf bereits lokale PDF-Dateien.

## Anlass

Der erste Webstand importierte Programm-Metadaten, aber keine PDF-Inhalte.
Bei nicht lokal vorbereiteten Wahlperioden führte „Textbelege finden“ deshalb
zum Fehler, bevor die Extraktion erreicht wurde. Außerdem fehlte eine sichtbare
Vergleichsaktion, obwohl die CLI schon einen gemeinsamen Bericht erzeugte.
Der Nutzer verlangt, fehlende Daten über die Oberfläche abrufen zu können.

## Entscheidung

- Programmlisten unabhängig vom Stimmenimport abrufen.
- Lokale GET-Abfragen bleiben ohne Netzwerk. Fehlende PDF-Originale liefern
  einen maschinenlesbaren Hinweis; die Oberfläche bietet eine Bestätigung an.
- Bestätigte POST-Aktionen laden ausschließlich die ausgewählte API-verlinkte,
  bei abgeordnetenwatch gehostete PDF über den bestehenden API-Client.
  Rate-Limit, Cache-Nutzung, Prozesssperre und Sicherheitsgrenzen bleiben erhalten.
- Text pro PDF-Seite sichtbar machen, mit Herkunft und Prüfsumme.
- Eine eigene Vergleichsaktion nutzt dieselbe Berichtserstellung wie die CLI,
  ohne die Bundestags-/Parteialias-Beschränkung der Freitextsyntax zu übernehmen.
- Optionaler Stimmenimport bleibt eine bewusst ausgewählte begrenzte Stichprobe.

## Grenzen

Ein Abrufangebot garantiert nicht die Verfügbarkeit historischer Quellen.
Fehlende Links, externe Downloadhosts, HTTP-Fehler und Scans ohne Textschicht
bleiben ausdrückliche Fehler. Keine erfundenen Ergebnisse oder stillen Downloads
aller Programme. Ein fehlendes PDF-Original mit bestehendem Manifest darf nur
mit identischer SHA-256 wiederhergestellt werden; keine fremden Dateien ersetzen.

Programmpartei und historische Fraktion sind getrennte Auswahlen. Worttreffer
bleiben ungeprüft. Ohne explizite Richtungsprüfung gibt es weder Übereinstimmungs-/
Widerspruchsurteil noch Erfüllungsbewertung.
