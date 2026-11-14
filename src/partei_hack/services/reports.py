"""Lesbarer Markdown-Bericht und maschinenlesbare Belege ohne Dateiüberschreibung."""

import json
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from partei_hack.services.promises import promise_template


def md(value: Any) -> str:
    text = str(value or "").replace("\n", " ").replace("\r", " ")
    for char in ("\\", "`", "*", "_", "[", "]", "<", ">", "|", "#"):
        text = text.replace(char, "\\" + char)
    return text


def link(value: Any) -> str:
    try:
        valid = isinstance(value, str) and urlsplit(value).scheme in {"http", "https"}
    except ValueError:
        valid = False
    if valid:
        safe = value.replace("\n", "").replace("\r", "").replace("<", "%3C").replace(">", "%3E")
        return f"<{safe}>"
    return "Kein externer HTTP-Quellenlink vorhanden"


def percentage(value: float | None) -> str:
    return f"{value * 100:.1f} %".replace(".", ",") if value is not None else "nicht berechenbar"


RESULT_LABELS = {
    "majority_aligned": "Mehrheit der Ja-/Nein-Stimmen in zugeordneter Richtung",
    "majority_opposed": "Mehrheit der Ja-/Nein-Stimmen entgegen zugeordneter Richtung",
    "split": "Ja-/Nein-Stimmen gleich verteilt",
    "not_assessable": "Keine auswertbaren Ja-/Nein-Stimmen",
    "insufficient_data": "Keine Bewertung: unvollständige oder unbekannte Stimmen",
}


def render_markdown(report: dict[str, Any]) -> str:
    coverage = report["coverage"]
    program = report["program"]
    totals = report["vote_totals"]
    available = coverage["available_api_polls"]
    available_label = str(available) if available is not None else "unbekannt"
    coverage_label = "ja" if coverage["complete_against_api"] else "nein"
    quality = report.get("quality_summary", {})
    lines = [
        f"# {md(report['period']['label'])} – {md(report['fraction']['label'])}",
        "",
        "## Wahlprogramm und Abstimmungsverhalten",
        "",
        "**Recherchebericht, kein Wahlversprechen-Erfüllungsscore.**",
        "",
        f"Erstellt: {report['generated_at']} · Methode: {report['method_version']}",
        "",
        f"- Abdeckung: **{coverage['local_polls']} von {available_label} Poll-Metadaten**.",
        f"- Polls mit lokalen Stimmen: **{coverage.get('polls_with_local_votes', 0)}**; "
        f"vollständige Stimmenimporte: **{coverage['polls_with_complete_votes']}**.",
        f"- Im Bericht detailliert: "
        f"**{coverage.get('reported_polls', coverage['local_polls'])}** Polls.",
        f"- Gesamte API-Abdeckung belegt: **{coverage_label}**.",
        f"- Programm: {md(program['label'])} ({program['pdf_pages']} PDF-Seiten).",
        f"- Originalquelle: {link(program['source_url'])}",
        f"- SHA-256: `{program['sha256']}`",
        f"- Passende Textstellen gefunden zu **{report['polls_with_text_matches']}** Polls.",
        "",
        "### Hinweise",
        "",
        *[f"- {md(warning)}" for warning in report["warnings"]],
        "",
        "### Stimmereignisse in den vorhandenen Abstimmungen",
        "",
        "| Ja | Nein | Enthaltung | Nicht beteiligt | Unbekannt |",
        "| ---: | ---: | ---: | ---: | ---: |",
        f"| {totals['yes']} | {totals['no']} | {totals['abstain']} | "
        f"{totals['no_show']} | {totals['unknown']} |",
        "",
        "Diese Summe zählt dieselben Personen bei mehreren Abstimmungen mehrfach. "
        "Sie ist kein Maß für Programmtreue.",
        "",
        "## Qualität und Prüfbedarf",
        "",
        f"- Polls mit blockierenden Datenproblemen: "
        f"**{quality.get('polls_with_blocking_data_issues', 0)}**; "
        f"Fraktionshistorie nicht vollständig prüfbar: "
        f"**{quality.get('polls_with_uncheckable_membership_history', 0)}**.",
        f"- Polls mit archivierten amtlichen Belegen: "
        f"**{quality.get('polls_with_official_sources', 0)}**.",
        f"- Amtliche Summen bestätigt / widersprüchlich: "
        f"**{quality.get('polls_with_matching_official_aggregates', 0)} / "
        f"{quality.get('polls_with_official_conflicts', 0)}**.",
        f"- API-Ergebnis angenommen / abgelehnt / unbekannt: "
        f"**{quality.get('polls_accepted_by_api', 0)} / "
        f"{quality.get('polls_rejected_by_api', 0)} / "
        f"{quality.get('polls_outcome_unknown', 0)}**.",
        f"- Ungeprüfte Versprechenskandidaten im Programm: "
        f"**{quality.get('promise_candidates', 0)}**; davon ohne Treffer in den lokalen "
        f"Top-Zuordnungen: **{quality.get('candidates_without_retrieved_poll', 0)}**.",
        "",
        "Kein Treffer ist kein Beleg für Untätigkeit. Kandidaten sind kein gültiger "
        "Nenner für einen Programmtreuescore. Amtliche Summen bestätigen weder einzelne "
        "Stimmen noch die politische Deutung oder die endgültige Gesetzesfassung.",
        "",
    ]
    analysis = report.get("program_analysis")
    if analysis:
        features = analysis["candidate_feature_counts"]
        lines.extend(
            [
                "## Programm genauer untersuchen",
                "",
                f"{analysis['candidate_count']} ungeprüfte Kandidaten in "
                f"{analysis['indexed_passages']} indexierten Passagen. "
                f"{analysis['pages_with_text']} von {analysis['pdf_pages']} PDF-Seiten mit Text.",
                "",
                f"Kandidaten mit Mengenangaben {features['quantities']}, "
                f"Jahreszahlen {features['years']}, Bedingungen {features['conditions']} "
                f"und Verneinungen {features['negations']}. "
                f"Bei {analysis['candidates_with_context_conditions']} Kandidaten "
                "enthalten Nachbarsätze Bedingungen. Die Kategorien können sich überschneiden.",
                "",
                "Diese Merkmale sind lexikalische Prüfhinweise. Jahreszahlen können auch "
                "historische Bezüge sein. Die Satzheuristik kann Zusagen übersehen oder "
                "Kontextpassagen einschließen. Alle Kandidaten mit Satzkontext stehen im JSON "
                "und in der durchsuchbaren Programmansicht der Website.",
                "",
            ]
        )
    lines.append("## Abstimmungen und automatische Textvorschläge")
    for poll in report["polls"]:
        votes = poll["votes"]
        lines.extend(
            [
                "",
                f"### {md(poll['date'])}: {md(poll['title'])} (ID {poll['id']})",
                "",
                f"Quelle: {link(poll['source_url'])}",
                "",
                f"Fraktion: **{votes['yes']} Ja · {votes['no']} Nein · "
                f"{votes['abstain']} Enthaltung · {votes['no_show']} nicht beteiligt"
                f" · {votes['unknown']} unbekannt**.",
                "",
                "Stimmenimport gegenüber API vollständig: "
                f"**{'ja' if poll['all_votes_complete_against_api'] else 'nein'}**.",
                "",
            ]
        )
        diagnostics = poll.get("vote_diagnostics", {})
        issues = diagnostics.get("issues", [])
        procedure = poll.get("procedure_context", {})
        outcome = poll.get("quality", {}).get("api_outcome", "unknown")
        lines.extend(
            [
                f"API-Ergebnis: **{md(outcome)}** "
                f"(Quelle: `{md(procedure.get('outcome_source', 'not_available'))}`; "
                "das ist keine Umsetzungs- oder Erfüllungsaussage).",
                f"Datenprobleme: **{len(issues)}**. Fraktionshistorie prüfbar bei "
                f"{diagnostics.get('membership_history_checked', 0)} Stimmereignissen; "
                f"nicht prüfbar bei {diagnostics.get('membership_history_uncheckable', 0)}.",
                "",
            ]
        )
        if "decisive_share_of_recorded_members" in diagnostics:
            lines.extend(
                [
                    "Anteil Ja/Nein an dokumentierten Fraktionsstimmen "
                    f"**{percentage(diagnostics['decisive_share_of_recorded_members'])}**. "
                    "Teilnahme einschließlich Enthaltungen "
                    f"**{percentage(diagnostics['participation_share_of_recorded_members'])}**. "
                    "Nenner sind alle lokalen Fraktionseinträge einschließlich "
                    "Nichtteilnahme und unbekannter Werte.",
                    "Anteil der Ja-/Nein-Mehrheitsrichtung an allen dokumentierten Einträgen "
                    f"**{percentage(diagnostics['majority_share_of_recorded_members'])}**. "
                    "Die Anteile beschreiben den lokalen Datenstand.",
                    "",
                ]
            )
        for issue in issues[:5]:
            lines.append(f"- Datenhinweis: `{md(issue['code'])}`.")
        for flag in procedure.get("flags", []):
            lines.append(f"- Vorgangsprüfung nötig: `{md(flag)}`.")
        dissidents = diagnostics.get("dissenting_votes", [])
        if dissidents:
            lines.extend(
                [
                    "",
                    "Abweichende Ja-/Nein-Stimmen gegenüber der Fraktionsmehrheit: "
                    + "; ".join(
                        f"{md(item.get('politician') or item['mandate_id'])}: {md(item['vote'])}"
                        for item in dissidents
                    ),
                    "",
                ]
            )
        for source in poll.get("official_sources", []):
            lines.extend(
                [
                    f"Amtlicher Beleg: **{md(source['title'])}** – {link(source['url'])}. "
                    f"SHA-256: `{source['sha256']}`.",
                    "Kontextquelle; Identität des Abstimmungsgegenstands nicht "
                    "automatisch geprüft.",
                    "",
                ]
            )
        audit = poll.get("official_crosscheck", {})
        if audit.get("status") != "not_checked":
            lines.extend(
                [
                    f"Amtlicher Summenabgleich: **{md(audit.get('status'))}** "
                    "(nur veröffentlichte Summen, keine Einzelstimmenprüfung).",
                    "",
                ]
            )
        if not poll["program_matches"]:
            lines.append(
                "Kein ausreichend ähnlicher Text gefunden. Das belegt weder "
                "fehlendes Versprechen noch einen Widerspruch."
            )
        for passage in poll["program_matches"]:
            kind = (
                "möglicher Versprechenskandidat"
                if passage["kind"] == "promise_candidate"
                else "Programmpassage"
            )
            lines.extend(
                [
                    f"**PDF-Seite {passage['page']} – {kind}, ungeprüft**",
                    "",
                    f"> {md(passage['quote'])}",
                    "",
                    f"Gemeinsame Suchwörter: {md(', '.join(passage['matched_terms']))}. "
                    f"Lexikalischer Rangwert: {passage['lexical_score']} "
                    "(keine Wahrscheinlichkeit).",
                    "",
                    f"Suchverfahren: {md(passage.get('retrieval_method', 'lexical'))}. "
                    "Suchkonzepte: "
                    f"{md(', '.join(passage.get('matched_concepts', []))) or 'keine'}.",
                    "",
                    "**Richtung/Erfüllung: nicht bewertet.** Vorlage, Bedingungen und "
                    "Wirkungsrichtung müssen geprüft werden.",
                    "",
                ]
            )
            if passage.get("context_before") or passage.get("context_after"):
                lines.extend(
                    [
                        "Kontext derselben PDF-Seite (gegebenenfalls gekürzt):",
                        "",
                        f"> {md(passage.get('context_before', ''))}",
                        ">",
                        f"> {md(passage.get('context_after', ''))}",
                        "",
                    ]
                )
            for flag in passage.get("review_flags", []):
                lines.append(f"- Zitatprüfung nötig: `{md(flag)}`.")
    lines.extend(["", "## Explizit geprüfte Zuordnungen", ""])
    if not report["reviewed_promises"]:
        lines.append(
            "Keine geprüften Zuordnungen übergeben. Die exportierte "
            "`promises.template.json` enthält nur ungeprüfte Zitatkandidaten ohne Richtungsangaben."
        )
    for promise in report["reviewed_promises"]:
        lines.extend(
            [
                f"### {md(promise['title'])}",
                "",
                f"PDF-Seite {promise['page']}:",
                "",
                f"> {md(promise['quote'])}",
                "",
            ]
        )
        if not promise["comparisons"]:
            lines.append("Noch keine Richtungszuordnung geprüft.")
        for comparison in promise["comparisons"]:
            direction = comparison["direction_comparison"]
            lines.extend(
                [
                    f"- Poll {comparison['poll_id']}, programmkompatible Richtung laut "
                    f"Prüfer: `{comparison['aligned_vote']}`.",
                    f"- Begründung: {md(comparison['rationale'])}",
                    f"- Beleg: {link(comparison['source_url'])}",
                    f"- Nutzerprüfung: {md(comparison['reviewed_by'])} am "
                    f"{comparison['reviewed_at']}; nicht unabhängig verifiziert.",
                    f"- **{RESULT_LABELS[direction['result']]}**: "
                    f"{direction['aligned']} in Richtung, {direction['opposed']} dagegen; "
                    f"{direction['abstain']} Enthaltungen, {direction['no_show']} nicht beteiligt.",
                    "- Tatsächliche Umsetzung/Erfüllung: **nicht beurteilt**.",
                    "- Noch offene Prüfungen: "
                    f"{md(', '.join(comparison.get('remaining_checks', [])))}.",
                    "",
                ]
            )
            if "recorded_votes" in direction:
                lines.extend(
                    [
                        f"- Anteil in zugeordneter Richtung an Ja/Nein "
                        f"**{percentage(direction['aligned_share_of_yes_no'])}** "
                        f"(Nenner {direction['decisive_votes']}). "
                        "An allen dokumentierten Fraktionseinträgen "
                        f"**{percentage(direction['aligned_share_of_recorded_votes'])}** "
                        f"(Nenner {direction['recorded_votes']}). "
                        "Beide Anteile beschreiben die beobachteten Einträge.",
                        "",
                    ]
                )
    if report.get("reviewed_summary"):
        reviewed = report["reviewed_summary"]
        lines.extend(
            [
                "",
                "### Zusammenfassung ausschließlich der geprüften Auswahl",
                "",
                f"{reviewed['reviewed_promises']} Versprechen; jedes höchstens einmal gezählt.",
                "",
                f"Davon mit geprüften Zuordnungen "
                f"{reviewed.get('promises_with_reviewed_links', 0)}, "
                f"ohne Zuordnungen {reviewed.get('promises_without_reviewed_links', 0)}. "
                f"{reviewed.get('poll_comparisons', 0)} Abstimmungszuordnungen in "
                f"{reviewed.get('procedure_cases', 0)} versprechenbezogenen Prüfvorhaben.",
                "Mehrere Polls mit expliziter gleicher `procedure_id` sind ein Prüfvorhaben. "
                "Ohne diese ID ist die Vorgangsgruppierung unvollständig.",
                f"Kategorien: {md(json.dumps(reviewed['categories'], ensure_ascii=False))}.",
                "Kein Gesamt- oder Erfüllungsscore.",
            ]
        )
        for case in reviewed.get("cases", []):
            lines.append(
                f"- {md(case['promise_id'])} / {md(case['procedure_key'])} – "
                f"{md(case['result'])}, {case['poll_comparisons']} Zuordnungen. "
                "Einzelergebnisse "
                f"{md(json.dumps(case.get('result_counts', {}), ensure_ascii=False))}."
            )
    return "\n".join(lines) + "\n"


def write_report(directory: Path, report: dict[str, Any]) -> dict[str, str]:
    # Gesamter Bericht bekommt einen neuen Ordner; keine bestehenden Dateien berühren.
    directory.mkdir(parents=True, exist_ok=False)
    outputs = {
        "report.md": render_markdown(report),
        "report.json": json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        "promises.template.json": json.dumps(promise_template(report), ensure_ascii=False, indent=2)
        + "\n",
    }
    for name, text in outputs.items():
        with (directory / name).open("x", encoding="utf-8") as handle:
            handle.write(text)
    return {name: str((directory / name).resolve()) for name in outputs}
