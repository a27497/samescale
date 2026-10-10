from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from harnesslab.contracts.common import Identifier, Sha256Digest
from harnesslab.episodes.service import SourceKind
from harnesslab.registry.models import RegistryModel, canonical_digest


class ApprovedSource(RegistryModel):
    source_id: Identifier
    format: Literal["verified-hook-v1", "native-hook-v1", "codex-h-lane-v1", "codex-jsonl-v1"]
    source_kind: SourceKind
    path: Path
    digest: Sha256Digest
    workspace: Path
    workspace_digest: Sha256Digest
    # Mapping is a separate operator assertion, never a command supplied by the Subject.
    task_reference: str | None = Field(default=None, max_length=180)
    task_digest: Sha256Digest | None = None

    @property
    def binding(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude={"path", "workspace"})


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
    kind: Literal["external-codex-evidence-v1"] = "external-codex-evidence-v1"
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

    @property
    def identity(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))
