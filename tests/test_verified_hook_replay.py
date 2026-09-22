"""Pinned real capture + independent verifier; all mutations below are synthetic."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest

from harnesslab.analyst.offline_replay import ReplayError
from harnesslab.episodes.hooks import encode, read_events, replay_hook_case
from harnesslab.episodes.verified_hooks import freeze_verified_hook_case, read_verified_hook_bundle
from harnesslab.tasks.package import sha256_bytes

ROOT = Path(__file__).resolve().parents[1]
REAL = ROOT / "docs/evidence/real-hook-trace-20260922/verifier-closeout/verification"
ANCHOR = "sha256:7eabbf0805c2e9fb3ec89ecc338850c31dffe2aea513928391f7e3195c5e2971"


def read(path: Path) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(path.read_bytes()))


def reanchor(root: Path) -> str:
    manifest = read(root / "bundle.json")
    manifest["files"] = {
        p.relative_to(root).as_posix(): sha256_bytes(p.read_bytes())
        for p in root.rglob("*")
        if p.is_file() and p.name != "bundle.json"
    }
    (root / "bundle.json").write_bytes(encode(manifest))
    return sha256_bytes((root / "bundle.json").read_bytes())


def report_mutation(root: Path, mutation: str) -> None:
    report = read(root / "verifier-run/stdout.txt")
    if mutation == "pass":
        report.update(passed=True, score=1.0)
        for check in report["checks"]:
            check.update(passed=True, score=1.0)
    elif mutation == "empty":
        report["checks"] = []
    elif mutation == "contradiction":
        report["passed"] = True
    elif mutation == "string_bool":
        report["checks"][0]["passed"] = "false"
    elif mutation == "score":
        report["score"] = 1.0
    elif mutation == "duplicate":
        report["checks"][1]["name"] = report["checks"][0]["name"]
    target = root / "verifier-run/stdout.txt"
    target.write_bytes(encode(report))
    manifest = read(root / "verifier-run/manifest.json")
    digest = sha256_bytes(target.read_bytes())
    manifest["stdout"]["digest"] = digest
    manifest["stdout_stream_digest"] = digest
    (root / "verifier-run/manifest.json").write_bytes(encode(manifest))


def test_real_workspace_failure_is_independently_verified_without_hook_exit_codes() -> None:
    result = read_verified_hook_bundle(REAL, ANCHOR)
    assert result["acceptance"] == "VERIFIED_FAIL"
    assert result["passed_checks"] == 1 and result["checks"] == 4
    assert result["failed_checks"] == ["inclusive_boundary", "singleton", "negative_endpoints"]
    assert result["authority"] == "L0_INDEPENDENT_VERIFIER"
    assert result["root_cause"] is None and result["comparison_eligible"] is False
    assert all(e.exit_code is None for e in read_events(REAL / "hooks"))


def test_verified_case_cli_freeze_and_two_offline_replays(tmp_path: Path) -> None:
    bundle = tmp_path / "verification"
    shutil.copytree(REAL, bundle)
    case = tmp_path / "regression.json"
    command = [
        sys.executable,
        "-c",
        "from harnesslab.cli import app; app()",
        "episode",
        "freeze-hooks",
        str(bundle / "hooks"),
        "--store",
        str(tmp_path / "store"),
        "--output",
        str(case),
        "--verification",
        str(bundle),
        "--verification-sha256",
        ANCHOR,
    ]
    frozen = subprocess.run(command, capture_output=True, text=True)
    assert frozen.returncode == 0, frozen.stderr
    digest = sha256_bytes(case.read_bytes())
    assert digest in frozen.stdout
    outputs = []
    for attempt in ["a", "b"]:
        output = tmp_path / (attempt + ".json")
        run = subprocess.run(
            [
                sys.executable,
                "scripts/replay_hook.py",
                "--case",
                str(case),
                "--sha256",
                digest,
                "--output",
                str(output),
            ],
            cwd=ROOT,
            # Direct script execution must work without repository PYTHONPATH injection.
            env={key: value for key, value in os.environ.items() if key != "PYTHONPATH"},
            capture_output=True,
        )
        assert run.returncode == 0, run.stderr
        outputs.append(output.read_bytes())
    assert outputs[0] == outputs[1]
    result = json.loads(outputs[0])
    assert result["acceptance"] == "VERIFIED_FAIL"
    assert result["subject_executed"] is result["verifier_executed"] is False


def test_passing_workspace_never_becomes_bad_case(tmp_path: Path) -> None:
    bundle = tmp_path / "verification"
    shutil.copytree(REAL, bundle)
    report_mutation(bundle, "pass")
    digest = reanchor(bundle)
    assert read_verified_hook_bundle(bundle, digest)["acceptance"] == "VERIFIED_PASS"
    case = tmp_path / "case.json"
    with pytest.raises(ReplayError, match="passing workspace"):
        freeze_verified_hook_case(
            bundle / "hooks", tmp_path / "store", bundle, digest, case, source_kind="unverified"
        )
    assert not case.exists()


@pytest.mark.parametrize(
    "mutation", ["empty", "contradiction", "string_bool", "score", "duplicate"]
)
def test_invalid_verifier_report_fails_closed(tmp_path: Path, mutation: str) -> None:
    bundle = tmp_path / "verification"
    shutil.copytree(REAL, bundle)
    report_mutation(bundle, mutation)
    with pytest.raises(ValueError):
        read_verified_hook_bundle(bundle, reanchor(bundle))


@pytest.mark.parametrize(
    "mutation",
    [
        "timeout",
        "nonzero",
        "truncated",
        "network",
        "writable",
        "workspace",
        "task",
        "verifier",
        "binding",
        "missing",
        "lifecycle",
        "raw_stream_drift",
    ],
)
def test_verifier_bindings_and_infrastructure_fail_closed(tmp_path: Path, mutation: str) -> None:
    bundle = tmp_path / "verification"
    shutil.copytree(REAL, bundle)
    path = bundle / "verifier-run/manifest.json"
    manifest = read(path)
    if mutation == "timeout":
        manifest["timed_out"] = True
    elif mutation == "nonzero":
        manifest["exit_code"] = 7
    elif mutation == "truncated":
        manifest["stdout_truncated"] = True
    elif mutation == "network":
        manifest["security"]["network_mode"] = "host"
    elif mutation == "writable":
        manifest["security"]["mounts"][0]["read_write"] = True
    elif mutation == "workspace":
        (bundle / "final-workspace/calculator.py").write_text("def inclusive_sum(a, b): return 0\n")
    elif mutation == "task":
        manifest["task_digest"] = "sha256:" + "0" * 64
    elif mutation == "verifier":
        (bundle / "verifier-source/verify.py").write_text("print('PASS')\n")
    elif mutation == "binding":
        obj = read(bundle / "binding.json")
        obj["episode_identity"] = "sha256:" + "0" * 64
        (bundle / "binding.json").write_bytes(encode(obj))
    elif mutation == "missing":
        (bundle / "verifier-run/stdout.txt").unlink()
    elif mutation == "raw_stream_drift":
        (bundle / "verifier-run/stderr.txt").write_text("unexpected data")
    else:
        obj = read(bundle / "verifier-lifecycle.json")
        obj["stages"] = []
        (bundle / "verifier-lifecycle.json").write_bytes(encode(obj))
    path.write_bytes(encode(manifest))
    with pytest.raises(ValueError):
        read_verified_hook_bundle(bundle, ANCHOR)
    with pytest.raises(ValueError):
        read_verified_hook_bundle(bundle, reanchor(bundle))


def test_replay_rejects_invented_attribution(tmp_path: Path) -> None:
    bundle = tmp_path / "verification"
    shutil.copytree(REAL, bundle)
    case = tmp_path / "case.json"
    digest = freeze_verified_hook_case(
        bundle / "hooks", tmp_path / "store", bundle, ANCHOR, case, source_kind="unverified"
    )
    obj = read(case)
    obj["bad_case"]["root_cause"] = "model_failure"
    case.write_bytes(encode(obj))
    with pytest.raises(ValueError):
        replay_hook_case(case, digest)
    with pytest.raises(ReplayError, match="attribution"):
        replay_hook_case(case, sha256_bytes(case.read_bytes()))
