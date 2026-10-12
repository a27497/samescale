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
from harnesslab.api.workbench_errors import WorkbenchAPIError
from harnesslab.episodes.hooks import _write_once, encode
from harnesslab.episodes.verified_hooks import read_verified_hook_bundle
from harnesslab.external_evidence.converters import Conversion, codex_artifacts, stream_json
from harnesslab.external_evidence.models import ApprovedSource, EvidencePolicy, ExternalRecord
from harnesslab.harness_lane.models import (
    NormalizedTrace,
    TraceEventType,
)
from harnesslab.local_plans.tasks import bounded_files, fail, no_links, read_owned_json
from harnesslab.productization.assets import distribution_root
from harnesslab.registry.models import canonical_digest
from harnesslab.tasks.models import validate_relative_path
from harnesslab.tasks.package import digest_tree, sha256_bytes

MAX_EXPORT = 12_000_000
PRIVATE_PARTS = {
    ".claude",
    ".cursor",
    ".codex",
    ".ssh",
    ".git",
    ".aws",
    ".config",
    "oracle",
    "verifier",
}
PRIVATE_NAMES = {"auth.json", "credentials.json", "id_rsa", "id_ed25519"}
SECRET = re.compile(
    rb"-----BEGIN [A-Z ]*PRIVATE KEY-----|\b(?:sk-|ghp_|github_pat_)[A-Za-z0-9_-]{16,}"
    rb"|\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"
    rb"|(?i:authorization\s*[:=]\s*bearer\s+\S+|"
    rb"(?:access_token|refresh_token|api_key|password|secret)\s*[\"']?\s*[:=]\s*[\"']?[^\s\"']{8,})"
)


class EvidenceInputError(ValueError):
    """A fixed public reason code; private input/exception text never crosses the boundary."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def input_require(condition: bool, code: str, message: str) -> None:
    if not condition:
        raise EvidenceInputError(code, message)


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
        raise EvidenceInputError("EVIDENCE_SENSITIVE_INPUT", "private or unsafe snapshot name")


def safe_content(data: bytes) -> None:
    # MVP accepts reviewed UTF-8 source snapshots only; it does not claim universal DLP.
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        raise EvidenceInputError(
            "EVIDENCE_INPUT_UNSUPPORTED", "unsupported snapshot content"
        ) from None
    if SECRET.search(data):
        raise EvidenceInputError("EVIDENCE_SENSITIVE_INPUT", "private snapshot content")
    if b"\x00" in data:
        raise EvidenceInputError("EVIDENCE_INPUT_UNSUPPORTED", "unsupported snapshot content")


def safe_root(path: Path) -> None:
    no_links(path)
    if (
        path == Path("/")
        or path == Path.home()
        or any(
            p.lower() in PRIVATE_PARTS | PRIVATE_NAMES or p.startswith(".env") for p in path.parts
        )
    ):
        raise ValueError("credential/session roots are forbidden")


def overlap(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


def load_policy() -> EvidencePolicy:
    configured = os.environ.get("HARNESSLAB_EXTERNAL_EVIDENCE_POLICY")
    if not configured:
        raise fail("EXTERNAL_EVIDENCE_DISABLED", "Set the private evidence policy.", 403)
    path = Path(configured)
    try:
        safe_root(path)
        info = path.stat()
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_uid != os.getuid()
            or info.st_mode & 0o077
        ):
            raise fail("EVIDENCE_POLICY_PERMISSION", "Use an owned private policy (0600).", 403)
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
            safe_content(encode(source.binding))
            for root in (source.path, source.workspace):
                if root is None:
                    continue
                safe_root(root)
                if any(overlap(root, r) for r in roots) or overlap(root, path):
                    raise ValueError("source/storage/policy overlap")
            if (source.task_reference is None) != (source.task_digest is None):
                raise ValueError("incomplete task mapping")
        # Reject links/special files before reading stored content on every request.
        validate_store(policy)
        return policy
    except PermissionError:
        raise fail(
            "EVIDENCE_POLICY_PERMISSION", "Private configuration is not readable.", 403
        ) from None
    except WorkbenchAPIError as exc:
        if exc.code in {"EVIDENCE_POLICY_PERMISSION", "EVIDENCE_STORAGE_UNSAFE"}:
            raise
        raise fail(
            "EVIDENCE_POLICY_INVALID", "Check canonical paths and policy structure.", 403
        ) from None
    except (OSError, ValueError):
        raise fail(
            "EVIDENCE_POLICY_INVALID", "Check the configured policy and paths.", 403
        ) from None


def validate_store(policy: EvidencePolicy) -> None:
    # Global structure/ownership failures must never become per-record warnings.
    try:
        safe_root(policy.store)
        if policy.store.exists():
            info = policy.store.stat()
            require(stat.S_ISDIR(info.st_mode), "store is not a directory")
            require(
                info.st_uid == os.getuid()
                and not info.st_mode & 0o077
                and info.st_mode & 0o700 == 0o700,
                "unsafe store rights",
            )
            bounded_files(policy.store, max_files=20_000, max_bytes=128_000_000)

            def unreadable(error: OSError) -> None:
                raise error

            for current, directories, files in os.walk(policy.store, onerror=unreadable):
                for name in (*directories, *files):
                    node = (Path(current) / name).lstat()
                    rights = 0o500 if stat.S_ISDIR(node.st_mode) else 0o400
                    require(
                        node.st_uid == os.getuid() and node.st_mode & rights == rights,
                        "untrusted or unreadable stored node",
                    )
    except (OSError, ValueError, WorkbenchAPIError):
        raise fail("EVIDENCE_STORAGE_UNSAFE", "Private storage safety check failed.", 403) from None


def configuration_check() -> dict[str, Any]:
    """Read policy and approved-path metadata only: no source content, writes or execution."""
    result: dict[str, Any] = {
        "status": "NOT_CONFIGURED",
        "issues": [],
        "sources": [],
        "operator_configured": len(os.environ.get("HARNESSLAB_LOCAL_CONFIGURATION_TOKEN", ""))
        >= 32,
        "source_contents_checked": False,
        "pins_verified": False,
        "record_integrity_checked": False,
        "subject_executed": False,
        "verifier_executed": False,
        "real_execution_enabled": False,
    }
    try:
        policy = load_policy()
    except WorkbenchAPIError as exc:
        result["issues"] = [exc.code]
        return result
    for source in policy.sources:
        try:
            available = (source.path is None or source.path.is_dir()) and source.workspace.is_dir()
        except OSError:
            available = False
        result["sources"].append(
            {
                "source_id": source.source_id,
                "status": "LOCATION_PRESENT" if available else "SOURCE_LOCATION_UNAVAILABLE",
            }
        )
    if not result["operator_configured"]:
        result["issues"].append("LOCAL_CONFIGURATION_DISABLED")
    if any(s["status"] == "SOURCE_LOCATION_UNAVAILABLE" for s in result["sources"]):
        result["issues"].append("SOURCE_LOCATION_UNAVAILABLE")
    result["status"] = (
        "NEEDS_ATTENTION"
        if result["issues"]
        else ("CONFIGURED" if policy.sources else "NO_APPROVED_SOURCES")
    )
    return result


def list_records(policy: EvidencePolicy) -> list[dict[str, Any]]:
    validate_store(policy)
    if not policy.store.exists():
        return []
    paths = sorted(p for p in policy.store.iterdir() if not p.name.startswith("."))
    if len(paths) > 1000 or any(
        not re.fullmatch(r"[a-f0-9]{64}", p.name) or not p.is_dir() for p in paths
    ):
        raise fail("EVIDENCE_STORAGE_UNSAFE", "Unexpected private store structure.", 403)
    result: list[dict[str, Any]] = []
    for path in paths:
        try:
            item = view(policy, path.name)
            record = item["record"]
            result.append(
                {
                    "identity": path.name,
                    "status": "AVAILABLE",
                    "source_id": record["source"]["source_id"],
                    "source_kind": record["source"]["source_kind"],
                    "acceptance": item["diagnosis"]["workspace_acceptance"],
                }
            )
        except PermissionError:
            raise fail("EVIDENCE_STORAGE_UNSAFE", "Private storage is not readable.", 403) from None
        except (FileNotFoundError, ValueError, KeyError, TypeError, AttributeError):
            # Never trust damaged metadata for labels or an acceptance verdict.
            result.append(
                {
                    "identity": path.name,
                    "status": "CORRUPT",
                    "error_code": "EVIDENCE_RECORD_CORRUPT",
                    "reason": "Stored record, Workspace or receipt failed integrity validation.",
                }
            )
        # Other OS / structural safety errors stay global, not silently skipped.
    return result


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
            input_require(
                not any(
                    p.lower() in PRIVATE_PARTS | PRIVATE_NAMES or p.startswith(".env")
                    for p in Path(change.path).parts
                ),
                "EVIDENCE_SENSITIVE_INPUT",
                "private trace file path",
            )
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
                        input_require(
                            not SECRET.search(data),
                            "EVIDENCE_SENSITIVE_INPUT",
                            "credential-shaped source content",
                        )
                        _write_once(target / name, data)
                finally:
                    os.close(child)

        copy(fd, destination)
    finally:
        os.close(fd)


def read_stream(source: ApprovedSource) -> bytes:
    """Explicitly supplied pinned JSONL stream; no rollout/session discovery or raw writes."""
    assert source.path is not None
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
            input_require(
                len(data) == info.st_size
                and after.st_mtime_ns == info.st_mtime_ns
                and content_digest({"events.jsonl": data}) == source.digest,
                "EVIDENCE_PIN_MISMATCH",
                "saved JSONL pin or capture mismatch",
            )
        finally:
            os.close(stream_fd)
    finally:
        os.close(fd)
    safe_content(data)  # Shared credential rejection before any projection or persistence.
    return data


def project(source: ApprovedSource) -> tuple[ExternalRecord, dict[str, bytes]]:
    safe_content(encode(source.binding))
    # Freeze bounded bytes first; legacy validators never traverse a live untrusted tree.
    with tempfile.TemporaryDirectory(prefix="samescale-evidence-read-") as temporary:
        private = Path(temporary)
        stream_conversion = (
            stream_json(source, read_stream(source))
            if source.format in {"codex-jsonl-v1", "stream-json-v1", "auto-v1"}
            else None
        )
        if stream_conversion is None and source.path is not None:
            snapshot(source.path, private / "source")
        snapshot(source.workspace, private / "workspace", max_bytes=4_000_000)
        copy = source.model_copy(
            update={
                "path": private / "source" if source.path else None,
                "workspace": private / "workspace",
            }
        )
        return _project_snapshot(copy, stream_conversion)


def _project_snapshot(
    source: ApprovedSource, stream_conversion: Conversion | None = None
) -> tuple[ExternalRecord, dict[str, bytes]]:
    # Validate structural safety before legacy readers hash or parse any approved artifact.
    if stream_conversion is None and source.path is not None:
        bounded_files(source.path, max_files=4000, max_bytes=32_000_000)
    files = workspace_files(source.workspace)
    input_require(
        content_digest(files) == source.workspace_digest,
        "EVIDENCE_PIN_MISMATCH",
        "workspace pin mismatch",
    )
    if source.format == "code-only-v1":
        converted = Conversion(
            NormalizedTrace(events=()),
            source.source_kind,
            "NOT_VERIFIED",
            None,
            "NO_RUN_RECORD",
            [
                "run_record",
                "actual_model",
                "provider_route",
                "usage",
                "cost",
                "independent_verifier",
            ],
            {"status": "BASELINE_MISSING", "paths": []},
            unknown_verification(),
            {"status": "UNKNOWN", "root_cause": None},
            None,
        )
    else:
        converted = stream_conversion or codex_artifacts(source, files)
    trace = converted.trace
    missing = list(converted.missing)
    verification = converted.verification
    projected = trace_projection(trace)
    missing.extend(
        ["tool_exit_codes"]
        if any(e["exit_code"] is None for e in projected if e["type"] == "COMMAND_EXECUTION")
        else []
    )
    record = ExternalRecord(
        kind="external-run-evidence-v1",
        harness=converted.harness,
        source=source.binding,
        original_source_kind=converted.original_kind,
        episode_identity=converted.episode_id,
        original_acceptance=converted.original,
        workspace_digest=source.workspace_digest,
        workspace_files={p: sha256_bytes(data) for p, data in files.items()},
        trace=projected,
        completeness={
            "status": "PARTIAL",
            "coverage": converted.coverage,
            "missing_fields": missing,
            "integrity": "PINNED_BYTES_VERIFIED",
            "origin": "NOT_ATTESTED",
        },
        file_changes=converted.changes,
        recorded_verification=verification,
        infrastructure=converted.infrastructure,
    )
    # Refuse moving sources before committing the projected snapshot.
    require(workspace_files(source.workspace) == files, "workspace changed during import")
    if stream_conversion is not None or source.path is None:
        pass  # Raw stream was pinned in memory; no raw snapshot exists.
    elif source.format != "verified-hook-v1":
        require(digest_tree(source.path) == source.digest, "source changed during import")
    else:
        assert source.digest is not None
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
    input_require(source is not None, "EVIDENCE_SOURCE_NOT_APPROVED", "source not approved")
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
    require(isinstance(raw, dict), "invalid verification receipt")
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
            isinstance(items, list)
            and len(items) == checks
            and all(isinstance(c, dict) and type(c.get("passed")) is bool for c in items),
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
