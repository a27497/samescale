from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from pydantic import ValidationError

from harnesslab.harness_lane.models import NormalizedTrace
from harnesslab.sandbox.artifacts import sha256_file


class EvidenceReadError(RuntimeError):
    """Persisted evidence failed its trusted-root, identity, or digest boundary."""


@dataclass(frozen=True)
class VerifiedManifest:
    raw: dict[str, Any]
    path: Path


class EvidenceRecord(Protocol):
    """Minimal immutable identity needed to verify one physical run attempt's evidence."""

    @property
    def run_id(self) -> str: ...

    @property
    def attempt(self) -> int: ...

    @property
    def artifact_manifest_path(self) -> str | None: ...

    @property
    def evidence_digest(self) -> str | None: ...


def trusted_artifact_path(raw_path: str | Path, roots: tuple[Path, ...]) -> Path:
    """Resolve an existing artifact and reject symlink and trusted-root escapes."""

    try:
        resolved = Path(raw_path).resolve(strict=True)
        trusted = tuple(root.resolve() for root in roots)
    except OSError as exc:
        raise EvidenceReadError("artifact location cannot be verified") from exc
    if not any(resolved == root or root in resolved.parents for root in trusted):
        raise EvidenceReadError("artifact is outside trusted storage")
    return resolved


def _expected_manifest_run_id(run: EvidenceRecord) -> str:
    suffix = f"-a{run.attempt}"
    expected = f"{run.run_id}{suffix}"
    if len(expected) <= 100:
        return expected
    identity_digest = hashlib.sha256(expected.encode()).hexdigest()[:16]
    prefix_length = 100 - len(suffix) - len(identity_digest) - 1
    return f"{run.run_id[:prefix_length]}-{identity_digest}{suffix}"


def load_verified_manifest(run: EvidenceRecord, roots: tuple[Path, ...]) -> VerifiedManifest:
    if run.artifact_manifest_path is None or run.evidence_digest is None:
        raise EvidenceReadError("run artifact is not reported")
    path = trusted_artifact_path(run.artifact_manifest_path, roots)
    try:
        if not path.is_file() or sha256_file(path) != run.evidence_digest:
            raise EvidenceReadError("run artifact digest does not match")
        raw = json.loads(path.read_text(encoding="utf-8"))
    except EvidenceReadError:
        raise
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceReadError("run artifact cannot be verified") from exc
    try:
        expected_run_id = _expected_manifest_run_id(run)
    except ValueError as exc:
        raise EvidenceReadError("run attempt identity is invalid") from exc
    if not isinstance(raw, dict) or raw.get("run_id") != expected_run_id:
        raise EvidenceReadError("run artifact identity mismatch")
    return VerifiedManifest(raw=raw, path=path)


def load_normalized_trace(
    run: EvidenceRecord | VerifiedManifest, roots: tuple[Path, ...] = ()
) -> tuple[NormalizedTrace, str, str | None]:
    """Read one digest-bound trace from a run or an already-verified manifest."""
    manifest = run if isinstance(run, VerifiedManifest) else load_verified_manifest(run, roots)
    digest = manifest.raw.get("normalized_trace_digest")
    coverage = manifest.raw.get("trace_coverage")
    if not isinstance(digest, str):
        raise EvidenceReadError("normalized trace is not reported")
    try:
        root = manifest.path.parent.resolve()
        trace_path = (root / "trace" / "normalized.json").resolve()
        if root not in trace_path.parents:
            raise EvidenceReadError("normalized trace escapes its run artifact")
        payload = trace_path.read_bytes()
        if "sha256:" + hashlib.sha256(payload).hexdigest() != digest:
            raise EvidenceReadError("normalized trace digest does not match")
        trace = NormalizedTrace.model_validate_json(payload)
    except EvidenceReadError:
        raise
    except (OSError, UnicodeDecodeError, ValidationError) as exc:
        raise EvidenceReadError("normalized trace cannot be verified") from exc
    return trace, digest, coverage if isinstance(coverage, str) else None
