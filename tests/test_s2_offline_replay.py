"""Portable real evidence, deterministic reconstruction, and adversarial offline regressions."""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest

from harnesslab.analyst.offline_replay import (
    ReplayError,
    compare_replays,
    decode,
    render_diagnosis,
    replay_bundle,
    safe_path,
)
from harnesslab.comparability.models import canonical_digest
from harnesslab.tasks.package import digest_tree, sha256_bytes

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "docs/evidence/s2-offline-replay-20260921"
ARCHIVE_DIGEST = "sha256:ee7748478fa7366d17454d1c5936a33466c580c2a3baf9ccdc5c302705345abd"
INPUTS_DIGEST = "sha256:d77d964fe60158da4e22ee7e60df0cfb54178a99c957298d861d977f925d0395"
Json = dict[str, Any]


def read(path: Path) -> Json:
    return decode(path.read_bytes())


def write(path: Path, obj: Json, *, seal: bool = False) -> None:
    if seal:
        obj.pop("identity", None)
        obj["identity"] = canonical_digest(obj)
    path.write_text(json.dumps(obj) + "\n")


@pytest.fixture(scope="session")
def evidence(tmp_path_factory: pytest.TempPathFactory) -> Path:
    archive = EVIDENCE / "representative-bundles.zip"
    assert sha256_bytes(archive.read_bytes()) == ARCHIVE_DIGEST
    destination = tmp_path_factory.mktemp("s2-real-bundles")
    with zipfile.ZipFile(archive) as zipped:
        for name in zipped.namelist():
            path = safe_path(destination, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(zipped.read(name))
    assert sha256_bytes((destination / "inputs.json").read_bytes()) == INPUTS_DIGEST
    return destination


def replay(evidence: Path, side: str) -> Json:
    entry = read(evidence / "inputs.json")["bundles"][side]
    return replay_bundle(evidence / entry["path"], entry["sha256"])


def copy_bundle(evidence: Path, tmp_path: Path, side: str = "codex") -> tuple[Path, str]:
    entry = read(evidence / "inputs.json")["bundles"][side]
    destination = tmp_path / side
    shutil.copytree(evidence / entry["path"], destination)
    return destination, entry["sha256"]


def reanchor(root: Path) -> str:
    """Deliberately grant new outer hashes, to exercise semantic checks behind the digest gate."""
    bundle = read(root / "bundle.json")
    bundle["run_digest"] = digest_tree(root / "run")
    bundle["files"] = {
        p.relative_to(root).as_posix(): sha256_bytes(p.read_bytes())
        for p in root.rglob("*")
        if p.is_file() and p.name != "bundle.json"
    }
    write(root / "bundle.json", bundle)
    return sha256_bytes((root / "bundle.json").read_bytes())


def sync_manifest(root: Path, manifest: Json) -> None:
    """Keep redundant records valid so a deeper cross-evidence contradiction is tested."""
    write(root / "run/manifest.json", manifest)
    result = read(root / "result.json")
    projection = result["projection"]
    projection["original_evidence"] = manifest
    for key in ["duration_ms", "timed_out", "usage", "normalized_trace_digest", "outcome"]:
        projection[key] = manifest[key]
    projection["changed_files"] = manifest["changed_paths"]
    projection.pop("identity", None)
    projection["identity"] = canonical_digest(projection)
    write(root / "result.json", result, seal=True)
    receipt = read(root / "receipt.json")
    receipt["artifact_digest"] = digest_tree(root / "run")
    write(root / "receipt.json", receipt, seal=True)


def test_real_runs_are_reconstructed_without_execution(
    evidence: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("offline replay attempted network or process execution")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    codex, claude = replay(evidence, "codex"), replay(evidence, "claude")
    assert codex["verification"]["state"] == "verified_pass"
    assert codex["verification"]["checks"] == codex["verification"]["passed_checks"] == 20
    assert len(codex["changed_files"]) == 2
    assert codex["trace"]["tool_count"] == 13  # 11 commands, 2 edits; no start/result double count.
    assert len(codex["validation"]["subject_commands"]) == 1
    assert codex["duration_usage"]["usage"]["output_tokens"] == 5230
    assert claude["outcome"] == "harness_error"
    assert claude["verification"]["state"] == "NOT_RUN"
    assert claude["verification"]["task_success"] is None
    assert claude["completion_failure"]["process_exit_code"] == 0  # Still NOT_VERIFIED.
    assert claude["completion_failure"]["native_terminal"] is None
    assert claude["completion_failure"]["failure_taxonomy"] == "execution_budget_exhausted"
    assert claude["trace"]["tool_count"] == 10
    assert claude["trace"]["last_tool_ordinal"] == 92
    assert claude["trace"]["thinking_metadata_events"] == 6828
    assert claude["duration_usage"]["usage"] is None
    assert claude["trace"]["per_event_duration"] is None
    assert claude["changed_files"] == []
    assert claude["validation"]["subject_commands"] == []
    assert len(claude["file_access"]["explicit_read_events"]) == 6
    assert claude["controls"]["original_cleanup"] == "FAIL"
    assert claude["controls"]["post_stop_cleanup"] == "PASS"
    assert codex["external_calls"] == claude["external_calls"] == 0


def test_diff_is_repeatable_and_keeps_limits(evidence: Path) -> None:
    first = compare_replays(replay(evidence, "codex"), replay(evidence, "claude"))
    second = compare_replays(replay(evidence, "codex"), replay(evidence, "claude"))
    assert first == second
    assert render_diagnosis(first) == render_diagnosis(second)
    assert not first["dimensions"]["file_access"]["equal"]
    assert first["comparison_type"] == "AI_CODING_CONFIGURATION_COMPARISON"
    assert any("no ability ranking" in limit for limit in first["limits"])


@pytest.mark.parametrize(
    "side,relative",
    [
        ("codex", "run/manifest.json"),
        ("codex", "run/native/codex.sanitized.jsonl"),
        ("codex", "run/trace/normalized.json"),
        ("codex", "run/verifier/stdout.txt"),
        ("codex", "run/workspace/frontend/src/stores/taskEvents.ts"),
        ("codex", "baseline/frontend/src/stores/taskEvents.ts"),
        ("codex", "receipt.json"),
        ("claude", "run/native/claude-code.sanitized.jsonl"),
        ("claude", "post-stop-cleanup.json"),
    ],
)
@pytest.mark.parametrize("mutation", ["missing", "tampered"])
def test_integrity_drift_fails_closed(
    evidence: Path,
    tmp_path: Path,
    side: str,
    relative: str,
    mutation: str,
) -> None:
    root, digest = copy_bundle(evidence, tmp_path, side)
    target = root / relative
    if mutation == "missing":
        target.unlink()
    else:
        target.write_bytes(target.read_bytes() + b"tamper")
    with pytest.raises(ReplayError):
        replay_bundle(root, digest)


@pytest.mark.parametrize(
    "mutation", ["extra", "symlink", "anchor", "duplicate_json", "path_escape"]
)
def test_inventory_and_trust_anchor_fail_closed(
    evidence: Path,
    tmp_path: Path,
    mutation: str,
) -> None:
    root, digest = copy_bundle(evidence, tmp_path)
    if mutation == "extra":
        (root / "unindexed.txt").write_text("not frozen")
    elif mutation == "symlink":
        (root / "receipt.json").unlink()
        (root / "receipt.json").symlink_to(evidence / "bundles/codex/receipt.json")
    elif mutation == "anchor":
        obj = read(root / "bundle.json")
        obj["run_id"] = "replaced"
        write(root / "bundle.json", obj)
    elif mutation == "duplicate_json":
        (root / "bundle.json").write_text('{"files":{},"files":{},"schema_version":1}')
        digest = sha256_bytes((root / "bundle.json").read_bytes())
    else:
        obj = read(root / "bundle.json")
        obj["files"]["../escape"] = "sha256:" + "0" * 64
        write(root / "bundle.json", obj)
        digest = sha256_bytes((root / "bundle.json").read_bytes())
    with pytest.raises(ReplayError):
        replay_bundle(root, digest)


@pytest.mark.parametrize(
    "mutation",
    [
        "false_success",
        "usage",
        "changed_files",
        "native_trace",
        "zero_checks",
        "check_failure",
        "verifier_timeout",
        "baseline",
        "terminal",
        "cleanup",
        "secret_audit",
        "duplicate_ordinal",
    ],
)
def test_semantic_contradictions_fail_even_with_reanchored_inventory(
    evidence: Path,
    tmp_path: Path,
    mutation: str,
) -> None:
    root, _ = copy_bundle(evidence, tmp_path)
    manifest = read(root / "run/manifest.json")
    if mutation in {"false_success", "usage", "cleanup"}:
        r = read(root / "receipt.json")
        if mutation == "false_success":
            r["task_success"] = False
        elif mutation == "usage":
            r["usage"]["output_tokens"] = 0
        else:
            r["cleanup_verified"] = False
        write(root / "receipt.json", r, seal=True)
    elif mutation == "secret_audit":
        r = read(root / "secret-audit.json")
        r["status"] = "FAIL"
        write(root / "secret-audit.json", r, seal=True)
    elif mutation == "changed_files":
        manifest["changed_paths"] = []
        sync_manifest(root, manifest)
    elif mutation == "baseline":
        p = root / "baseline/frontend/src/stores/taskEvents.ts"
        p.write_text("not the original starting workspace")
    elif mutation in {"native_trace", "duplicate_ordinal"}:
        p = root / "run/trace/normalized.json"
        trace = read(p)
        trace["events"][0][
            "ordinal" if mutation == "duplicate_ordinal" else "native_event_type"
        ] = 2 if mutation == "duplicate_ordinal" else "turn.completed"
        write(p, trace)
        manifest["normalized_trace_digest"] = sha256_bytes(p.read_bytes())
        sync_manifest(root, manifest)
    elif mutation == "terminal":
        manifest["terminal_native_event"] = None
        sync_manifest(root, manifest)
    else:
        report_path = root / "run/verifier/stdout.txt"
        report = read(report_path)
        if mutation == "zero_checks":
            report["checks"] = []
        elif mutation == "check_failure":
            report["checks"][0]["passed"] = False
        write(report_path, report)
        sandbox = manifest["verifier_sandbox_manifest"]
        sandbox["stdout"]["digest"] = sha256_bytes(report_path.read_bytes())
        sandbox["stdout_stream_digest"] = sandbox["stdout"]["digest"]
        if mutation == "verifier_timeout":
            sandbox["timed_out"] = True
        write(root / "run/verifier/manifest.json", sandbox)
        manifest["verifier_artifact_digest"] = digest_tree(root / "run/verifier")
        sync_manifest(root, manifest)
    with pytest.raises(ReplayError):
        replay_bundle(root, reanchor(root))


def test_different_task_or_duplicate_run_cannot_be_compared(evidence: Path) -> None:
    left, right = replay(evidence, "codex"), replay(evidence, "claude")
    with pytest.raises(ReplayError):
        compare_replays(left, left)
    right["task"]["task_digest"] = "different"
    with pytest.raises(ReplayError):
        compare_replays(left, right)


def test_cli_atomic_fail_closed(evidence: Path, tmp_path: Path) -> None:
    local = tmp_path / "input"
    shutil.copytree(evidence, local)
    (local / "bundles/claude/run/manifest.json").unlink()
    output = tmp_path / "output"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/replay_s2.py"),
            "--inputs",
            str(local / "inputs.json"),
            "--sha256",
            INPUTS_DIGEST,
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "FAIL_CLOSED" in result.stderr
    assert not output.exists()


def test_cli_offline_guard_rejects_network_and_processes() -> None:
    # The audit hook rejects socket construction before any connection can be attempted.
    program = """
import runpy, socket, subprocess, sys
module = runpy.run_path('scripts/replay_s2.py')
sys.addaudithook(module['offline_guard'])
for action in [lambda: socket.socket(), lambda: subprocess.run([sys.executable, '-V'])]:
    try:
        action()
    except module['ReplayError']:
        pass
    else:
        raise AssertionError('offline boundary bypassed')
for event in ['os.exec', 'os.spawn', 'os.posix_spawn', 'os.system', 'pty.spawn']:
    try:
        sys.audit(event)
    except module['ReplayError']:
        pass
    else:
        raise AssertionError(f'offline boundary bypassed: {event}')
print('blocked both before execution')
"""
    result = subprocess.run(
        [sys.executable, "-c", program], cwd=ROOT, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
    assert "blocked both" in result.stdout


@pytest.mark.parametrize("raw", [b'{"x":NaN}', b'{"x":Infinity}', b'{"x":-Infinity}'])
def test_non_finite_json_is_rejected(raw: bytes) -> None:
    with pytest.raises(ReplayError):
        decode(raw)


def test_cli_refuses_output_inside_immutable_bundle(evidence: Path) -> None:
    output = evidence / "bundles/codex/new-output"
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/replay_s2.py"),
            "--inputs",
            str(evidence / "inputs.json"),
            "--sha256",
            INPUTS_DIGEST,
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert not output.exists()
