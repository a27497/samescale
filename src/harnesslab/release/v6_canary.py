from __future__ import annotations

import hashlib
import json
import os
import shutil
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal
from typing import Protocol as TypingProtocol
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, model_validator

from harnesslab.contracts.common import Protocol, Sha256Digest
from harnesslab.contracts.provider import validate_provider_base_url
from harnesslab.egress import (
    EgressProxyRuntime,
    boundary_for_provider_url,
    preflight_egress_network_isolation,
)
from harnesslab.harness_lane.models import HarnessLaneOutcome, ObservedModelStatus
from harnesslab.judgelab.models import (
    JudgeEvaluationSlot,
    JudgeRunOutcome,
    OrderVariant,
)
from harnesslab.judgelab.models import (
    digest as judge_digest,
)
from harnesslab.judgelab.runner import JudgeRunner
from harnesslab.judgelab.suite import load_judge_definition, load_judge_suite
from harnesslab.model_lane.models import DirectModelOutcome
from harnesslab.model_lane.providers import OpenAICompatibleChatAdapter
from harnesslab.model_lane.runner import DirectModelRunner
from harnesslab.multi_harness.adapter import ClaudeCodeAdapter
from harnesslab.multi_harness.docker_backend import DockerMultiHarnessBackend
from harnesslab.multi_harness.models import HarnessKind
from harnesslab.multi_harness.profile import configured_qwen_alibaba_bailian_claude_profile
from harnesslab.multi_harness.runner import MultiHarnessRunner
from harnesslab.multi_harness.runtime import MultiHarnessRuntime
from harnesslab.preflight.io import PreflightInputError, load_control_manifest
from harnesslab.registry.alibaba import configured_alibaba_bailian_profile
from harnesslab.registry.seeds import build_registry_catalog
from harnesslab.release.v6_authorization import (
    V6CanaryAuthorizationReceipt,
    V6CanaryAuthorizationRequest,
    issue_v6_canary_authorization,
)
from harnesslab.sandbox.models import ImageIdentity
from harnesslab.sandbox.preflight import docker_preflight
from harnesslab.tasks.package import TaskPackage, digest_tree

V6_CANARY_CONTROL_REFERENCE = Path("release/core-real-matrix-v6-canary-control.json")
V6_OPERATOR_INPUT_TEMPLATE_REFERENCE = Path(
    "release/core-real-matrix-v6-operator-inputs.template.json"
)
V6_EXPERIMENT_ID = "core-real-matrix-v6"
V6_PLAN_DIGEST = "sha256:c18afc7b003a379f3456b23649e6d161da55e4fb5a34b4702dffbff35fb3604a"
V6_QWEN_MODEL_REFERENCE = "HARNESSLAB_ALIBABA_BAILIAN_QWEN38_MODEL_ID"
V6_GLM_MODEL_REFERENCE = "HARNESSLAB_ALIBABA_BAILIAN_GLM52_MODEL_ID"

EXPECTED_CALL_IDS = (
    "v6-canary-1-direct-qwen38-alibaba-chat",
    "v6-canary-2-claude-qwen38-alibaba-messages",
    "v6-canary-3-judge-glm52-alibaba-chat",
)
EXPECTED_PROFILE_IDS = (
    "alibaba-bailian-qwen3.8-max-chat",
    "alibaba-bailian-qwen3.8-max-messages",
    "alibaba-bailian-glm-5.2-chat",
)


class V6CanaryControlError(RuntimeError):
    """The V6 preflight or bounded canary cannot proceed safely."""


class _FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class V6CanaryStatus(StrEnum):
    READY = "READY"
    BLOCKED = "BLOCKED"


class V6CheckStatus(StrEnum):
    PASS = "PASS"
    BLOCKED = "BLOCKED"


class V6CanaryCallRole(StrEnum):
    SUBJECT_DIRECT = "SUBJECT_DIRECT"
    SUBJECT_HARNESS = "SUBJECT_HARNESS"
    JUDGE = "JUDGE"


class V6EndpointContract(_FrozenModel):
    region: Literal["cn-beijing"]
    dns_suffix: Literal[".cn-beijing.maas.aliyuncs.com"]
    openai_base_url_reference: Literal["HARNESSLAB_ALIBABA_BAILIAN_OPENAI_BASE_URL"]
    openai_path: Literal["/compatible-mode/v1"]
    anthropic_base_url_reference: Literal["HARNESSLAB_ALIBABA_BAILIAN_ANTHROPIC_BASE_URL"]
    anthropic_path: Literal["/apps/anthropic"]
    same_workspace_hostname_required: Literal[True]
    credential_reference: Literal["HARNESSLAB_ALIBABA_BAILIAN_API_KEY"]


class V6CanaryCall(_FrozenModel):
    call_id: str
    ordinal: int = Field(ge=1, le=3)
    role: V6CanaryCallRole
    provider_profile_id: str
    provider_profile_identity: Sha256Digest
    execution_binding_identity: Sha256Digest
    requested_model: str
    protocol: Protocol
    route_identity: str
    harness_id: str
    harness_profile_id: str
    runner_identity: str
    task_reference: str | None
    task_digest: Sha256Digest | None
    judge_case_reference: str | None
    max_output_tokens: int = Field(gt=0)
    timeout_seconds: int = Field(gt=0, le=180)

    @model_validator(mode="after")
    def role_has_one_workload(self) -> V6CanaryCall:
        is_judge = self.role is V6CanaryCallRole.JUDGE
        if is_judge != (self.judge_case_reference is not None):
            raise ValueError("only the Judge canary may carry a Judge case")
        if is_judge == (self.task_reference is not None or self.task_digest is not None):
            raise ValueError("subject calls require one task identity; Judge calls do not")
        return self


class V6HostMinimums(_FrozenModel):
    cpu_count: Literal[8]
    memory_bytes: Literal[17179869184]
    disk_free_bytes: Literal[1073741824]
    claude_image_reference: Literal["harnesslab-phase-f-claude:2.1.241"]
    egress_proxy_image_reference: Literal["harnesslab-egress-proxy:1.0.0"]


class V6CanaryControl(_FrozenModel):
    schema_version: Literal[1] = 1
    control_id: Literal["core-real-matrix-v6-three-call-canary"]
    phase: Literal["K_B3_V6_REAL_PREFLIGHT_AND_CANARY_CONTROL"]
    experiment_id: Literal["core-real-matrix-v6"]
    plan_digest: Literal["sha256:c18afc7b003a379f3456b23649e6d161da55e4fb5a34b4702dffbff35fb3604a"]
    v6_control_reference: Literal["release/core-real-matrix-v6-control.json"]
    v6_control_sha256: Sha256Digest
    corpus_reference: Literal["release/core-corpus-v4.json"]
    corpus_sha256: Sha256Digest
    endpoint_contract: V6EndpointContract
    deployed_model_references: dict[str, str]
    calls: tuple[V6CanaryCall, ...]
    judge_suite_digest: Sha256Digest
    public_rate_fact_digest: Sha256Digest
    host_minimums: V6HostMinimums
    max_primary_calls: Literal[3] = 3
    retries: Literal[0] = 0
    semantic_retries: Literal[0] = 0
    substitutions: Literal[0] = 0
    matrix_execution_allowed: Literal[False] = False
    judge_initial_state: Literal["PROVISIONAL_PENDING_REAL_CANARY"]
    throughput_profile_binding: Literal[
        "NOT_REQUIRED_FOR_THREE_CALL_CANARY_FUTURE_MATRIX_AUTHORIZATION_MUST_BIND_FINAL_PROFILE"
    ]
    execution_state: Literal["NOT_RUN"]

    @model_validator(mode="after")
    def exact_three_call_plan(self) -> V6CanaryControl:
        if tuple(item.call_id for item in self.calls) != EXPECTED_CALL_IDS:
            raise ValueError("V6 canary call identity or order drifted")
        if tuple(item.ordinal for item in self.calls) != (1, 2, 3):
            raise ValueError("V6 canary ordinals must be exactly 1, 2, 3")
        if tuple(item.provider_profile_id for item in self.calls) != EXPECTED_PROFILE_IDS:
            raise ValueError("V6 canary provider profiles drifted")
        if tuple(item.role for item in self.calls) != (
            V6CanaryCallRole.SUBJECT_DIRECT,
            V6CanaryCallRole.SUBJECT_HARNESS,
            V6CanaryCallRole.JUDGE,
        ):
            raise ValueError("V6 canary roles drifted")
        if tuple(item.requested_model for item in self.calls) != (
            "qwen3.8-max",
            "qwen3.8-max",
            "glm-5.2",
        ):
            raise ValueError("V6 canary model identities drifted")
        if tuple(item.protocol for item in self.calls) != (
            Protocol.CHAT_COMPLETIONS,
            Protocol.MESSAGES,
            Protocol.CHAT_COMPLETIONS,
        ):
            raise ValueError("V6 canary protocol identities drifted")
        if tuple(item.harness_id for item in self.calls) != (
            "direct-model",
            "claude-code",
            "judge-runner",
        ) or tuple(item.runner_identity for item in self.calls) != (
            "DirectModelRunner",
            "MultiHarnessRunner",
            "JudgeRunner",
        ):
            raise ValueError("V6 canary execution routes drifted")
        if (
            self.calls[0].task_reference is None
            or self.calls[0].task_reference != self.calls[1].task_reference
            or self.calls[0].task_digest != self.calls[1].task_digest
        ):
            raise ValueError("V6 subject canary task identities differ")
        if tuple(item.max_output_tokens for item in self.calls) != (2000, 2000, 256):
            raise ValueError("V6 canary output bounds drifted")
        if tuple(item.timeout_seconds for item in self.calls) != (180, 180, 90):
            raise ValueError("V6 canary timeout bounds drifted")
        if self.deployed_model_references != {
            "qwen3.8-max": V6_QWEN_MODEL_REFERENCE,
            "glm-5.2": V6_GLM_MODEL_REFERENCE,
        }:
            raise ValueError("V6 deployed-model references drifted")
        return self

    @property
    def digest(self) -> str:
        return _digest(self.model_dump(mode="json"))


class V6OperatorInputs(_FrozenModel):
    """Non-secret account, pricing, and host attestations supplied by the operator."""

    schema_version: Literal[1] = 1
    input_id: str = Field(min_length=3, max_length=100)
    billing_region: str | None = Field(default=None, max_length=100)
    billing_currency: str | None = Field(default=None, max_length=10)
    qwen_deployed_model_id: str | None = Field(default=None, max_length=60)
    glm_deployed_model_id: str | None = Field(default=None, max_length=60)
    cache_or_batch_adjustments: str | None = Field(default=None, min_length=1, max_length=300)
    account_specific_promotions: str | None = Field(default=None, min_length=1, max_length=300)
    tax_treatment: str | None = Field(default=None, min_length=1, max_length=300)
    fx_treatment: str | None = Field(default=None, min_length=1, max_length=300)
    public_region_and_model_rates_apply: bool | None = None
    account_reference_fingerprint: Sha256Digest | None = None
    host_attestation_reference: str | None = Field(default=None, min_length=1, max_length=300)

    @property
    def digest(self) -> str:
        return _digest(self.model_dump(mode="json"))


class V6HostObservation(_FrozenModel):
    docker_ready: bool
    egress_isolation_ready: bool
    cpu_count: int | None = Field(default=None, ge=1)
    memory_bytes: int | None = Field(default=None, ge=1)
    disk_free_bytes: int | None = Field(default=None, ge=0)
    claude_image: ImageIdentity | None = None
    egress_proxy_image: ImageIdentity | None = None


class V6PreflightFinding(_FrozenModel):
    check_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._:-]*$")
    status: V6CheckStatus
    reason_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    detail: str = Field(min_length=1, max_length=500)


class V6EndpointEvidence(_FrozenModel):
    openai_endpoint_fingerprint: Sha256Digest | None = None
    anthropic_endpoint_fingerprint: Sha256Digest | None = None
    workspace_fingerprint: Sha256Digest | None = None
    same_workspace: bool
    raw_endpoint_values_persisted: Literal[False] = False


class V6ModelBindingEvidence(_FrozenModel):
    provider_profile_id: str
    provider_profile_identity: Sha256Digest
    requested_model: str
    deployed_model_reference: str
    deployed_model_matches: bool
    route_identity: str
    execution_binding_identity: Sha256Digest


class V6CanaryPreflightReceipt(_FrozenModel):
    schema_version: Literal[1] = 1
    receipt_type: Literal["V6_CANARY_PREFLIGHT"] = "V6_CANARY_PREFLIGHT"
    experiment_id: Literal["core-real-matrix-v6"]
    plan_digest: Literal["sha256:c18afc7b003a379f3456b23649e6d161da55e4fb5a34b4702dffbff35fb3604a"]
    canary_plan_digest: Sha256Digest
    operator_input_digest: Sha256Digest
    status: V6CanaryStatus
    findings: tuple[V6PreflightFinding, ...]
    endpoint_evidence: V6EndpointEvidence
    credential_reference: Literal["HARNESSLAB_ALIBABA_BAILIAN_API_KEY"]
    credential_present: bool
    credential_value_persisted: Literal[False] = False
    model_bindings: tuple[V6ModelBindingEvidence, ...]
    host_observation: V6HostObservation
    pricing_status: Literal["CONFIRMED", "OPERATOR_INPUTS_REQUIRED"]
    public_rate_fact_digest: Sha256Digest
    max_primary_calls: Literal[3] = 3
    retries: Literal[0] = 0
    semantic_retries: Literal[0] = 0
    substitutions: Literal[0] = 0
    matrix_execution_authorized: Literal[False] = False
    judge_state: Literal["PROVISIONAL_PENDING_REAL_CANARY"]
    provider_calls: Literal[0] = 0
    harness_provider_calls: Literal[0] = 0
    judge_calls: Literal[0] = 0
    receipt_digest: Sha256Digest

    @property
    def expected_receipt_digest(self) -> str:
        return _digest(self.model_dump(mode="json", exclude={"receipt_digest"}))

    @model_validator(mode="after")
    def status_and_digest_are_bound(self) -> V6CanaryPreflightReceipt:
        expected = (
            V6CanaryStatus.BLOCKED
            if any(item.status is V6CheckStatus.BLOCKED for item in self.findings)
            else V6CanaryStatus.READY
        )
        if self.status is not expected:
            raise ValueError("V6 preflight status disagrees with findings")
        if self.receipt_digest != self.expected_receipt_digest:
            raise ValueError("V6 preflight receipt digest mismatch")
        return self


def load_v6_canary_control(repository_root: Path) -> V6CanaryControl:
    root = repository_root.resolve()
    path = root / V6_CANARY_CONTROL_REFERENCE
    try:
        control = load_control_manifest(path, V6CanaryControl)
    except PreflightInputError as exc:
        raise V6CanaryControlError("V6 canary control is invalid") from exc
    _verify_protected_file(root, control.v6_control_reference, control.v6_control_sha256)
    _verify_protected_file(root, control.corpus_reference, control.corpus_sha256)
    _validate_v6_source_control(root, control)
    _validate_registry_and_workloads(root, control)
    return control


def load_v6_operator_inputs(path: Path) -> V6OperatorInputs:
    try:
        return load_control_manifest(path, V6OperatorInputs)
    except PreflightInputError as exc:
        raise V6CanaryControlError("V6 operator inputs are invalid") from exc


async def collect_v6_host_observation(repository_root: Path) -> V6HostObservation:
    """Inspect only the local production host; it never contacts an Alibaba endpoint."""

    docker_ready = False
    egress_ready = False
    claude_image: ImageIdentity | None = None
    proxy_image: ImageIdentity | None = None
    try:
        await docker_preflight()
        docker_ready = True
    except Exception:
        pass
    if docker_ready:
        try:
            await preflight_egress_network_isolation()
            egress_ready = True
        except Exception:
            pass
        with suppress(Exception):
            claude_image = await MultiHarnessRuntime(HarnessKind.CLAUDE_CODE).ensure_image()
        with suppress(Exception):
            proxy_image = await EgressProxyRuntime().ensure_image()
    try:
        disk_free = shutil.disk_usage(repository_root.resolve()).free
    except OSError:
        disk_free = None
    memory_bytes: int | None
    try:
        memory_bytes = int(os.sysconf("SC_PHYS_PAGES")) * int(os.sysconf("SC_PAGE_SIZE"))
    except (OSError, ValueError):
        memory_bytes = None
    return V6HostObservation(
        docker_ready=docker_ready,
        egress_isolation_ready=egress_ready,
        cpu_count=os.cpu_count(),
        memory_bytes=memory_bytes,
        disk_free_bytes=disk_free,
        claude_image=claude_image,
        egress_proxy_image=proxy_image,
    )


def assess_v6_canary_preflight(
    repository_root: Path,
    control: V6CanaryControl,
    operator_inputs: V6OperatorInputs,
    environment: Mapping[str, str],
    host: V6HostObservation,
) -> V6CanaryPreflightReceipt:
    """Evaluate secret-bearing process state into a secret-free, zero-call receipt."""

    root = repository_root.resolve()
    findings: list[V6PreflightFinding] = []
    endpoint_evidence = _assess_endpoints(control, environment, findings)

    credential_present = bool(
        environment.get(control.endpoint_contract.credential_reference, "").strip()
    )
    _add_finding(
        findings,
        "credential:alibaba-bailian",
        credential_present,
        "ALIBABA_CREDENTIAL_PRESENT",
        "ALIBABA_CREDENTIAL_MISSING",
        "The Alibaba credential reference is present; its value is not persisted.",
        "The required Alibaba credential reference is missing.",
    )

    model_bindings = _assess_model_bindings(control, operator_inputs, environment, findings)
    _assess_runtime_bindings(control, host, findings)
    _assess_workloads(root, control, findings)
    pricing_ready = _assess_pricing(control, operator_inputs, findings)
    _assess_host(control, host, findings)

    status = (
        V6CanaryStatus.BLOCKED
        if any(item.status is V6CheckStatus.BLOCKED for item in findings)
        else V6CanaryStatus.READY
    )
    raw = {
        "experiment_id": control.experiment_id,
        "plan_digest": control.plan_digest,
        "canary_plan_digest": control.digest,
        "operator_input_digest": operator_inputs.digest,
        "status": status,
        "findings": tuple(findings),
        "endpoint_evidence": endpoint_evidence,
        "credential_reference": control.endpoint_contract.credential_reference,
        "credential_present": credential_present,
        "model_bindings": model_bindings,
        "host_observation": host,
        "pricing_status": "CONFIRMED" if pricing_ready else "OPERATOR_INPUTS_REQUIRED",
        "public_rate_fact_digest": control.public_rate_fact_digest,
        "judge_state": control.judge_initial_state,
    }
    draft = V6CanaryPreflightReceipt.model_construct(
        **raw,  # type: ignore[arg-type]
        receipt_digest="sha256:" + "0" * 64,
    )
    digest = _digest(draft.model_dump(mode="json", exclude={"receipt_digest"}))
    return V6CanaryPreflightReceipt.model_validate({**raw, "receipt_digest": digest})


async def run_v6_canary_preflight(
    repository_root: Path,
    operator_inputs: V6OperatorInputs,
    environment: Mapping[str, str] | None = None,
    *,
    host_observation: V6HostObservation | None = None,
) -> V6CanaryPreflightReceipt:
    control = load_v6_canary_control(repository_root)
    selected_environment = environment if environment is not None else os.environ
    host = host_observation or await collect_v6_host_observation(repository_root)
    return assess_v6_canary_preflight(
        repository_root, control, operator_inputs, selected_environment, host
    )


def persist_v6_preflight_receipt(receipt_root: Path, receipt: V6CanaryPreflightReceipt) -> Path:
    path = (
        receipt_root.resolve()
        / "preflight-receipts"
        / (receipt.receipt_digest.removeprefix("sha256:") + ".json")
    )
    return _write_immutable_json(path, receipt)


def authorize_v6_canary(
    preflight_receipt: V6CanaryPreflightReceipt,
    request: V6CanaryAuthorizationRequest,
) -> V6CanaryAuthorizationReceipt:
    if preflight_receipt.status is not V6CanaryStatus.READY:
        raise V6CanaryControlError("blocked V6 preflight cannot be authorized")
    if (
        request.preflight_receipt_digest != preflight_receipt.receipt_digest
        or request.canary_plan_digest != preflight_receipt.canary_plan_digest
        or request.plan_digest != preflight_receipt.plan_digest
    ):
        raise V6CanaryControlError("V6 canary authorization does not bind the preflight")
    return issue_v6_canary_authorization(request)


def persist_v6_canary_authorization(
    receipt_root: Path, receipt: V6CanaryAuthorizationReceipt
) -> Path:
    path = (
        receipt_root.resolve()
        / "authorizations"
        / (receipt.authorization_digest.removeprefix("sha256:") + ".json")
    )
    return _write_immutable_json(path, receipt)


def load_v6_preflight_receipt(path: Path) -> V6CanaryPreflightReceipt:
    try:
        return load_control_manifest(path, V6CanaryPreflightReceipt)
    except PreflightInputError as exc:
        raise V6CanaryControlError("V6 preflight receipt is invalid") from exc


def load_v6_canary_authorization(path: Path) -> V6CanaryAuthorizationReceipt:
    try:
        return load_control_manifest(path, V6CanaryAuthorizationReceipt)
    except PreflightInputError as exc:
        raise V6CanaryControlError("V6 canary authorization is invalid") from exc


class V6CanaryExecutionStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    ABORTED = "ABORTED"


class V6CanaryCallStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class V6CanaryFailureCategory(StrEnum):
    PROVIDER = "PROVIDER"
    HARNESS = "HARNESS"
    JUDGE_SCHEMA = "JUDGE_SCHEMA"
    OBSERVED_MODEL = "OBSERVED_MODEL"
    ARTIFACT = "ARTIFACT"
    INFRASTRUCTURE = "INFRASTRUCTURE"


class V6CanaryLaunchMarker(_FrozenModel):
    schema_version: Literal[1] = 1
    receipt_type: Literal["V6_CANARY_LAUNCH_MARKER"] = "V6_CANARY_LAUNCH_MARKER"
    experiment_id: Literal["core-real-matrix-v6"]
    canary_plan_digest: Sha256Digest
    preflight_receipt_digest: Sha256Digest
    authorization_digest: Sha256Digest
    call_id: str
    ordinal: int = Field(ge=1, le=3)
    provider_profile_id: str
    provider_profile_identity: Sha256Digest
    execution_binding_identity: Sha256Digest
    requested_model: str
    protocol: Protocol
    route_identity: str
    primary_attempt: Literal[1] = 1
    retry_count: Literal[0] = 0
    substitution_count: Literal[0] = 0
    marker_digest: Sha256Digest

    @model_validator(mode="after")
    def digest_is_bound(self) -> V6CanaryLaunchMarker:
        expected = _digest(self.model_dump(mode="json", exclude={"marker_digest"}))
        if self.marker_digest != expected:
            raise ValueError("V6 canary launch marker digest mismatch")
        return self


class V6CanaryCallEvidence(_FrozenModel):
    schema_version: Literal[1] = 1
    receipt_type: Literal["V6_CANARY_CALL_EVIDENCE"] = "V6_CANARY_CALL_EVIDENCE"
    experiment_id: Literal["core-real-matrix-v6"]
    canary_plan_digest: Sha256Digest
    launch_marker_digest: Sha256Digest
    call_id: str
    ordinal: int = Field(ge=1, le=3)
    role: V6CanaryCallRole
    provider_profile_id: str
    provider_profile_identity: Sha256Digest
    execution_binding_identity: Sha256Digest
    requested_model: str
    observed_model: str | None = Field(default=None, max_length=200)
    protocol: Protocol
    route_identity: str
    status: V6CanaryCallStatus
    safe_outcome: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$", max_length=100)
    failure_category: V6CanaryFailureCategory | None = None
    evidence_references: tuple[str, ...] = Field(min_length=1, max_length=4)
    evidence_digests: tuple[Sha256Digest, ...] = Field(min_length=1, max_length=4)
    primary_launches: Literal[1] = 1
    retry_count: Literal[0] = 0
    semantic_retry_count: Literal[0] = 0
    substitution_count: Literal[0] = 0
    raw_secret_values_persisted: Literal[False] = False
    raw_private_endpoints_persisted: Literal[False] = False
    evidence_digest: Sha256Digest

    @model_validator(mode="after")
    def evidence_is_bound(self) -> V6CanaryCallEvidence:
        if len(self.evidence_references) != len(self.evidence_digests):
            raise ValueError("V6 call evidence references and digests disagree")
        if (self.status is V6CanaryCallStatus.FAILED) != (self.failure_category is not None):
            raise ValueError("V6 call failure state is incoherent")
        expected = _digest(self.model_dump(mode="json", exclude={"evidence_digest"}))
        if self.evidence_digest != expected:
            raise ValueError("V6 call evidence digest mismatch")
        return self


class V6CanaryCloseout(_FrozenModel):
    schema_version: Literal[1] = 1
    receipt_type: Literal["V6_CANARY_CLOSEOUT"] = "V6_CANARY_CLOSEOUT"
    experiment_id: Literal["core-real-matrix-v6"]
    plan_digest: Literal["sha256:c18afc7b003a379f3456b23649e6d161da55e4fb5a34b4702dffbff35fb3604a"]
    canary_plan_digest: Sha256Digest
    preflight_receipt_digest: Sha256Digest
    authorization_digest: Sha256Digest
    status: V6CanaryExecutionStatus
    attempted_primary_calls: int = Field(ge=0, le=3)
    direct_primary_calls: int = Field(ge=0, le=1)
    harness_primary_calls: int = Field(ge=0, le=1)
    judge_primary_calls: int = Field(ge=0, le=1)
    completed_call_ids: tuple[str, ...]
    call_evidence_digests: tuple[Sha256Digest, ...]
    failing_call_id: str | None = None
    failure_category: V6CanaryFailureCategory | None = None
    max_primary_calls: Literal[3] = 3
    retries: Literal[0] = 0
    semantic_retries: Literal[0] = 0
    substitutions: Literal[0] = 0
    matrix_execution_authorized: Literal[False] = False
    judge_state: Literal["PROVISIONAL_PENDING_REAL_CANARY", "CANARY_QUALIFIED"]
    closeout_digest: Sha256Digest

    @model_validator(mode="after")
    def closeout_is_bound(self) -> V6CanaryCloseout:
        if len(self.completed_call_ids) != len(self.call_evidence_digests):
            raise ValueError("V6 closeout call identities and evidence disagree")
        if self.attempted_primary_calls != len(self.completed_call_ids):
            raise ValueError("V6 closeout attempted count disagrees with evidence")
        expected_counts = (
            int(EXPECTED_CALL_IDS[0] in self.completed_call_ids),
            int(EXPECTED_CALL_IDS[1] in self.completed_call_ids),
            int(EXPECTED_CALL_IDS[2] in self.completed_call_ids),
        )
        if (
            self.direct_primary_calls,
            self.harness_primary_calls,
            self.judge_primary_calls,
        ) != expected_counts:
            raise ValueError("V6 closeout primary-call category counts disagree")
        succeeded = self.status is V6CanaryExecutionStatus.SUCCEEDED
        if succeeded:
            if (
                self.completed_call_ids != EXPECTED_CALL_IDS
                or self.failing_call_id is not None
                or self.failure_category is not None
                or self.judge_state != "CANARY_QUALIFIED"
            ):
                raise ValueError("successful V6 closeout is incomplete")
        elif (
            self.failing_call_id is None
            or self.failure_category is None
            or self.judge_state != "PROVISIONAL_PENDING_REAL_CANARY"
        ):
            raise ValueError("aborted V6 closeout lacks a safe failure")
        expected = _digest(self.model_dump(mode="json", exclude={"closeout_digest"}))
        if self.closeout_digest != expected:
            raise ValueError("V6 canary closeout digest mismatch")
        return self


class V6CanaryInvoker(TypingProtocol):
    async def invoke(
        self, call: V6CanaryCall, marker: V6CanaryLaunchMarker
    ) -> V6CanaryCallEvidence: ...


@dataclass(frozen=True)
class ProductionV6CanaryInvoker:
    repository_root: Path
    environment: Mapping[str, str]
    artifact_root: Path
    host: V6HostObservation

    async def invoke(
        self, call: V6CanaryCall, marker: V6CanaryLaunchMarker
    ) -> V6CanaryCallEvidence:
        if call.call_id == EXPECTED_CALL_IDS[0]:
            return await self._direct(call, marker)
        if call.call_id == EXPECTED_CALL_IDS[1]:
            return await self._claude(call, marker)
        if call.call_id == EXPECTED_CALL_IDS[2]:
            return await self._judge(call, marker)
        raise V6CanaryControlError("attempted V6 canary call is not preregistered")

    async def _direct(
        self, call: V6CanaryCall, marker: V6CanaryLaunchMarker
    ) -> V6CanaryCallEvidence:
        profile = configured_alibaba_bailian_profile(
            call.requested_model,
            Protocol.CHAT_COMPLETIONS,
            max_output_tokens=call.max_output_tokens,
        ).model_copy(update={"request_timeout_seconds": call.timeout_seconds})
        assert call.task_reference is not None
        result = await DirectModelRunner(
            artifact_root=self._provider_artifact_root(call),
            environment=self.environment,
            allow_custom_endpoint=True,
        ).run(
            self.repository_root / call.task_reference,
            profile,
            adapter=OpenAICompatibleChatAdapter(environment=self.environment),
            run_id=call.call_id,
        )
        evidence = result.evidence
        failure = None
        if evidence.provider_failure is not None:
            failure = V6CanaryFailureCategory.PROVIDER
        elif evidence.outcome in {DirectModelOutcome.INFRA_ERROR}:
            failure = V6CanaryFailureCategory.INFRASTRUCTURE
        elif evidence.outcome is DirectModelOutcome.ARTIFACT_ERROR:
            failure = V6CanaryFailureCategory.ARTIFACT
        elif evidence.observed_model != call.requested_model:
            failure = V6CanaryFailureCategory.OBSERVED_MODEL
        return self._call_evidence(
            call,
            marker,
            observed_model=evidence.observed_model,
            safe_outcome=evidence.outcome.value.upper(),
            failure=failure,
            evidence_reference=str(result.artifact_directory.resolve()),
            evidence_digest=digest_tree(result.artifact_directory),
        )

    async def _claude(
        self, call: V6CanaryCall, marker: V6CanaryLaunchMarker
    ) -> V6CanaryCallEvidence:
        if self.host.claude_image is None or self.host.egress_proxy_image is None:
            raise V6CanaryControlError("production Claude or egress image identity is unavailable")
        profile = configured_qwen_alibaba_bailian_claude_profile(
            self.host.claude_image, execution_timeout_seconds=call.timeout_seconds
        )
        provider_url = self.environment["HARNESSLAB_ALIBABA_BAILIAN_ANTHROPIC_BASE_URL"]
        token = marker.marker_digest.removeprefix("sha256:")[:16]
        boundary = boundary_for_provider_url(
            provider_url,
            network_name=f"hl-v6-canary-{token}-internal",
            proxy_name=f"hl-v6-canary-{token}-proxy",
            proxy_image=self.host.egress_proxy_image,
        )
        backend = DockerMultiHarnessBackend(
            explicitly_enabled=True,
            credentials={
                "HARNESSLAB_ALIBABA_BAILIAN_ANTHROPIC_BASE_URL": provider_url,
                "HARNESSLAB_ALIBABA_BAILIAN_API_KEY": self.environment[
                    "HARNESSLAB_ALIBABA_BAILIAN_API_KEY"
                ],
            },
            egress_boundary=boundary,
        )
        assert call.task_reference is not None
        result = await MultiHarnessRunner(artifact_root=self._provider_artifact_root(call)).run(
            self.repository_root / call.task_reference,
            profile,
            adapter=ClaudeCodeAdapter(),
            backend=backend,
            run_id=call.call_id,
        )
        evidence = result.evidence
        failure = None
        if evidence.harness_failure is not None:
            failure = V6CanaryFailureCategory.HARNESS
        elif evidence.outcome is HarnessLaneOutcome.INFRA_ERROR:
            failure = V6CanaryFailureCategory.INFRASTRUCTURE
        elif evidence.outcome is HarnessLaneOutcome.ARTIFACT_ERROR:
            failure = V6CanaryFailureCategory.ARTIFACT
        elif (
            evidence.observed_model_status is not ObservedModelStatus.EXPOSED
            or evidence.observed_model != call.requested_model
        ):
            failure = V6CanaryFailureCategory.OBSERVED_MODEL
        references = [str(result.artifact_directory.resolve())]
        digests = [digest_tree(result.artifact_directory)]
        if backend.egress_attestation is not None:
            references.append(
                "egress-proxy:"
                f"{backend.egress_attestation.image.reference}@"
                f"{backend.egress_attestation.image.image_id}"
            )
            digests.append(backend.egress_attestation.digest)
        return self._call_evidence(
            call,
            marker,
            observed_model=evidence.observed_model,
            safe_outcome=evidence.outcome.value.upper(),
            failure=failure,
            evidence_reference=references[0],
            evidence_digest=digests[0],
            extra_references=tuple(references[1:]),
            extra_digests=tuple(digests[1:]),
        )

    async def _judge(
        self, call: V6CanaryCall, marker: V6CanaryLaunchMarker
    ) -> V6CanaryCallEvidence:
        suite_root = self.repository_root / "judge_suites/core-calibration/1.0.0"
        suite = load_judge_suite(suite_root)
        definition = load_judge_definition(suite_root / "definition.yaml")
        case = next(item for item in suite.public.cases if item.case_id == "label-l0-pass")
        profile = configured_alibaba_bailian_profile(
            call.requested_model,
            Protocol.CHAT_COMPLETIONS,
            max_output_tokens=call.max_output_tokens,
        ).model_copy(update={"request_timeout_seconds": call.timeout_seconds})
        profile_identity = judge_digest(profile)
        slot_facts = {
            "calibration_id": "core-real-matrix-v6-three-call-canary",
            "judge_cell_id": "judge-alibaba-bailian-glm-5.2-chat",
            "suite_digest": suite.suite_digest,
            "definition_digest": definition.definition_digest,
            "profile_identity": profile_identity,
            "case_id": case.case_id,
            "case_public_digest": case.public_digest,
            "repeat_index": 0,
            "order_variant": OrderVariant.NOT_APPLICABLE.value,
        }
        slot = JudgeEvaluationSlot(
            slot_id=judge_digest(slot_facts),
            slot_order=0,
            calibration_id="core-real-matrix-v6-three-call-canary",
            judge_cell_id="judge-alibaba-bailian-glm-5.2-chat",
            case_id=case.case_id,
            case_mode=case.mode,
            case_public_digest=case.public_digest,
            repeat_index=0,
            order_variant=OrderVariant.NOT_APPLICABLE,
        )
        result = await JudgeRunner(self._provider_artifact_root(call)).run(
            slot=slot,
            case=case,
            suite_id=suite.public.suite_id,
            suite_version=suite.public.version,
            suite_digest=suite.suite_digest,
            definition=definition,
            profile_identity=profile_identity,
            profile=profile,
            adapter=OpenAICompatibleChatAdapter(environment=self.environment),
        )
        failure = None
        if result.evidence.outcome is JudgeRunOutcome.PROVIDER_ERROR:
            failure = V6CanaryFailureCategory.PROVIDER
        elif result.evidence.outcome is JudgeRunOutcome.JUDGE_OUTPUT_ERROR:
            failure = V6CanaryFailureCategory.JUDGE_SCHEMA
        elif result.evidence.outcome is JudgeRunOutcome.ARTIFACT_ERROR:
            failure = V6CanaryFailureCategory.ARTIFACT
        elif (
            result.evidence.outcome is not JudgeRunOutcome.JUDGED
            or result.evidence.observed_judge_model != call.requested_model
        ):
            failure = V6CanaryFailureCategory.OBSERVED_MODEL
        if result.artifact_path is None or result.artifact_digest is None:
            raise V6CanaryControlError("V6 Judge evidence was not persisted")
        return self._call_evidence(
            call,
            marker,
            observed_model=result.evidence.observed_judge_model,
            safe_outcome=result.evidence.outcome.value,
            failure=failure,
            evidence_reference=str(result.artifact_path.resolve()),
            evidence_digest=result.artifact_digest,
        )

    def _provider_artifact_root(self, call: V6CanaryCall) -> Path:
        return self.artifact_root.resolve() / "provider-evidence" / call.call_id

    @staticmethod
    def _call_evidence(
        call: V6CanaryCall,
        marker: V6CanaryLaunchMarker,
        *,
        observed_model: str | None,
        safe_outcome: str,
        failure: V6CanaryFailureCategory | None,
        evidence_reference: str,
        evidence_digest: str,
        extra_references: tuple[str, ...] = (),
        extra_digests: tuple[str, ...] = (),
    ) -> V6CanaryCallEvidence:
        raw = {
            "experiment_id": V6_EXPERIMENT_ID,
            "canary_plan_digest": marker.canary_plan_digest,
            "launch_marker_digest": marker.marker_digest,
            "call_id": call.call_id,
            "ordinal": call.ordinal,
            "role": call.role,
            "provider_profile_id": call.provider_profile_id,
            "provider_profile_identity": call.provider_profile_identity,
            "execution_binding_identity": call.execution_binding_identity,
            "requested_model": call.requested_model,
            "observed_model": observed_model,
            "protocol": call.protocol,
            "route_identity": call.route_identity,
            "status": (
                V6CanaryCallStatus.SUCCEEDED if failure is None else V6CanaryCallStatus.FAILED
            ),
            "safe_outcome": safe_outcome,
            "failure_category": failure,
            "evidence_references": (evidence_reference, *extra_references),
            "evidence_digests": (evidence_digest, *extra_digests),
        }
        draft = V6CanaryCallEvidence.model_construct(
            **raw,  # type: ignore[arg-type]
            evidence_digest="sha256:" + "0" * 64,
        )
        digest = _digest(draft.model_dump(mode="json", exclude={"evidence_digest"}))
        return V6CanaryCallEvidence.model_validate({**raw, "evidence_digest": digest})


class V6CanaryControlPlane:
    """Exact three-call executor with crash-safe no-retry resume semantics."""

    def __init__(self, control: V6CanaryControl) -> None:
        self.control = control

    async def execute(
        self,
        *,
        preflight: V6CanaryPreflightReceipt,
        authorization: V6CanaryAuthorizationReceipt,
        invoker: V6CanaryInvoker,
        artifact_root: Path,
        allow_real_v6_canary: bool,
        calls: Sequence[V6CanaryCall] | None = None,
    ) -> V6CanaryCloseout:
        selected_calls = tuple(self.control.calls if calls is None else calls)
        self._validate_launch_authority(
            preflight, authorization, allow_real_v6_canary, selected_calls
        )
        output = artifact_root.resolve()
        closeout_path = output / "canary-closeout.json"
        self._reject_unregistered_artifacts(output)
        if closeout_path.exists():
            closeout = _load_json_model(closeout_path, V6CanaryCloseout, "V6 canary closeout")
            if (
                closeout.canary_plan_digest != self.control.digest
                or closeout.preflight_receipt_digest != preflight.receipt_digest
                or closeout.authorization_digest != authorization.authorization_digest
            ):
                raise V6CanaryControlError("V6 canary closeout resume binding mismatch")
            self._validate_existing_closeout(closeout, output, preflight, authorization)
            return closeout

        evidence: list[V6CanaryCallEvidence] = []
        for call in selected_calls:
            marker_path = output / "launch-journal" / f"{call.ordinal:03d}-{call.call_id}.json"
            evidence_path = output / "per-call-evidence" / f"{call.ordinal:03d}-{call.call_id}.json"
            if marker_path.exists():
                marker = _load_json_model(
                    marker_path, V6CanaryLaunchMarker, "V6 canary launch marker"
                )
                self._validate_marker(marker, call, preflight, authorization)
                if not evidence_path.exists():
                    raise V6CanaryControlError(
                        "a V6 canary call may have launched without terminal evidence; "
                        "retries are zero"
                    )
                item = _load_json_model(
                    evidence_path, V6CanaryCallEvidence, "V6 canary call evidence"
                )
                self._validate_call_evidence(item, call, marker)
                self._verify_call_artifacts(item, output)
            else:
                if evidence_path.exists():
                    raise V6CanaryControlError("V6 call evidence exists without a launch marker")
                provider_root = output / "provider-evidence" / call.call_id
                if provider_root.exists():
                    raise V6CanaryControlError("unbound provider evidence already exists")
                marker = self._launch_marker(call, preflight, authorization)
                _write_immutable_json(marker_path, marker)
                try:
                    item = await invoker.invoke(call, marker)
                except V6CanaryControlError:
                    raise
                except Exception as exc:
                    raise V6CanaryControlError(
                        "V6 canary invocation ended without terminal evidence; retries are zero"
                    ) from exc
                self._validate_call_evidence(item, call, marker)
                self._verify_call_artifacts(item, output)
                _write_immutable_json(evidence_path, item)
            evidence.append(item)
            if item.status is V6CanaryCallStatus.FAILED:
                closeout = self._closeout(preflight, authorization, tuple(evidence))
                _write_immutable_json(closeout_path, closeout)
                return closeout

        closeout = self._closeout(preflight, authorization, tuple(evidence))
        _write_immutable_json(closeout_path, closeout)
        return closeout

    def _validate_launch_authority(
        self,
        preflight: V6CanaryPreflightReceipt,
        authorization: V6CanaryAuthorizationReceipt,
        allowed: bool,
        calls: tuple[V6CanaryCall, ...],
    ) -> None:
        if not allowed:
            raise V6CanaryControlError("real V6 canary requires --allow-real-v6-canary")
        if preflight.status is not V6CanaryStatus.READY:
            raise V6CanaryControlError("failed V6 preflight leaves external-call count at zero")
        if calls != self.control.calls or len(calls) != 3:
            raise V6CanaryControlError(
                "V6 canary executor accepts exactly the preregistered three calls"
            )
        exact = (
            preflight.canary_plan_digest == self.control.digest,
            preflight.plan_digest == self.control.plan_digest,
            authorization.canary_plan_digest == self.control.digest,
            authorization.preflight_receipt_digest == preflight.receipt_digest,
            authorization.plan_digest == self.control.plan_digest,
            authorization.max_primary_calls == self.control.max_primary_calls,
            authorization.retries == self.control.retries,
            authorization.semantic_retries == self.control.semantic_retries,
            authorization.substitutions == self.control.substitutions,
            authorization.matrix_execution_authorized is False,
        )
        if not all(exact):
            raise V6CanaryControlError("V6 canary authorization boundary mismatch")

    def _launch_marker(
        self,
        call: V6CanaryCall,
        preflight: V6CanaryPreflightReceipt,
        authorization: V6CanaryAuthorizationReceipt,
    ) -> V6CanaryLaunchMarker:
        raw = {
            "experiment_id": self.control.experiment_id,
            "canary_plan_digest": self.control.digest,
            "preflight_receipt_digest": preflight.receipt_digest,
            "authorization_digest": authorization.authorization_digest,
            "call_id": call.call_id,
            "ordinal": call.ordinal,
            "provider_profile_id": call.provider_profile_id,
            "provider_profile_identity": call.provider_profile_identity,
            "execution_binding_identity": call.execution_binding_identity,
            "requested_model": call.requested_model,
            "protocol": call.protocol,
            "route_identity": call.route_identity,
        }
        draft = V6CanaryLaunchMarker.model_construct(
            **raw,  # type: ignore[arg-type]
            marker_digest="sha256:" + "0" * 64,
        )
        digest = _digest(draft.model_dump(mode="json", exclude={"marker_digest"}))
        return V6CanaryLaunchMarker.model_validate({**raw, "marker_digest": digest})

    def _validate_marker(
        self,
        marker: V6CanaryLaunchMarker,
        call: V6CanaryCall,
        preflight: V6CanaryPreflightReceipt,
        authorization: V6CanaryAuthorizationReceipt,
    ) -> None:
        if (
            marker.call_id,
            marker.ordinal,
            marker.provider_profile_id,
            marker.provider_profile_identity,
            marker.execution_binding_identity,
            marker.requested_model,
            marker.protocol,
            marker.route_identity,
            marker.canary_plan_digest,
            marker.preflight_receipt_digest,
            marker.authorization_digest,
        ) != (
            call.call_id,
            call.ordinal,
            call.provider_profile_id,
            call.provider_profile_identity,
            call.execution_binding_identity,
            call.requested_model,
            call.protocol,
            call.route_identity,
            self.control.digest,
            preflight.receipt_digest,
            authorization.authorization_digest,
        ):
            raise V6CanaryControlError("V6 launch marker binding mismatch")

    def _validate_existing_closeout(
        self,
        closeout: V6CanaryCloseout,
        output: Path,
        preflight: V6CanaryPreflightReceipt,
        authorization: V6CanaryAuthorizationReceipt,
    ) -> None:
        completed = set(closeout.completed_call_ids)
        expected_files = {
            f"{call.ordinal:03d}-{call.call_id}.json"
            for call in self.control.calls
            if call.call_id in completed
        }
        for directory_name in ("launch-journal", "per-call-evidence"):
            directory = output / directory_name
            actual_files = (
                {item.name for item in directory.iterdir()} if directory.exists() else set()
            )
            if actual_files != expected_files:
                raise V6CanaryControlError("V6 closeout artifact suffix is inconsistent")
        provider = output / "provider-evidence"
        provider_calls = {item.name for item in provider.iterdir()} if provider.exists() else set()
        if provider_calls != completed:
            raise V6CanaryControlError("V6 closeout provider-evidence suffix is inconsistent")
        observed_digests: list[str] = []
        for call in self.control.calls:
            if call.call_id not in completed:
                continue
            marker = _load_json_model(
                output / "launch-journal" / f"{call.ordinal:03d}-{call.call_id}.json",
                V6CanaryLaunchMarker,
                "V6 canary launch marker",
            )
            self._validate_marker(marker, call, preflight, authorization)
            evidence = _load_json_model(
                output / "per-call-evidence" / f"{call.ordinal:03d}-{call.call_id}.json",
                V6CanaryCallEvidence,
                "V6 canary call evidence",
            )
            self._validate_call_evidence(evidence, call, marker)
            self._verify_call_artifacts(evidence, output)
            observed_digests.append(evidence.evidence_digest)
        if tuple(observed_digests) != closeout.call_evidence_digests:
            raise V6CanaryControlError("V6 closeout evidence digest sequence mismatch")

    @staticmethod
    def _validate_call_evidence(
        evidence: V6CanaryCallEvidence,
        call: V6CanaryCall,
        marker: V6CanaryLaunchMarker,
    ) -> None:
        if (
            evidence.call_id,
            evidence.ordinal,
            evidence.role,
            evidence.provider_profile_id,
            evidence.provider_profile_identity,
            evidence.execution_binding_identity,
            evidence.requested_model,
            evidence.protocol,
            evidence.route_identity,
            evidence.launch_marker_digest,
        ) != (
            call.call_id,
            call.ordinal,
            call.role,
            call.provider_profile_id,
            call.provider_profile_identity,
            call.execution_binding_identity,
            call.requested_model,
            call.protocol,
            call.route_identity,
            marker.marker_digest,
        ):
            raise V6CanaryControlError("V6 per-call evidence binding mismatch")

    def _closeout(
        self,
        preflight: V6CanaryPreflightReceipt,
        authorization: V6CanaryAuthorizationReceipt,
        evidence: tuple[V6CanaryCallEvidence, ...],
    ) -> V6CanaryCloseout:
        failed = next((item for item in evidence if item.status is V6CanaryCallStatus.FAILED), None)
        succeeded = failed is None and len(evidence) == 3
        raw = {
            "experiment_id": self.control.experiment_id,
            "plan_digest": self.control.plan_digest,
            "canary_plan_digest": self.control.digest,
            "preflight_receipt_digest": preflight.receipt_digest,
            "authorization_digest": authorization.authorization_digest,
            "status": (
                V6CanaryExecutionStatus.SUCCEEDED if succeeded else V6CanaryExecutionStatus.ABORTED
            ),
            "attempted_primary_calls": len(evidence),
            "direct_primary_calls": int(
                EXPECTED_CALL_IDS[0] in {item.call_id for item in evidence}
            ),
            "harness_primary_calls": int(
                EXPECTED_CALL_IDS[1] in {item.call_id for item in evidence}
            ),
            "judge_primary_calls": int(EXPECTED_CALL_IDS[2] in {item.call_id for item in evidence}),
            "completed_call_ids": tuple(item.call_id for item in evidence),
            "call_evidence_digests": tuple(item.evidence_digest for item in evidence),
            "failing_call_id": failed.call_id if failed else None,
            "failure_category": failed.failure_category if failed else None,
            "judge_state": ("CANARY_QUALIFIED" if succeeded else "PROVISIONAL_PENDING_REAL_CANARY"),
        }
        draft = V6CanaryCloseout.model_construct(
            **raw,  # type: ignore[arg-type]
            closeout_digest="sha256:" + "0" * 64,
        )
        digest = _digest(draft.model_dump(mode="json", exclude={"closeout_digest"}))
        return V6CanaryCloseout.model_validate({**raw, "closeout_digest": digest})

    @staticmethod
    def _verify_call_artifacts(evidence: V6CanaryCallEvidence, output: Path) -> None:
        provider_root = (output / "provider-evidence").resolve()
        for reference, expected in zip(
            evidence.evidence_references, evidence.evidence_digests, strict=True
        ):
            if reference.startswith(("egress-proxy:", "egress-network:")):
                continue
            path = Path(reference).resolve()
            if provider_root not in path.parents:
                raise V6CanaryControlError("V6 call evidence escaped the provider artifact root")
            if path.is_dir():
                actual = digest_tree(path)
            elif path.is_file():
                actual = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
            else:
                raise V6CanaryControlError("V6 call evidence reference is unavailable")
            if actual != expected:
                raise V6CanaryControlError("V6 call evidence artifact digest mismatch")

    @staticmethod
    def _reject_unregistered_artifacts(output: Path) -> None:
        allowed = {
            "launch-journal",
            "per-call-evidence",
            "provider-evidence",
            "canary-closeout.json",
        }
        if output.exists() and any(item.name not in allowed for item in output.iterdir()):
            raise V6CanaryControlError("V6 canary artifact root contains unregistered state")
        closeout = output / "canary-closeout.json"
        if closeout.exists() and not closeout.is_file():
            raise V6CanaryControlError("V6 canary closeout path is not an immutable file")
        for directory, suffix in (
            (output / "launch-journal", ".json"),
            (output / "per-call-evidence", ".json"),
        ):
            if directory.exists() and any(
                not item.is_file()
                or item.suffix != suffix
                or not any(item.name.endswith(f"-{call_id}.json") for call_id in EXPECTED_CALL_IDS)
                for item in directory.iterdir()
            ):
                raise V6CanaryControlError("V6 canary artifact set contains a fourth call")
        provider = output / "provider-evidence"
        if provider.exists() and any(
            not item.is_dir() or item.name not in EXPECTED_CALL_IDS for item in provider.iterdir()
        ):
            raise V6CanaryControlError("V6 provider evidence contains a fourth call")


async def execute_real_v6_canary(
    repository_root: Path,
    *,
    operator_inputs: V6OperatorInputs,
    preflight_receipt: V6CanaryPreflightReceipt,
    authorization: V6CanaryAuthorizationReceipt,
    artifact_root: Path,
    allow_real_v6_canary: bool,
    environment: Mapping[str, str] | None = None,
    host_observation: V6HostObservation | None = None,
) -> V6CanaryCloseout:
    """Future real entry point; all local gates complete before call one can launch."""

    if not allow_real_v6_canary:
        raise V6CanaryControlError("real V6 canary requires --allow-real-v6-canary")
    selected_environment = environment if environment is not None else os.environ
    control = load_v6_canary_control(repository_root)
    current = await run_v6_canary_preflight(
        repository_root,
        operator_inputs,
        selected_environment,
        host_observation=host_observation,
    )
    if current != preflight_receipt:
        raise V6CanaryControlError(
            "current V6 preflight differs from the authorized immutable receipt"
        )
    invoker = ProductionV6CanaryInvoker(
        repository_root.resolve(),
        selected_environment,
        artifact_root.resolve(),
        current.host_observation,
    )
    return await V6CanaryControlPlane(control).execute(
        preflight=current,
        authorization=authorization,
        invoker=invoker,
        artifact_root=artifact_root,
        allow_real_v6_canary=True,
    )


def _load_json_model[ModelT: BaseModel](path: Path, model: type[ModelT], label: str) -> ModelT:
    try:
        return load_control_manifest(path, model)
    except PreflightInputError as exc:
        raise V6CanaryControlError(f"{label} is invalid") from exc


def _assess_endpoints(
    control: V6CanaryControl,
    environment: Mapping[str, str],
    findings: list[V6PreflightFinding],
) -> V6EndpointEvidence:
    contract = control.endpoint_contract
    openai = _parse_alibaba_endpoint(
        environment.get(contract.openai_base_url_reference),
        contract.openai_path,
        contract.dns_suffix,
    )
    anthropic = _parse_alibaba_endpoint(
        environment.get(contract.anthropic_base_url_reference),
        contract.anthropic_path,
        contract.dns_suffix,
    )
    _add_finding(
        findings,
        "endpoint:openai-compatible",
        openai is not None,
        "ALIBABA_OPENAI_ENDPOINT_IDENTITY_VERIFIED",
        "ALIBABA_OPENAI_ENDPOINT_INVALID",
        "The OpenAI-compatible endpoint has the frozen Alibaba region and path identity.",
        "The OpenAI-compatible endpoint is missing or does not match the frozen Alibaba identity.",
    )
    _add_finding(
        findings,
        "endpoint:anthropic-compatible",
        anthropic is not None,
        "ALIBABA_ANTHROPIC_ENDPOINT_IDENTITY_VERIFIED",
        "ALIBABA_ANTHROPIC_ENDPOINT_INVALID",
        "The Anthropic-compatible endpoint has the frozen Alibaba region and path identity.",
        "The Anthropic-compatible endpoint is missing or does not match the frozen identity.",
    )
    same_workspace = bool(openai and anthropic and openai[0] == anthropic[0])
    _add_finding(
        findings,
        "endpoint:same-workspace",
        same_workspace,
        "ALIBABA_ENDPOINT_WORKSPACE_MATCH",
        "ALIBABA_ENDPOINT_WORKSPACE_MISMATCH",
        "Both endpoint classes resolve to the same configured workspace boundary.",
        "Both endpoint classes must identify the same Alibaba workspace boundary.",
    )
    return V6EndpointEvidence(
        openai_endpoint_fingerprint=openai[1] if openai else None,
        anthropic_endpoint_fingerprint=anthropic[1] if anthropic else None,
        workspace_fingerprint=(
            _digest({"workspace_hostname": openai[0]})
            if same_workspace and openai is not None
            else None
        ),
        same_workspace=same_workspace,
    )


def _parse_alibaba_endpoint(
    value: str | None, expected_path: str, dns_suffix: str
) -> tuple[str, str] | None:
    if value is None or not value.strip():
        return None
    try:
        normalized = validate_provider_base_url(value)
        parsed = urlsplit(normalized)
    except ValueError:
        return None
    hostname = parsed.hostname
    if (
        hostname is None
        or not hostname.endswith(dns_suffix)
        or hostname == dns_suffix.removeprefix(".")
        or parsed.path != expected_path
    ):
        return None
    workspace = hostname.removesuffix(dns_suffix)
    if not workspace or any(
        character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in workspace
    ):
        return None
    return hostname, _digest({"runtime_endpoint": normalized})


def _assess_model_bindings(
    control: V6CanaryControl,
    operator: V6OperatorInputs,
    environment: Mapping[str, str],
    findings: list[V6PreflightFinding],
) -> tuple[V6ModelBindingEvidence, ...]:
    configured = {
        "qwen3.8-max": (
            operator.qwen_deployed_model_id,
            environment.get(V6_QWEN_MODEL_REFERENCE),
        ),
        "glm-5.2": (
            operator.glm_deployed_model_id,
            environment.get(V6_GLM_MODEL_REFERENCE),
        ),
    }
    matches: dict[str, bool] = {}
    for model, (operator_value, environment_value) in configured.items():
        matches[model] = operator_value == model and environment_value == model
        _add_finding(
            findings,
            f"model:{model}",
            matches[model],
            "ALIBABA_DEPLOYED_MODEL_ID_MATCH",
            "ALIBABA_DEPLOYED_MODEL_ID_MISMATCH",
            f"The deployed model ID for {model} exactly matches the frozen binding.",
            f"The deployed model ID for {model} is missing or differs from the frozen binding.",
        )
    return tuple(
        V6ModelBindingEvidence(
            provider_profile_id=call.provider_profile_id,
            provider_profile_identity=call.provider_profile_identity,
            requested_model=call.requested_model,
            deployed_model_reference=control.deployed_model_references[call.requested_model],
            deployed_model_matches=matches[call.requested_model],
            route_identity=call.route_identity,
            execution_binding_identity=call.execution_binding_identity,
        )
        for call in control.calls
    )


def _assess_runtime_bindings(
    control: V6CanaryControl,
    host: V6HostObservation,
    findings: list[V6PreflightFinding],
) -> None:
    direct = configured_alibaba_bailian_profile("qwen3.8-max", Protocol.CHAT_COMPLETIONS)
    judge = configured_alibaba_bailian_profile(
        "glm-5.2", Protocol.CHAT_COMPLETIONS, max_output_tokens=256
    ).model_copy(update={"request_timeout_seconds": 90})
    claude = (
        configured_qwen_alibaba_bailian_claude_profile(
            host.claude_image, execution_timeout_seconds=180
        )
        if host.claude_image is not None
        else None
    )
    valid = (
        direct.provider_route_identity == control.calls[0].route_identity,
        claude is not None
        and claude.provider_route == control.calls[1].route_identity
        and claude.requested_model == control.calls[1].requested_model,
        judge.provider_route_identity == control.calls[2].route_identity
        and judge.requested_model == control.calls[2].requested_model,
    )
    for call, ready in zip(control.calls, valid, strict=True):
        _add_finding(
            findings,
            f"binding:{call.call_id}",
            ready,
            "V6_CANARY_RUNTIME_BINDING_MATCH",
            "V6_CANARY_RUNTIME_BINDING_MISMATCH",
            f"Runtime binding {call.call_id} matches the frozen provider, model, route, "
            "and Harness.",
            f"Runtime binding {call.call_id} is unavailable or differs from the frozen contract.",
        )


def _assess_workloads(
    root: Path, control: V6CanaryControl, findings: list[V6PreflightFinding]
) -> None:
    subject = control.calls[0]
    assert subject.task_reference is not None and subject.task_digest is not None
    try:
        package = TaskPackage.load(root / subject.task_reference)
        task_ready = package.definition.content_digest == subject.task_digest
    except Exception:
        task_ready = False
    _add_finding(
        findings,
        "workload:subject-task",
        task_ready,
        "V6_CANARY_SUBJECT_TASK_MATCH",
        "V6_CANARY_SUBJECT_TASK_MISMATCH",
        "Both subject calls bind the frozen Core task package.",
        "The frozen Core canary task package is missing or changed.",
    )
    try:
        from harnesslab.judgelab.suite import load_judge_suite

        suite = load_judge_suite(root / "judge_suites/core-calibration/1.0.0")
        judge_ready = suite.suite_digest == control.judge_suite_digest and any(
            item.case_id == "label-l0-pass" for item in suite.public.cases
        )
    except Exception:
        judge_ready = False
    _add_finding(
        findings,
        "workload:judge-case",
        judge_ready,
        "V6_CANARY_JUDGE_CASE_MATCH",
        "V6_CANARY_JUDGE_CASE_MISMATCH",
        "The preferred Judge binds the frozen strict public calibration case.",
        "The frozen Judge suite or case identity is unavailable or changed.",
    )


def _assess_pricing(
    control: V6CanaryControl,
    operator: V6OperatorInputs,
    findings: list[V6PreflightFinding],
) -> bool:
    inputs = {
        "billing-region": operator.billing_region == "China (Beijing)",
        "billing-currency": operator.billing_currency == "USD",
        "qwen-model": operator.qwen_deployed_model_id == "qwen3.8-max",
        "glm-model": operator.glm_deployed_model_id == "glm-5.2",
        "cache-batch": _explicit_operator_statement(operator.cache_or_batch_adjustments),
        "promotions": _explicit_operator_statement(operator.account_specific_promotions),
        "tax": _explicit_operator_statement(operator.tax_treatment),
        "fx": _explicit_operator_statement(operator.fx_treatment),
        "rate-applicability": operator.public_region_and_model_rates_apply is True,
        "account-reference": operator.account_reference_fingerprint is not None,
        "host-attestation": _explicit_operator_statement(operator.host_attestation_reference),
    }
    for name, ready in inputs.items():
        _add_finding(
            findings,
            f"pricing:{name}",
            ready,
            "V6_OPERATOR_PRICING_INPUT_CONFIRMED",
            "V6_OPERATOR_PRICING_INPUT_REQUIRED",
            f"Operator pricing/account input {name} is explicitly confirmed.",
            f"Operator pricing/account input {name} remains required; cost is not treated as zero.",
        )
    return all(inputs.values()) and control.public_rate_fact_digest.startswith("sha256:")


def _explicit_operator_statement(value: str | None) -> bool:
    if value is None or not value.strip():
        return False
    return value.strip().upper() not in {
        "UNKNOWN",
        "UNCONFIRMED",
        "TBD",
        "NOT_AVAILABLE",
        "N/A",
    }


def _assess_host(
    control: V6CanaryControl,
    host: V6HostObservation,
    findings: list[V6PreflightFinding],
) -> None:
    minimums = control.host_minimums
    checks = (
        ("docker", host.docker_ready, "PRODUCTION_DOCKER_READY", "PRODUCTION_DOCKER_NOT_READY"),
        (
            "egress-isolation",
            host.egress_isolation_ready,
            "PRODUCTION_EGRESS_ISOLATION_READY",
            "PRODUCTION_EGRESS_ISOLATION_NOT_READY",
        ),
        (
            "cpu",
            host.cpu_count is not None and host.cpu_count >= minimums.cpu_count,
            "PRODUCTION_CPU_READY",
            "PRODUCTION_CPU_INSUFFICIENT",
        ),
        (
            "memory",
            host.memory_bytes is not None and host.memory_bytes >= minimums.memory_bytes,
            "PRODUCTION_MEMORY_READY",
            "PRODUCTION_MEMORY_INSUFFICIENT",
        ),
        (
            "disk",
            host.disk_free_bytes is not None and host.disk_free_bytes >= minimums.disk_free_bytes,
            "PRODUCTION_DISK_READY",
            "PRODUCTION_DISK_INSUFFICIENT",
        ),
        (
            "claude-image",
            _image_matches(host.claude_image, minimums.claude_image_reference),
            "PRODUCTION_CLAUDE_IMAGE_READY",
            "PRODUCTION_CLAUDE_IMAGE_NOT_READY",
        ),
        (
            "egress-proxy-image",
            _image_matches(host.egress_proxy_image, minimums.egress_proxy_image_reference),
            "PRODUCTION_EGRESS_PROXY_IMAGE_READY",
            "PRODUCTION_EGRESS_PROXY_IMAGE_NOT_READY",
        ),
    )
    for name, ready, pass_code, block_code in checks:
        _add_finding(
            findings,
            f"host:{name}",
            ready,
            pass_code,
            block_code,
            f"Production host check {name} passed.",
            f"Production host check {name} failed or is unavailable.",
        )


def _image_matches(image: ImageIdentity | None, reference: str) -> bool:
    return bool(
        image is not None
        and image.reference == reference
        and image.image_id != "sha256:" + "0" * 64
    )


def _validate_v6_source_control(root: Path, control: V6CanaryControl) -> None:
    try:
        raw = json.loads((root / control.v6_control_reference).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise V6CanaryControlError("frozen V6 source control is unreadable") from exc
    preregistration = raw.get("canary_preregistration", {})
    execution = raw.get("execution_state", {})
    judge = raw.get("judge", {})
    pricing = raw.get("pricing", {})
    cells = {
        item.get("provider_profile_id"): item
        for item in raw.get("cells", [])
        if isinstance(item, dict)
    }
    candidates = {
        item.get("provider_profile_id"): item
        for item in judge.get("candidates", [])
        if isinstance(item, dict)
    }
    subject_bindings_match = all(
        source.get("provider_profile_identity") == call.provider_profile_identity
        and source.get("execution_binding_identity") == call.execution_binding_identity
        and source.get("requested_model") == call.requested_model
        and source.get("protocol") == call.protocol.value
        and source.get("harness_id") == call.harness_id
        and source.get("harness_profile_id") == call.harness_profile_id
        for call in control.calls[:2]
        for source in (cells.get(call.provider_profile_id, {}),)
    )
    judge_binding = candidates.get(control.calls[2].provider_profile_id, {})
    judge_binding_matches = (
        judge_binding.get("provider_profile_identity") == control.calls[2].provider_profile_identity
        and control.calls[2].execution_binding_identity
        == control.calls[2].provider_profile_identity
        and judge_binding.get("requested_model") == control.calls[2].requested_model
        and judge_binding.get("protocol") == control.calls[2].protocol.value
    )
    exact = (
        raw.get("experiment_id") == control.experiment_id,
        raw.get("plan_digest") == control.plan_digest,
        preregistration.get("max_future_calls") == 3,
        preregistration.get("retries") == 0,
        preregistration.get("matrix_acquisition_allowed") is False,
        judge.get("preferred_candidate") == control.calls[2].provider_profile_id,
        judge.get("formal_judge_execution_gate") == "BLOCKED_PENDING_SELECTED_CANDIDATE_CANARY",
        pricing.get("public_rate_fact_digest") == control.public_rate_fact_digest,
        subject_bindings_match,
        judge_binding_matches,
        execution
        == {
            "keyless_provider_calls": 0,
            "real_harness_calls": 0,
            "real_judge_calls": 0,
            "real_v6_execution_started": False,
        },
    )
    if not all(exact):
        raise V6CanaryControlError("frozen V6 source control conflicts with canary invariants")


def _validate_registry_and_workloads(root: Path, control: V6CanaryControl) -> None:
    catalog = build_registry_catalog(root, {})
    profiles = {item.profile_id: item for item in catalog.provider_model_profiles}
    harness_profiles = {
        profile.profile_id: (harness.harness_id, profile)
        for harness in catalog.harnesses
        for profile in harness.profiles
    }
    for call in control.calls:
        profile = profiles.get(call.provider_profile_id)
        if (
            profile is None
            or profile.profile_identity != call.provider_profile_identity
            or profile.requested_model != call.requested_model
            or profile.protocol is not call.protocol
            or profile.provider_route_identity != call.route_identity
        ):
            raise V6CanaryControlError(f"frozen registry profile drifted: {call.call_id}")
        if call.role is not V6CanaryCallRole.JUDGE:
            harness = harness_profiles.get(call.harness_profile_id)
            if (
                harness is None
                or harness[0] != call.harness_id
                or call.provider_profile_id not in harness[1].supported_provider_profile_ids
            ):
                raise V6CanaryControlError(f"frozen Harness binding drifted: {call.call_id}")


def _verify_protected_file(root: Path, reference: str, expected: str) -> None:
    path = (root / reference).resolve()
    if root not in path.parents or not path.is_file():
        raise V6CanaryControlError("protected V6 input is unavailable")
    actual = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    if actual != expected:
        raise V6CanaryControlError("protected V6 input digest mismatch")


def _add_finding(
    findings: list[V6PreflightFinding],
    check_id: str,
    passed: bool,
    pass_code: str,
    block_code: str,
    pass_detail: str,
    block_detail: str,
) -> None:
    findings.append(
        V6PreflightFinding(
            check_id=check_id,
            status=V6CheckStatus.PASS if passed else V6CheckStatus.BLOCKED,
            reason_code=pass_code if passed else block_code,
            detail=pass_detail if passed else block_detail,
        )
    )


def _write_immutable_json(path: Path, value: BaseModel) -> Path:
    payload = (
        json.dumps(
            value.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        + "\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        try:
            existing = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise V6CanaryControlError("immutable evidence path already exists unreadably") from exc
        if existing != payload:
            raise V6CanaryControlError(
                "immutable evidence path already contains different bytes"
            ) from None
        return path
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        with suppress(OSError):
            path.unlink()
        raise
    return path


def _digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(payload.encode()).hexdigest()


__all__ = [
    "EXPECTED_CALL_IDS",
    "V6CanaryAuthorizationReceipt",
    "V6CanaryAuthorizationRequest",
    "V6CanaryControl",
    "V6CanaryControlError",
    "V6CanaryPreflightReceipt",
    "V6CanaryStatus",
    "V6HostObservation",
    "V6OperatorInputs",
    "assess_v6_canary_preflight",
    "authorize_v6_canary",
    "collect_v6_host_observation",
    "load_v6_canary_authorization",
    "load_v6_canary_control",
    "load_v6_operator_inputs",
    "load_v6_preflight_receipt",
    "persist_v6_canary_authorization",
    "persist_v6_preflight_receipt",
    "run_v6_canary_preflight",
]
