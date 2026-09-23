"""Import completed Codex H-Lane artifacts without invoking models or copying raw content."""

from __future__ import annotations

import json
import os
import stat
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from harnesslab.episodes.hooks import HookEpisode

from pydantic import BaseModel, ConfigDict, Field

from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.common import Identifier, Sha256Digest
from harnesslab.harness_lane.models import (
    HarnessLaneEvidence,
    HarnessLaneOutcome,
    NormalizedTrace,
    TraceEventType,
)
from harnesslab.sandbox.models import SandboxArtifactManifest, SandboxStatus
from harnesslab.tasks.models import VerifierReport
from harnesslab.tasks.package import digest_tree, sha256_bytes

type SourceKind = Literal["historical", "synthetic", "unverified"]


class EpisodeImportError(ValueError):
    """Input could not establish a consistent recorded observation."""


class Episode(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    namespace: Literal["CUSTOM"] = "CUSTOM"
    source_format: Literal["codex-h-lane-v1"] = "codex-h-lane-v1"
    source_kind: SourceKind
    source_authenticity: Literal["NOT_ATTESTED"] = "NOT_ATTESTED"
    source_manifest_digest: Sha256Digest
    source_bundle_digest: Sha256Digest
    run_id: Identifier
    task_id: Identifier
    task_version: str
    task_digest: Sha256Digest
    workspace_input_digest: Sha256Digest
    workspace_output_digest: Sha256Digest
    workspace_integrity: Literal["VERIFIED", "MISSING"]
    profile_identity: Sha256Digest
    prompt_identity: Sha256Digest
    setup_identity: Sha256Digest
    requested_model: str
    observed_model: str | None
    harness_version: str
    reasoning_effort: str
    duration_ms: int = Field(ge=0)
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: None = None
    trace_digest: Sha256Digest
    event_count: int = Field(ge=0)
    event_counts: dict[str, int]
    failed_commands: int = Field(ge=0)
    changed_file_count: int = Field(ge=0)
    source_outcome: str
    acceptance: Literal["RECORDED_PASS", "RECORDED_FAIL", "NOT_VERIFIED"]
    verifier_manifest_digest: Sha256Digest | None
    verifier_check_count: int = Field(ge=0)
    execution_authorized: Literal[False] = False
    comparison_eligible: Literal[False] = False

    @property
    def identity(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EpisodeImportError("Duplicate JSON key")
        result[key] = value
    return result


def _json(path: Path) -> Any:
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 4_000_000:
        raise EpisodeImportError("Missing, unsafe or oversized JSON artifact")
    return json.loads(path.read_bytes(), object_pairs_hook=_unique)


def _bounded_tree(root: Path) -> str:
    if root.is_symlink() or not root.is_dir():
        raise EpisodeImportError("Source must be a regular artifact directory")
    count = total = 0
    for directory, names, files in os.walk(root, followlinks=False):
        for name in (*names, *files):
            path = Path(directory) / name
            mode = path.lstat().st_mode
            if not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
                raise EpisodeImportError("Links and special files are not importable")
            if stat.S_ISREG(mode):
                count += 1
                total += path.stat().st_size
            if count > 10_000 or total > 128_000_000:
                raise EpisodeImportError("Artifact bundle exceeds import limits")
    return digest_tree(root)


def read_codex_episode(source: Path, *, source_kind: SourceKind) -> Episode:
    """Validate recorded bindings. Integrity does not attest who created the input."""
    before = _bounded_tree(source)
    evidence = HarnessLaneEvidence.model_validate(_json(source / "manifest.json"))
    trace_path = source / "trace/normalized.json"
    trace = NormalizedTrace.model_validate(_json(trace_path))
    if sha256_bytes(trace_path.read_bytes()) != evidence.normalized_trace_digest:
        raise EpisodeImportError("Normalized trace digest mismatch")
    native = source / "native/codex.sanitized.jsonl"
    if (
        not native.is_file()
        or sha256_bytes(native.read_bytes()) != evidence.native_transcript_digest
    ):
        raise EpisodeImportError("Native trace digest mismatch")
    if (
        len(trace.events) != evidence.trace_event_count
        or tuple(event.type for event in trace.events) != evidence.trace_event_types
    ):
        raise EpisodeImportError("Trace summary does not match manifest")
    if [event.ordinal for event in trace.events] != list(range(1, len(trace.events) + 1)):
        raise EpisodeImportError("Trace ordinals are not contiguous")
    workspace_integrity: Literal["VERIFIED", "MISSING"] = "MISSING"
    workspace = source / "workspace"
    if workspace.exists():
        if digest_tree(workspace) != evidence.workspace_output_digest:
            raise EpisodeImportError("Workspace digest mismatch")
        workspace_integrity = "VERIFIED"
    acceptance: Literal["RECORDED_PASS", "RECORDED_FAIL", "NOT_VERIFIED"] = "NOT_VERIFIED"
    verifier_digest = None
    check_count = 0
    if evidence.verifier_sandbox_manifest is not None:
        if evidence.outcome not in {
            HarnessLaneOutcome.VERIFIED_PASS,
            HarnessLaneOutcome.VERIFIED_FAIL,
        }:
            raise EpisodeImportError("Recorded acceptance contradicts the source outcome")
        if workspace_integrity != "VERIFIED":
            raise EpisodeImportError("Recorded acceptance requires the final workspace")
        verifier_root = source / "verifier"
        if digest_tree(verifier_root) != evidence.verifier_artifact_digest:
            raise EpisodeImportError("Verifier bundle digest mismatch")
        manifest = SandboxArtifactManifest.model_validate(_json(verifier_root / "manifest.json"))
        if manifest != evidence.verifier_sandbox_manifest:
            raise EpisodeImportError("Verifier manifest differs from recorded manifest")
        if (
            manifest.status is not SandboxStatus.SUCCEEDED
            or manifest.exit_code != 0
            or manifest.timed_out
            or manifest.cancelled
            or manifest.stdout_truncated
        ):
            raise EpisodeImportError("Verifier process did not complete successfully")
        if (manifest.task_id, manifest.task_version, manifest.task_digest) != (
            evidence.task_id,
            evidence.task_version,
            evidence.task_digest,
        ) or manifest.role != "verifier":
            raise EpisodeImportError("Verifier task identity mismatch")
        if manifest.workspace_input_digest != evidence.workspace_output_digest:
            raise EpisodeImportError("Verifier input identity mismatch")
        snapshot = manifest.workspace_snapshot
        if (
            snapshot is None
            or snapshot.path != "workspace"
            or snapshot.digest != evidence.workspace_output_digest
            or manifest.workspace_output_digest != snapshot.digest
            or digest_tree(verifier_root / "workspace") != snapshot.digest
        ):
            raise EpisodeImportError("Verifier workspace snapshot mismatch")
        for asset, expected in (("stdout.txt", manifest.stdout), ("stderr.txt", manifest.stderr)):
            if (
                expected.path != asset
                or sha256_bytes((verifier_root / asset).read_bytes()) != expected.digest
            ):
                raise EpisodeImportError("Verifier stream identity mismatch")
        result = VerifierReport.model_validate(_json(verifier_root / "stdout.txt"))
        if result.passed != evidence.verifier_passed or result.score != evidence.verifier_score:
            raise EpisodeImportError("Verifier outcome mismatch")
        if result.passed and not all(check.passed for check in result.checks):
            raise EpisodeImportError("Passing report contains failed checks")
        acceptance = "RECORDED_PASS" if result.passed else "RECORDED_FAIL"
        verifier_digest = sha256_bytes((verifier_root / "manifest.json").read_bytes())
        check_count = len(result.checks)
    setup = {
        "profile": evidence.profile_hash,
        "prompt": evidence.prompt_hash,
        "resource_budget": evidence.resource_budget.model_dump(mode="json"),
    }
    episode = Episode(
        source_kind=source_kind,
        source_manifest_digest=sha256_bytes((source / "manifest.json").read_bytes()),
        source_bundle_digest=before,
        run_id=evidence.run_id,
        task_id=evidence.task_id,
        task_version=evidence.task_version,
        task_digest=evidence.task_digest,
        workspace_input_digest=evidence.workspace_input_digest,
        workspace_output_digest=evidence.workspace_output_digest,
        workspace_integrity=workspace_integrity,
        profile_identity=evidence.profile_hash,
        prompt_identity=evidence.prompt_hash,
        setup_identity=canonical_digest(setup),
        requested_model=evidence.requested_model,
        observed_model=evidence.observed_model,
        harness_version=evidence.profile.codex_cli_version,
        reasoning_effort=evidence.profile.reasoning_effort,
        duration_ms=evidence.duration_ms,
        input_tokens=evidence.usage.input_tokens if evidence.usage else None,
        output_tokens=evidence.usage.output_tokens if evidence.usage else None,
        trace_digest=evidence.normalized_trace_digest,
        event_count=len(trace.events),
        event_counts=dict(Counter(event.type.value for event in trace.events)),
        failed_commands=sum(
            event.type is TraceEventType.COMMAND_EXECUTION
            and event.native_event_type == "item.completed"
            and event.exit_code not in (None, 0)
            for event in trace.events
        ),
        changed_file_count=len(evidence.changed_paths),
        source_outcome=evidence.outcome.value,
        acceptance=acceptance,
        verifier_manifest_digest=verifier_digest,
        verifier_check_count=check_count,
    )
    if _bounded_tree(source) != before:
        raise EpisodeImportError("Source changed during import")
    return episode


def import_codex_episode(source: Path, store: Path, *, source_kind: SourceKind) -> Episode:
    source_root, store_root = source.resolve(), store.resolve()
    repository = Path(__file__).resolve().parents[3]
    for name in ("tasks", "release"):
        protected = repository / name
        if store_root == protected or protected in store_root.parents:
            raise EpisodeImportError("Episode store cannot use an Official namespace")
    if (
        source_root == store_root
        or source_root in store_root.parents
        or store_root in source_root.parents
    ):
        raise EpisodeImportError("Source and Episode store must not overlap")
    episode = read_codex_episode(source, source_kind=source_kind)
    store.mkdir(parents=True, exist_ok=True)
    destination = store / (episode.identity.removeprefix("sha256:") + ".json")
    payload = json.dumps(episode.model_dump(mode="json"), sort_keys=True, indent=2) + "\n"
    if destination.is_symlink():
        raise EpisodeImportError("Episode destination is a link")
    try:
        with destination.open("x", encoding="utf-8") as stream:
            stream.write(payload)
    except FileExistsError:
        if destination.read_text() != payload:
            raise EpisodeImportError("Stored Episode identity collision or corruption") from None
    return episode


def inspect_episode(path: Path) -> Episode | HookEpisode:
    from harnesslab.episodes.hooks import HookEpisode

    raw = _json(path)
    if not isinstance(raw, dict):
        raise EpisodeImportError("Stored Episode must be an object")
    episode = (
        HookEpisode.model_validate(raw)
        if raw.get("source_format") == "native-hook-v1"
        else Episode.model_validate(raw)
    )
    if path.name != episode.identity.removeprefix("sha256:") + ".json":
        raise EpisodeImportError("Stored Episode identity mismatch")
    return episode
