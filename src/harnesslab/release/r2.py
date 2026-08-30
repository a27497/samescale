from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from harnesslab.contracts.common import Identifier, Sha256Digest
from harnesslab.egress import preflight_egress_network_isolation
from harnesslab.release.smoke import (
    EXPECTED_V5_CALL_IDS,
    ProductionSmokeInvoker,
    SmokeCallFailure,
    SmokeCallResult,
    SmokeControlPlane,
    SmokeControlPlaneError,
    SmokeFailureCategory,
    resolve_runtime_identities,
)


class R2StrictModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class R2CanonicalModel(R2StrictModel):
    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @property
    def digest(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_json().encode()).hexdigest()


class PortableEvidenceReference(R2StrictModel):
    logical_namespace: str = Field(min_length=1, max_length=300)
    call_id: Identifier
    content_digest: Sha256Digest

    @model_validator(mode="after")
    def namespace_is_portable(self) -> PortableEvidenceReference:
        path = PurePosixPath(self.logical_namespace)
        if path.is_absolute() or ".." in path.parts or "\\" in self.logical_namespace:
            raise ValueError("evidence namespace must be repository-logical and portable")
        return self


class ReadinessControlVector(R2CanonicalModel):
    call_id: Identifier
    task_id: Identifier
    task_version: str
    task_digest: Sha256Digest
    workspace_input_digest: Sha256Digest
    verifier_identity: Sha256Digest
    requested_model: str
    protocol: str
    provider_route: str
    credential_references: tuple[str, ...]
    provider_profile_identity: Sha256Digest
    harness_runtime: str
    harness_version: str
    harness_image_identity: str
    runner_contract: str
    reasoning_effort: str
    prompt_contract: str
    resource_envelope_identity: Sha256Digest
    max_output_tokens: int = Field(gt=0)
    timeout_seconds: int = Field(gt=0, le=600)
    network_security_policy: str


class ReadinessEquivalenceEntry(R2StrictModel):
    call_id: Identifier
    source_evidence: PortableEvidenceReference
    source: ReadinessControlVector
    target: ReadinessControlVector
    equivalent: Literal[True] = True

    @model_validator(mode="after")
    def controls_match_exactly(self) -> ReadinessEquivalenceEntry:
        if self.call_id != self.source_evidence.call_id:
            raise ValueError("source evidence call identity drifted")
        if self.source.call_id != self.call_id or self.target.call_id != self.call_id:
            raise ValueError("readiness vector call identity drifted")
        if self.source != self.target:
            raise ValueError("v4/v5 readiness controls are not exactly equivalent")
        return self


class V4ToV5ReadinessEquivalence(R2CanonicalModel):
    schema_version: Literal[1] = 1
    equivalence_id: Literal["V4_TO_V5_READINESS_EQUIVALENCE"]
    source_plan_reference: Literal["release/core-real-evidence-plan-v4.json"]
    source_plan_digest: Sha256Digest
    source_smoke_reference: Literal["release/core-real-smoke-plan-v4.json"]
    source_smoke_digest: Sha256Digest
    target_plan_reference: Literal["release/core-real-evidence-plan-v5.json"]
    target_plan_digest: Sha256Digest
    target_smoke_reference: Literal["release/core-real-smoke-plan-v5.json"]
    target_smoke_digest: Sha256Digest
    scope: Literal["TECHNICAL_READINESS_ONLY"] = "TECHNICAL_READINESS_ONLY"
    does_not_satisfy: tuple[
        Literal["V5_MATRIX_EVIDENCE", "FORMAL_STATISTICS", "K_B3_EVIDENCE", "K_C_EVIDENCE"],
        ...,
    ]
    entries: tuple[ReadinessEquivalenceEntry, ...]

    @model_validator(mode="after")
    def exact_six_call_equivalence(self) -> V4ToV5ReadinessEquivalence:
        expected = EXPECTED_V5_CALL_IDS[:6]
        if tuple(item.call_id for item in self.entries) != expected:
            raise ValueError("readiness equivalence must bind exact unchanged Calls 1-6")
        if self.does_not_satisfy != (
            "V5_MATRIX_EVIDENCE",
            "FORMAL_STATISTICS",
            "K_B3_EVIDENCE",
            "K_C_EVIDENCE",
        ):
            raise ValueError("readiness equivalence scope limitations drifted")
        return self


class R2CanaryPolicy(R2CanonicalModel):
    schema_version: Literal[1] = 1
    policy_id: Literal["kb2r-r2-v5-canary"]
    base_commit: Literal["290d99c26425dcf1b60bfc711a93640edd37645e"]
    frozen_implementation_commit: str = Field(pattern=r"^[0-9a-f]{40}$")
    release_plan_reference: Literal["release/core-real-evidence-plan-v5.json"]
    release_plan_digest: Sha256Digest
    smoke_plan_reference: Literal["release/core-real-smoke-plan-v5.json"]
    smoke_plan_digest: Sha256Digest
    readiness_equivalence_reference: Literal["release/kb2r-r2-readiness-equivalence.json"]
    readiness_equivalence_digest: Sha256Digest
    cell7_call_id: Literal["smoke-7-model-deepseek-v4flash-chat"]
    cell7_profile_id: Literal["model-deepseek-v4flash-chat"]
    judge_call_id: Literal["smoke-8-judge-glm52-opencode-go"]
    judge_profile_id: Literal["judge-glm52-opencode-go-chat"]
    max_new_subject_launches: Literal[1] = 1
    max_new_judge_launches: Literal[1] = 1
    max_new_external_launches: Literal[2] = 2
    recovery_attempts_allowed: Literal[0] = 0
    substitution_after_freeze_allowed: Literal[False] = False
    protected_file_sha256: dict[str, Sha256Digest]

    @model_validator(mode="after")
    def tracked_references_are_portable(self) -> R2CanaryPolicy:
        for reference in (
            self.release_plan_reference,
            self.smoke_plan_reference,
            self.readiness_equivalence_reference,
            *self.protected_file_sha256,
        ):
            path = PurePosixPath(reference)
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("R2 policy contains a nonportable tracked reference")
        return self


class R2CanaryReceipt(R2CanonicalModel):
    schema_version: Literal[1] = 1
    policy_id: Literal["kb2r-r2-v5-canary"]
    status: Literal["SUCCEEDED", "HARD_STOPPED"]
    new_subject_launches: int = Field(ge=0, le=1)
    new_judge_launches: int = Field(ge=0, le=1)
    total_new_external_launches: int = Field(ge=0, le=2)
    recovery_attempts: Literal[0] = 0
    cell7_outcome: str
    judge_outcome: str
    failing_call_id: str | None = None
    failure_category: SmokeFailureCategory | None = None
    results: tuple[SmokeCallResult, ...]

    @model_validator(mode="after")
    def launch_arithmetic_is_exact(self) -> R2CanaryReceipt:
        if self.total_new_external_launches != self.new_subject_launches + self.new_judge_launches:
            raise ValueError("R2 launch arithmetic drifted")
        if self.new_judge_launches and self.new_subject_launches != 1:
            raise ValueError("Judge cannot launch before Cell 7")
        if self.status == "SUCCEEDED" and (
            self.new_subject_launches != 1
            or self.new_judge_launches != 1
            or self.failing_call_id is not None
        ):
            raise ValueError("successful R2 canary requires exactly one subject and one Judge")
        return self


def _load(path: Path, model: type[R2CanonicalModel], label: str) -> R2CanonicalModel:
    try:
        return model.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise SmokeControlPlaneError(f"invalid {label}") from exc


def load_readiness_equivalence(path: Path) -> V4ToV5ReadinessEquivalence:
    value = _load(path, V4ToV5ReadinessEquivalence, "R2 readiness equivalence")
    assert isinstance(value, V4ToV5ReadinessEquivalence)
    return value


def load_r2_canary_policy(path: Path) -> R2CanaryPolicy:
    value = _load(path, R2CanaryPolicy, "R2 canary policy")
    assert isinstance(value, R2CanaryPolicy)
    return value


def validate_r2_policy(
    repository_root: Path,
    control: SmokeControlPlane,
    policy: R2CanaryPolicy,
    equivalence: V4ToV5ReadinessEquivalence,
) -> None:
    root = repository_root.resolve()
    if control.release_plan.digest != policy.release_plan_digest:
        raise SmokeControlPlaneError("R2 release plan digest drifted")
    if control.smoke_plan_digest != policy.smoke_plan_digest:
        raise SmokeControlPlaneError("R2 smoke plan digest drifted")
    if equivalence.digest != policy.readiness_equivalence_digest:
        raise SmokeControlPlaneError("R2 readiness equivalence digest drifted")
    if (
        equivalence.target_plan_digest != control.release_plan.digest
        or equivalence.target_smoke_digest != control.smoke_plan_digest
    ):
        raise SmokeControlPlaneError("R2 readiness target binding drifted")
    for reference, expected in policy.protected_file_sha256.items():
        path = (root / reference).resolve()
        if root not in path.parents or not path.is_file():
            raise SmokeControlPlaneError(f"protected R2 input unavailable: {reference}")
        actual = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != expected:
            raise SmokeControlPlaneError(f"protected R2 input changed: {reference}")


def _persist_receipt(path: Path, receipt: R2CanaryReceipt) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        handle.write(receipt.canonical_json() + "\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


async def execute_r2_canary(
    repository_root: Path,
    *,
    allow_real_canary: bool,
    environment: Mapping[str, str],
    artifact_root: Path,
    policy_path: Path,
    equivalence_path: Path,
) -> R2CanaryReceipt:
    if not allow_real_canary:
        raise SmokeControlPlaneError("R2 canary requires --allow-real-canary")
    root = repository_root.resolve()
    output = artifact_root.resolve()
    receipt_path = output / "r2-canary-execution.json"
    if receipt_path.exists() or any(
        (output / call_id).exists() for call_id in EXPECTED_V5_CALL_IDS[6:]
    ):
        raise SmokeControlPlaneError("R2 canary evidence already exists; retries are forbidden")
    control = SmokeControlPlane.load(root, plan_version="v5")
    policy = load_r2_canary_policy(policy_path)
    equivalence = load_readiness_equivalence(equivalence_path)
    validate_r2_policy(root, control, policy, equivalence)
    control.validate_real_environment(environment)
    await preflight_egress_network_isolation()
    runtime = await resolve_runtime_identities()
    bindings = control.resolve_real_bindings(environment, runtime)
    invoker = ProductionSmokeInvoker(
        root,
        environment,
        output,
        smoke_plan_id=control.smoke_plan.plan_id,
    )
    results: list[SmokeCallResult] = []
    subject_launches = 0
    judge_launches = 0
    cell7_outcome = "NOT_RUN"
    judge_outcome = "NOT_RUN"
    failing_call_id: str | None = None
    failure_category: SmokeFailureCategory | None = None
    subject_launches = 1
    try:
        result = await invoker.invoke(bindings[6])
        results.append(result)
        cell7_outcome = "VALID_CAPABILITY_OBSERVATION"
    except SmokeCallFailure as exc:
        if exc.evidence_result is not None:
            results.append(exc.evidence_result)
        cell7_outcome = "HARD_STOPPED"
        failing_call_id = policy.cell7_call_id
        failure_category = exc.category
    except Exception:
        cell7_outcome = "HARD_STOPPED"
        failing_call_id = policy.cell7_call_id
        failure_category = SmokeFailureCategory.INFRASTRUCTURE
    if failing_call_id is None:
        judge_launches = 1
        try:
            result = await invoker.invoke(bindings[7])
            results.append(result)
            judge_outcome = "VALID_JUDGE_OBSERVATION"
        except SmokeCallFailure as exc:
            if exc.evidence_result is not None:
                results.append(exc.evidence_result)
            judge_outcome = "HARD_STOPPED"
            failing_call_id = policy.judge_call_id
            failure_category = exc.category
        except Exception:
            judge_outcome = "HARD_STOPPED"
            failing_call_id = policy.judge_call_id
            failure_category = SmokeFailureCategory.INFRASTRUCTURE
    receipt = R2CanaryReceipt(
        policy_id=policy.policy_id,
        status="SUCCEEDED" if failing_call_id is None else "HARD_STOPPED",
        new_subject_launches=subject_launches,
        new_judge_launches=judge_launches,
        total_new_external_launches=subject_launches + judge_launches,
        cell7_outcome=cell7_outcome,
        judge_outcome=judge_outcome,
        failing_call_id=failing_call_id,
        failure_category=failure_category,
        results=tuple(results),
    )
    _persist_receipt(receipt_path, receipt)
    return receipt
