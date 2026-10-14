from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from scripts.swe_full_report import summary


@pytest.fixture
def campaign(tmp_path: Path) -> tuple[Path, Path, Path]:
    root, swe, he = (tmp_path / name for name in ("full", "swe", "he"))
    for path in (root / "results", swe, he):
        path.mkdir(parents=True)
    for path in (swe, he):
        (path / "pilot-summary.json").write_text('{"rows":[]}')
    ids = [f"case-{n}" for n in range(30)]
    (root / "selection.json").write_text(json.dumps({"tasks": ids}))
    for n, identity in enumerate(ids):
        (root / "results" / (identity + ".json")).write_text(
            json.dumps(
                {
                    "task_id": identity,
                    "group": "SWE-bench" if n < 25 else "HumanEval",
                    "retained": False,
                    "environment": "FAIL",
                    "self_report": "NOT_RUN",
                    "verifier": "NOT_RUN",
                    "failure_type": "ENVIRONMENT_FAILURE",
                    "false_completion": False,
                    "agent_seconds": None,
                    "api_equivalent_usd": 0,
                    "physical_agent_attempts": 0,
                    "evidence_path": str(root / identity),
                }
            )
        )
    return root, swe, he


def test_environment_failures_remain_in_all_fixed_denominators(
    campaign: tuple[Path, Path, Path],
) -> None:
    value = summary(*campaign)
    assert [value["groups"][g]["selected"] for g in ("All", "SWE-bench", "HumanEval")] == [
        30,
        25,
        5,
    ]
    assert value["groups"]["All"]["environment_failures"] == 30
    assert value["groups"]["All"]["independent_pass_rate"] == 0


def test_no_missing_or_substituted_task_can_publish(campaign: tuple[Path, Path, Path]) -> None:
    root, _, _ = campaign
    (root / "results/case-0.json").unlink()
    with pytest.raises(ValueError, match="all fixed thirty"):
        summary(*campaign)


def test_successor_requires_exact_zero_agent_predecessor(campaign: tuple[Path, Path, Path]) -> None:
    root, _, _ = campaign
    directory = root / "results-successors"
    directory.mkdir()
    original = json.loads((root / "results/case-0.json").read_text())
    replacement = {
        **original,
        "physical_agent_attempts": 1,
        "supersedes_projection_sha256": "wrong",
    }
    (directory / "case-0.json").write_text(json.dumps(replacement))
    with pytest.raises(ValueError, match="invalid environment correction"):
        summary(*campaign)


def test_budget_stop_preserves_selected_unrun_rows(campaign: tuple[Path, Path, Path]) -> None:
    root, _, _ = campaign
    (root / "results/case-0.json").unlink()
    (root / "STOP_BUDGET.json").write_text("{}")
    value = summary(*campaign)
    assert value["status"] == "PARTIAL_BUDGET_STOP"
    assert value["groups"]["All"]["selected"] == 30
    assert value["rows"][0]["not_run_reason"] == "OBSERVED_BUDGET_STOP"


def test_relocated_evidence_preserves_exact_canonical_projection(
    campaign: tuple[Path, Path, Path],
    tmp_path: Path,
) -> None:
    root, swe, he = campaign
    (root / "origin-paths.json").write_text(
        json.dumps({"full": str(root), "swe": str(swe), "human": str(he)})
    )
    expected = summary(*campaign)
    copied = tmp_path / "relocated"
    shutil.copytree(root, copied)
    assert summary(copied, swe, he) == expected
