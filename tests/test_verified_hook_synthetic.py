"""Synthetic, digest-pinned verifier evidence for passive native Hook cases."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from harnesslab.analyst.offline_replay import ReplayError
from harnesslab.episodes.hooks import (
    derive_episode,
    encode,
    normalized,
    read_events,
    receive_hook,
    replay_hook_case,
)
from harnesslab.episodes.verified_hooks import (
    freeze_verified_hook_case,
    read_verified_hook_bundle,
)
from harnesslab.sandbox.models import (
    ArtifactDigest,
    ImageIdentity,
    MountEvidence,
    SandboxArtifactManifest,
    SandboxStatus,
    SecurityEvidence,
    VerifierLifecycleDiagnostics,
    VerifierLifecycleStage,
    VerifierLifecycleStageEvidence,
    VerifierLifecycleStageStatus,
)
from harnesslab.tasks.models import CheckResult, VerifierReport
from harnesslab.tasks.package import TaskPackage, digest_tree, sha256_bytes


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _index(root: Path) -> str:
    files = {
        p.relative_to(root).as_posix(): sha256_bytes(p.read_bytes())
        for p in root.rglob("*")
        if p.is_file() and p.name != "bundle.json"
    }
    data = encode({"schema_version": 1, "kind": "verified-hook-workspace-v1", "files": files})
    _write(root / "bundle.json", data)
    return sha256_bytes(data)


def _bundle(tmp_path: Path) -> tuple[Path, Path, str]:
    root = tmp_path / "verified"
    spool = root / "hooks"
    for event in ("SessionStart", "PreToolUse", "PostToolUse", "Stop"):
        raw: dict[str, object] = {"hook_event_name": event, "session_id": "synthetic-session"}
        if "ToolUse" in event:
            raw.update(tool_name="Bash", tool_use_id="synthetic-call")
        if event == "PostToolUse":
            raw["tool_response"] = "Exit code: 1; this is stdout, not process status"
        receive_hook(encode(raw), "codex", spool)
    events = read_events(spool)
    episode = derive_episode(events, "synthetic")
    assert episode.acceptance == "NOT_VERIFIED" and episode.failed_tools == 0
    _write(root / "episode.json", encode(episode.model_dump(mode="json")))
    _write(root / "normalized.json", (normalized(events).canonical_json() + "\n").encode())

    package_root = Path(__file__).resolve().parents[1] / "tasks/micro-python-clamp/1.0.0"
    package = TaskPackage.load(package_root)
    shutil.copytree(
        package_root, root / "task-package" / package.definition.id / package.definition.version
    )
    shutil.copytree(package_root / "verifier", root / "verifier-source")
    _write(root / "task.json", encode(package.definition.model_dump(mode="json")))

    source_files: dict[str, str] = {}
    for source in (package_root / "workspace").rglob("*"):
        if source.is_file():
            name = source.relative_to(package_root / "workspace").as_posix()
            data = source.read_bytes()
            source_files[name] = sha256_bytes(data)
            _write(root / "final-workspace" / name, data)
            _write(root / "verifier-run" / "workspace" / name, data)

    receipt = encode({"fixture_unchanged": True})
    _write(root / "prior-workspace-receipt.json", receipt)
    prior = {"privacy.json": sha256_bytes(receipt)}
    prior.update({f"fixture/{name}": digest for name, digest in source_files.items()})
    prior.update(
        {f"hooks/{p.name}": sha256_bytes(p.read_bytes()) for p in spool.iterdir() if p.is_file()}
    )
    prior_data = encode(prior)
    _write(root / "prior-capture-index.json", prior_data)
    _write(
        root / "binding.json",
        encode(
            {
                "schema_version": 1,
                "episode_identity": episode.identity,
                "agent_reexecuted": False,
                "binding_authority": "OPERATOR_RECORDED_NOT_ATTESTED",
                "prior_capture_manifest_digest": sha256_bytes(prior_data),
                "source_files": source_files,
            }
        ),
    )

    report = VerifierReport(
        schema_version=1,
        passed=False,
        score=0.0,
        checks=(CheckResult(name="synthetic-contract", passed=False, score=0.0),),
        summary="Independent synthetic workspace contract failure",
    )
    stdout = encode(report.model_dump(mode="json"))
    stderr = b""
    _write(root / "verifier-run/stdout.txt", stdout)
    _write(root / "verifier-run/stderr.txt", stderr)
    # The package workspace bytes are the final and verifier input/output snapshots.
    workspace_digest = digest_tree(root / "final-workspace")
    manifest = SandboxArtifactManifest(
        run_id="synthetic-verifier",
        role="verifier",
        task_id=package.definition.id,
        task_version=package.definition.version,
        task_digest=package.definition.content_digest,
        workspace_input_digest=workspace_digest,
        workspace_output_digest=workspace_digest,
        image=ImageIdentity(
            reference="synthetic:fixture", image_id=sha256_bytes(b"synthetic-image")
        ),
        security=SecurityEvidence(
            privileged=False,
            read_only_rootfs=True,
            cap_drop=("ALL",),
            security_options=("no-new-privileges=true",),
            network_mode="none",
            memory_bytes=1024,
            nano_cpus=1,
            pids_limit=1,
            restart_policy="no",
            user="1000:1000",
            pid_mode="private",
            published_ports=False,
            device_count=0,
            mounts=(
                MountEvidence(destination="/workspace", read_write=False, mount_type="bind"),
                MountEvidence(destination="/verifier", read_write=False, mount_type="bind"),
            ),
            tmpfs_destinations=("/tmp",),
            docker_socket_mounted=False,
            seccomp_unconfined=False,
        ),
        status=SandboxStatus.SUCCEEDED,
        exit_code=0,
        duration_ms=1,
        timed_out=False,
        cancelled=False,
        cleanup_verified=True,
        stdout_stream_digest=sha256_bytes(stdout),
        stderr_stream_digest=sha256_bytes(stderr),
        stdout_truncated=False,
        stderr_truncated=False,
        stdout=ArtifactDigest(path="stdout.txt", digest=sha256_bytes(stdout)),
        stderr=ArtifactDigest(path="stderr.txt", digest=sha256_bytes(stderr)),
        workspace_snapshot=ArtifactDigest(path="workspace", digest=workspace_digest),
        summary="Synthetic verifier process completed",
    )
    _write(root / "verifier-run/manifest.json", encode(manifest.model_dump(mode="json")))
    lifecycle = VerifierLifecycleDiagnostics(
        stages=(
            VerifierLifecycleStageEvidence(
                stage=VerifierLifecycleStage.RESULT_COLLECT,
                status=VerifierLifecycleStageStatus.COMPLETED,
                duration_ms=1,
            ),
            VerifierLifecycleStageEvidence(
                stage=VerifierLifecycleStage.STAGING_CLEANUP,
                status=VerifierLifecycleStageStatus.COMPLETED,
                duration_ms=1,
            ),
        ),
    )
    _write(root / "verifier-lifecycle.json", encode(lifecycle.model_dump(mode="json")))
    return spool, root, _index(root)


def test_unknown_hook_status_can_be_frozen_only_with_independent_verifier(tmp_path: Path) -> None:
    spool, bundle, expected = _bundle(tmp_path)
    result = read_verified_hook_bundle(bundle, expected)
    assert result["acceptance"] == "VERIFIED_FAIL"
    assert result["authority"] == "L0_INDEPENDENT_VERIFIER"
    assert result["source_authenticity"] == "NOT_ATTESTED"
    assert result["scope"] == "FINAL_WORKSPACE_CONTRACT_NOT_AGENT_INSTRUCTION_COMPLIANCE"
    assert result["root_cause"] is None
    assert all(event.exit_code is None for event in read_events(spool))

    case = tmp_path / "case.json"
    digest = freeze_verified_hook_case(
        spool, tmp_path / "store", bundle, expected, case, source_kind="synthetic"
    )
    replay = replay_hook_case(case, digest)
    assert replay["status"] == "PASS" and replay["acceptance"] == "VERIFIED_FAIL"
    assert replay["subject_executed"] is False and replay["verifier_executed"] is False
    assert replay["external_calls"] == 0


def test_verified_bundle_tamper_rejected(tmp_path: Path) -> None:
    _, bundle, expected = _bundle(tmp_path)
    (bundle / "verifier-run/stdout.txt").write_bytes(b"changed")
    with pytest.raises(ReplayError):
        read_verified_hook_bundle(bundle, expected)


def _passing_bundle(tmp_path: Path) -> tuple[Path, Path, str]:
    spool, bundle, _ = _bundle(tmp_path)
    report = VerifierReport(
        schema_version=1,
        passed=True,
        score=1.0,
        checks=(CheckResult(name="synthetic-contract", passed=True, score=1.0),),
        summary="Independent synthetic workspace contract pass",
    )
    stdout = encode(report.model_dump(mode="json"))
    _write(bundle / "verifier-run/stdout.txt", stdout)
    manifest_path = bundle / "verifier-run/manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["stdout"]["digest"] = manifest["stdout_stream_digest"] = sha256_bytes(stdout)
    _write(manifest_path, encode(manifest))
    return spool, bundle, _index(bundle)


def test_verified_pass_requires_neutral_opt_in_and_replays(tmp_path: Path) -> None:
    spool, bundle, expected = _passing_bundle(tmp_path)
    episode_before = (bundle / "episode.json").read_bytes()
    case = tmp_path / "case.json"
    with pytest.raises(ReplayError, match="passing workspace is not a Bad Case"):
        freeze_verified_hook_case(
            spool, tmp_path / "store", bundle, expected, case, source_kind="synthetic"
        )
    assert not case.exists()
    digest = freeze_verified_hook_case(
        spool,
        tmp_path / "store",
        bundle,
        expected,
        case,
        source_kind="synthetic",
        allow_pass=True,
    )
    frozen = case.read_bytes()
    first = encode(replay_hook_case(case, digest))
    assert first == encode(replay_hook_case(case, digest))
    assert case.read_bytes() == frozen
    result = json.loads(first)
    assert result["acceptance"] == "VERIFIED_PASS" and "bad_case" not in result
    assert result["verification_result"]["root_cause"] is None
    assert result["verification_result"]["source_authenticity"] == "NOT_ATTESTED"
    assert result["verification_result"]["namespace"] == "CUSTOM"
    assert result["verification_result"]["comparison_eligible"] is False
    assert result["external_calls"] == 0
    assert result["subject_executed"] is result["verifier_executed"] is False
    assert (bundle / "episode.json").read_bytes() == episode_before
    stored_episode = next((tmp_path / "store").glob("*.json"))
    assert stored_episode.read_bytes() == episode_before
    assert json.loads(episode_before)["acceptance"] == "NOT_VERIFIED"

    from typer.testing import CliRunner

    from harnesslab.episodes.cli import episode_app

    cli_case = tmp_path / "cli-case.json"
    cli_result = CliRunner().invoke(
        episode_app,
        [
            "freeze-hooks",
            str(spool),
            "--store",
            str(tmp_path / "cli-store"),
            "--output",
            str(cli_case),
            "--verification",
            str(bundle),
            "--verification-sha256",
            expected,
            "--allow-pass",
            "--source-kind",
            "synthetic",
        ],
    )
    assert cli_result.exit_code == 0
    assert cli_case.read_bytes() == frozen

    # Relabeling a pass as the historical failure-only schema must still fail closed.
    relabeled = json.loads(frozen)
    relabeled["kind"] = "verified-hook-regression-v1"
    relabeled["bad_case"] = relabeled.pop("verification_result")
    bad_case = tmp_path / "relabeled.json"
    _write(bad_case, encode(relabeled))
    with pytest.raises(ReplayError, match="passing workspace is not a Bad Case"):
        replay_hook_case(bad_case, sha256_bytes(bad_case.read_bytes()))


def test_allow_pass_requires_independent_verification(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from harnesslab.episodes.cli import episode_app

    spool, _, _ = _bundle(tmp_path)
    case = tmp_path / "case.json"
    result = CliRunner().invoke(
        episode_app,
        [
            "freeze-hooks",
            str(spool),
            "--store",
            str(tmp_path / "store"),
            "--output",
            str(case),
            "--allow-pass",
        ],
    )
    assert result.exit_code == 1 and "FAIL_CLOSED" in result.stdout
    assert not case.exists()


def test_task_lane_set_order_does_not_change_identity(tmp_path: Path) -> None:
    _, bundle, _ = _bundle(tmp_path)
    task_path = bundle / "task.json"
    task = json.loads(task_path.read_bytes())
    assert len(task["lane_support"]) > 1
    task["lane_support"].reverse()
    _write(task_path, encode(task))
    expected = _index(bundle)
    assert read_verified_hook_bundle(bundle, expected)["acceptance"] == "VERIFIED_FAIL"
    task["lane_support"] = ["M"]
    _write(task_path, encode(task))
    with pytest.raises(ReplayError, match="task package identity drift"):
        read_verified_hook_bundle(bundle, _index(bundle))


@pytest.mark.parametrize("mutation", ["missing-default", "coerced-budget", "duplicate-lane"])
def test_task_identity_only_ignores_lane_order(tmp_path: Path, mutation: str) -> None:
    _, bundle, _ = _passing_bundle(tmp_path)
    task_path = bundle / "task.json"
    task = json.loads(task_path.read_bytes())
    if mutation == "missing-default":
        task.pop("context_bundle")
    elif mutation == "coerced-budget":
        task["budget"]["timeout_seconds"] = str(task["budget"]["timeout_seconds"])
    else:
        task["lane_support"].append(task["lane_support"][0])
    _write(task_path, encode(task))
    with pytest.raises(ReplayError, match="task package identity drift"):
        read_verified_hook_bundle(bundle, _index(bundle))


@pytest.mark.parametrize(
    "mutation",
    ["zero-checks", "duplicate-checks", "contradictory-pass", "contradictory-score", "non-bool"],
)
def test_allow_pass_rejects_invalid_verifier_report(tmp_path: Path, mutation: str) -> None:
    spool, bundle, _ = _passing_bundle(tmp_path)
    report_path = bundle / "verifier-run/stdout.txt"
    report = json.loads(report_path.read_bytes())
    if mutation == "zero-checks":
        report["checks"] = []
    elif mutation == "duplicate-checks":
        report["checks"].append(report["checks"][0])
    elif mutation == "contradictory-pass":
        report["passed"] = False
    elif mutation == "contradictory-score":
        report["checks"][0]["score"] = 0.0
    else:
        report["checks"][0]["passed"] = "true"
    stdout = encode(report)
    _write(report_path, stdout)
    manifest_path = bundle / "verifier-run/manifest.json"
    manifest = json.loads(manifest_path.read_bytes())
    manifest["stdout"]["digest"] = manifest["stdout_stream_digest"] = sha256_bytes(stdout)
    _write(manifest_path, encode(manifest))
    case = tmp_path / "case.json"
    with pytest.raises(ReplayError):
        freeze_verified_hook_case(
            spool,
            tmp_path / "store",
            bundle,
            _index(bundle),
            case,
            source_kind="synthetic",
            allow_pass=True,
        )
    assert not case.exists()


@pytest.mark.parametrize(
    "mutation", ["workspace", "nonzero-exit", "lifecycle", "binding", "provenance", "episode-pass"]
)
def test_allow_pass_preserves_verification_bindings(tmp_path: Path, mutation: str) -> None:
    spool, bundle, _ = _passing_bundle(tmp_path)
    if mutation == "workspace":
        target = next((bundle / "verifier-run/workspace").rglob("*.py"))
        target.write_bytes(target.read_bytes() + b"\n# drift\n")
    else:
        filename = {
            "nonzero-exit": "verifier-run/manifest.json",
            "lifecycle": "verifier-lifecycle.json",
            "binding": "binding.json",
            "provenance": "episode.json",
            "episode-pass": "episode.json",
        }[mutation]
        target = bundle / filename
        data = json.loads(target.read_bytes())
        if mutation == "nonzero-exit":
            data["exit_code"] = 1
        elif mutation == "lifecycle":
            data["stages"] = []
        elif mutation == "binding":
            data["episode_identity"] = sha256_bytes(b"another-session")
        elif mutation == "provenance":
            data["source_authenticity"] = "ATTESTED"
        else:
            data["acceptance"] = "VERIFIED_PASS"
        _write(target, encode(data))
    case = tmp_path / "case.json"
    with pytest.raises(ValueError):
        freeze_verified_hook_case(
            spool,
            tmp_path / "store",
            bundle,
            _index(bundle),
            case,
            source_kind="synthetic",
            allow_pass=True,
        )
    assert not case.exists()


def test_allow_pass_rejects_verification_for_another_episode(tmp_path: Path) -> None:
    _, bundle, expected = _passing_bundle(tmp_path)
    other_spool = tmp_path / "other-hooks"
    for event in ("SessionStart", "PreToolUse", "PostToolUse", "Stop"):
        raw: dict[str, object] = {"hook_event_name": event, "session_id": "another-session"}
        if "ToolUse" in event:
            raw.update(tool_name="Bash", tool_use_id="another-call")
        receive_hook(
            encode(raw),
            "codex",
            other_spool,
        )
    case = tmp_path / "case.json"
    with pytest.raises(ReplayError, match="wrong session verification"):
        freeze_verified_hook_case(
            other_spool,
            tmp_path / "store",
            bundle,
            expected,
            case,
            source_kind="synthetic",
            allow_pass=True,
        )
    assert not case.exists()
