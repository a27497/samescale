from __future__ import annotations

import json
from pathlib import Path

import yaml
from typer.testing import CliRunner

from harnesslab.cli import app
from harnesslab.experiment.plan import ExperimentPlan
from tests.phase_g_helpers import basic_spec

runner = CliRunner()


def test_phase_g_cli_surface_and_canonical_plan_output(tmp_path: Path) -> None:
    help_result = runner.invoke(app, ["--help"])
    assert help_result.exit_code == 0
    assert "experiment" in help_result.stdout
    assert "run" in help_result.stdout
    assert "report" in help_result.stdout

    spec_path = tmp_path / "experiment.yaml"
    spec_path.write_text(
        yaml.safe_dump(basic_spec(repeat_count=3).model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )
    result = runner.invoke(app, ["experiment", "plan", str(spec_path)])
    assert result.exit_code == 0
    assert "runs=6" in result.stdout
    assert "plan_digest=sha256:" in result.stdout

    json_result = runner.invoke(app, ["experiment", "plan", str(spec_path), "--json"])
    assert json_result.exit_code == 0
    plan = ExperimentPlan.model_validate(json.loads(json_result.stdout))
    assert len(plan.run_slots) == 6
    assert plan.digest in result.stdout


def test_phase_g_nested_cli_help() -> None:
    for command in (
        ["experiment", "run", "--help"],
        ["run", "inspect", "--help"],
        ["report", "compare", "--help"],
    ):
        result = runner.invoke(app, command)
        assert result.exit_code == 0


def test_methodology_v2_cli_is_strictly_planning_only() -> None:
    result = runner.invoke(app, ["experiment", "methodology-v2"])

    assert result.exit_code == 0
    assert "methodology_id=harnesslab-evaluation-methodology-v2" in result.stdout
    assert "methodology_digest=sha256:" in result.stdout
    assert "breadth_subject_runs=126" in result.stdout
    assert "incremental_critical_subject_runs=90" in result.stdout
    assert "projected_subject_runs=216" in result.stdout
    assert "formal_exhaustive_subject_runs=630" in result.stdout
    assert "reduction_subject_runs=414" in result.stdout
    assert "real_calls=0" in result.stdout
