import json
import shutil
from contextlib import nullcontext
from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

from partei_hack.cli import app
from partei_hack.config import Settings
from partei_hack.services.comparison import build_comparison
from partei_hack.services.importer import Importer
from partei_hack.services.matching import PassageMatcher
from partei_hack.services.programs import prepare_program
from partei_hack.services.promises import compare_direction, load_promises
from partei_hack.services.reports import render_markdown, write_report
from partei_hack.services.requests import parse_request, resolve_period, resolve_targets
from partei_hack.services.selection import rank_polls_for_program, relevant_poll_ids
from partei_hack.storage.database import utc_now
from tests.test_programs import TEST_TEXT, make_pdf


@pytest.fixture
def comparison_data(database, dataset_client, dataset, tmp_path):
    period = dataset["parliament-periods"][0]
    period.update(
        label="Bundestag 2021 - 2025",
        start_date_period="2021-10-26",
        end_date_period="2025-03-24",
    )
    period["parliament"]["label"] = "Bundestag"
    dataset["fractions"][0]["short_name"] = "BÜNDNIS 90/DIE GRÜNEN"
    dataset["fractions"][0]["label"] = "BÜNDNIS 90/DIE GRÜNEN (Test-Legislatur)"
    dataset["election-program"][0]["party"]["label"] = "BÜNDNIS 90/DIE GRÜNEN"
    dataset["polls"][0]["field_intro"] = (
        "<p>Synthetisch: Verkehr und Mobilität mit zuverlässigen Busse verbessern.</p>"
    )
    dataset["polls"][0]["api_url"] = "https://invalid.example/poll/9041"
    dataset["polls"][1]["api_url"] = "https://invalid.example/poll/9042"
    client, _ = dataset_client
    Importer(client, database).sync_period(9001, max_polls=1, with_votes=True)
    request = parse_request("Bundestag Wahlperiode 2021 bis 2025 Grüne")
    selected = resolve_period(database, request)
    program, fraction = resolve_targets(database, selected, request.party)
    pdf = tmp_path / "synthetic.pdf"
    pdf.write_bytes(make_pdf(TEST_TEXT))
    document = prepare_program(tmp_path, program, local_file=pdf)
    return request, selected, program, fraction, document


def build(database, comparison_data, **kwargs):
    return build_comparison(database, *comparison_data, **kwargs)


@pytest.mark.parametrize(
    "text",
    [
        "Bundestag Wahlperiode von 2021 bis 2025 Abstimmverhalten der Grünen "
        "verglichen mit Wahlprogramm und Versprechen",
        "Bundestag 2021–2025 Bündnis 90/Die Grünen",
        "bundestag 2021-2025 Gruene",
    ],
)
def test_german_request(text):
    request = parse_request(text)
    assert request.start_year == 2021
    assert request.end_year == 2025
    assert request.party == "gruene"


@pytest.mark.parametrize(
    "text",
    [
        "Bundestag Grüne",
        "Bundestag 2025 bis 2021 Grüne",
        "Bundestag 2021 bis 2025 SPD und Grüne",
        "Bundestag 2021 bis 2025 CDU/CSU",
        "Bundestag 2021 bis 2025 Unbekannte",
        "Landtag 2021 bis 2025 Grüne",
    ],
)
def test_ambiguous_or_unsupported_request_fails(text):
    with pytest.raises(ValueError):
        parse_request(text)


def test_comparison_preserves_coverage_and_unreviewed_state(database, comparison_data):
    report = build(database, comparison_data)
    assert report["coverage"]["local_polls"] == 1
    assert report["coverage"]["available_api_polls"] == 2
    assert report["coverage"]["complete_against_api"] is False
    assert "STICHPROBE" in report["warnings"][0]
    assert report["vote_totals"]["no_show"] == 1
    assert report["vote_totals"]["no"] == 0
    assert report["polls"][0]["program_matches"]
    for passage in report["polls"][0]["program_matches"]:
        assert passage["quote"] in comparison_data[-1]["pages"][0]["text"]
        assert passage["assessment"] == "not_assessable"
        assert passage["review_status"] == "unreviewed"
    assert report["reviewed_promises"] == []
    assert report["fulfillment"] == "not_assessed"


def test_only_with_votes_limits_report_scope_but_keeps_metadata_coverage(
    database, dataset_client, comparison_data
):
    client, _ = dataset_client
    Importer(client, database).sync_period(9001, max_polls=None, with_votes=False)
    request, period, program, fraction, document = comparison_data

    full = build(database, comparison_data)
    assert full["coverage"]["local_polls"] == 2
    assert full["coverage"]["reported_polls"] == 2
    assert full["coverage"]["polls_with_local_votes"] == 1
    assert full["coverage"]["polls_with_complete_votes"] == 1
    assert full["report_scope"] == {
        "only_with_votes": False,
        "reported_polls": 2,
        "local_polls": 2,
    }
    by_id = {poll["id"]: poll for poll in full["polls"]}
    assert by_id[9041]["quality"]["api_outcome"] == "rejected"
    assert by_id[9042]["quality"]["api_outcome"] == "accepted"
    assert by_id[9041]["direction_data_usable"] is True
    assert by_id[9042]["direction_data_usable"] is False
    assert full["quality_summary"]["polls_accepted_by_api"] == 1
    assert full["quality_summary"]["polls_rejected_by_api"] == 1
    assert full["quality_summary"]["polls_outcome_unknown"] == 0

    limited = build(database, comparison_data, only_with_votes=True)
    assert limited["coverage"]["local_polls"] == 2
    assert limited["coverage"]["reported_polls"] == 1
    assert [poll["id"] for poll in limited["polls"]] == [9041]
    assert limited["report_scope"]["only_with_votes"] is True
    assert limited["quality_summary"]["polls_accepted_by_api"] == 0
    assert limited["quality_summary"]["polls_rejected_by_api"] == 1
    assert limited["quality_summary"]["polls_outcome_unknown"] == 0


def test_poll_ranking_is_lexical_and_prioritizes_polls_with_votes(
    database, dataset_client, comparison_data
):
    client, _ = dataset_client
    Importer(client, database).sync_period(9001, max_polls=None, with_votes=False)
    request, period, program, fraction, document = comparison_data

    ranking = rank_polls_for_program(database, period["id"], document)
    assert ranking
    assert ranking[0]["poll_id"] == 9041
    assert ranking[0]["votes_complete"] is True
    assert ranking[0]["selection_method"] == "program_relevance_bm25_not_political_direction"
    assert ranking[0]["quote"] in document["pages"][0]["text"]
    assert ranking[0]["matched_terms"]
    assert all(item["poll_id"] != 9041 or item["api_accepted"] is False for item in ranking)

    complete_only = relevant_poll_ids(ranking, 1)
    assert complete_only == [9041]
    assert relevant_poll_ids(ranking, 2, skip_complete=False)[0] == 9041
    assert len(relevant_poll_ids(ranking, 2, skip_complete=False)) == len(ranking[:2])
    with pytest.raises(ValueError, match="1 bis 50"):
        relevant_poll_ids(ranking, 0)


def test_program_from_different_election_is_not_used(database, comparison_data):
    request, period, program, fraction, document = comparison_data
    changed = {**program, "parliament_period": {"id": 12345}}
    database.save_entity("election-program", changed, "https://invalid.example", utc_now())
    with pytest.raises(ValueError, match="Programm nicht eindeutig"):
        resolve_targets(database, period, request.party)


def test_period_is_not_guessed(database):
    with pytest.raises(ValueError, match="nicht eindeutig"):
        resolve_period(database, parse_request("Bundestag 2021 bis 2025 Grüne"))


def test_unrelated_text_has_no_match():
    matcher = PassageMatcher(
        [{"number": 1, "text": "Wir wollen zuverlässige Busse und öffentlichen Verkehr ausbauen."}]
    )
    assert matcher.match({"label": "Militäreinsatz", "field_intro": "<p>Verteidigung</p>"}) == []


def test_generic_money_and_party_names_do_not_create_matches():
    matcher = PassageMatcher(
        [
            {
                "number": 1,
                "text": (
                    "BÜNDNIS 90 DIE GRÜNEN wollen weitere Milliarden Euro bis 2025 "
                    "und zehn Prozent investieren."
                ),
            }
        ]
    )
    assert (
        matcher.match(
            {
                "label": "Lockerung der Schuldenbremse",
                "field_intro": "Die Grünen wollen weitere 500 Milliarden Euro bis 2025 ausgeben.",
            }
        )
        == []
    )


def test_title_overlap_prioritizes_actual_subject():
    matcher = PassageMatcher(
        [
            {
                "number": 1,
                "text": "Wir wollen die Schuldenbremse reformieren und Investitionen ermöglichen.",
            },
            {
                "number": 2,
                "text": "Wir wollen Investitionen in Solaranlagen und neue Windkraft ermöglichen.",
            },
        ]
    )
    matches = matcher.match(
        {
            "label": "Lockerung der Schuldenbremse",
            "field_intro": "Investitionen und Windkraft durch Solaranlagen ermöglichen.",
        }
    )
    assert len(matches) == 1
    assert matches[0]["page"] == 1
    assert "schuldenbremse" in matches[0]["matched_title_terms"]


def test_complete_import_can_be_reported_complete(database, comparison_data, dataset_client):
    client, _ = dataset_client
    Importer(client, database).sync_period(9001, max_polls=None, with_votes=True)
    report = build(database, comparison_data)
    assert report["coverage"]["complete_against_api"] is True
    assert report["coverage"]["local_polls"] == 2
    assert report["coverage"]["polls_with_complete_votes"] == 2


def test_complete_poll_list_without_votes_is_not_a_complete_comparison(
    database, comparison_data, dataset_client
):
    client, _ = dataset_client
    Importer(client, database).sync_period(9001, max_polls=None, with_votes=False)
    report = build(database, comparison_data)
    assert report["coverage"]["poll_list_complete_against_api"] is True
    assert report["coverage"]["complete_against_api"] is False


def reviewed_file(tmp_path, document, **overrides):
    quote = TEST_TEXT.split(". ")[0] + "."
    data = {
        "schema_version": 1,
        "program_id": document["program_id"],
        "document_sha256": document["sha256"],
        "promises": [
            {
                "id": "test-verkehr",
                "title": "Synthetisches Verkehrsversprechen",
                "page": 1,
                "quote": quote,
                "links": [
                    {
                        "poll_id": 9041,
                        "aligned_vote": "yes",
                        "rationale": "Synthetische, ausdrücklich als Test markierte Zuordnung.",
                        "source_url": "https://invalid.example/vorlage",
                        "reviewed_by": "Testprüfer",
                        "reviewed_at": date.today().isoformat(),
                    }
                ],
            }
        ],
        **overrides,
    }
    path = tmp_path / "review.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_reviewed_quote_is_validated_against_original_pdf(tmp_path, comparison_data):
    document = comparison_data[-1]
    path = reviewed_file(tmp_path, document)
    assert len(load_promises(path, document).promises) == 1
    data = json.loads(path.read_text(encoding="utf-8"))
    data["promises"][0]["quote"] = "Erfundenes Zitat, das nicht in der Originaldatei steht."
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="nicht nachweisbar"):
        load_promises(path, document)


def test_reviewed_document_hash_must_match(tmp_path, comparison_data):
    document = comparison_data[-1]
    path = reviewed_file(tmp_path, document, document_sha256="0" * 64)
    with pytest.raises(ValueError, match="Prüfsumme"):
        load_promises(path, document)


def test_reviewed_links_are_shown_without_claiming_fulfillment(database, tmp_path, comparison_data):
    path = reviewed_file(tmp_path, comparison_data[-1])
    report = build(database, comparison_data, promises_file=path)
    result = report["reviewed_promises"][0]["comparisons"][0]["direction_comparison"]
    assert result["result"] == "not_assessable"  # no_show is not "opposed"
    assert result["no_show"] == 1
    assert result["fulfillment"] == "not_assessed"


@pytest.mark.parametrize(
    ("counts", "complete", "expected"),
    [
        ({"yes": 3, "no": 1}, True, "majority_aligned"),
        ({"yes": 1, "no": 3}, True, "majority_opposed"),
        ({"yes": 1, "no": 1}, True, "split"),
        ({"no_show": 10}, True, "not_assessable"),
        ({"yes": 3}, False, "insufficient_data"),
        ({"yes": 3, "unknown": 1}, True, "insufficient_data"),
    ],
)
def test_reviewed_direction_has_explicit_denominator(counts, complete, expected):
    result = compare_direction(counts, "yes", complete=complete)
    assert result["result"] == expected
    assert result["fulfillment"] == "not_assessed"
    assert "yes + no" in result["denominator"]


@pytest.mark.parametrize("aligned_vote", ["yes", "no"])
def test_direction_exposes_all_recorded_entries_as_second_denominator(aligned_vote):
    counts = {aligned_vote: 2, "abstain": 3, "no_show": 5}
    result = compare_direction(counts, aligned_vote, complete=True)
    assert result["result"] == "majority_aligned"
    assert result["aligned_share_of_yes_no"] == 1.0
    assert result["aligned_share_of_recorded_votes"] == 0.2
    assert result["participation_share_of_recorded_votes"] == 0.5
    assert result["decisive_votes"] == 2
    assert result["recorded_votes"] == 10


def test_empty_direction_has_no_numeric_shares():
    result = compare_direction({}, "yes", complete=False)
    assert result["aligned_share_of_recorded_votes"] is None
    assert result["participation_share_of_recorded_votes"] is None
    assert result["result"] == "insufficient_data"


def test_program_inventory_keeps_unmatched_candidates_and_original_context(
    database, comparison_data
):
    request, period, program, fraction, document = comparison_data
    text = (
        "Wenn die Finanzierung gesichert ist, gilt die folgende Zusage. "
        "Wir wollen bis 2030 mindestens 20 Prozent mehr Wohnungen bauen. "
        "Dabei beachten wir die örtlichen Voraussetzungen für den Wohnungsbau."
    )
    document = {**document, "pages": [{"number": 1, "text": text}, {"number": 2, "text": ""}]}
    report = build_comparison(database, request, period, program, fraction, document)
    candidate = report["promise_candidates"][0]
    assert candidate["quote"] in text
    assert candidate["context_before"].startswith("Wenn")
    assert candidate["context_after"].startswith("Dabei")
    assert candidate["context_features"]["conditions"] == ["wenn"]
    assert candidate["matched_poll_ids"] == []
    assert candidate["status"] == "unreviewed"
    analysis = report["program_analysis"]
    assert analysis["candidate_count"] == 1
    assert analysis["candidate_feature_counts"] == {
        "quantities": 1,
        "years": 1,
        "conditions": 0,
        "negations": 0,
    }
    assert analysis["candidates_with_context_conditions"] == 1
    assert analysis["candidates_with_top_matches"] == 0
    assert analysis["pages_with_text"] == 1
    assert analysis["pages_without_text"] == [2]
    assert "Programm genauer untersuchen" in render_markdown(report)


def test_report_files_are_reproducible_and_never_overwritten(database, comparison_data, tmp_path):
    report = build(database, comparison_data)
    markdown = render_markdown(report)
    assert "STICHPROBE" in markdown
    assert "PDF-Seite 1" in markdown
    assert "nicht bewertet" in markdown
    assert "Anteil Ja/Nein an dokumentierten Fraktionsstimmen" in markdown
    assert "nicht berechenbar" in markdown
    output = tmp_path / "report"
    paths = write_report(output, report)
    template = json.loads(Path(paths["promises.template.json"]).read_text(encoding="utf-8"))
    assert template["promises"]
    assert all(promise["links"] == [] for promise in template["promises"])
    assert json.loads(Path(paths["report.json"]).read_text(encoding="utf-8")) == report
    with pytest.raises(FileExistsError):
        write_report(output, report)


def test_compare_cli_works_offline_with_local_pdf(database, comparison_data, tmp_path):
    runner = CliRunner()
    # CLI opens its own database: use the existing fixture database path.
    data_dir = tmp_path / "cli"
    database.connection.commit()
    target = Settings.resolve(data_dir).database_path
    target.parent.mkdir(parents=True)
    source = database.connection.execute("PRAGMA database_list").fetchone()["file"]
    shutil.copyfile(source, target)
    result = runner.invoke(
        app,
        [
            "--data-dir",
            str(data_dir),
            "compare",
            "Bundestag 2021 bis 2025 Grüne",
            "--program-file",
            str(tmp_path / "synthetic.pdf"),
            "--format",
            "json",
            "--only-with-votes",
        ],
    )
    assert result.exit_code == 0, result.output
    report = json.loads(result.stdout)
    assert report["program"]["id"] == 9071
    assert report["coverage"]["complete_against_api"] is False
    assert report["report_scope"]["only_with_votes"] is True
    assert report["coverage"]["reported_polls"] == len(report["polls"])


def test_online_relevance_exports_full_ranking_and_actual_selection(
    database, comparison_data, dataset_client, tmp_path, monkeypatch
):
    from partei_hack import cli

    client, _ = dataset_client
    data_dir = tmp_path / "cli-selection"
    database.connection.commit()
    target = Settings.resolve(data_dir).database_path
    target.parent.mkdir(parents=True)
    source = database.connection.execute("PRAGMA database_list").fetchone()["file"]
    shutil.copyfile(source, target)
    monkeypatch.setattr(cli, "APIClient", lambda *args: nullcontext(client))
    monkeypatch.setattr(cli, "discover_periods", lambda *args: None)
    result = CliRunner().invoke(
        app,
        [
            "--data-dir",
            str(data_dir),
            "compare",
            "Bundestag 2021 bis 2025 Grüne",
            "--online",
            "--relevant-polls",
            "1",
            "--program-file",
            str(tmp_path / "synthetic.pdf"),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    selection = json.loads(result.stdout)["import_selection"]
    assert selection["assessment"] == "unreviewed_not_political_direction"
    assert selection["selected_poll_ids"] == selection["votes"]["poll_ids"]
    assert set(selection["selected_poll_ids"]) <= {item["poll_id"] for item in selection["ranking"]}
    assert selection["poll_metadata"]["polls"] == 2


def test_compare_cli_rejects_ambiguous_input_before_network(tmp_path):
    result = CliRunner().invoke(
        app, ["--data-dir", str(tmp_path), "compare", "Bundestag Grüne", "--online"]
    )
    assert result.exit_code == 2
