from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from harnesslab.contracts.common import Identifier, Sha256Digest
from harnesslab.episodes.service import SourceKind
from harnesslab.registry.models import RegistryModel, canonical_digest


class HarnessIdentity(RegistryModel):
    name: Identifier
    version: str | None = Field(default=None, min_length=1, max_length=80)
    # Converter-owned metadata only; never raw tool payloads.
    extensions: dict[str, str] = Field(default_factory=dict)


class ApprovedSource(RegistryModel):
    source_id: Identifier
    format: Literal[
        "stream-json-v1",
        "hook-v1",
        "h-lane-v1",
        "code-only-v1",
        "auto-v1",
        "verified-hook-v1",
        "native-hook-v1",
        "codex-h-lane-v1",
        "codex-jsonl-v1",
    ]
    harness: HarnessIdentity | None = None
    source_kind: SourceKind
    path: Path | None = None
    digest: Sha256Digest | None = None
    workspace: Path
    workspace_digest: Sha256Digest
    # Mapping is a separate operator assertion, never a command supplied by the Subject.
    task_reference: str | None = Field(default=None, min_length=1, max_length=180)
    task_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def validate_inputs(self) -> ApprovedSource:
        if self.format == "code-only-v1":
            if self.path is not None or self.digest is not None or self.harness is not None:
                raise ValueError("code-only sources have no run evidence or harness")
            if self.task_reference is None or self.task_digest is None:
                raise ValueError("code-only intake requires separate acceptance conditions")
        else:
            if self.path is None or self.digest is None:
                raise ValueError("run sources require explicitly approved evidence and pin")
            if self.format == "stream-json-v1" and self.harness is None:
                raise ValueError("stream format requires a harness identity")
            if (
                self.format not in {"stream-json-v1", "auto-v1"}
                and self.harness is not None
                and self.harness.name != "codex"
            ):
                raise ValueError("the existing artifact converters are Codex-specific")
        if self.format in {"stream-json-v1", "auto-v1", "hook-v1", "h-lane-v1"} and (
            self.task_reference is None or self.task_digest is None
        ):
            raise ValueError("new intake requires separate acceptance conditions")
        if self.harness is not None and self.harness.extensions:
            raise ValueError("approved harness extensions are converter-owned")
        return self

    @property
    def binding(self) -> dict[str, Any]:
        excluded = {"path", "workspace"}
        if self.harness is None:
            excluded.add("harness")  # Preserve existing operator bindings byte for byte.
        return self.model_dump(mode="json", exclude=excluded)


class EvidencePolicy(RegistryModel):
    schema_version: Literal[1] = 1
    store: Path
    sources: tuple[ApprovedSource, ...] = Field(max_length=100)
    # Optional offline verifier only. No build/pull, auth, Provider or Agent execution.
    verifier_image_id: Sha256Digest | None = None
    runtime_root: Path | None = None
    artifact_root: Path | None = None


class ImportRequest(RegistryModel):
    source_id: Identifier
    consent: Literal["IMPORT_APPROVED_SAVED_EVIDENCE"]


class ExternalRecord(RegistryModel):
    schema_version: Literal[1] = 1
    kind: Literal["external-run-evidence-v1", "external-codex-evidence-v1"] = (
        "external-run-evidence-v1"
    )
    harness: HarnessIdentity | None = None
    namespace: Literal["CUSTOM"] = "CUSTOM"
    source: dict[str, Any]
    original_source_kind: SourceKind
    episode_identity: Sha256Digest | None
    original_acceptance: Literal["NOT_VERIFIED", "RECORDED_PASS", "RECORDED_FAIL"]
    workspace_digest: Sha256Digest
    workspace_files: dict[str, Sha256Digest]
    trace: tuple[dict[str, Any], ...]
    completeness: dict[str, Any]
    file_changes: dict[str, Any]
    recorded_verification: dict[str, Any]
    infrastructure: dict[str, Any]
    source_authenticity: Literal["NOT_ATTESTED"] = "NOT_ATTESTED"
    session_workspace_binding: Literal["OPERATOR_ASSERTED_NOT_ATTESTED"] = (
        "OPERATOR_ASSERTED_NOT_ATTESTED"
    )
    execution_authorized: Literal[False] = False
    comparison_eligible: Literal[False] = False

    @model_validator(mode="after")
    def validate_legacy_metadata(self) -> ExternalRecord:
        if self.kind == "external-codex-evidence-v1" and self.harness is not None:
            raise ValueError("legacy records cannot carry unbound new metadata")
        return self

    @property
    def identity(self) -> str:
        # A stored pre-migration record keeps its original content address and receipts.
        excluded = {"harness"} if self.kind == "external-codex-evidence-v1" else set()
        return canonical_digest(self.model_dump(mode="json", exclude=excluded))
