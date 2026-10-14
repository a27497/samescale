from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def campaign() -> ModuleType:
    spec = importlib.util.spec_from_file_location("campaign", ROOT / "scripts/coding_agent_eval.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_selection_ignores_input_order_and_rejects_duplicates(campaign: ModuleType) -> None:
    config = campaign.load(ROOT / "evaluation/coding-agent/config.json")
    rows = [{"task_id": f"HumanEval/{i}"} for i in range(164)]
    selected = campaign.select_tasks(rows, config)
    assert selected == campaign.select_tasks(list(reversed(rows)), config)
    assert [row["task_id"] for row in selected[:3]] == [
        "HumanEval/122",
        "HumanEval/33",
        "HumanEval/153",
    ]
    assert len(selected) == 30
    with pytest.raises(ValueError, match="duplicate"):
        campaign.select_tasks([*rows, rows[0]], config)


def make_case(campaign: ModuleType, tmp_path: Path, message: str, *, usage: bool = True) -> Path:
    case = tmp_path / "HumanEval_122"
    case.mkdir()
    campaign.save(
        case / "agent-process.json", {"exit_code": 0, "timed_out": False, "duration_seconds": 3.0}
    )
    events = [{"type": "item.completed", "item": {"type": "agent_message", "text": message}}]
    if usage:
        events.append(
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 1000, "cached_input_tokens": 500, "output_tokens": 100},
            }
        )
    (case / "agent.stdout").write_text("\n".join(json.dumps(event) for event in events))
    campaign.save(
        case / "verifier-process.json",
        {"exit_code": 0, "timed_out": False, "duration_seconds": 1.0},
    )
    campaign.save(
        case / "verifier.stdout", {"verdict": "FAIL", "failure_type": "HIDDEN_TEST_FAILURE"}
    )
    return case


@pytest.mark.parametrize(
    "message,expected",
    [
        ("Done, all tests passed.", "UNKNOWN"),
        ("SAMESCALE_SELF_REPORT=PASS", "PASS"),
        ("SAMESCALE_SELF_REPORT=PASS\nSAMESCALE_SELF_REPORT=FAIL", "UNKNOWN"),
        ("SAMESCALE_SELF_REPORT=UNKNOWN", "UNKNOWN"),
    ],
)
def test_claim_is_explicit_and_independent(
    campaign: ModuleType, tmp_path: Path, message: str, expected: str
) -> None:
    config = campaign.load(ROOT / "evaluation/coding-agent/config.json")
    row = campaign.facts(make_case(campaign, tmp_path, message), config)
    assert row["self_report"] == expected
    assert row["verifier"] == "FAIL"
    assert row["false_completion"] is (expected == "PASS")
    assert row["api_equivalent_usd"] == 0.00205
    assert row["actual_billed_usd"] is None


def test_missing_usage_does_not_become_free(campaign: ModuleType, tmp_path: Path) -> None:
    config = campaign.load(ROOT / "evaluation/coding-agent/config.json")
    row = campaign.facts(
        make_case(campaign, tmp_path, "SAMESCALE_SELF_REPORT=PASS", usage=False), config
    )
    summary = campaign.aggregate([row], config)
    assert summary["api_equivalent_usd"] is None
    assert summary["estimated_30_task_api_equivalent_usd"] is None
    assert row["failure_type"] == "ENVIRONMENT_FAILURE"


def test_append_only_and_tamper_detection(campaign: ModuleType, tmp_path: Path) -> None:
    (tmp_path / "final").mkdir()
    source = tmp_path / "final/solution.py"
    source.write_text("def f(): return 1\n")
    campaign.freeze(tmp_path)
    campaign.check_inventory(tmp_path)
    with pytest.raises(FileExistsError):
        campaign.freeze(tmp_path)
    source.write_text("def f(): return 2\n")
    with pytest.raises(ValueError, match="digest mismatch"):
        campaign.check_inventory(tmp_path)


def test_capture_withholds_reasoning_and_secrets(campaign: ModuleType, tmp_path: Path) -> None:
    reasoning = {"type": "item.completed", "item": {"type": "reasoning", "text": "private"}}
    program = f"print({json.dumps(reasoning)!r}); print('credential-value')"
    result = campaign.run_capture(
        [sys.executable, "-c", program],
        tmp_path / "agent",
        timeout=5,
        secrets=[b"credential-value"],
        jsonl=True,
    )
    saved = (tmp_path / "agent.stdout").read_text()
    assert "private" not in saved
    assert "credential-value" not in saved
    assert "PRIVATE_REASONING_WITHHELD" in saved
    assert result["capture"]["reasoning_events_withheld"] == 1


def test_full_requires_pilot_before_any_docker(campaign: ModuleType, tmp_path: Path) -> None:
    # The CLI rejects a missing confirmation without touching Docker or a credential.
    import subprocess

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/coding_agent_eval.py"),
            "full",
            "--root",
            str(tmp_path),
            "--codex-vendor",
            "/unused",
            "--auth-file",
            "/unused",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "user confirmation" in result.stderr


def test_verifier_and_subject_mounts_are_disjoint(campaign: ModuleType) -> None:
    command = campaign.restrictions(
        "test", "none", "sha256:placeholder", ["type=bind,src=/final,dst=/candidate,readonly"]
    )
    assert command[command.index("--network") + 1] == "none"
    assert "--read-only" in command
    assert all("credential" not in value and "docker.sock" not in value for value in command)


def test_historical_paid_entrypoint_obeys_closed_gate_before_inputs(
    campaign: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from harnesslab.api.workbench_errors import WorkbenchAPIError

    monkeypatch.setenv("HARNESSLAB_ENABLE_REAL_CODEX", "1")
    monkeypatch.setenv("HARNESSLAB_REAL_CODEX_ENABLED", "true")
    with pytest.raises(WorkbenchAPIError) as denied:
        asyncio.run(
            campaign.run(
                tmp_path / "missing",
                tmp_path / "missing-vendor",
                tmp_path / "missing-auth",
                full_confirmation=None,
            )
        )
    assert denied.value.code == "REAL_EXECUTION_BLOCKED"
    assert denied.value.status_code == 403
