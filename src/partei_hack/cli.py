"""CLI-Einstieg: explizite Online-Importe und rein lokale Auswertungen."""

import csv
import io
import json
import sqlite3
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Any

import typer

from partei_hack import __version__
from partei_hack.api.client import APIClient, APIError
from partei_hack.config import Settings
from partei_hack.services.comparison import build_comparison
from partei_hack.services.evidence import enrich_period
from partei_hack.services.importer import VOTE_VALUES, Importer
from partei_hack.services.programs import prepare_program
from partei_hack.services.queries import list_polls, list_votes, project_status, vote_summary
from partei_hack.services.reports import render_markdown, write_report
from partei_hack.services.requests import (
    discover_periods,
    parse_request,
    resolve_period,
    resolve_targets,
)
from partei_hack.services.selection import rank_polls_for_program, relevant_poll_ids
from partei_hack.storage.database import Database

app = typer.Typer(no_args_is_help=True, help="Lokale Recherche mit der abgeordnetenwatch-API.")


class OutputFormat(StrEnum):
    json = "json"
    csv = "csv"


@app.callback()
def main(
    ctx: typer.Context,
    data_dir: Annotated[Path | None, typer.Option(help="Lokales Datenverzeichnis.")] = None,
) -> None:
    ctx.obj = Settings.resolve(data_dir)


@contextmanager
def open_database(ctx: typer.Context) -> Iterator[Database]:
    settings: Settings = ctx.obj
    try:
        with Database(settings.database_path) as database:
            yield database
    except (APIError, OSError, sqlite3.Error, RuntimeError, ValueError) as exc:
        typer.echo(f"Fehler: {exc}", err=True)
        raise typer.Exit(1) from exc


def csv_cell(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False)
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@", "\t", "\r")):
        return "'" + value
    return value


def emit(
    payload: Any,
    output_format: OutputFormat = OutputFormat.json,
    output: Path | None = None,
) -> None:
    if output_format == OutputFormat.csv:
        if not isinstance(payload, list):
            raise typer.BadParameter("CSV erfordert eine Liste.")
        buffer = io.StringIO(newline="")
        if payload:
            fields = list(dict.fromkeys(key for row in payload for key in row))
            writer = csv.DictWriter(buffer, fieldnames=fields)
            writer.writeheader()
            writer.writerows(
                {key: csv_cell(value) for key, value in row.items()} for row in payload
            )
        text = buffer.getvalue()
    else:
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        # Kein stilles Überschreiben bereits vorhandener Dateien.
        with output.open("x", encoding="utf-8", newline="") as handle:
            handle.write(text)
        typer.echo(f"Export gespeichert: {output}", err=True)
    else:
        typer.echo(text, nl=False)


def validate_dates(since: str | None, until: str | None) -> None:
    try:
        for value in (since, until):
            if value and date.fromisoformat(value).isoformat() != value:
                raise ValueError
        if since and until and since > until:
            raise ValueError
    except ValueError as exc:
        raise typer.BadParameter("Datumsbereich im Format YYYY-MM-DD, von <= bis.") from exc


@app.command()
def doctor(ctx: typer.Context) -> None:
    """Konfiguration anzeigen; kein Netzwerk und keine Datenbankanlage."""
    settings: Settings = ctx.obj
    emit(
        {
            "version": __version__,
            "python": sys.version.split()[0],
            "sqlite": sqlite3.sqlite_version,
            "data_dir": str(settings.data_dir),
            "database": str(settings.database_path),
            "api_key_required": False,
        }
    )


@app.command("init-db")
def init_db(ctx: typer.Context) -> None:
    """Lokale Datenbank mit Schema 1 anlegen."""
    with open_database(ctx):
        emit({"database": str(ctx.obj.database_path), "schema_version": 1})


@app.command()
def periods(
    ctx: typer.Context,
    parliament: Annotated[int, typer.Option(min=1)] = 5,
    refresh: bool = False,
) -> None:
    """Online: Wahlen und Legislaturen eines Parlaments auflisten."""
    with open_database(ctx) as database:
        with APIClient(database, ctx.obj.raw_dir, refresh=refresh) as client:
            results = []
            for page in client.iter_pages("parliament-periods", {"parliament": parliament}):
                for item in page.items:
                    ref = item.get("parliament") or {}
                    if ref.get("id") != parliament:
                        raise APIError("API hat den Parlamentsfilter nicht eingehalten.")
                    database.save_entity(
                        "parliament-periods", item, page.source_url, page.fetched_at
                    )
                    results.append(item)
            emit(results)


@app.command("sync-period")
def sync_period(
    ctx: typer.Context,
    period_id: Annotated[int, typer.Argument(min=1)],
    max_polls: Annotated[int, typer.Option(min=1, help="Stichprobengröße.")] = 5,
    all_polls: Annotated[bool, typer.Option(help="Alle verfügbaren Abstimmungen abrufen.")] = False,
    with_votes: Annotated[bool, typer.Option(help="Einzelstimmen mitimportieren.")] = False,
    refresh: Annotated[bool, typer.Option(help="Antwortcache umgehen.")] = False,
) -> None:
    """Online: Legislatur importieren; standardmäßig höchstens fünf Polls."""
    if all_polls:
        typer.echo("Vollständiger API-Listenimport angefordert; bitte Fair Use beachten.", err=True)
    typer.echo("Import läuft; Netzrequests haben mindestens 2,1 Sekunden Abstand.", err=True)
    with open_database(ctx) as database:
        with APIClient(database, ctx.obj.raw_dir, refresh=refresh) as client:
            emit(
                Importer(client, database).sync_period(
                    period_id, max_polls=None if all_polls else max_polls, with_votes=with_votes
                )
            )


@app.command()
def polls(
    ctx: typer.Context,
    period: Annotated[int | None, typer.Option(min=1)] = None,
    search: str | None = None,
    since: str | None = None,
    until: str | None = None,
    topic: Annotated[int | None, typer.Option(min=1)] = None,
    output_format: Annotated[OutputFormat, typer.Option("--format")] = OutputFormat.json,
    output: Path | None = None,
) -> None:
    """Offline: lokale Abstimmungen nach Legislatur, Titel, Datum und Thema filtern."""
    validate_dates(since, until)
    with open_database(ctx) as database:
        emit(
            list_polls(
                database, period_id=period, search=search, since=since, until=until, topic_id=topic
            ),
            output_format,
            output,
        )


@app.command()
def votes(
    ctx: typer.Context,
    poll: Annotated[int, typer.Option(min=1)],
    vote: str | None = None,
    fraction: Annotated[int | None, typer.Option(min=1)] = None,
    output_format: Annotated[OutputFormat, typer.Option("--format")] = OutputFormat.json,
    output: Path | None = None,
) -> None:
    """Offline: lokale Einzelstimmen; Werte yes, no, abstain, no_show."""
    if vote is not None and vote not in VOTE_VALUES:
        raise typer.BadParameter("vote: yes, no, abstain oder no_show.")
    with open_database(ctx) as database:
        emit(
            list_votes(database, poll, vote=vote, fraction_id=fraction),
            output_format,
            output,
        )


@app.command()
def summary(ctx: typer.Context, poll: Annotated[int, typer.Option(min=1)]) -> None:
    """Offline: Stimmen je Fraktion zählen und technischen Importstatus anzeigen."""
    with open_database(ctx) as database:
        emit(vote_summary(database, poll))


@app.command()
def status(ctx: typer.Context) -> None:
    """Offline: lokale Entitätszahlen und letzte zehn Importläufe."""
    with open_database(ctx) as database:
        emit(project_status(database))


@app.command()
def web(
    ctx: typer.Context,
    port: Annotated[int, typer.Option(min=1, max=65535, help="Lokaler HTTP-Port.")] = 8000,
) -> None:
    """Lokale Website starten; keine automatischen Online-Abrufe."""
    from partei_hack.web.server import create_server

    try:
        with create_server(ctx.obj, port) as server:
            typer.echo(f"ParteiHack: http://127.0.0.1:{server.server_port}")
            typer.echo("Nur lokal. Beenden mit Strg+C. Keine parallelen CLI-Importe starten.")
            server.serve_forever()
    except KeyboardInterrupt:
        typer.echo("\nWebserver beendet.")
    except OSError as exc:
        typer.echo(f"Webserver konnte nicht gestartet werden: {exc}", err=True)
        raise typer.Exit(1) from exc


class ReportFormat(StrEnum):
    markdown = "markdown"
    json = "json"


@app.command("enrich-period")
def enrich(
    ctx: typer.Context,
    period_id: Annotated[int, typer.Argument(min=1)],
    poll: Annotated[int | None, typer.Option(min=1)] = None,
    max_polls: Annotated[int, typer.Option(min=1, max=50)] = 5,
    max_documents: Annotated[int, typer.Option(min=0, max=20)] = 3,
    source: Annotated[
        list[str] | None, typer.Option(help="Zusätzliche amtliche URL; erfordert --poll.")
    ] = None,
) -> None:
    """Online: relevante API-Kontexte und begrenzte amtliche Originalbelege ergänzen."""
    typer.echo(
        f"Belegrecherche: höchstens {max_polls} lokale Polls, "
        f"{max_documents} amtliche Dokumente insgesamt. Keine politischen Urteile.",
        err=True,
    )
    with open_database(ctx) as database:
        with APIClient(database, ctx.obj.raw_dir) as client:
            emit(
                enrich_period(
                    client,
                    database,
                    period_id,
                    max_polls=max_polls,
                    max_documents=max_documents,
                    poll_id=poll,
                    official_sources=source,
                )
            )


@app.command()
def compare(
    ctx: typer.Context,
    request: Annotated[str, typer.Argument(help='Zum Beispiel: "Bundestag 2021 bis 2025 Grüne".')],
    online: Annotated[
        bool, typer.Option(help="Daten importieren und ausgewählte Programm-PDF laden.")
    ] = False,
    max_polls: Annotated[int, typer.Option(min=1, help="Online-Stichprobengröße.")] = 5,
    all_polls: Annotated[
        bool, typer.Option(help="Online alle verfügbaren Polls und Stimmen.")
    ] = False,
    relevant_polls: Annotated[
        int | None,
        typer.Option(
            "--relevant-polls",
            min=1,
            max=50,
            help="Alle Poll-Metadaten laden, nur die N relevantesten Stimmen importieren.",
        ),
    ] = None,
    only_with_votes: Annotated[
        bool,
        typer.Option(
            "--only-with-votes",
            help="Bericht auf Polls mit lokalen Stimmen begrenzen.",
        ),
    ] = False,
    enrich_sources: Annotated[
        bool, typer.Option(help="Begrenzt API-Kontext und amtliche Belege ergänzen; nur --online.")
    ] = False,
    program_id: Annotated[int | None, typer.Option(min=1)] = None,
    program_file: Annotated[Path | None, typer.Option(help="Lokale Original-PDF.")] = None,
    promises: Annotated[
        Path | None, typer.Option(help="Geprüfte Zitate und Richtungszuordnungen.")
    ] = None,
    matches: Annotated[int, typer.Option(min=1, max=10)] = 3,
    output: Annotated[
        Path | None, typer.Option(help="Neuer Ordner für Markdown, JSON und Vorlage.")
    ] = None,
    output_format: Annotated[ReportFormat, typer.Option("--format")] = ReportFormat.markdown,
) -> None:
    """Wahlprogramm und Fraktionsstimmen anhand einer deutschen Anfrage gegenüberstellen."""
    try:
        parsed = parse_request(request)
    except ValueError as exc:
        raise typer.BadParameter(str(exc), param_hint="request") from exc
    if all_polls and not online:
        raise typer.BadParameter("--all-polls erfordert --online.")
    if relevant_polls is not None and not online:
        raise typer.BadParameter("--relevant-polls erfordert --online.")
    if all_polls and relevant_polls is not None:
        raise typer.BadParameter("--all-polls und --relevant-polls schließen sich aus.")
    if enrich_sources and not online:
        raise typer.BadParameter(
            "--enrich-sources erfordert --online; lokale Belege werden immer genutzt."
        )
    for path in (program_file, promises):
        if path is not None and not path.is_file():
            raise typer.BadParameter(f"Eingabedatei nicht vorhanden: {path}")
    if output is not None and output.exists():
        raise typer.BadParameter(
            "Ausgabeordner existiert bereits; bitte einen neuen Pfad verwenden."
        )
    with open_database(ctx) as database:
        selection_export = None
        if online:
            label = (
                "alle verfügbaren Polls"
                if all_polls
                else f"alle Poll-Metadaten, danach {relevant_polls} relevante Stimmenimporte"
                if relevant_polls is not None
                else f"höchstens {max_polls} Polls"
            )
            typer.echo(
                f"Online-Recherche: ausgewähltes Programm und {label}. "
                "Bitte Fair Use beachten; Zitate und Richtungen bleiben prüfpflichtig.",
                err=True,
            )
            with APIClient(database, ctx.obj.raw_dir) as client:
                discover_periods(client, database, parsed.parliament)
                period = resolve_period(database, parsed)
                if relevant_polls is not None:
                    metadata = Importer(client, database).sync_period(
                        period["id"], max_polls=None, with_votes=False
                    )
                    program, fraction = resolve_targets(database, period, parsed.party, program_id)
                    document = prepare_program(
                        ctx.obj.data_dir, program, client=client, local_file=program_file
                    )
                    ranking = rank_polls_for_program(database, period["id"], document)
                    selected = relevant_poll_ids(ranking, relevant_polls)
                    if not selected:
                        raise ValueError(
                            "Keine Poll-Metadaten mit belastbarem Programmtreffer gefunden; "
                            "es wurden keine Stimmen importiert."
                        )
                    votes = Importer(client, database).import_votes(period["id"], selected)
                    selection_export = {
                        "poll_metadata": metadata,
                        "ranking": ranking,
                        "selected_poll_ids": selected,
                        "votes": votes,
                        "assessment": "unreviewed_not_political_direction",
                    }
                    typer.echo(
                        json.dumps(selection_export, ensure_ascii=False),
                        err=True,
                    )
                else:
                    Importer(client, database).sync_period(
                        period["id"],
                        max_polls=None if all_polls else max_polls,
                        with_votes=True,
                    )
                    program, fraction = resolve_targets(database, period, parsed.party, program_id)
                    document = prepare_program(
                        ctx.obj.data_dir, program, client=client, local_file=program_file
                    )
                if enrich_sources:
                    enrichment = enrich_period(
                        client,
                        database,
                        period["id"],
                        max_polls=min(max_polls, 50),
                    )
                    typer.echo(json.dumps(enrichment, ensure_ascii=False), err=True)
        else:
            period = resolve_period(database, parsed)
            program, fraction = resolve_targets(database, period, parsed.party, program_id)
            document = prepare_program(ctx.obj.data_dir, program, local_file=program_file)
        report = build_comparison(
            database,
            parsed,
            period,
            program,
            fraction,
            document,
            promises_file=promises,
            matches_per_poll=matches,
            only_with_votes=only_with_votes or relevant_polls is not None,
        )
        if selection_export is not None:
            report["import_selection"] = selection_export
        if output is not None:
            emit({"files": write_report(output, report), "coverage": report["coverage"]})
        elif output_format == ReportFormat.json:
            emit(report)
        else:
            typer.echo(render_markdown(report), nl=False)
