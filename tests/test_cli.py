from __future__ import annotations

import pytest
from typer.testing import CliRunner

from harnesslab import __version__
from harnesslab.cli import app

runner = CliRunner()


def test_help_lists_phase_a_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "doctor" in result.stdout
    assert "serve" in result.stdout


def test_version_uses_package_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_serve_uses_psycopg_compatible_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(application: str, **options: object) -> None:
        captured["application"] = application
        captured.update(options)

    monkeypatch.setattr("harnesslab.cli.uvicorn.run", fake_run)
    result = runner.invoke(app, ["serve", "--port", "8123"])

    assert result.exit_code == 0
    assert captured["application"] == "harnesslab.api.app:app"
    assert captured["port"] == 8123
    assert captured["loop"] == "harnesslab.core.runtime:selector_loop_factory"


def test_doctor_reports_not_configured_with_distinct_exit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: object
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    result = runner.invoke(app, ["doctor"], env={"DATABASE_URL": ""})

    assert result.exit_code == 2
    assert "NOT_CONFIGURED" in result.stdout
    assert "postgresql" in result.stdout


@pytest.mark.integration
def test_doctor_reports_pass_with_database(database_url: str) -> None:
    result = runner.invoke(app, ["doctor"], env={"DATABASE_URL": database_url})

    assert result.exit_code == 0
    assert "PASS" in result.stdout
    assert "SELECT 1 succeeded" in result.stdout
