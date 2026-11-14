# Methodik für den späteren Wahlversprechen-Abgleich

## Analyseebenen trennen

1. **Quelle:** Originalprogramm mit Version, Datum, URL und Fundstelle.
2. **Versprechen:** Wörtliches Zitat, Partei, Wahl, Ziel, Bedingungen und Zeitraum.
3. **Vorgang:** Antrag/Gesetz/Änderungsantrag und konkrete Abstimmungsfrage.
4. **Verhalten:** Einzelstimme und gegebenenfalls Fraktion am Abstimmungstag.
5. **Interpretation:** Begründete Beziehung zwischen Versprechen und Verhalten.

## Keine voreiligen Schlussfolgerungen

- Eine Ja-Stimme kann einen Kompromiss betreffen; Nein kann sich gegen
  Ausgestaltung oder Paketbestandteile richten.
- Abstimmungsverhalten ist nicht identisch mit tatsächlicher Umsetzung.
- Oppositionsparteien haben andere Handlungsmöglichkeiten als Regierungsparteien.
- Fehlende namentliche Abstimmung bedeutet nicht, dass nichts getan wurde.
- Nichtteilnahme und Enthaltung bleiben eigene Kategorien.
- Fraktion, Wahlpartei und heutige persönliche Partei sind nicht austauschbar.
- CDU und CSU haben eine gemeinsame Fraktion, aber nicht notwendig identische Programme.
- Eine Stichprobe erlaubt keinen allgemeingültigen Parteienvergleich.

## Vorhandener Prüfdatensatz ab 0.2.0

Programm-ID und SHA-256 fixieren das Dokument. Pro Versprechen werden ID, Titel,
PDF-Seite und nachgewiesenes Originalzitat gespeichert. Geprüfte Links enthalten
Poll-ID, programmkompatible Stimmrichtung, Begründung, Quellen-URL, Prüfer und Datum.
Der Bericht ergänzt Wahl-/Partei-/Fraktionsreferenzen, Methodikversion und Abdeckung.

Automatische Worttreffer bleiben `unreviewed` und `not_assessable`.
Explizit nutzergeprüfte Zuordnungen können `majority_aligned`,
`majority_opposed`, `split`, `not_assessable` oder `insufficient_data` ergeben.
Das betrifft nur die Mehrheit der Ja-/Nein-Stimmen, nicht die tatsächliche Erfüllung.
Prüferbehauptungen sind nicht unabhängig verifiziert.
Keine numerischen Parteien-Scores; Verfahren und Pflichtfelder in `COMPARISON.md`.

## Erweiterter Prüfdatensatz ab 0.3.0

- **Retrieval:** BM25 mit deutschen Wortstämmen und einer kleinen offengelegten
  Konzeptliste. Trefferquote ist kein Beleg für inhaltliche Übereinstimmung;
  Suchkonzepte allein erzeugen keinen Treffer.
- **Kontext:** Jeder Vorschlag enthält den vorherigen und nächsten Satz derselben
  PDF-Seite. Bedingungen, Verneinungen, Jahre und Mengen werden als Prüfhinweise
  markiert, nicht automatisch ausgewertet.
- **Datenintegrität:** Poll-Datum, Legislatur- und Mandatsgrenzen, doppelte
  Mandatsstimmen, unbekannte Stimmwerte und historische Fraktionsmitgliedschaften
  werden getrennt geprüft. Ein blockierender Befund verhindert die Nutzung als
  Richtungsbeleg.
- **Identität:** Poll- und Vote-ID-Mengen werden protokolliert und erneut
  verglichen. Gleiche Anzahl allein belegt keine vollständige Übernahme.
- **Amtliche Summen:** Veröffentlichte Gesamt- und Fraktionssummen können gegen
  die lokale API-Ableitung geprüft werden. Das prüft Aggregate, nicht Einzelstimmen,
  nicht die endgültige Gesetzesfassung und nicht die politische Wirkungsrichtung.
- **Zählung:** Mehrere Polls mit derselben `procedure_id` sind ein Prüfvorhaben.
  Jedes Versprechen wird höchstens einmal gezählt. `partial` und `mixed` gelten
  nicht als Zustimmung. Ungeprüfte Kandidaten sind kein Score-Nenner.
- **Qualitätsdimensionen statt Gesamtscore:** Abdeckung, Datenprobleme, Quellenlage,
  Summenabgleich und Prüfbedarf bleiben getrennt. `overall_score` bleibt `null`.

## Ergänzung ab 0.3.1

- **Relevanzauswahl:** Wenn nicht alle Stimmen importiert werden, werden zuerst
  alle Poll-Metadaten geladen und dann nur die N Polls mit den stärksten
  lexikalischen Programmtreffern (Titelstämme, BM25, Datum, ID). Das ist eine
  Ressourcenauswahl, kein politisches Urteil und keine Stichprobe im
  statistischen Sinn.
- **Abdeckung:** Der Bericht unterscheidet lokale Poll-Metadaten, Polls mit
  lokalen Stimmen, vollständige Stimmenimporte und den tatsächlich detaillierten
  Umfang. Eine hohe Metadatenzahl ersetzt keine vollständigen Stimmen.
- **Vorgangsergebnis:** `field_accepted` wird als angenommen/abgelehnt/unbekannt
  ausgewiesen. Es belegt nur den dokumentierten Verfahrensausgang, nicht die
  Umsetzung oder die Erfüllung eines Wahlversprechens.
- **Fraktionshistorie:** Eine historische Mitgliedschaft gilt nur dann als
  geprüft, wenn ein Eintrag das Abstimmungsdatum tatsächlich abdeckt. Fehlt eine
  solche Abdeckung, ist das Ergebnis „nicht prüfbar“ und kein Widerspruch; die
  API liefert bei Fraktionswechslern teilweise nur den neuesten Eintrag.

## Auswertung mit Methodenstand v3

Die Richtungsmehrheit wird weiterhin aus Ja/Nein ermittelt. Zusätzlich enthält
der Bericht die absoluten Nenner und den Richtungsanteil an allen dokumentierten
Fraktionseinträgen. Teilnahme umfasst Ja, Nein und Enthaltung. Der Nenner für
diese Anteile umfasst auch `no_show` und unbekannte Werte. Bei null Einträgen
bleiben die Anteile `null`. Alle Anteile beschreiben die beobachteten Daten.
Die Datenfreigabe und der Ergebnisstatus werden zusätzlich ausgewiesen.

Synthetisches Rechenbeispiel mit 2 Ja, 3 Enthaltungen und 5 Nichtteilnahmen
ergibt 100 % Ja unter Ja/Nein, 20 % Ja unter allen zehn Einträgen und 50 %
Teilnahme. Die Mehrheit allein beschreibt die Breite der Unterstützung nur
eingeschränkt. Historische Fraktionssitzanzahlen werden dafür nicht geschätzt.

Bei zusammengefassten Zuordnungen werden sämtliche Einzelergebniskategorien
pro versprechenbezogenem Vorgang als `result_counts` erhalten. Ein nicht
auswertbarer Teil führt auch bei weiteren auswertbaren Zuordnungen zu
`not_assessable`. Unvollständige Daten ergeben `insufficient_data`.
Explizit gegenläufige Richtungen bleiben als `mixed` sichtbar.
Die vorhandene Rangfolge für Teilbezüge und Gleichstände gilt weiterhin.
Mehrere Vorgänge eines Versprechens werden nach derselben Regel zusammengefasst.
Der Bericht zählt Versprechen mit und ohne geprüfte Links separat.

## Nächste Evaluierungsschritte

Die eigene Programmanalyse ist jetzt als Inventar zugänglich. Sie zählt die
erkannten Kandidaten mit Mengenangaben, Jahreszahlen, Bedingungen und
Verneinungen. Bedingungen der Nachbarsätze werden gesondert berücksichtigt.
Die Website erlaubt die Prüfung auch der Kandidaten ohne lokalen Top-Treffer.
Die Satzheuristik umfasst nur 50–1600 Zeichen lange Passagen mit mindestens
zwei nicht ausgeschlossenen Suchwörtern. Zusagemarker bestimmen den Kandidaten-
Status. Die Merkmale werden wörtlich erkannt. Eine Jahreszahl wird dabei
noch keiner Zielvorgabe oder Frist zugeordnet.

Die folgenden Verfahren sind ein Arbeitsplan. Ein gemessener Retrieval-Benchmark
oder eine unabhängige inhaltliche Validierung liegt noch nicht vor.

1. Einen fest versionierten Prüfsatz mit Originalzitaten, Poll-IDs und
   Dokumentprüfsummen aufbauen. Mehrere Themen, Zeiträume, Vorlagenarten und
   Beispiele ohne passenden Programmbezug einbeziehen. Die Auswahl vor dem
   Vergleich von Suchvarianten dokumentieren.
2. Relevanz und politische Richtung getrennt prüfen. Zwei Personen markieren
   die Relevanz zunächst unabhängig und halten Übereinstimmungen, Konflikte
   und deren begründete Auflösung fest. Eine zweite Prüferangabe allein misst
   noch keine Übereinstimmung.
3. Für die Top-k-Suche die manuell relevanten Treffer durch k teilen
   (Precision@k). Recall erst mit einem unabhängig vollständig geprüften
   relevanten Bestand innerhalb des festgelegten Prüfsatzes berechnen.
   Die Beurteilungen müssen auch Textstellen außerhalb der gelieferten
   Top-Treffer umfassen.
4. Parameter und Suchkonzepte auf einem Entwicklungsbestand ändern und auf
   einem getrennten, festgelegten Prüfbestand auswerten. Ergebnisse je Thema
   und Vorlagenart sowie konkrete Fehlertypen festhalten.
5. Für spätere Umsetzungsprüfungen pro Zusage überprüfbare Kriterien,
   Bedingungen, Zeitraum und amtliche Umsetzungsbelege festlegen. Die
   Vorgehensweise orientiert sich an der Anforderung überprüfbarer Zusagen
   des Comparative Pledges Project.
   [Methodischer Bezug](https://comparativepledges.net/)

Weitere Datenquellen und ihre Zugangsvoraussetzungen stehen in
`API_RESEARCH.md`, Abschnitt „Fortgesetzte Quellenrecherche“.

## Rolle von KI

KI kann Kandidaten für passende Textstellen oder Vorgänge vorschlagen. Sie darf
keine Zitate erfinden und sollte nicht ohne menschliche Prüfung öffentliche
Behauptungen über einen angeblichen Wahlversprechenbruch erzeugen.
Originalbelege und überprüfbare Zwischenschritte bleiben erforderlich.
