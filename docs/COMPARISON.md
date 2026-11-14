# Wahlprogramm und Abstimmungsverhalten vergleichen

## In der Website

1. `uv run parteihack web` starten und **Auswahldaten beim Auswählen online ergänzen**
   einmalig für diese Seite freigeben. Ohne Freigabe bleibt alles lokal.
2. Parlament und Wahlperiode wählen. Fraktionen, Programm-Metadaten und sämtliche
   Abstimmungstitel werden vor den Einzelstimmen angeboten.
3. Fraktion, optional Programm und im aufklappbaren Titelfeld mehrere Abstimmungen
   auswählen. **Alle Abstimmungen** ist eine separate, bewusste Option.
4. **Auswahl laden & untersuchen** einmal bestätigen: fehlende ausgewählte Stimmen,
   historische Mandate und nur die gewählte Original-PDF laden; mit Programm wird
   der Vergleich unmittelbar erstellt. Vollständige Stimmen und vorhandene PDFs
   werden wiederverwendet. Große Importe möglichst zwischen 22 und 6 Uhr starten.
5. Unter **Wahlprogramme** bleibt **Programm laden & Text anzeigen** für die
   seitenweise Originalansicht verfügbar. Der Vergleich enthält Zitatvorschläge,
   Fraktionsstimmen, Quellen und technische API-Abdeckung, kein Erfüllungsurteil.
   „Amtliche Belege ergänzen“ lädt weiterhin höchstens fünf lokale Poll-Kontexte und
   insgesamt höchstens drei verlinkte Bundestagsoriginale.
   Vergleich als JSON exportieren.

Der gemeinsame Start begrenzt den Vergleich ausdrücklich auf die gewählten Poll-IDs
(`report_scope.poll_ids`); die Abdeckung der ganzen Legislatur bleibt separat.
Ohne explizite Poll-Auswahl liefern die bisherigen lokalen Vergleichsendpunkte
weiterhin alle lokalen Polls. Explizite Webauswahlen unterstützen auch Landesparlamente
und Parteien außerhalb der CLI-Freitextaliasliste. Programmpartei und Fraktion
sind unabhängig ausgewählt; daraus folgt keine historische Parteizugehörigkeit.

Keine PDF-Sammeldownloads und keine stillen Massenimporte. Falls die API keinen
geeigneten Link liefert, die Quelle ausfällt oder die PDF keine Textschicht hat,
wird der konkrete Fehler angezeigt. OCR und externe PDF-Hosts werden nicht
automatisch nachgerüstet. Eine gezielte lokale Datei bleibt per CLI möglich.
Die Webaktion ist ein belegter lexikalischer Recherchevergleich, keine
automatische Richtungs-/Erfüllungsbewertung. Explizite Prüfdateien weiterhin
über die unten beschriebene CLI.

## Direkter Einstieg

```powershell
uv run parteihack compare "Bundestag 2021 bis 2025 Grüne" --online --output data/exports/gruene-probe
```

Das importiert höchstens fünf Polls samt Stimmen, ermittelt das Programm zur
**vorhergehenden Wahl**, lädt nur die ausgewählte PDF und erstellt:

- `report.md`: lesbarer Recherchebericht.
- `report.json`: Quellen, Abdeckung, Stimmen und Textvorschläge.
- `promises.template.json`: Zitatkandidaten ohne erfundene Richtungsprüfung.

Der Ausgabeordner muss neu sein. Ohne `--output` erscheint der Bericht im Terminal;
`--format json` liefert JSON. Ohne `--online` wird kein Netzwerk verwendet.
Lokal werden immer alle vorhandenen Polls dieser Legislatur berücksichtigt,
nicht nur die zuletzt angeforderte Stichprobengröße.

### Alle verfügbaren Abstimmungen

```powershell
uv run parteihack compare "Bundestag 2021 bis 2025 Grüne" --online --all-polls --output data/exports/gruene-komplett
```

Bewusster Massenabruf: möglichst 22–6 Uhr, nicht mehrere Prozesse parallel.
Der Bericht kennzeichnet, ob Poll-Liste und Stimmen gegenüber der API vollständig
sind. Das ist kein Nachweis vollständiger amtlicher Abdeckung.

### Relevanzgesteuerter Import

```powershell
uv run parteihack compare "Bundestag 2021 bis 2025 Grüne" --online --relevant-polls 10 --output data/exports/gruene-relevant
```

1. Alle Poll-Metadaten der Legislatur werden geladen und lokal gespeichert.
2. Jeder Poll wird mit dem bereits extrahierten Programmtext lexikalisch
   gerankt (Titelstämme vor BM25-Score, danach Datum/ID).
3. Nur die Stimmen der ersten N noch nicht vollständigen Polls werden importiert.
4. Der Bericht beschränkt sich auf Polls mit lokalen Stimmen; die Abdeckung
   nennt zusätzlich alle lokalen Poll-Metadaten und die Zahl der Polls mit
   Stimmen. `report_scope` hält diese Begrenzung ausdrücklich fest.

Die Rangliste ist keine politische Richtung und keine Bewertung; sie dient nur
der Auswahl ressourcenintensiver Stimmenimporte. `--relevant-polls` erlaubt
1–50 und schließt `--all-polls` aus. Ein späterer lokaler Bericht lässt sich mit
`--only-with-votes` ebenfalls auf Polls mit importierten Stimmen begrenzen.

### API-Ergebnis

Das Poll-Feld `field_accepted` wird als `api_outcome` (`accepted`, `rejected`,
`unknown`) ausgewiesen, sofern es boolesch vorliegt. Es belegt nur die
Annahme/Ablehnung des dokumentierten Vorgangs, nicht seine Umsetzung und nicht
die Erfüllung eines Wahlversprechens.

Später offline: `uv run parteihack compare "Bundestag 2021 bis 2025 Grüne"`.

## Eingaben und Auswahl

Die deterministische Freitextsyntax erkennt derzeit **Bundestag**, genau zwei
Jahreszahlen und eine Partei. Auch die lange Form „Bundestag Wahlperiode von
2021 bis 2025 Abstimmverhalten der Grünen verglichen mit Wahlprogramm“ funktioniert.
Es ist kein allgemeines Sprachmodell.

Parteibezeichnungen: Grüne/Bündnis 90/Die Grünen, SPD, FDP, AfD, Linke, CDU, CSU.
Die Datenverfügbarkeit ist damit nicht garantiert. CDU und CSU werden einzeln
angefragt; das gemeinsame Fraktionsverhalten ist entsprechend gekennzeichnet.

Perioden werden anhand von Parlament, Typ und tatsächlichem Start-/Endjahr
aufgelöst, nicht über fest eingebaute IDs. Fehlende oder mehrdeutige Auswahlen
führen zum Fehler. Bei mehreren Programmen `--program-id ID` verwenden.
Mit `--program-file ORIGINAL.pdf` ist eine lokale PDF möglich; deren Identität
mit der API-Datei wird nicht behauptet.

## Automatische Gegenüberstellung

1. Original-PDF mit SHA-256 archivieren und Text pro **PDF-Seite** extrahieren.
2. Sätze indexieren; „Wir wollen“ usw. nur als **Versprechenskandidaten** markieren.
3. Poll-Titel, API-Beschreibung, Themen/Ausschüsse und vorhandene amtliche
   Textbelege mit Textstellen abgleichen.
4. Fraktionsstimmen aus Vote-Daten gegenüberstellen und Abdeckung ausweisen.
5. Datenintegrität und veröffentlichte amtliche Summen getrennt prüfen.

Die Suche verwendet BM25-Ranking, deutsches Snowball-Stemming, deutsche
Stoppwörter und eine kleine, im Code offengelegte Liste von Suchkonzepten
(z. B. Windkraft/Solar → erneuerbare Energien). Treffer werden nach Titel,
API-Beschreibung, amtlichem Kontext und Themen/Ausschüssen gewichtet.
Mindestens zwei belastbare gemeinsame Wortstämme aus Titel/Beschreibung/Beleg
sind erforderlich; Suchkonzepte oder Themen allein erzeugen keinen Treffer.
Identische Sätze auf mehreren PDF-Seiten werden einmal indexiert.
`lexical_score` ist ein Rangwert, keine Wahrscheinlichkeit oder Programmtreue.

Bedingungen, Verneinungen, Jahre und Mengen werden als **Prüfhinweise** erfasst.
Der vorherige und nächste Satz derselben PDF-Seite wird mitgeliefert, damit eine
Aussage nicht aus dem Zusammenhang gerissen wirkt. Es gibt weiterhin keine
automatische logische Interpretation. Relevante Passagen können fehlen,
irrelevante vorkommen. Texttreffer ergeben niemals automatisch „Versprechen
gebrochen“ oder „erfüllt“. Separate Interviews/Reden als Versprechensquellen
sind noch nicht unterstützt. OCR ebenfalls nicht.

## Amtliche Belege und Datenqualität

### Programmkandidaten gezielt untersuchen

Die Vergleichsansicht enthält „Programm genauer untersuchen“. Textsuche
durchsucht Zitat und Nachbarsätze. Filter zeigen Kandidaten mit Mengenangaben,
Jahreszahlen, Bedingungen im Zitat oder Satzkontext sowie Kandidaten ohne
lokalen Top-Treffer. Die Liste beginnt mit 20 Einträgen und lässt sich
schrittweise erweitern. Jede Passage behält PDF-Seite und Satzkontext.

`report.json` enthält die Übersicht unter `program_analysis` und alle Einträge
unter `promise_candidates`. Der Markdown-Bericht enthält die Übersicht.
Jahreszahlen und Mengenangaben sind ungeprüfte Merkmale. Eine Jahreszahl
kann ein historischer Bezug sein. Die Merkmalsgruppen überschneiden sich.

Die Kandidaten entstehen aus der bestehenden Satzheuristik mit 50 bis 1600
Zeichen und sprachlichen Zusagemarkern. Seitenübergreifende Sätze, abweichende
Formulierungen, kurze Zusagen oder OCR-Lücken können fehlen. Die Zahl der
Kandidaten beschreibt deshalb den erkannten Bestand. Top-Treffer beziehen sich
auf den Berichtsumfang und dessen Trefferlimit pro Poll.

Zusätzliche Programmchecks und Quellen sind in `PROGRAM_SOURCES.md` dokumentiert.

### Amtliche Ergänzungen

```powershell
uv run parteihack enrich-period 132 --poll 5957 --max-polls 1 --max-documents 3 `
  --source "https://www.bundestag.de/parlament/plenum/abstimmung/abstimmung?id=951"
```

Der Befehl ergänzt lokal fehlende Themen-/Ausschussdaten und lädt ausdrücklich
ausgewählte oder in der API verlinkte amtliche Bundestagsbelege. Standard sind
höchstens drei Dokumente pro Lauf; die CLI erlaubt bewusst bis 20, die Website
bleibt auf drei begrenzt. Erlaubt sind nur
konkrete Abstimmungs-/Textarchivseiten und Drucksachen/Plenarprotokolle unter
`bundestag.de`/`dserver.bundestag.de`; keine freie URL-Abrufschnittstelle.
Originale werden unter `data/evidence/` mit SHA-256 archiviert.

Der Bericht trennt:

- API-Abdeckung und geprüfte ID-Mengen,
- blockierende Datenprobleme (z. B. Doppelstimme, Mandats-/Legislaturbruch),
- prüfbare und nicht prüfbare historische Fraktionsverläufe,
- veröffentlichte amtliche Summen (Gesamt und ausgewählte Fraktion),
- Kontextbelege ohne automatisch geprüfte Identität der Abstimmungsfassung,
- ungeprüfte Programmstellen und ausdrücklich `overall_score: null`.

Ein Summenabgleich ist kein Beweis für Erfüllung oder Verletzung eines
Versprechens. Eine Änderung des archivierten Originals wird gemeldet, nicht still
ersetzt.

## Explizit geprüfte Versprechen

In der Template-Datei können nach tatsächlicher Prüfung `links` ergänzt werden:

```json
{
  "poll_id": 9041,
  "aligned_vote": "yes",
  "rationale": "Synthetisches Beispiel: Die Vorlage wirkt in Richtung des zitierten Ziels.",
  "source_url": "https://example.org/synthetische-vorlage",
  "reviewed_by": "Name der tatsächlich prüfenden Person",
  "reviewed_at": "2026-11-14",
  "procedure_id": "20/15096",
  "relationship": "direct",
  "conditions_checked": true,
  "package_reviewed": true,
  "second_reviewer": "Name der zweiten Prüfung",
  "counter_sources": ["https://example.org/synthetische-gegenquelle"]
}
```

`procedure_id` gruppiert mehrere Abstimmungen zu **einem** Prüfvorhaben.
`relationship` muss `direct` oder `partial` sein, damit eine Richtungsmehrheit
als Programmbezug erscheint; `mixed` und `unclear` bleiben getrennt.
`conditions_checked`, `package_reviewed` und `second_reviewer` sind zusätzliche
Nachweise der Nutzerprüfung, keine automatische Verifikation.

**Keine reale Bewertung.** Die ID muss zu einem importierten Poll dieser Legislatur
gehören. `aligned_vote` bedeutet: Ja oder Nein wirkt für genau diese Frage laut
Prüfer in Richtung des Zitats. Das ist nicht allein aus dem Titel ableitbar.

```powershell
uv run parteihack compare "Bundestag 2021 bis 2025 Grüne" --promises meine-pruefung.json --output data/exports/gruene-geprueft
```

Programm-ID, Dokument-Prüfsumme und Zitat auf der PDF-Seite werden validiert.
Begründung und Prüferidentität können **nicht unabhängig verifiziert** werden.

Ergebnisse je geprüfter Zuordnung:

- `majority_aligned` / `majority_opposed`: Mehrheit der **Ja-/Nein-Stimmen**
  in beziehungsweise entgegen der zugeordneten Richtung.
- `split`: gleich viele Ja und Nein.
- `not_assessable`: keine Ja-/Nein-Stimmen.
- `insufficient_data`: fehlende oder unbekannte Stimmen.

Enthaltungen und Nichtteilnahme bleiben separat; der Anteil bezieht sich auf
Ja plus Nein. Keine Aussage zur tatsächlichen Umsetzung:
`fulfillment: not_assessed`. Kein Gesamt-Parteien-Score.
Mehrere Polls mit gleicher `procedure_id` zählen als ein Prüfvorhaben. Die
Zusammenfassung zählt jedes Versprechen höchstens einmal; `partial` und `mixed`
werden nicht als Zustimmung ausgegeben.

### Ergänzte Bezugsgrößen und Gruppierung ab Methodenstand v3

`direction_comparison` ergänzt `decisive_votes`, `recorded_votes`,
`participating_votes`, `aligned_share_of_recorded_votes` und
`participation_share_of_recorded_votes`. Der bestehende Anteil an Ja/Nein
bleibt enthalten. Unbekannte Werte und Nichtteilnahme sind im Nenner aller
dokumentierten Einträge enthalten. Leere Nenner ergeben `null`.

Markdown und Website zeigen Ja/Nein-Anteil, Teilnahme und den Anteil der
Ja-/Nein-Mehrheitsrichtung an allen dokumentierten Fraktionseinträgen.
Diese Kennzahlen beschreiben den lokalen Datenstand. Der vollständige
Stimmenimport und mögliche Integritätsprobleme werden separat ausgewiesen.

`reviewed_summary.cases` enthält pro Versprechen/Vorgang die Häufigkeiten
aller zusammengeführten Ergebniskategorien in `result_counts`. Nicht auswertbare
Zuordnungen bleiben bei der Zusammenfassung sichtbar. `reviewed_promises`
zählt aus Kompatibilitätsgründen weiterhin alle übergebenen Versprechen.
`promises_with_reviewed_links` und `promises_without_reviewed_links` trennen
den tatsächlichen Zuordnungsstand. `poll_comparisons` und `procedure_cases`
zeigen die Zahl der Links und der versprechenbezogenen Prüfvorhaben.

## Dateien und Provenienz

`data/programs/PROGRAMM_ID/` enthält PDF und Metadaten mit SHA-256 als Dateiname.
Die API-Lizenz wird nicht auf die PDF übertragen; keine automatische Veröffentlichung.
Vor Vergleichen werden Prüfsumme und PDF erneut gelesen, nicht nur der Textcache.
Mehrere lokale Versionen erfordern die Auswahl mit `--program-file`.

Dateikarte relativ zu `src/partei_hack/`:

| Datei | Zuständigkeit |
| --- | --- |
| `services/requests.py` | Anfrage, Perioden-, Programm- und Fraktionsauswahl |
| `services/programs.py` | PDF, SHA-256, Metadaten und Seitentext |
| `services/language.py` | Deutsche Stämme, Suchkonzepte und Prüfmerkmale |
| `services/matching.py` | BM25-Treffer, Originalkontext und ungeprüfte Zitate |
| `services/promises.py` | Zitat-/Linkvalidierung und Stimmrichtungsvergleich |
| `services/quality.py` | Datenintegrität, Vorgangsflags und getrennte Zählung |
| `services/evidence.py` | begrenzte amtliche Belege, SHA-256 und Summenabgleich |
| `services/selection.py` | lexikalische Poll-Relevanz für gezielte Stimmenimporte |
| `services/comparison.py` | Abdeckung, Qualität und Vergleich zusammenführen |
| `services/reports.py` | Markdown, JSON und Vorlage |
| `api/official.py` | enge Allowlist für amtliche Bundestagsquellen |
