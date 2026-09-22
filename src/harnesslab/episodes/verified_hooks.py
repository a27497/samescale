"""Read and freeze independently verified Hook workspaces; never execute evidence."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from harnesslab.analyst.offline_replay import (
    _snapshot,
    decode,
    require,
    safe_path,
    tree_digest,
)
from harnesslab.episodes.hooks import (
    HookEpisode,
    _directory,
    _write_once,
    derive_episode,
    encode,
    import_hook_episode,
    normalized,
    read_events,
)
from harnesslab.episodes.service import SourceKind, _bounded_tree
from harnesslab.sandbox.models import (
    SandboxArtifactManifest,
    SandboxStatus,
    VerifierLifecycleDiagnostics,
    VerifierLifecycleStage,
    VerifierLifecycleStageStatus,
)
from harnesslab.tasks.models import VerifierReport
from harnesslab.tasks.package import TaskPackage, sha256_bytes


def read_verified_hook_bundle(root: Path, expected: str) -> dict[str, Any]:
    """An external digest pins the entire capture, task, workspace and verifier evidence."""
    before = _bounded_tree(root)
    bundle, files = _snapshot(root, expected)
    require(bundle.get("kind") == "verified-hook-workspace-v1", "unsupported verification bundle")
    require(
        {
            "episode.json",
            "normalized.json",
            "binding.json",
            "prior-capture-index.json",
            "prior-workspace-receipt.json",
            "task.json",
            "verifier-run/manifest.json",
            "verifier-run/stdout.txt",
            "verifier-run/stderr.txt",
            "verifier-lifecycle.json",
        }
        <= files.keys(),
        "missing verification evidence",
    )
    episode = HookEpisode.model_validate(decode(files["episode.json"]))
    events = read_events(root / "hooks")
    require(episode == derive_episode(events, episode.source_kind), "hook episode drift")
    require(
        files["normalized.json"] == (normalized(events).canonical_json() + "\n").encode(),
        "normalized trace drift",
    )
    binding = decode(files["binding.json"])
    require(binding["schema_version"] == 1, "unsupported binding")
    require(binding["episode_identity"] == episode.identity, "workspace/session binding drift")
    require(binding["agent_reexecuted"] is False, "not a passive observation")
    require(
        binding["binding_authority"] == "OPERATOR_RECORDED_NOT_ATTESTED", "binding authority drift"
    )
    prior = decode(files["prior-capture-index.json"])
    require(
        sha256_bytes(files["prior-capture-index.json"]) == binding["prior_capture_manifest_digest"],
        "prior capture digest drift",
    )
    for name, content in files.items():
        if name.startswith("hooks/"):
            require(sha256_bytes(content) == prior.get(name), "prior hook capture drift")
    require(
        sha256_bytes(files["prior-workspace-receipt.json"]) == prior.get("privacy.json")
        and decode(files["prior-workspace-receipt.json"]).get("fixture_unchanged") is True,
        "missing recorded final workspace binding",
    )
    source_files = binding["source_files"]
    require(isinstance(source_files, dict) and bool(source_files), "missing workspace inventory")
    actual = {
        name.removeprefix("final-workspace/")
        for name in files
        if name.startswith("final-workspace/")
    }
    require(actual == set(source_files), "workspace inventory drift")
    for name, digest in source_files.items():
        safe_path(root / "final-workspace", name)
        require(
            sha256_bytes(files["final-workspace/" + name])
            == digest
            == prior.get("fixture/" + name),
            "workspace differs from recorded final source",
        )
    task = decode(files["task.json"])
    package = TaskPackage.load(safe_path(root, f"task-package/{task['id']}/{task['version']}"))
    require(package.definition.model_dump(mode="json") == task, "task package identity drift")
    require(
        tree_digest(files, "verifier-source/") == package.verifier_digest, "verifier source drift"
    )
    workspace_digest = tree_digest(files, "final-workspace/")
    manifest = SandboxArtifactManifest.model_validate(decode(files["verifier-run/manifest.json"]))
    require(
        manifest.role == "verifier"
        and manifest.status is SandboxStatus.SUCCEEDED
        and manifest.exit_code == 0
        and not manifest.timed_out
        and not manifest.cancelled
        and manifest.cleanup_verified
        and not manifest.stdout_truncated
        and not manifest.stderr_truncated,
        "incomplete verifier process",
    )
    require(
        (manifest.task_id, manifest.task_version, manifest.task_digest)
        == (task["id"], task["version"], task["content_digest"]),
        "verifier task binding drift",
    )
    require(
        manifest.workspace_input_digest == manifest.workspace_output_digest == workspace_digest
        and tree_digest(files, "verifier-run/workspace/") == workspace_digest
        and manifest.workspace_snapshot is not None
        and manifest.workspace_snapshot.path == "workspace"
        and manifest.workspace_snapshot.digest == workspace_digest,
        "verifier workspace binding drift",
    )
    mounts = {m.destination: m for m in manifest.security.mounts}
    require(
        set(mounts) == {"/workspace", "/verifier"}
        and all(not m.read_write for m in mounts.values()),
        "verifier inputs must be read-only",
    )
    for name in ("stdout", "stderr"):
        artifact = getattr(manifest, name)
        require(artifact.path == name + ".txt", "invalid verifier stream path")
        require(
            sha256_bytes(files[f"verifier-run/{name}.txt"])
            == artifact.digest
            == getattr(manifest, name + "_stream_digest"),
            "verifier stream digest drift",
        )
    lifecycle = VerifierLifecycleDiagnostics.model_validate(
        decode(files["verifier-lifecycle.json"])
    )
    require(
        lifecycle.failure_subtype is None
        and all(s.status is VerifierLifecycleStageStatus.COMPLETED for s in lifecycle.stages)
        and {VerifierLifecycleStage.RESULT_COLLECT, VerifierLifecycleStage.STAGING_CLEANUP}
        <= {s.stage for s in lifecycle.stages},
        "incomplete verifier lifecycle",
    )
    raw = decode(files["verifier-run/stdout.txt"])
    require(type(raw.get("passed")) is bool, "invalid verifier outcome")
    require(isinstance(raw.get("checks"), list) and bool(raw["checks"]), "zero verifier checks")
    require(
        all(isinstance(c, dict) and type(c.get("passed")) is bool for c in raw["checks"]),
        "invalid check result",
    )
    report = VerifierReport.model_validate(raw)
    require(len({c.name for c in report.checks}) == len(report.checks), "duplicate checks")
    passed = all(c.passed for c in report.checks)
    require(
        report.passed is passed
        and all(c.score == float(c.passed) for c in report.checks)
        and report.score == sum(c.passed for c in report.checks) / len(report.checks),
        "contradictory verifier outcome",
    )
    require(_bounded_tree(root) == before, "verification bundle changed during read")
    return {
        "schema_version": 1,
        "namespace": "CUSTOM",
        "episode_identity": episode.identity,
        "trace_digest": episode.trace_digest,
        "workspace_digest": workspace_digest,
        "verifier_digest": package.verifier_digest,
        "task_digest": task["content_digest"],
        "report_digest": sha256_bytes(files["verifier-run/stdout.txt"]),
        "acceptance": "VERIFIED_PASS" if passed else "VERIFIED_FAIL",
        "checks": len(report.checks),
        "passed_checks": sum(c.passed for c in report.checks),
        "failed_checks": [c.name for c in report.checks if not c.passed],
        "authority": "L0_INDEPENDENT_VERIFIER",
        "root_cause": None,
        "category": "workspace_contract_failure" if not passed else None,
        "scope": "FINAL_WORKSPACE_CONTRACT_NOT_AGENT_INSTRUCTION_COMPLIANCE",
        "source_authenticity": "NOT_ATTESTED",
        "comparison_eligible": False,
    }


def freeze_verified_hook_case(
    spool: Path,
    store: Path,
    bundle: Path,
    expected: str,
    destination: Path,
    *,
    source_kind: SourceKind,
) -> str:
    episode = import_hook_episode(spool, store, source_kind=source_kind)
    result = read_verified_hook_bundle(bundle, expected)
    require(result["episode_identity"] == episode.identity, "wrong session verification")
    require(result["acceptance"] == "VERIFIED_FAIL", "passing workspace is not a Bad Case")
    relative = bundle.resolve().relative_to(destination.parent.resolve()).as_posix()
    safe_path(destination.parent, relative)
    require(
        not destination.resolve().is_relative_to(bundle.resolve()), "case must be outside bundle"
    )
    case = {
        "schema_version": 1,
        "kind": "verified-hook-regression-v1",
        "verification": {"path": relative, "sha256": expected},
        "bad_case": result,
    }
    _directory(destination.parent)
    _write_once(destination, encode(case))
    return sha256_bytes(encode(case))


def replay_verified_hook_case(path: Path, expected: str, case: dict[str, Any]) -> dict[str, Any]:
    require(
        set(case) == {"schema_version", "kind", "verification", "bad_case"}, "invalid case schema"
    )
    require(case["schema_version"] == 1, "unsupported verified case version")
    reference = case["verification"]
    require(set(reference) == {"path", "sha256"}, "invalid verification reference")
    result = read_verified_hook_bundle(
        safe_path(path.parent, reference["path"]), reference["sha256"]
    )
    require(result["acceptance"] == "VERIFIED_FAIL", "passing workspace is not a Bad Case")
    require(result == case["bad_case"], "verified attribution replay drift")
    return {
        "status": "PASS",
        "case_digest": expected,
        "episode_identity": result["episode_identity"],
        "acceptance": result["acceptance"],
        "bad_case": result,
        "external_calls": 0,
        "subject_executed": False,
        "verifier_executed": False,
    }
