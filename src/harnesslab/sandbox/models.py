from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from harnesslab.contracts.common import Sha256Digest


class SandboxStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    ARTIFACT_ERROR = "artifact_error"
    CLEANUP_ERROR = "cleanup_error"


class VerifierLifecycleStage(StrEnum):
    WORKSPACE_PREPARE = "VERIFIER_WORKSPACE_PREPARE"
    SANDBOX_CREATE = "VERIFIER_SANDBOX_CREATE"
    WORKSPACE_ATTACH = "VERIFIER_WORKSPACE_ATTACH"
    SANDBOX_START = "VERIFIER_SANDBOX_START"
    PROCESS_START = "VERIFIER_PROCESS_START"
    PROCESS_WAIT = "VERIFIER_PROCESS_WAIT"
    RESULT_COLLECT = "VERIFIER_RESULT_COLLECT"
    ARTIFACT_PERSIST = "VERIFIER_ARTIFACT_PERSIST"
    SANDBOX_CLEANUP = "VERIFIER_SANDBOX_CLEANUP"
    STAGING_CLEANUP = "VERIFIER_STAGING_CLEANUP"


class VerifierLifecycleStageStatus(StrEnum):
    STARTED = "STARTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class VerifierFailureSubtype(StrEnum):
    WORKSPACE_PREPARE_FAILED = "WORKSPACE_PREPARE_FAILED"
    WORKSPACE_PERMISSION_HANDOFF_FAILED = "WORKSPACE_PERMISSION_HANDOFF_FAILED"
    SANDBOX_CREATE_FAILED = "SANDBOX_CREATE_FAILED"
    SANDBOX_START_FAILED = "SANDBOX_START_FAILED"
    WORKSPACE_ATTACH_FAILED = "WORKSPACE_ATTACH_FAILED"
    VERIFIER_PROCESS_START_FAILED = "VERIFIER_PROCESS_START_FAILED"
    VERIFIER_PROCESS_NONZERO = "VERIFIER_PROCESS_NONZERO"
    VERIFIER_TIMEOUT = "VERIFIER_TIMEOUT"
    RESULT_COLLECTION_FAILED = "RESULT_COLLECTION_FAILED"
    ARTIFACT_PERSIST_FAILED = "ARTIFACT_PERSIST_FAILED"
    SANDBOX_CLEANUP_FAILED = "SANDBOX_CLEANUP_FAILED"
    STAGING_CLEANUP_FAILED = "STAGING_CLEANUP_FAILED"
    UNKNOWN_VERIFIER_LIFECYCLE_FAILURE = "UNKNOWN_VERIFIER_LIFECYCLE_FAILURE"


class VerifierLifecycleStageEvidence(BaseModel):
    """Bounded lifecycle facts; commands, paths, streams, and environment are excluded."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stage: VerifierLifecycleStage
    status: VerifierLifecycleStageStatus
    duration_ms: int = Field(ge=0)
    exception_class: str | None = Field(default=None, pattern=r"^[A-Za-z][A-Za-z0-9_]{0,99}$")
    reason_code: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,99}$")
    container_exit_code: int | None = None
    timeout: bool = False

    @model_validator(mode="after")
    def failure_fields_are_bounded(self) -> VerifierLifecycleStageEvidence:
        if self.status is VerifierLifecycleStageStatus.FAILED and self.reason_code is None:
            raise ValueError("failed verifier lifecycle stage requires a safe reason code")
        if self.status is not VerifierLifecycleStageStatus.FAILED and (
            self.exception_class is not None or self.reason_code is not None or self.timeout
        ):
            raise ValueError("only a failed verifier lifecycle stage may carry failure facts")
        return self


class VerifierLifecycleDiagnostics(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    stages: tuple[VerifierLifecycleStageEvidence, ...]
    failure_subtype: VerifierFailureSubtype | None = None

    @model_validator(mode="after")
    def stages_are_unique_and_failure_is_coherent(self) -> VerifierLifecycleDiagnostics:
        if len({item.stage for item in self.stages}) != len(self.stages):
            raise ValueError("verifier lifecycle stages must be unique")
        failed = tuple(
            item for item in self.stages if item.status is VerifierLifecycleStageStatus.FAILED
        )
        if (self.failure_subtype is None) != (not failed):
            raise ValueError("verifier lifecycle subtype and failed stage disagree")
        return self


class DockerPreflight(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ready: bool
    cli_path: str
    client_version: str
    server_version: str
    context: str
    endpoint_scheme: str
    server_os: str
    server_arch: str
    operating_system: str
    default_seccomp: bool


class ImageIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    reference: str
    image_id: Sha256Digest
    repo_digests: tuple[str, ...] = ()


class MountEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    destination: str
    read_write: bool
    mount_type: str


class SecurityEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    privileged: bool
    read_only_rootfs: bool
    cap_drop: tuple[str, ...]
    security_options: tuple[str, ...]
    network_mode: str
    memory_bytes: int = Field(gt=0)
    nano_cpus: int = Field(gt=0)
    pids_limit: int = Field(gt=0)
    restart_policy: str
    user: str
    pid_mode: str
    published_ports: bool
    device_count: int = Field(ge=0)
    mounts: tuple[MountEvidence, ...]
    tmpfs_destinations: tuple[str, ...]
    docker_socket_mounted: bool
    seccomp_unconfined: bool

    @model_validator(mode="after")
    def hardened_profile(self) -> SecurityEvidence:
        required = (
            not self.privileged,
            self.read_only_rootfs,
            "ALL" in self.cap_drop,
            "no-new-privileges=true" in self.security_options,
            self.network_mode == "none",
            self.restart_policy == "no",
            self.user not in {"", "0", "0:0", "root"},
            self.pid_mode in {"", "private"},
            not self.published_ports,
            self.device_count == 0,
            self.tmpfs_destinations == ("/tmp",),
            not self.docker_socket_mounted,
            not self.seccomp_unconfined,
        )
        if not all(required):
            raise ValueError("effective Docker configuration is not hardened")
        return self


class ArtifactDigest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    path: str
    digest: Sha256Digest


class SandboxArtifactManifest(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = 1
    run_id: str
    role: str
    task_id: str
    task_version: str
    task_digest: Sha256Digest
    workspace_input_digest: Sha256Digest
    workspace_output_digest: Sha256Digest | None
    image: ImageIdentity
    security: SecurityEvidence
    status: SandboxStatus
    exit_code: int | None
    duration_ms: int = Field(ge=0)
    timed_out: bool
    cancelled: bool
    cleanup_verified: bool
    stdout_stream_digest: Sha256Digest
    stderr_stream_digest: Sha256Digest
    stdout_truncated: bool
    stderr_truncated: bool
    stdout: ArtifactDigest
    stderr: ArtifactDigest
    workspace_snapshot: ArtifactDigest | None
    summary: str

    @model_validator(mode="after")
    def cleanup_status_matches_evidence(self) -> SandboxArtifactManifest:
        if not self.cleanup_verified and self.status is not SandboxStatus.CLEANUP_ERROR:
            raise ValueError(
                "unverified cleanup requires cleanup_error status; success is forbidden"
            )
        if self.cleanup_verified and self.status is SandboxStatus.CLEANUP_ERROR:
            raise ValueError("cleanup_error status requires unverified cleanup")
        return self

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )


@dataclass(frozen=True)
class SandboxRunResult:
    run_id: str
    container_name: str
    artifact_directory: Path
    manifest: SandboxArtifactManifest
    stdout: str
    stderr: str


class FakeSubjectRequest(BaseModel):
    """Narrow trusted Phase C fixture behavior; never accepts raw Docker arguments."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    solve_python_clamp: bool = True
    write_marker: bool = False
    require_marker_absent: bool = False
    sleep_seconds: float = Field(default=0.0, ge=0.0, le=60.0)
    echo_secret_name: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    write_secret_file: bool = False
    write_secret_filename: bool = False
    create_unsafe_symlink: bool = False
    output_bytes: int = Field(default=0, ge=0, le=200_000)

    @model_validator(mode="after")
    def secret_workspace_fixture_requires_secret_name(self) -> FakeSubjectRequest:
        if (self.write_secret_file or self.write_secret_filename) and self.echo_secret_name is None:
            raise ValueError("secret workspace fixture requires echo_secret_name")
        return self


class IsolatedVerifierResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    run: SandboxRunResult
    passed: bool
    score: float = Field(ge=0.0, le=1.0)
    lifecycle: VerifierLifecycleDiagnostics | None = None
