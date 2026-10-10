"""Private data-only import, bounded safe snapshots and deterministic evidence diagnosis.

The operator pins individual sources, not a session discovery directory. Raw sessions,
reasoning, prompts, command output, hidden verifier source and auth are never copied.
The filesystem store extends the existing content-addressed Episode pattern, without DB changes.
"""

from __future__ import annotations

import base64
import fcntl
import os
import re
import stat
import tempfile
from pathlib import Path
from typing import Any

from harnesslab.analyst.offline_replay import decode, require
from harnesslab.episodes.hooks import _write_once, derive_episode, encode, normalized, read_events
from harnesslab.episodes.service import read_codex_episode
from harnesslab.episodes.verified_hooks import read_verified_hook_bundle
from harnesslab.external_evidence.models import ApprovedSource, EvidencePolicy, ExternalRecord
from harnesslab.harness_lane.models import (
    HarnessLaneEvidence,
    NormalizedTrace,
    NormalizedTraceEvent,
    TraceEventType,
)
from harnesslab.harness_lane.trace import _normalized_trace, _sanitize_event
from harnesslab.local_plans.tasks import bounded_files, fail, no_links, read_owned_json
from harnesslab.productization.assets import distribution_root
from harnesslab.registry.models import canonical_digest
from harnesslab.tasks.models import validate_relative_path
from harnesslab.tasks.package import digest_tree, sha256_bytes

MAX_EXPORT = 12_000_000
PRIVATE_PARTS = {".codex", ".ssh", ".git", ".aws", ".config", "oracle", "verifier"}
PRIVATE_NAMES = {"auth.json", "credentials.json", "id_rsa", "id_ed25519"}
SECRET = re.compile(
    rb"-----BEGIN [A-Z ]*PRIVATE KEY-----|\b(?:sk-|ghp_|github_pat_)[A-Za-z0-9_-]{16,}"
    rb"|\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"
    rb"|(?i:authorization\s*[:=]\s*bearer\s+\S+|"
    rb"(?:access_token|refresh_token|api_key|password|secret)\s*[\"']?\s*[:=]\s*[\"']?[^\s\"']{8,})"
)


def safe_name(name: str) -> None:
    validate_relative_path(name)
    parts = Path(name).parts
    if (
        "\\" in name
        or ":" in name
        or any(p.lower() in PRIVATE_PARTS | PRIVATE_NAMES or p.startswith(".env") for p in parts)
        or any(ord(c) < 32 for c in name)
        or len(name) > 240
        or SECRET.search(name.encode())
    ):
        raise ValueError("private or unsafe snapshot name")


def safe_content(data: bytes) -> None:
    # MVP accepts reviewed UTF-8 source snapshots only; it does not claim universal DLP.
    data.decode("utf-8")
    if b"\x00" in data or SECRET.search(data):
        raise ValueError("private or unsupported snapshot content")


def safe_root(path: Path) -> None:
    no_links(path)
    if (
        path == Path("/")
        or path == Path.home()
        or any(p.lower() in PRIVATE_PARTS | PRIVATE_NAMES for p in path.parts)
    ):
        raise ValueError("credential/session roots are forbidden")


def overlap(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def load_policy() -> EvidencePolicy:
    try:
        path = Path(os.environ["HARNESSLAB_EXTERNAL_EVIDENCE_POLICY"])
        policy = EvidencePolicy.model_validate(read_owned_json(path))
        safe_root(policy.store)
        if overlap(policy.store, distribution_root()) or overlap(policy.store, path):
            raise ValueError("protected storage")
        if len({s.source_id for s in policy.sources}) != len(policy.sources):
            raise ValueError("duplicate source")
        roots = [policy.store]
        for root in (policy.runtime_root, policy.artifact_root):
            if root is not None:
                safe_root(root)
                if overlap(root, distribution_root()) or any(overlap(root, r) for r in roots):
                    raise ValueError("overlapping verifier storage")
                roots.append(root)
        for source in policy.sources:
            for root in (source.path, source.workspace):
                safe_root(root)
                if any(overlap(root, r) for r in roots) or overlap(root, path):
                    raise ValueError("source/storage/policy overlap")
            if (source.task_reference is None) != (source.task_digest is None):
                raise ValueError("incomplete task mapping")
        # Reject links/special files before reading stored content on every request.
        if policy.store.exists():
            info = policy.store.stat()
            if info.st_uid != os.getuid() or info.st_mode & 0o077:
                raise ValueError("evidence store must be private and owned")
            bounded_files(policy.store, max_files=20_000, max_bytes=128_000_000)
        return policy
    except (KeyError, OSError, ValueError):
        raise fail(
            "EXTERNAL_EVIDENCE_DISABLED", "Configure a separate owned evidence policy.", 403
        ) from None


def workspace_files(root: Path) -> dict[str, bytes]:
    safe_root(root)
    bounded_files(root, max_files=500, max_bytes=4_000_000)
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            name = path.relative_to(root).as_posix()
            safe_name(name)
            content = path.read_bytes()
            safe_content(content)
            result[name] = content
    require(bool(result), "empty final workspace")
    return result


def content_digest(files: dict[str, bytes]) -> str:
    # Same canonical tree algorithm as TaskStore/Workspace/Verifier; no path materialization.
    import hashlib

    digest = hashlib.sha256()
    for name, data in sorted(files.items()):
        relative = name.encode()
        digest.update(len(relative).to_bytes(8, "big") + relative)
        digest.update(len(data).to_bytes(8, "big") + data)
    return "sha256:" + digest.hexdigest()


def trace_projection(trace: NormalizedTrace) -> tuple[dict[str, Any], ...]:
    require(len(trace.events) <= 4096, "oversized trace")
    result = []
    for event in trace.events:
        # Deliberately drop free text, reasoning, raw output, IDs and command strings.
        paths = []
        for change in event.file_changes:
            try:
                safe_name(change.path)
                paths.append(change.path)
            except ValueError:
                pass
        result.append(
            {
                "ordinal": event.ordinal,
                "type": event.type.value,
                "exit_code": event.exit_code,
                "status": event.status
                if event.status in {"observed", "failed", "completed", "in_progress"}
                else "UNKNOWN",
                "command_digest": sha256_bytes(event.command.encode()) if event.command else None,
                "call_identity": canonical_digest(event.item_id) if event.item_id else None,
                "file_paths": paths,
                "agent_report": "SELF_REPORT_NOT_ACCEPTANCE"
                if event.type is TraceEventType.AGENT_MESSAGE
                else None,
            }
        )
    return tuple(result)


def unknown_verification(reason: str = "TRUSTED_TASK_OR_VERIFIER_MISSING") -> dict[str, Any]:
    return {"acceptance": "NOT_VERIFIED", "checks": 0, "passed_checks": 0, "reason": reason}


def snapshot(root: Path, destination: Path, *, max_bytes: int = 32_000_000) -> None:
    """Open every ancestor/file without following links, including concurrent substitutions."""
    safe_root(root)
    count = total = nodes = 0
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in root.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child

        def copy(directory: int, target: Path, depth: int = 0) -> None:
            nonlocal count, total, nodes
            require(depth <= 20, "source depth limit")
            target.mkdir(mode=0o700)
            names = os.listdir(directory)
            require(len(names) <= 4000, "directory entry limit")
            for name in sorted(names):
                nodes += 1
                require(nodes <= 4000, "source node limit")
                require(
                    name.lower() not in PRIVATE_NAMES | {".codex", ".ssh", ".git", ".aws"}
                    and not name.startswith(".env")
                    and not name.startswith("rollout-"),
                    "private acquisition asset",
                )
                info = os.stat(name, dir_fd=directory, follow_symlinks=False)
                require(
                    stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode), "unsafe source node"
                )
                child = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
                try:
                    opened = os.fstat(child)
                    require(
                        (opened.st_dev, opened.st_ino) == (info.st_dev, info.st_ino),
                        "source substituted",
                    )
                    if stat.S_ISDIR(opened.st_mode):
                        copy(child, target / name, depth + 1)
                    else:
                        count += 1
                        total += opened.st_size
                        require(
                            opened.st_nlink == 1
                            and opened.st_size <= 8_000_000
                            and count <= 4000
                            and total <= max_bytes,
                            "source size/link limit",
                        )
                        with os.fdopen(os.dup(child), "rb") as stream:
                            data = stream.read(opened.st_size + 1)
                        after = os.fstat(child)
                        require(
                            len(data) == opened.st_size
                            and after.st_mtime_ns == opened.st_mtime_ns
                            and after.st_size == opened.st_size,
                            "source changed during capture",
                        )
                        require(not SECRET.search(data), "credential-shaped source content")
                        _write_once(target / name, data)
                finally:
                    os.close(child)

        copy(fd, destination)
    finally:
        os.close(fd)


def read_jsonl(source: ApprovedSource) -> NormalizedTrace:
    """Explicitly supplied exec --json stream; no rollout/session discovery or raw writes."""
    safe_root(source.path)
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in source.path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
        require(set(os.listdir(fd)) == {"events.jsonl"}, "review one saved exec JSONL file only")
        stream_fd = os.open("events.jsonl", os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            info = os.fstat(stream_fd)
            require(
                stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= 4_000_000,
                "unsafe JSONL source",
            )
            with os.fdopen(os.dup(stream_fd), "rb") as stream:
                data = stream.read(info.st_size + 1)
            after = os.fstat(stream_fd)
            require(
                len(data) == info.st_size
                and after.st_mtime_ns == info.st_mtime_ns
                and content_digest({"events.jsonl": data}) == source.digest,
                "saved JSONL pin or capture mismatch",
            )
        finally:
            os.close(stream_fd)
    finally:
        os.close(fd)
    lines = data.splitlines()
    require(0 < len(lines) <= 4096, "JSONL event limit")
    events = []
    for ordinal, line in enumerate(lines, 1):
        require(len(line) <= 1_000_000, "JSONL line limit")
        raw = decode(line)
        require(
            raw.get("type")
            in {
                "thread.started",
                "turn.started",
                "turn.completed",
                "turn.failed",
                "item.started",
                "item.updated",
                "item.completed",
                "error",
            },
            "unsupported saved exec protocol",
        )
        item = raw.get("item", {})
        require(isinstance(item, dict), "invalid item envelope")
        # Drop free text/output/usage/diagnostics before any write, reuse existing normalization.
        safe = {
            "type": raw["type"],
            "item": {
                k: v
                for k, v in item.items()
                if k in {"type", "id", "status", "command", "exit_code", "changes"}
            },
        }
        events.append(_sanitize_event(safe, ordinal, ()))
    return _normalized_trace(tuple(events))


def project(source: ApprovedSource) -> tuple[ExternalRecord, dict[str, bytes]]:
    # Freeze bounded bytes first; legacy validators never traverse a live untrusted tree.
    with tempfile.TemporaryDirectory(prefix="samescale-evidence-read-") as temporary:
        private = Path(temporary)
        native_trace = read_jsonl(source) if source.format == "codex-jsonl-v1" else None
        if native_trace is None:
            snapshot(source.path, private / "source")
        snapshot(source.workspace, private / "workspace", max_bytes=4_000_000)
        copy = source.model_copy(
            update={"path": private / "source", "workspace": private / "workspace"}
        )
        return _project_snapshot(copy, native_trace)


def _project_snapshot(
    source: ApprovedSource, native_trace: NormalizedTrace | None = None
) -> tuple[ExternalRecord, dict[str, bytes]]:
    # Validate structural safety before legacy readers hash or parse any approved artifact.
    if native_trace is None:
        bounded_files(source.path, max_files=4000, max_bytes=32_000_000)
    files = workspace_files(source.workspace)
    require(content_digest(files) == source.workspace_digest, "workspace pin mismatch")
    verification = unknown_verification()
    changes: dict[str, Any] = {"status": "BASELINE_MISSING", "paths": []}
    infrastructure: dict[str, Any] = {"status": "UNKNOWN", "root_cause": None}
    missing = [
        "actual_model",
        "provider_route",
        "request_count",
        "usage",
        "cost",
        "wall_clock_order",
    ]
    if source.format == "codex-jsonl-v1":
        assert native_trace is not None
        trace = native_trace
        original_kind = source.source_kind
        original = "NOT_VERIFIED"
        episode_id = None
        coverage = "SUPPLIED_EXEC_JSONL_ONLY"
        missing.extend(["process_exit_code", "trusted_task_contract", "independent_verifier"])
        if not any(
            e.type in {TraceEventType.TURN_COMPLETED, TraceEventType.TURN_FAILED}
            for e in trace.events
        ):
            missing.append("native_completion")
        if any(e.type in {TraceEventType.ERROR, TraceEventType.TURN_FAILED} for e in trace.events):
            infrastructure = {"status": "RECORDED_TURN_OR_STREAM_FAILURE", "root_cause": None}
    elif source.format == "verified-hook-v1":
        verification = read_verified_hook_bundle(source.path, source.digest)
        require(
            verification["workspace_digest"] == source.workspace_digest,
            "verifier workspace mismatch",
        )
        # Free-form hidden check names never leave the trusted verifier reader.
        verification = {
            **verification,
            "failed_checks": [canonical_digest(name) for name in verification["failed_checks"]],
        }
        events = read_events(source.path / "hooks")
        raw = decode((source.path / "episode.json").read_bytes())
        original_kind = raw["source_kind"]
        require(
            original_kind != "synthetic" or source.source_kind == "synthetic", "fixture relabeling"
        )
        episode = derive_episode(events, original_kind)
        trace = normalized(events)
        task = decode((source.path / "task.json").read_bytes())
        baseline = source.path / "task-package" / task["id"] / task["version"] / "workspace"
        baseline_files = workspace_files(baseline)
        changes = {
            "status": "DIGEST_BOUND_BASELINE",
            "paths": sorted(
                p
                for p in files.keys() | baseline_files.keys()
                if files.get(p) != baseline_files.get(p)
            ),
        }
        original = "NOT_VERIFIED"
        episode_id = episode.identity
        coverage = "PAIRED_HOOKS_ONLY"
    elif source.format == "native-hook-v1":
        original_kind = source.source_kind
        require(digest_tree(source.path) == source.digest, "hook pin mismatch")
        events = read_events(source.path)
        require(len({(e.source, e.session) for e in events}) == 1, "mixed hook sessions")
        try:
            episode = derive_episode(events, source.source_kind)
            trace = normalized(events)
            episode_id = episode.identity
            coverage = "PAIRED_HOOKS_ONLY"
        except ValueError:
            # Keep partial observations, without fabricating a valid original Episode.
            episode_id = None
            coverage = "INCOMPLETE_HOOKS"
            missing.append("paired_hook_lifecycle")
            trace = NormalizedTrace(
                events=tuple(
                    NormalizedTraceEvent(
                        ordinal=i,
                        type=TraceEventType.UNKNOWN,
                        native_event_type="hook." + e.event,
                        exit_code=e.exit_code,
                        status="failed" if e.failure else "observed",
                    )
                    for i, e in enumerate(sorted(events, key=lambda e: e.key), 1)
                )
            )
        original = "NOT_VERIFIED"
    else:
        original_kind = source.source_kind
        episode_record = read_codex_episode(source.path, source_kind=source.source_kind)
        require(episode_record.source_bundle_digest == source.digest, "H-Lane pin mismatch")
        require(
            episode_record.workspace_output_digest == source.workspace_digest,
            "H-Lane workspace mismatch",
        )
        trace = NormalizedTrace.model_validate(
            decode((source.path / "trace/normalized.json").read_bytes())
        )
        evidence = HarnessLaneEvidence.model_validate(
            decode((source.path / "manifest.json").read_bytes())
        )
        original = episode_record.acceptance
        require(
            original == "NOT_VERIFIED" or episode_record.verifier_check_count > 0,
            "zero collected verifier checks",
        )
        episode_id = episode_record.identity
        coverage = "RECORDED_H_LANE"
        changes = {"status": "SOURCE_REPORTED_NOT_DIFF_RECONSTRUCTED", "paths": []}
        for name in evidence.changed_paths:
            safe_name(name.path)
            changes["paths"].append(name.path)
        infrastructure = {
            "status": evidence.harness_failure.value
            if evidence.harness_failure
            else "NO_RECORDED_FAILURE",
            "timed_out": evidence.timed_out,
            "root_cause": None,
        }
        # A legacy report is kept separate; do not elevate it to the strict hook reader's L0.
        verification = unknown_verification(
            "RECORDED_RESULT_ONLY_REQUIRES_TRUSTED_INDEPENDENT_ADMISSION"
        )
        verification["task_digest"] = episode_record.task_digest
    projected = trace_projection(trace)
    missing.extend(
        ["tool_exit_codes"]
        if any(e["exit_code"] is None for e in projected if e["type"] == "COMMAND_EXECUTION")
        else []
    )
    record = ExternalRecord(
        source=source.binding,
        original_source_kind=original_kind,
        episode_identity=episode_id,
        original_acceptance=original,
        workspace_digest=source.workspace_digest,
        workspace_files={p: sha256_bytes(data) for p, data in files.items()},
        trace=projected,
        completeness={
            "status": "PARTIAL",
            "coverage": coverage,
            "missing_fields": missing,
            "integrity": "PINNED_BYTES_VERIFIED",
            "origin": "NOT_ATTESTED",
        },
        file_changes=changes,
        recorded_verification=verification,
        infrastructure=infrastructure,
    )
    # Refuse moving sources before committing the projected snapshot.
    require(workspace_files(source.workspace) == files, "workspace changed during import")
    if source.format == "codex-jsonl-v1":
        pass  # Raw stream was pinned in memory; no raw snapshot exists.
    elif source.format != "verified-hook-v1":
        require(digest_tree(source.path) == source.digest, "source changed during import")
    else:
        repeated = read_verified_hook_bundle(source.path, source.digest)
        repeated["failed_checks"] = [canonical_digest(name) for name in repeated["failed_checks"]]
        require(repeated == verification, "source changed during import")
    return record, files


def record_root(policy: EvidencePolicy, identity: str) -> Path:
    require(bool(re.fullmatch(r"[a-f0-9]{64}", identity)), "invalid record identity")
    root = policy.store / identity
    no_links(root)
    return root


def ingest(policy: EvidencePolicy, source_id: str) -> dict[str, Any]:
    source = next((s for s in policy.sources if s.source_id == source_id), None)
    require(source is not None, "source not approved")
    assert source is not None
    record, files = project(source)
    policy.store.mkdir(parents=True, exist_ok=True, mode=0o700)
    with (policy.store / ".lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        root = record_root(policy, record.identity[7:])
        if not root.exists():
            with tempfile.TemporaryDirectory(dir=policy.store, prefix=".import-") as temporary:
                staging = Path(temporary) / "record"
                staging.mkdir(mode=0o700)
                _write_once(staging / "record.json", encode(record.model_dump(mode="json")))
                for name, data in files.items():
                    destination = staging / "workspace" / name
                    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    _write_once(destination, data)
                os.rename(staging, root)
    return view(policy, record.identity[7:])


def read_record(policy: EvidencePolicy, identity: str) -> ExternalRecord:
    root = record_root(policy, identity)
    bounded_files(root, max_files=510, max_bytes=8_000_000)
    path = root / "record.json"
    require(path.stat().st_size <= 4_000_000, "oversized record")
    record = ExternalRecord.model_validate(decode(path.read_bytes()))
    require(record.identity[7:] == identity, "record identity drift")
    files = workspace_files(root / "workspace")
    require(content_digest(files) == record.workspace_digest, "stored workspace drift")
    require(
        {p: sha256_bytes(data) for p, data in files.items()} == record.workspace_files,
        "inventory drift",
    )
    return record


def verification_receipt(policy: EvidencePolicy, identity: str) -> dict[str, Any] | None:
    path = record_root(policy, identity) / "verification.json"
    if not path.exists():
        return None
    raw = decode(path.read_bytes())
    require(
        raw.get("receipt_digest")
        == canonical_digest({k: v for k, v in raw.items() if k != "receipt_digest"}),
        "verification receipt drift",
    )
    require(raw.get("record_identity") == "sha256:" + identity, "wrong verification record")
    record = read_record(policy, identity)
    require(raw.get("workspace_digest") == record.workspace_digest, "wrong verification workspace")
    validate_verification(raw)
    return raw


def validate_verification(result: dict[str, Any]) -> None:
    acceptance, checks, passed = (
        result.get("acceptance"),
        result.get("checks"),
        result.get("passed_checks"),
    )
    require(acceptance in {"NOT_VERIFIED", "VERIFIED_PASS", "VERIFIED_FAIL"}, "invalid acceptance")
    require(type(checks) is int and type(passed) is int, "invalid collected check counts")
    assert isinstance(checks, int) and isinstance(passed, int)
    require(0 <= passed <= checks <= 10000, "invalid collected check counts")
    if acceptance == "NOT_VERIFIED":
        require(checks == passed == 0, "unknown result contains acceptance checks")
    else:
        require(
            checks > 0 and (acceptance == "VERIFIED_PASS") == (checks == passed),
            "zero or contradictory independent checks",
        )
    if "check_results" in result:
        items = result["check_results"]
        require(
            len(items) == checks and all(type(c.get("passed")) is bool for c in items),
            "malformed independent check results",
        )
        require(sum(c["passed"] for c in items) == passed, "independent check count drift")


def diagnosis(record: ExternalRecord, receipt: dict[str, Any] | None) -> dict[str, Any]:
    independent = receipt if receipt is not None else record.recorded_verification
    validate_verification(independent)
    return {
        "authority": "DETERMINISTIC_RECORDED_OBSERVATIONS",
        "original_episode_acceptance": record.original_acceptance,
        "workspace_acceptance": independent["acceptance"],
        "independent_verification": independent,
        "agent_self_reports": [e["ordinal"] for e in record.trace if e["agent_report"]],
        "observed_failed_tools": [
            e["ordinal"]
            for e in record.trace
            if e["exit_code"] not in (None, 0) or e["status"] == "failed"
        ],
        "file_changes": record.file_changes,
        "infrastructure": record.infrastructure,
        "root_cause": None,
        "causal_attribution": "NOT_ESTABLISHED",
        "agent_reexecuted": False,
        "limits": [
            "Digests bind supplied bytes, not origin or ownership.",
            "Agent reports and tool success do not establish task acceptance.",
            "Workspace checks do not establish instruction compliance or model quality.",
            "Missing values remain unknown; this record is not comparison eligible.",
        ],
    }


def view(policy: EvidencePolicy, identity: str) -> dict[str, Any]:
    record = read_record(policy, identity)
    receipt = verification_receipt(policy, identity)
    return {
        "identity": identity,
        "record": record.model_dump(mode="json"),
        "diagnosis": diagnosis(record, receipt),
    }


def export_record(policy: EvidencePolicy, identity: str) -> bytes:
    record = read_record(policy, identity)
    receipt = verification_receipt(policy, identity)
    packet = {
        "schema_version": 1,
        "kind": "external-evidence-export-v1",
        "record": record.model_dump(mode="json"),
        "record_identity": record.identity,
        "verification_receipt": receipt,
        "diagnosis": diagnosis(record, receipt),
        "workspace": {
            p: base64.b64encode(data).decode()
            for p, data in workspace_files(record_root(policy, identity) / "workspace").items()
        },
        "hidden_assets_included": False,
        "external_calls": 0,
        "agent_reexecuted": False,
    }
    data = encode(packet)
    require(len(data) <= MAX_EXPORT, "oversized export")
    return data


def replay_export(data: bytes, expected: str) -> dict[str, Any]:
    require(len(data) <= MAX_EXPORT and sha256_bytes(data) == expected, "export pin mismatch")
    packet = decode(data)
    require(
        set(packet)
        == {
            "schema_version",
            "kind",
            "record",
            "record_identity",
            "verification_receipt",
            "diagnosis",
            "workspace",
            "hidden_assets_included",
            "external_calls",
            "agent_reexecuted",
        },
        "unsupported export",
    )
    require(
        packet["schema_version"] == 1 and packet["kind"] == "external-evidence-export-v1",
        "unsupported version",
    )
    require(
        packet["hidden_assets_included"] is False
        and packet["external_calls"] == 0
        and packet["agent_reexecuted"] is False,
        "invalid execution claims",
    )
    record = ExternalRecord.model_validate(packet["record"])
    require(record.identity == packet["record_identity"], "record drift")
    files = {}
    for name, value in packet["workspace"].items():
        safe_name(name)
        files[name] = base64.b64decode(value, validate=True)
        safe_content(files[name])
    require(content_digest(files) == record.workspace_digest, "export workspace drift")
    require(
        {p: sha256_bytes(data) for p, data in files.items()} == record.workspace_files,
        "export inventory drift",
    )
    receipt = packet["verification_receipt"]
    if receipt is not None:
        require(
            receipt["record_identity"] == record.identity
            and receipt["workspace_digest"] == record.workspace_digest,
            "receipt binding drift",
        )
        require(
            receipt["receipt_digest"]
            == canonical_digest({k: v for k, v in receipt.items() if k != "receipt_digest"}),
            "receipt digest drift",
        )
        validate_verification(receipt)
    require(diagnosis(record, receipt) == packet["diagnosis"], "diagnosis drift")
    return {
        "status": "PASS",
        "export_digest": expected,
        "record_identity": record.identity,
        "workspace_digest": record.workspace_digest,
        "diagnosis": packet["diagnosis"],
        "subject_executed": False,
        "verifier_executed": False,
        "external_calls": 0,
        "scope": "EXPORTED_RECORD_INTEGRITY_NOT_NEW_VERIFIER_OR_SOURCE_ATTESTATION",
    }
