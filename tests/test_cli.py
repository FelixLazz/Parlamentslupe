import json

from typer.testing import CliRunner

from partei_hack.cli import app, csv_cell
from partei_hack.storage.database import Database, utc_now

runner = CliRunner()


def test_help_and_doctor_do_not_create_data(tmp_path):
    data = tmp_path / "unused"
    help_result = runner.invoke(app, ["--help"])
    assert help_result.exit_code == 0
    assert "sync-period" in help_result.output
    result = runner.invoke(app, ["--data-dir", str(data), "doctor"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["api_key_required"] is False
    assert not data.exists()


def test_init_and_offline_status(tmp_path):
    args = ["--data-dir", str(tmp_path)]
    assert runner.invoke(app, [*args, "init-db"]).exit_code == 0
    result = runner.invoke(app, [*args, "status"])
    assert result.exit_code == 0
    assert json.loads(result.stdout)["entity_counts"] == {}


def test_invalid_vote_and_date_are_rejected(tmp_path):
    args = ["--data-dir", str(tmp_path)]
    assert runner.invoke(app, [*args, "votes", "--poll", "1", "--vote", "maybe"]).exit_code == 2
    assert runner.invoke(app, [*args, "polls", "--since", "bad"]).exit_code == 2
    result = runner.invoke(app, [*args, "polls", "--since", "2025-02-01", "--until", "2025-01-01"])
    assert result.exit_code == 2
    assert runner.invoke(app, [*args, "sync-period", "-1"]).exit_code == 2


def test_csv_export_neutralizes_formulas_and_does_not_overwrite(tmp_path):
    with Database(tmp_path / "processed" / "parteihack.sqlite3") as database:
        database.save_entity(
            "polls",
            {"id": 1, "label": "=SUM(1,2)", "field_poll_date": "2024-01-01"},
            "https://invalid.example",
            utc_now(),
        )
    output = tmp_path / "exports" / "test.csv"
    args = ["--data-dir", str(tmp_path), "polls", "--format", "csv", "--output", str(output)]
    result = runner.invoke(app, args)
    assert result.exit_code == 0, result.output
    content = output.read_text(encoding="utf-8")
    assert "'=SUM" in content
    assert runner.invoke(app, args).exit_code == 1
    assert output.read_text(encoding="utf-8") == content


def test_csv_formula_prefixes_are_escaped():
    for value in ["=1", "+1", "-1", "@SUM", "   =1", "\t=1", "\r=1"]:
        assert csv_cell(value).startswith("'")
    assert csv_cell("Normaler Titel") == "Normaler Titel"
    assert csv_cell(-1) == -1
