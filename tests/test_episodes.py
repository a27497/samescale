from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from harnesslab.episodes.cli import episode_app
from harnesslab.episodes.service import EpisodeImportError, import_codex_episode, inspect_episode
from harnesslab.harness_lane.models import (
    CodexProcessCapture,
    HarnessFailureCategory,
    HarnessLaneEvidence,
    HarnessLaneOutcome,
)
from harnesslab.harness_lane.profile import canonical_codex_profile
from harnesslab.harness_lane.trace import collect_codex_jsonl
from harnesslab.sandbox.models import ImageIdentity, SandboxArtifactManifest
from harnesslab.tasks.package import TaskPackage, digest_tree, sha256_bytes

ROOT = Path(__file__).resolve().parents[1]
PRIVATE = "private-content-that-must-not-be-copied"


def put(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True, separators=(",", ":")))


@pytest.fixture
def source(tmp_path: Path) -> Path:
    root = tmp_path / "source"
    root.mkdir()
    package = TaskPackage.load(ROOT / "tasks/micro-python-clamp/1.0.0")
    shutil.copytree(package.root / "workspace", root / "workspace")
    trace = collect_codex_jsonl(
        CodexProcessCapture(
            tuple(
                json.dumps(event)
                for event in [
                    {"type": "thread.started", "thread_id": "synthetic-thread"},
                    {
                        "type": "item.completed",
                        "item": {"id": "message", "type": "agent_message", "text": PRIVATE},
                    },
                    {
                        "type": "item.completed",
                        "item": {"id": "reasoning", "type": "reasoning", "text": PRIVATE},
                    },
                    {
                        "type": "item.completed",
                        "item": {
                            "id": "cmd",
                            "type": "command_execution",
                            "command": PRIVATE,
                            "aggregated_output": PRIVATE,
                            "exit_code": 1,
                        },
                    },
                    {"type": "turn.failed", "error": {"message": "failure"}},
                ]
            ),
            0,
            123,
        )
    )
    (root / "trace").mkdir()
    (root / "trace/normalized.json").write_text(trace.trace.canonical_json())
    (root / "native").mkdir()
    (root / "native/codex.sanitized.jsonl").write_text(trace.sanitized_jsonl)
    profile = canonical_codex_profile(
        ImageIdentity(reference="synthetic", image_id="sha256:" + "1" * 64)
    )
    evidence = HarnessLaneEvidence(
        run_id="synthetic-episode",
        task_id=package.definition.id,
        task_version=package.definition.version,
        task_digest=package.definition.content_digest,
        verifier_definition_digest=package.verifier_digest,
        resource_budget=package.definition.budget,
        workspace_input_digest=digest_tree(root / "workspace"),
        workspace_output_digest=digest_tree(root / "workspace"),
        changed_paths=(),
        prompt_template_version="synthetic-v1",
        prompt_hash="sha256:" + "2" * 64,
        profile=profile,
        profile_hash=profile.fingerprint,
        requested_model=profile.requested_model,
        observed_model_status=trace.observed_model_status,
        provider_route=profile.provider_route,
        native_transcript_digest=trace.native_digest,
        normalized_trace_digest=trace.trace_digest,
        trace_event_count=len(trace.trace.events),
        trace_event_types=tuple(e.type for e in trace.trace.events),
        process_exit_code=0,
        duration_ms=123,
        outcome=HarnessLaneOutcome.HARNESS_ERROR,
        harness_failure=HarnessFailureCategory.MODEL_TURN_FAILED,
        summary="Agent says done",
    )
    (root / "manifest.json").write_text(evidence.canonical_json())
    return root


def verified(source: Path) -> None:
    """Create explicit synthetic L0 evidence; never relabel it as a live model result."""
    raw = json.loads((source / "manifest.json").read_text())
    verifier = source / "verifier"
    shutil.copytree(source / "workspace", verifier / "workspace")
    put(
        verifier / "stdout.txt",
        {
            "schema_version": 1,
            "passed": False,
            "score": 0.0,
            "checks": [{"name": "contract", "passed": False, "score": 0.0}],
            "summary": "FAIL",
        },
    )
    (verifier / "stderr.txt").write_text("")
    security = {
        "privileged": False,
        "read_only_rootfs": True,
        "cap_drop": ["ALL"],
        "security_options": ["no-new-privileges=true"],
        "network_mode": "none",
        "memory_bytes": 134217728,
        "nano_cpus": 500000000,
        "pids_limit": 64,
        "restart_policy": "no",
        "user": "10001:10001",
        "pid_mode": "",
        "published_ports": False,
        "device_count": 0,
        "mounts": [],
        "tmpfs_destinations": ["/tmp"],
        "docker_socket_mounted": False,
        "seccomp_unconfined": False,
    }
    manifest = SandboxArtifactManifest.model_validate(
        {
            "schema_version": 1,
            "run_id": "synthetic-verifier",
            "role": "verifier",
            **{
                k: raw[k]
                for k in (
                    "task_id",
                    "task_version",
                    "task_digest",
                    "workspace_input_digest",
                    "workspace_output_digest",
                )
            },
            "image": {"reference": "synthetic", "image_id": "sha256:" + "1" * 64},
            "security": security,
            "status": "succeeded",
            "exit_code": 0,
            "duration_ms": 1,
            "timed_out": False,
            "cancelled": False,
            "cleanup_verified": True,
            "stdout_stream_digest": sha256_bytes((verifier / "stdout.txt").read_bytes()),
            "stderr_stream_digest": sha256_bytes(b""),
            "stdout_truncated": False,
            "stderr_truncated": False,
            "stdout": {
                "path": "stdout.txt",
                "digest": sha256_bytes((verifier / "stdout.txt").read_bytes()),
            },
            "stderr": {"path": "stderr.txt", "digest": sha256_bytes(b"")},
            "workspace_snapshot": {"path": "workspace", "digest": raw["workspace_output_digest"]},
            "summary": "synthetic verifier",
        }
    )
    (verifier / "manifest.json").write_text(manifest.canonical_json())
    raw.update(
        outcome="verified_fail",
        harness_failure=None,
        verifier_passed=False,
        verifier_score=0.0,
        verifier_sandbox_manifest=manifest.model_dump(mode="json"),
        verifier_artifact_namespace="verifier",
        verifier_artifact_digest=digest_tree(verifier),
    )
    put(source / "manifest.json", raw)


def test_metadata_only_idempotent_and_unknown_cost(source: Path, tmp_path: Path) -> None:
    before = digest_tree(source)
    store = tmp_path / "episodes"
    episode = import_codex_episode(source, store, source_kind="synthetic")
    assert episode.acceptance == "NOT_VERIFIED"
    assert episode.cost_usd is None and episode.input_tokens is None
    assert episode.failed_commands == 1
    assert not episode.comparison_eligible and not episode.execution_authorized
    assert episode.source_authenticity == "NOT_ATTESTED"
    assert import_codex_episode(source, store, source_kind="synthetic") == episode
    saved = next(store.glob("*.json"))
    assert PRIVATE not in saved.read_text()
    assert inspect_episode(saved) == episode
    assert digest_tree(source) == before
    assert len(list(store.iterdir())) == 1


def test_recorded_verifier_fail_is_not_inferred_from_agent(source: Path, tmp_path: Path) -> None:
    verified(source)
    episode = import_codex_episode(source, tmp_path / "store", source_kind="synthetic")
    assert episode.acceptance == "RECORDED_FAIL"
    assert episode.verifier_check_count == 1


@pytest.mark.parametrize(
    "file", ["trace/normalized.json", "native/codex.sanitized.jsonl", "workspace/calculator.py"]
)
def test_tampered_input_rejected(source: Path, tmp_path: Path, file: str) -> None:
    with (source / file).open("a") as stream:
        stream.write(" ")
    with pytest.raises(EpisodeImportError):
        import_codex_episode(source, tmp_path / "store", source_kind="synthetic")
    assert not (tmp_path / "store").exists()


def test_missing_verifier_fails_closed(source: Path, tmp_path: Path) -> None:
    verified(source)
    (source / "verifier/stdout.txt").unlink()
    with pytest.raises(EpisodeImportError):
        import_codex_episode(source, tmp_path / "store", source_kind="synthetic")


def test_duplicate_json_and_symlinks_rejected(source: Path, tmp_path: Path) -> None:
    original = (source / "manifest.json").read_text()
    (source / "manifest.json").write_text(original[:-1] + ',"schema_version":1}')
    with pytest.raises(EpisodeImportError, match="Duplicate"):
        import_codex_episode(source, tmp_path / "store", source_kind="synthetic")
    (source / "manifest.json").write_text(original)
    (source / "escape").symlink_to(tmp_path)
    with pytest.raises(EpisodeImportError, match="Links"):
        import_codex_episode(source, tmp_path / "store", source_kind="synthetic")


def test_store_overlap_and_stored_tamper_rejected(source: Path, tmp_path: Path) -> None:
    with pytest.raises(EpisodeImportError, match="overlap"):
        import_codex_episode(source, source / "episodes", source_kind="synthetic")
    store = tmp_path / "store"
    import_codex_episode(source, store, source_kind="synthetic")
    path = next(store.glob("*.json"))
    raw = json.loads(path.read_text())
    raw["duration_ms"] = 999
    put(path, raw)
    with pytest.raises(EpisodeImportError, match="identity"):
        inspect_episode(path)
    with pytest.raises(EpisodeImportError, match="collision"):
        import_codex_episode(source, store, source_kind="synthetic")


def test_cli_import_and_inspect(source: Path, tmp_path: Path) -> None:
    runner = CliRunner()
    store = tmp_path / "store"
    result = runner.invoke(episode_app, ["import-codex", str(source), "--store", str(store)])
    assert result.exit_code == 0, result.output
    assert '"source_kind":"unverified"' in result.output
    assert runner.invoke(episode_app, ["inspect", str(next(store.glob("*.json")))]).exit_code == 0
    bad = runner.invoke(episode_app, ["import-codex", str(tmp_path / "absent")])
    assert bad.exit_code == 1


def test_official_store_rejected(source: Path) -> None:
    with pytest.raises(EpisodeImportError, match="Official"):
        import_codex_episode(source, ROOT / "tasks/episodes", source_kind="synthetic")


def test_verifier_task_cannot_be_substituted(source: Path, tmp_path: Path) -> None:
    verified(source)
    raw = json.loads((source / "manifest.json").read_text())
    raw["verifier_sandbox_manifest"]["task_id"] = "unrelated-task"
    put(source / "verifier/manifest.json", raw["verifier_sandbox_manifest"])
    raw["verifier_artifact_digest"] = digest_tree(source / "verifier")
    put(source / "manifest.json", raw)
    with pytest.raises(EpisodeImportError, match="task identity"):
        import_codex_episode(source, tmp_path / "store", source_kind="synthetic")


def test_verified_record_requires_final_workspace(source: Path, tmp_path: Path) -> None:
    verified(source)
    shutil.rmtree(source / "workspace")
    with pytest.raises(EpisodeImportError, match="final workspace"):
        import_codex_episode(source, tmp_path / "store", source_kind="synthetic")


@pytest.mark.parametrize("agree_with_manifest", [False, True])
def test_contradictory_pass_rejected(
    source: Path, tmp_path: Path, agree_with_manifest: bool
) -> None:
    verified(source)
    raw = json.loads((source / "manifest.json").read_text())
    report_path = source / "verifier/stdout.txt"
    report = json.loads(report_path.read_text())
    report["passed"] = True  # Individual checks still fail.
    put(report_path, report)
    manifest = raw["verifier_sandbox_manifest"]
    manifest["stdout"]["digest"] = sha256_bytes(report_path.read_bytes())
    manifest["stdout_stream_digest"] = manifest["stdout"]["digest"]
    put(source / "verifier/manifest.json", manifest)
    raw["verifier_artifact_digest"] = digest_tree(source / "verifier")
    if agree_with_manifest:
        raw["verifier_passed"] = True
        raw["outcome"] = "verified_pass"
    put(source / "manifest.json", raw)
    with pytest.raises(EpisodeImportError, match=r"outcome mismatch|failed checks"):
        import_codex_episode(source, tmp_path / "store", source_kind="synthetic")


@pytest.mark.parametrize(
    "incomplete",
    [None, "infra_error", "timed_out", "cancelled", "stdout_truncated"],
)
def test_recorded_pass_requires_complete_verifier_execution(
    source: Path, tmp_path: Path, incomplete: str | None
) -> None:
    verified(source)
    raw = json.loads((source / "manifest.json").read_text())
    report_path = source / "verifier/stdout.txt"
    put(
        report_path,
        {
            "schema_version": 1,
            "passed": True,
            "score": 1.0,
            "checks": [{"name": "contract", "passed": True, "score": 1.0}],
            "summary": "Synthetic pass",
        },
    )
    manifest = raw["verifier_sandbox_manifest"]
    manifest["stdout"]["digest"] = sha256_bytes(report_path.read_bytes())
    manifest["stdout_stream_digest"] = manifest["stdout"]["digest"]
    if incomplete not in (None, "infra_error"):
        manifest[incomplete] = True
    put(source / "verifier/manifest.json", manifest)
    raw.update(
        outcome="infra_error" if incomplete == "infra_error" else "verified_pass",
        verifier_passed=True,
        verifier_score=1.0,
        verifier_artifact_digest=digest_tree(source / "verifier"),
    )
    put(source / "manifest.json", raw)
    store = tmp_path / "store"
    if incomplete is None:
        episode = import_codex_episode(source, store, source_kind="synthetic")
        assert episode.acceptance == "RECORDED_PASS"
        assert episode.verifier_check_count == 1
    else:
        with pytest.raises(EpisodeImportError, match=r"Recorded acceptance|Verifier process"):
            import_codex_episode(source, store, source_kind="synthetic")
        assert not store.exists()
