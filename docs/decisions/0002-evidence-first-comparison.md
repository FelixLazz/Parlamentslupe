# ADR 0002: Belegvergleich vor automatischen politischen Bewertungen

- Datum: 2026-11-14
- Status: angenommen für Version 0.2.0

## Anlass

Eine deutsche Anfrage wie „Bundestag 2021 bis 2025 Grüne“ soll Programm und
Abstimmungsverhalten zusammenführen. Ein KI-Provider ist nicht konfiguriert;
aus Ja/Nein allein lässt sich kein Wahlversprechenbruch zuverlässig ableiten.

## Entscheidung

Deterministische Anfrageauflösung, Original-PDF mit SHA-256, PDF-Seitenzitate,
lexikalische Vorschläge und transparente Datenabdeckung. Ohne externe Dienste.
Politische Richtungszuordnungen kommen ausschließlich aus expliziten Prüfdateien.
Das Originalzitat wird maschinell nachgewiesen; die Prüferbehauptung bleibt
als nicht unabhängig verifiziert gekennzeichnet.

## Konsequenzen

Sofort lokal nutzbare Berichte, keine erfundenen Zitate, keine vorgetäuschte
semantische Kompetenz. Die Wortsuche verpasst Synonyme und kann irrelevante
Treffer liefern. Ein Richtungsvergleich ist keine Umsetzungskontrolle.
Spätere Suchverfahren können ausgetauscht werden, ohne Rohdaten umzudeuten.
