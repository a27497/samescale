"""Frozen outputs catch consistent parser/attribution drift, beyond input digest checks."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from scripts.record_s3_ci import record
from scripts.verify_s3_regression import (
    EVIDENCE,
    GOLDEN,
    ROOT,
    check_junit,
    check_outputs,
    extract_archive,
)

from harnesslab.analyst import offline_replay
from harnesslab.analyst.offline_replay import ReplayError, replay_bundle
from harnesslab.harness_lane.models import NormalizedTrace
from harnesslab.multi_harness.trace import _trace_event
from tests.test_s2_offline_replay import (
    copy_bundle,
    read,
    reanchor,
    replay,
    sync_manifest,
    write,
)
from tests.test_s2_offline_replay import (
    evidence as evidence,
)


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", 2),
        ("changed_files", []),
        ("file_access", {"explicit_read_events": ["invented-shell-read"]}),
        ("trace", {"tool_count": 0}),
        ("completion_failure", {"failure_taxonomy": "task_failure"}),
        ("verification", {"state": "verified_pass", "task_success": True}),
        ("duration_usage", {"usage": {"output_tokens": 6828}}),
    ],
)
def test_golden_rejects_semantic_regressions(tmp_path: Path, field: str, value: Any) -> None:
    for name in GOLDEN:
        shutil.copyfile(EVIDENCE / name, tmp_path / name)
    check_outputs(tmp_path)
    # Deliberately mutate a valid output (no evidence corruption): catches code regressions
    # even when a regressed parser and its self-consistency check agree with each other.
    obj = read(tmp_path / "codex.json")
    obj[field] = value
    write(tmp_path / "codex.json", obj)
    with pytest.raises(ReplayError, match="digest"):
        check_outputs(tmp_path)


@pytest.mark.parametrize("side", ["codex", "claude"])
def test_parser_mutation_fails_closed(
    evidence: Path, monkeypatch: pytest.MonkeyPatch, side: str
) -> None:
    if side == "codex":
        monkeypatch.setattr(
            offline_replay, "_normalized_trace", lambda _: NormalizedTrace(events=())
        )
    else:
        monkeypatch.setattr(
            offline_replay,
            "_trace_event",
            lambda event: _trace_event(event).model_copy(update={"native_event_type": "regressed"}),
        )
    with pytest.raises(ReplayError, match="native/normalized"):
        replay(evidence, side)


@pytest.mark.parametrize("mutation", ["schema", "taxonomy", "attribution"])
def test_schema_and_taxonomy_drift_fail_closed(
    evidence: Path, tmp_path: Path, mutation: str
) -> None:
    root, _ = copy_bundle(evidence, tmp_path, "claude")
    manifest = read(root / "run/manifest.json")
    if mutation == "schema":
        manifest["schema_version"] = 2
    elif mutation == "taxonomy":
        manifest["harness_failure"] = "protocol_error"
    else:
        manifest["changed_paths"] = ["frontend/src/stores/taskEvents.ts"]
    sync_manifest(root, manifest)
    with pytest.raises(ReplayError):
        replay_bundle(root, reanchor(root))


@pytest.mark.parametrize("mutation", ["missing", "extra", "digest"])
def test_output_inventory_is_frozen(tmp_path: Path, mutation: str) -> None:
    for name in GOLDEN:
        shutil.copyfile(EVIDENCE / name, tmp_path / name)
    if mutation == "missing":
        (tmp_path / "diagnosis.md").unlink()
    elif mutation == "extra":
        (tmp_path / "extra.json").write_text("{}")
    else:
        (tmp_path / "diagnosis.md").write_text("ability ranking")
    with pytest.raises(ReplayError):
        check_outputs(tmp_path)


def test_archive_drift_rejected_before_extraction(tmp_path: Path) -> None:
    archive = tmp_path / "changed.zip"
    archive.write_bytes((EVIDENCE / "representative-bundles.zip").read_bytes() + b"drift")
    with pytest.raises(ReplayError):
        extract_archive(archive, tmp_path / "inputs")
    assert not (tmp_path / "inputs").exists()


@pytest.mark.parametrize("child", ["", "<skipped/>", "<failure/>", "<error/>"])
def test_missing_or_nonpassing_test_evidence_is_not_pass(tmp_path: Path, child: str) -> None:
    path = tmp_path / "pytest.xml"
    case = f'<testcase name="unrelated">{child}</testcase>'
    path.write_text(f"<testsuites><testsuite>{case * 44}</testsuite></testsuites>")
    with pytest.raises(ReplayError):
        check_junit(path)
    path.write_text("<testsuites/>")
    with pytest.raises(ReplayError):
        check_junit(path)


def test_workflow_uses_offline_entry_without_execution_credentials() -> None:
    path = ROOT / ".github/workflows/offline-regression.yml"
    workflow = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
    assert set(workflow["on"]) == {"push", "pull_request"}
    assert workflow["permissions"] == {"contents": "read"}
    job = workflow["jobs"]["offline-regression"]
    assert "if" not in job and "continue-on-error" not in job
    step = next(s for s in job["steps"] if s.get("name") == "Offline replay and trace regression")
    assert step["run"] == 'bash scripts/ci_s3.sh "$RUNNER_TEMP/s3-regression"'
    assert "if" not in step and "continue-on-error" not in step
    assert "secrets." not in path.read_text()
    assert not any("env" in s for s in job["steps"])
    record = job["steps"][-1]
    assert record["if"] == "${{ always() }}"
    assert record["run"] == 'python3 scripts/record_s3_ci.py "$RUNNER_TEMP/s3-regression"'
    assert "continue-on-error" not in record
    launcher = (ROOT / "scripts/ci_s3.sh").read_text()
    assert "sudo -n unshare --net -- setpriv" in launcher
    assert "env -i HOME=" in launcher and "--no-new-privs" in launcher
    assert "UV_OFFLINE=1" in launcher
    assert "verify_s3_regression.py" in launcher
    recorded = json.loads((EVIDENCE / "reproducibility.json").read_text())
    assert recorded["identical_outputs"] == GOLDEN


def test_actions_receipt_is_bounded_and_checks_junit(tmp_path: Path, capsys: Any) -> None:
    source = ROOT / "docs/evidence/phase0-candidate-20260922/offline"
    for name in ("result.json", "pytest.txt", "pytest.xml", "replay-a.txt", "replay-b.txt"):
        shutil.copyfile(source / name, tmp_path / name)
    summary = tmp_path / "summary.md"
    assert record(tmp_path, "a" * 40, summary) == 0
    output = capsys.readouterr().out
    assert len(output) < 5000
    receipt = json.loads(output.removeprefix("S3_GITHUB_RECEIPT="))
    assert receipt["head_sha"] == "a" * 40
    assert receipt["junit_cases"] == receipt["regression"]["tests_passed"] == 122
    assert set(receipt["evidence_sha256"]) == {
        "pytest.txt",
        "pytest.xml",
        "replay-a.txt",
        "replay-b.txt",
    }
    assert "Offline regression" in summary.read_text()

    (tmp_path / "pytest.xml").write_text("<testsuites/>")
    assert record(tmp_path, "a" * 40, summary) == 2
    assert "S3_RECORDING_FAILED=" in capsys.readouterr().err
