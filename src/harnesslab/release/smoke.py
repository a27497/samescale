from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal
from typing import Protocol as TypingProtocol
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from harnesslab.contracts.common import Protocol
from harnesslab.contracts.model import ModelProfile
from harnesslab.contracts.provider import ProviderProfile
from harnesslab.egress import (
    EGRESS_PROXY_IMAGE,
    EgressProxyRuntime,
    ProviderScopedDockerBoundary,
    ProxySecurityAttestation,
    boundary_for_provider_url,
    preflight_egress_network_isolation,
)
from harnesslab.harness_lane.docker_backend import DockerCodexBackend
from harnesslab.harness_lane.models import (
    CodexHarnessProfile,
    HarnessFailureCategory,
    HarnessLaneOutcome,
    ObservedModelStatus,
    is_capability_harness_failure,
)
from harnesslab.harness_lane.profile import (
    CODEX_IMAGE,
    configured_gpt56_relay_codex_profile,
)
from harnesslab.harness_lane.runner import CodexHarnessRunner
from harnesslab.harness_lane.runtime import CodexRuntime
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
from harnesslab.model_lane.models import DirectModelOutcome, ProviderFailureCategory
from harnesslab.model_lane.providers import (
    AnthropicMessagesAdapter,
    OpenAICompatibleChatAdapter,
    OpenAIResponsesAdapter,
)
from harnesslab.model_lane.runner import DirectModelRunner
from harnesslab.multi_harness.adapter import ClaudeCodeAdapter, DeepSeekHarnessAdapter
from harnesslab.multi_harness.docker_backend import DockerMultiHarnessBackend
from harnesslab.multi_harness.models import (
    ClaudeCredentialTransport,
    HarnessKind,
    MultiHarnessProfile,
    TraceCoverage,
)
from harnesslab.multi_harness.profile import (
    CLAUDE_IMAGE,
    DEEPSEEK_IMAGE,
    configured_deepseek_v4flash_profile,
    configured_qwen_opencode_go_claude_profile,
)
from harnesslab.multi_harness.runner import MultiHarnessRunner
from harnesslab.multi_harness.runtime import MultiHarnessRuntime
from harnesslab.release.contracts import (
    CoreReleaseError,
    load_core_corpus,
    load_real_evidence_plan,
    load_real_smoke_plan,
)
from harnesslab.release.models import RealEvidencePlan, RealSmokeCall, RealSmokePlan
from harnesslab.release.provider_config import configured_model_profile
from harnesslab.sandbox.models import ImageIdentity
from harnesslab.tasks.package import TaskPackage, TaskPackageError, digest_tree

EXPECTED_CALL_IDS = (
    "smoke-1-model-gpt56-relay-responses",
    "smoke-2-model-qwen38-opencode-go-messages",
    "smoke-3-model-deepseek-v4pro-chat",
    "smoke-4-harness-codex-gpt56-medium",
    "smoke-5-harness-codex-gpt56-high",
    "smoke-6-harness-claude-qwen38-opencode-go",
    "smoke-7-harness-deepseek-v4flash",
    "smoke-8-judge-glm52-opencode-go",
)
EXPECTED_RUNNERS = (
    "DirectModelRunner",
    "DirectModelRunner",
    "DirectModelRunner",
    "CodexHarnessRunner",
    "CodexHarnessRunner",
    "MultiHarnessRunner",
    "MultiHarnessRunner",
    "JudgeRunner",
)
EXPECTED_ADAPTERS = (
    "OpenAIResponsesAdapter",
    "AnthropicMessagesAdapter",
    "OpenAICompatibleChatAdapter",
    "DockerCodexBackend",
    "DockerCodexBackend",
    "DockerMultiHarnessBackend",
    "DockerMultiHarnessBackend",
    "OpenAICompatibleChatAdapter",
)
REQUIRED_CONFIGURATION_REFERENCES = (
    "HARNESSLAB_GPT56_RELAY_BASE_URL",
    "HARNESSLAB_GPT56_RELAY_API_KEY",
    "HARNESSLAB_OPENCODE_GO_API_KEY",
    "DEEPSEEK_API_KEY",
)
SUBJECT_TASK_ID = "core-python-deduplicate"
JUDGE_CASE_REFERENCE = "judge_suites/core-calibration/1.0.0#label-l0-pass"
PLAN_PATHS = {
    "v2": (
        "release/core-real-evidence-plan.json",
        "release/core-real-smoke-plan.json",
    ),
    "v3": (
        "release/core-real-evidence-plan-v3.json",
        "release/core-real-smoke-plan-v3.json",
    ),
    "v4": (
        "release/core-real-evidence-plan-v4.json",
        "release/core-real-smoke-plan-v4.json",
    ),
}


class SmokeControlPlaneError(CoreReleaseError):
    """The frozen K-B1 smoke cannot be resolved or safely executed."""


class SmokeFailureCategory(StrEnum):
    CONFIGURATION = "CONFIGURATION"
    AUTHENTICATION = "AUTHENTICATION"
    ROUTE_MISMATCH = "ROUTE_MISMATCH"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
    OBSERVED_MODEL_CONFLICT = "OBSERVED_MODEL_CONFLICT"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"
    HARNESS_FAILURE = "HARNESS_FAILURE"
    ARTIFACT_INTEGRITY = "ARTIFACT_INTEGRITY"
    SECURITY_BOUNDARY = "SECURITY_BOUNDARY"
    JUDGE_PERSISTENCE = "JUDGE_PERSISTENCE"
    INFRASTRUCTURE = "INFRASTRUCTURE"


class ObservedModelAssessment(StrEnum):
    VERIFIED = "VERIFIED"
    OBSERVED_MODEL_MISSING = "OBSERVED_MODEL_MISSING"


class SmokeCallFailure(RuntimeError):
    def __init__(
        self,
        category: SmokeFailureCategory,
        message: str,
        evidence_result: SmokeCallResult | None = None,
    ) -> None:
        super().__init__(message)
        self.category = category
        self.evidence_result = evidence_result


def _validate_harness_observed_model(
    profile: CodexHarnessProfile | MultiHarnessProfile,
    *,
    trace_coverage: TraceCoverage | str,
    observed_model_status: ObservedModelStatus,
    observed_model: str | None,
) -> ObservedModelAssessment:
    """Validate each harness's declared observation surface without inferring identity."""

    coverage = TraceCoverage(trace_coverage)
    if isinstance(profile, CodexHarnessProfile):
        valid_coverage = coverage is TraceCoverage.FULL_STREAM
        if (
            valid_coverage
            and observed_model_status is ObservedModelStatus.NOT_EXPOSED
            and observed_model is None
        ):
            return ObservedModelAssessment.OBSERVED_MODEL_MISSING
        valid = (
            valid_coverage
            and observed_model_status is ObservedModelStatus.EXPOSED
            and observed_model == profile.requested_model
        )
    elif profile.harness is HarnessKind.CLAUDE_CODE:
        valid = (
            coverage is TraceCoverage.FULL_STREAM
            and observed_model_status is ObservedModelStatus.EXPOSED
            and observed_model == profile.requested_model
        )
    else:
        valid = (
            coverage is TraceCoverage.FINAL_OUTPUT_ONLY
            and observed_model_status is ObservedModelStatus.NOT_EXPOSED
            and observed_model is None
        )
    if not valid:
        raise SmokeCallFailure(
            SmokeFailureCategory.OBSERVED_MODEL_CONFLICT,
            f"{profile.harness} observed-model contract failed",
        )
    return ObservedModelAssessment.VERIFIED


class SmokeCallResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    call_id: str
    evidence_references: tuple[str, ...] = ()
    evidence_digests: tuple[str, ...] = ()


class SmokeExecutionStatus(StrEnum):
    SUCCEEDED = "SUCCEEDED"
    ABORTED = "ABORTED"


class SmokeExecutionReceipt(BaseModel):
    """Safe terminal state; it intentionally excludes credentials and provider content."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = 1
    plan_id: str
    smoke_plan_digest: str
    release_plan_digest: str
    status: SmokeExecutionStatus
    attempted_top_level_launches: int = Field(ge=0, le=8)
    failing_call_id: str | None = None
    failure_category: SmokeFailureCategory | None = None
    results: tuple[SmokeCallResult, ...]

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )


class SmokeContinuationPolicy(BaseModel):
    """Append-only authority for the unattempted v4 suffix."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    policy_id: Literal["kb2r-r1-v4-suffix-continuation"]
    base_branch_head: Literal["cd7de16eb4549d4a108ec9908b57905b50cd0562"]
    repair_commit_identity: str = Field(pattern=r"^[0-9a-f]{40}$")
    release_plan_reference: Literal["release/core-real-evidence-plan-v4.json"]
    release_plan_digest: str
    smoke_plan_reference: Literal["release/core-real-smoke-plan-v4.json"]
    smoke_plan_digest: str
    original_receipt_reference: Literal["artifacts/core-real-matrix-v4-canary/smoke-execution.json"]
    original_receipt_digest: str
    original_calls: tuple[SmokeCallResult, ...]
    old_control_plane_classification: Literal["OBSERVED_MODEL_CONFLICT"]
    raw_safe_fact: Literal["observed_model_status=NOT_EXPOSED;observed_model=null;verifier=PASS"]
    repaired_classification_rule: Literal[
        "NOT_EXPOSED_PLUS_NULL_IS_OBSERVED_MODEL_MISSING_LIMITATION_NOT_CONFLICT"
    ]
    codex_observed_model_capability: Literal["NOT_GUARANTEED_BY_PINNED_SCHEMA"]
    allowed_suffix_call_ids: tuple[str, ...]
    historical_subject_launches: Literal[4] = 4
    historical_judge_launches: Literal[0] = 0
    max_new_subject_launches: Literal[3] = 3
    max_new_judge_launches: Literal[1] = 1
    max_total_subject_launches: Literal[7] = 7
    max_total_judge_launches: Literal[1] = 1
    retries_allowed: Literal[0] = 0
    protected_file_sha256: dict[str, str]

    @model_validator(mode="after")
    def exact_suffix(self) -> SmokeContinuationPolicy:
        if self.allowed_suffix_call_ids != EXPECTED_CALL_IDS[4:]:
            raise ValueError("continuation authority is not the exact Calls 5-8 suffix")
        if tuple(item.call_id for item in self.original_calls) != EXPECTED_CALL_IDS[:4]:
            raise ValueError("continuation does not bind exact original Calls 1-4")
        return self


class SmokeContinuationReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    policy_id: Literal["kb2r-r1-v4-suffix-continuation"]
    status: SmokeExecutionStatus
    historical_subject_launches: Literal[4] = 4
    new_subject_launches: int = Field(ge=0, le=3)
    total_subject_launches: int = Field(ge=4, le=7)
    historical_judge_launches: Literal[0] = 0
    new_judge_launches: int = Field(ge=0, le=1)
    total_judge_launches: int = Field(ge=0, le=1)
    recovery_attempts: Literal[0] = 0
    reran_calls_1_to_4: Literal[False] = False
    failing_call_id: str | None = None
    failure_category: SmokeFailureCategory | None = None
    results: tuple[SmokeCallResult, ...]

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )


@dataclass(frozen=True)
class SmokeBinding:
    call: RealSmokeCall
    provider_profile: ProviderProfile
    runner_identity: str
    adapter_identity: str
    task_path: Path | None


@dataclass(frozen=True)
class RuntimeIdentities:
    codex_image: ImageIdentity
    claude_image: ImageIdentity
    deepseek_image: ImageIdentity
    egress_proxy_image: ImageIdentity
    deepseek_config_digest: str

    def validate(self) -> None:
        expected = (
            (self.codex_image, CODEX_IMAGE),
            (self.claude_image, CLAUDE_IMAGE),
            (self.deepseek_image, DEEPSEEK_IMAGE),
            (self.egress_proxy_image, EGRESS_PROXY_IMAGE),
        )
        for identity, reference in expected:
            if identity.reference != reference or identity.image_id == "sha256:" + "0" * 64:
                raise SmokeControlPlaneError(f"uninspected runtime image: {reference}")
        if not self.deepseek_config_digest.startswith("sha256:"):
            raise SmokeControlPlaneError("DeepSeek effective config identity is unavailable")


@dataclass(frozen=True)
class ResolvedSmokeBinding:
    frozen: SmokeBinding
    runtime_profile: ModelProfile | CodexHarnessProfile | MultiHarnessProfile
    egress_boundary: ProviderScopedDockerBoundary | None = None


class SmokeInvoker(TypingProtocol):
    async def invoke(self, binding: ResolvedSmokeBinding) -> SmokeCallResult: ...


class SmokeControlPlane:
    """The sole exact-plan control plane used by fake and future real smoke execution."""

    def __init__(
        self,
        repository_root: Path,
        release_plan: RealEvidencePlan,
        smoke_plan: RealSmokePlan,
        bindings: tuple[SmokeBinding, ...],
    ) -> None:
        self.repository_root = repository_root.resolve()
        self.release_plan = release_plan
        self.smoke_plan = smoke_plan
        self.bindings = bindings

    @classmethod
    def load(cls, repository_root: Path, *, plan_version: str = "v2") -> SmokeControlPlane:
        root = repository_root.resolve()
        try:
            release_reference, smoke_reference = PLAN_PATHS[plan_version]
        except KeyError as exc:
            raise SmokeControlPlaneError("plan version must be v2, v3, or v4") from exc
        try:
            release_plan = load_real_evidence_plan(root / release_reference)
            smoke_plan = load_real_smoke_plan(root / smoke_reference)
            corpus = load_core_corpus(root / release_plan.corpus_reference)
        except CoreReleaseError as exc:
            raise SmokeControlPlaneError(str(exc)) from exc
        expected_ids = (
            f"core-real-evidence-{plan_version}",
            f"core-real-smoke-{plan_version}",
        )
        if (release_plan.plan_id, smoke_plan.plan_id) != expected_ids:
            raise SmokeControlPlaneError("selected smoke/release plan version drifted")
        if smoke_plan.release_plan_digest != release_plan.digest:
            raise SmokeControlPlaneError("smoke/release plan digest mismatch")
        for reference, expected_digest, label in (
            (
                release_plan.history_reference,
                release_plan.history_digest,
                "v1 history",
            ),
            (
                release_plan.official_route_snapshot_reference,
                release_plan.official_route_snapshot_digest,
                "OpenCode Go route snapshot",
            ),
        ):
            path = (root / reference).resolve()
            if root not in path.parents or not path.is_file():
                raise SmokeControlPlaneError(f"{label} is unavailable")
            actual = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != expected_digest:
                raise SmokeControlPlaneError(f"{label} digest mismatch")
        if (
            len(smoke_plan.calls) != 8
            or smoke_plan.max_top_level_launch_count != 8
            or smoke_plan.max_output_token_ceiling != 14_256
            or sum(int(call.top_level_launches) for call in smoke_plan.calls) != 8
            or sum(call.max_output_tokens for call in smoke_plan.calls) != 14_256
        ):
            raise SmokeControlPlaneError("smoke bounds are not exactly 8 calls / 14,256 tokens")
        if tuple(call.call_id for call in smoke_plan.calls) != EXPECTED_CALL_IDS:
            raise SmokeControlPlaneError("smoke call identity or deterministic order drifted")
        profiles = {profile.profile_id: profile for profile in release_plan.selected_profiles}
        corpus_tasks = {task.task_id: task for task in corpus.tasks}
        task = corpus_tasks.get(SUBJECT_TASK_ID)
        if task is None:
            raise SmokeControlPlaneError("frozen smoke task is absent from the Core corpus")
        task_path = (root / task.package_path).resolve()
        if root not in task_path.parents or not task_path.is_dir():
            raise SmokeControlPlaneError("frozen smoke task escapes the repository")
        try:
            package = TaskPackage.load(task_path)
        except TaskPackageError as exc:
            raise SmokeControlPlaneError("frozen smoke task package is invalid") from exc
        if (
            package.definition.id != task.task_id
            or package.definition.content_digest != task.task_digest
        ):
            raise SmokeControlPlaneError("frozen smoke task package identity drifted")
        bindings: list[SmokeBinding] = []
        for index, call in enumerate(smoke_plan.calls):
            profile = profiles.get(call.profile_id)
            if profile is None:
                raise SmokeControlPlaneError("smoke call references an undeclared profile")
            expected_lane = "J" if index == 7 else "M" if index < 3 else "H"
            expected_task_id = None if expected_lane == "J" else SUBJECT_TASK_ID
            expected_task_digest = None if expected_lane == "J" else task.task_digest
            expected_judge = JUDGE_CASE_REFERENCE if expected_lane == "J" else None
            exact = (
                call.lane == expected_lane,
                call.task_id == expected_task_id,
                call.task_digest == expected_task_digest,
                call.judge_case_reference == expected_judge,
                call.requested_model == profile.requested_model,
                call.provider_route == profile.route_identity,
                call.max_output_tokens == profile.max_output_tokens,
                call.timeout_seconds == profile.timeout_seconds,
                call.credential_references
                == tuple(
                    reference
                    for reference in (profile.base_url_reference, profile.credential_reference)
                    if reference is not None
                ),
            )
            if not all(exact):
                raise SmokeControlPlaneError(f"frozen call contract drifted: {call.call_id}")
            bindings.append(
                SmokeBinding(
                    call=call,
                    provider_profile=profile,
                    runner_identity=EXPECTED_RUNNERS[index],
                    adapter_identity=EXPECTED_ADAPTERS[index],
                    task_path=None if expected_lane == "J" else task_path,
                )
            )
        if release_plan.credential_references != REQUIRED_CONFIGURATION_REFERENCES:
            raise SmokeControlPlaneError("release configuration reference order drifted")
        return cls(root, release_plan, smoke_plan, tuple(bindings))

    @property
    def smoke_plan_digest(self) -> str:
        return self.smoke_plan.digest

    def preflight(self) -> SmokeExecutionReceipt:
        """Keyless structural preflight. It cannot invoke a provider or resolve credentials."""

        return SmokeExecutionReceipt(
            plan_id=self.smoke_plan.plan_id,
            smoke_plan_digest=self.smoke_plan_digest,
            release_plan_digest=self.release_plan.digest,
            status=SmokeExecutionStatus.SUCCEEDED,
            attempted_top_level_launches=0,
            results=(),
        )

    def validate_real_environment(self, environment: Mapping[str, str]) -> None:
        missing = tuple(
            reference
            for reference in REQUIRED_CONFIGURATION_REFERENCES
            if not environment.get(reference, "").strip()
        )
        if missing:
            raise SmokeControlPlaneError(
                "required operator configuration is missing: " + ",".join(missing)
            )
        for profile in self.release_plan.selected_profiles:
            profile.resolve_base_url(environment)

    def resolve_real_bindings(
        self, environment: Mapping[str, str], runtime: RuntimeIdentities
    ) -> tuple[ResolvedSmokeBinding, ...]:
        self.validate_real_environment(environment)
        runtime.validate()
        execution_id = uuid4().hex[:12]
        resolved: list[ResolvedSmokeBinding] = []
        for index, binding in enumerate(self.bindings):
            provider = binding.provider_profile
            call = binding.call
            boundary = None
            if call.call_id.startswith("smoke-4-") or call.call_id.startswith("smoke-5-"):
                codex_profile = configured_gpt56_relay_codex_profile(
                    runtime.codex_image,
                    provider_base_url_reference=provider.base_url_reference or "",
                    reasoning_effort=provider.reasoning_effort or "",
                    execution_timeout_seconds=provider.timeout_seconds,
                )
                profile: ModelProfile | CodexHarnessProfile | MultiHarnessProfile = codex_profile
                boundary = self._boundary(provider, environment, execution_id, index, runtime)
                self._assert_codex_route(codex_profile, provider, environment)
            elif call.call_id == "smoke-6-harness-claude-qwen38-opencode-go":
                profile = configured_qwen_opencode_go_claude_profile(
                    runtime.claude_image, execution_timeout_seconds=provider.timeout_seconds
                )
                boundary = self._boundary(provider, environment, execution_id, index, runtime)
                self._assert_claude_route(profile, provider, environment)
            elif call.call_id == "smoke-7-harness-deepseek-v4flash":
                profile = configured_deepseek_v4flash_profile(
                    runtime.deepseek_image,
                    runtime.deepseek_config_digest,
                    execution_timeout_seconds=provider.timeout_seconds,
                )
                boundary = self._boundary(provider, environment, execution_id, index, runtime)
                self._assert_deepseek_route(profile, provider, environment)
            else:
                profile = configured_model_profile(provider, environment)
                if call.call_id == "smoke-8-judge-glm52-opencode-go":
                    self._assert_judge_route(profile, provider, environment)
            resolved.append(ResolvedSmokeBinding(binding, profile, boundary))
        direct = resolved[0].runtime_profile
        codex = resolved[3].runtime_profile
        assert isinstance(direct, ModelProfile)
        assert isinstance(codex, CodexHarnessProfile)
        direct_provider = resolved[0].frozen.provider_profile
        codex_provider = resolved[3].frozen.provider_profile
        if (
            direct.provider_route_identity != codex.provider_route
            or direct_provider.route_identity != codex_provider.route_identity
        ):
            raise SmokeControlPlaneError("Direct GPT and Codex-medium resolved routes differ")
        return tuple(resolved)

    def _boundary(
        self,
        profile: ProviderProfile,
        environment: Mapping[str, str],
        execution_id: str,
        index: int,
        runtime: RuntimeIdentities,
    ) -> ProviderScopedDockerBoundary:
        return boundary_for_provider_url(
            profile.resolve_base_url(environment),
            network_name=f"hl-smoke-{execution_id}-{index}-internal",
            proxy_name=f"hl-smoke-{execution_id}-{index}-proxy",
            proxy_image=runtime.egress_proxy_image,
        )

    @staticmethod
    def _assert_codex_route(
        profile: CodexHarnessProfile,
        provider: ProviderProfile,
        environment: Mapping[str, str],
    ) -> None:
        required = (
            profile.model_provider_id == "harnesslab_gpt56_relay",
            profile.provider_wire_api == "responses",
            profile.provider_base_url_reference == provider.base_url_reference,
            profile.provider_credential_reference == "HARNESSLAB_GPT56_RELAY_API_KEY",
            profile.provider_supports_websockets is False,
            profile.ignore_user_config is False,
            profile.ambient_user_config_isolated is True,
            profile.requested_model == "gpt-5.6-sol",
            profile.provider_route == provider.route_identity,
        )
        if not all(required):
            raise SmokeControlPlaneError("Codex relay fallback protection failed")

    @staticmethod
    def _assert_claude_route(
        profile: MultiHarnessProfile,
        provider: ProviderProfile,
        environment: Mapping[str, str],
    ) -> None:
        required = (
            profile.provider_base_url_reference is None,
            profile.provider_fixed_base_url == "https://opencode.ai/zen/go",
            profile.provider_credential_reference == "HARNESSLAB_OPENCODE_GO_API_KEY",
            profile.provider_credential_transport is ClaudeCredentialTransport.ANTHROPIC_API_KEY,
            profile.requested_model == "qwen3.8-max",
            profile.provider_route == provider.route_identity,
            provider.resolve_base_url(environment) == "https://opencode.ai/zen/go",
            f"{profile.provider_fixed_base_url}/v1/messages"
            == "https://opencode.ai/zen/go/v1/messages",
        )
        if not all(required):
            raise SmokeControlPlaneError("Claude OpenCode Go route protection failed")

    @staticmethod
    def _assert_deepseek_route(
        profile: MultiHarnessProfile,
        provider: ProviderProfile,
        environment: Mapping[str, str],
    ) -> None:
        required = (
            provider.resolve_base_url(environment) == "https://api.deepseek.com",
            profile.requested_model == "deepseek-v4-flash",
            profile.provider_route == provider.route_identity,
        )
        if not all(required):
            raise SmokeControlPlaneError("DeepSeek official-route protection failed")

    @staticmethod
    def _assert_judge_route(
        profile: ModelProfile,
        provider: ProviderProfile,
        environment: Mapping[str, str],
    ) -> None:
        required = (
            profile.requested_model == "glm-5.2",
            profile.protocol is Protocol.CHAT_COMPLETIONS,
            profile.base_url == provider.resolve_base_url(environment),
            profile.base_url == "https://opencode.ai/zen/go",
            profile.route == "/v1/chat/completions",
            profile.credential_reference == "HARNESSLAB_OPENCODE_GO_API_KEY",
            profile.thinking_mode is None,
            profile.thinking_transport is None,
        )
        if not all(required):
            raise SmokeControlPlaneError("Judge OpenCode Go route protection failed")

    async def execute(
        self,
        bindings: Sequence[ResolvedSmokeBinding],
        invoker: SmokeInvoker,
        *,
        allow_real_smoke: bool,
        receipt_path: Path | None = None,
    ) -> SmokeExecutionReceipt:
        if not allow_real_smoke:
            raise SmokeControlPlaneError("real smoke requires --allow-real-smoke")
        if len(bindings) != 8 or tuple(item.frozen for item in bindings) != self.bindings:
            raise SmokeControlPlaneError("executor received a mutated smoke binding set")
        results: list[SmokeCallResult] = []
        attempted = 0
        failing_call_id = None
        failure_category = None
        for expected_call, binding in zip(EXPECTED_CALL_IDS, bindings, strict=True):
            if binding.frozen.call.call_id != expected_call or attempted >= 8:
                raise SmokeControlPlaneError("top-level launch bound was exceeded")
            attempted += 1
            try:
                result = await invoker.invoke(binding)
                if result.call_id != expected_call:
                    raise SmokeCallFailure(
                        SmokeFailureCategory.ARTIFACT_INTEGRITY,
                        "smoke result identity mismatch",
                    )
                results.append(result)
            except SmokeCallFailure as exc:
                if exc.evidence_result is not None:
                    results.append(exc.evidence_result)
                failing_call_id = expected_call
                failure_category = exc.category
                break
            except Exception:
                failing_call_id = expected_call
                failure_category = SmokeFailureCategory.INFRASTRUCTURE
                break
        receipt = SmokeExecutionReceipt(
            plan_id=self.smoke_plan.plan_id,
            smoke_plan_digest=self.smoke_plan_digest,
            release_plan_digest=self.release_plan.digest,
            status=(
                SmokeExecutionStatus.SUCCEEDED
                if failing_call_id is None
                else SmokeExecutionStatus.ABORTED
            ),
            attempted_top_level_launches=attempted,
            failing_call_id=failing_call_id,
            failure_category=failure_category,
            results=tuple(results),
        )
        if receipt_path is not None:
            self._persist_receipt(receipt_path, receipt)
        return receipt

    def validate_continuation_policy(
        self, policy: SmokeContinuationPolicy
    ) -> SmokeExecutionReceipt:
        """Validate historical bindings and suffix authority without a provider call."""

        if (
            policy.release_plan_digest != self.release_plan.digest
            or policy.smoke_plan_digest != self.smoke_plan_digest
        ):
            raise SmokeControlPlaneError("continuation plan digest drifted")
        for reference, expected in policy.protected_file_sha256.items():
            path = (self.repository_root / reference).resolve()
            if self.repository_root not in path.parents or not path.is_file():
                raise SmokeControlPlaneError(
                    f"protected continuation input is unavailable: {reference}"
                )
            actual = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
            if actual != expected:
                raise SmokeControlPlaneError(f"protected historical bytes changed: {reference}")
        receipt_path = (self.repository_root / policy.original_receipt_reference).resolve()
        if self.repository_root not in receipt_path.parents or not receipt_path.is_file():
            raise SmokeControlPlaneError("original aborted receipt is unavailable")
        receipt_digest = "sha256:" + hashlib.sha256(receipt_path.read_bytes()).hexdigest()
        if receipt_digest != policy.original_receipt_digest:
            raise SmokeControlPlaneError("original aborted receipt bytes changed")
        try:
            receipt = SmokeExecutionReceipt.model_validate_json(
                receipt_path.read_text(encoding="utf-8")
            )
        except ValueError as exc:
            raise SmokeControlPlaneError("original aborted receipt is invalid") from exc
        if (
            receipt.status is not SmokeExecutionStatus.ABORTED
            or receipt.attempted_top_level_launches != 4
            or receipt.failing_call_id != EXPECTED_CALL_IDS[3]
            or receipt.failure_category is not SmokeFailureCategory.OBSERVED_MODEL_CONFLICT
            or receipt.results != policy.original_calls
        ):
            raise SmokeControlPlaneError("original Calls 1-4 receipt semantics drifted")
        for result in receipt.results:
            if not result.evidence_references or not result.evidence_digests:
                raise SmokeControlPlaneError("original call evidence binding is incomplete")
            evidence_path = Path(result.evidence_references[0]).resolve()
            artifacts = (self.repository_root / "artifacts").resolve()
            if artifacts not in evidence_path.parents or not evidence_path.is_dir():
                raise SmokeControlPlaneError("original call evidence path escaped artifacts")
            if digest_tree(evidence_path) != result.evidence_digests[0]:
                raise SmokeControlPlaneError("original call evidence identity drifted")
        commit = subprocess.run(
            ("git", "cat-file", "-e", f"{policy.repair_commit_identity}^{{commit}}"),
            cwd=self.repository_root,
            capture_output=True,
            check=False,
        )
        if commit.returncode != 0:
            raise SmokeControlPlaneError("repair commit identity is unavailable")
        return receipt

    async def execute_continuation(
        self,
        bindings: Sequence[ResolvedSmokeBinding],
        invoker: SmokeInvoker,
        policy: SmokeContinuationPolicy,
        *,
        allow_real_smoke: bool,
        receipt_path: Path,
    ) -> SmokeContinuationReceipt:
        if not allow_real_smoke:
            raise SmokeControlPlaneError("real suffix requires --allow-real-smoke")
        self.validate_continuation_policy(policy)
        suffix = tuple(bindings[4:])
        if len(bindings) != 8 or tuple(item.frozen for item in bindings) != self.bindings:
            raise SmokeControlPlaneError("continuation received mutated v4 bindings")
        if tuple(item.frozen.call.call_id for item in suffix) != policy.allowed_suffix_call_ids:
            raise SmokeControlPlaneError("continuation binding is not exact Calls 5-8")
        if receipt_path.exists() or any(
            (receipt_path.parent / call_id).exists() for call_id in policy.allowed_suffix_call_ids
        ):
            raise SmokeControlPlaneError("suffix evidence already exists; retries are forbidden")

        results: list[SmokeCallResult] = []
        failing_call_id: str | None = None
        failure_category: SmokeFailureCategory | None = None
        new_subject = 0
        new_judge = 0
        for index, binding in enumerate(suffix):
            call_id = policy.allowed_suffix_call_ids[index]
            if index < 3:
                if new_subject >= policy.max_new_subject_launches:
                    raise SmokeControlPlaneError("new subject launch ceiling exceeded")
                new_subject += 1
            else:
                if len(results) != 3 or new_judge >= policy.max_new_judge_launches:
                    raise SmokeControlPlaneError("Judge prerequisite or launch ceiling failed")
                new_judge += 1
            try:
                result = await invoker.invoke(binding)
                if result.call_id != call_id:
                    raise SmokeCallFailure(
                        SmokeFailureCategory.ARTIFACT_INTEGRITY,
                        "continuation result identity mismatch",
                    )
                results.append(result)
            except SmokeCallFailure as exc:
                if exc.evidence_result is not None:
                    results.append(exc.evidence_result)
                failing_call_id = call_id
                failure_category = exc.category
                break
            except Exception:
                failing_call_id = call_id
                failure_category = SmokeFailureCategory.INFRASTRUCTURE
                break
        receipt = SmokeContinuationReceipt(
            policy_id=policy.policy_id,
            status=(
                SmokeExecutionStatus.SUCCEEDED
                if failing_call_id is None
                else SmokeExecutionStatus.ABORTED
            ),
            new_subject_launches=new_subject,
            total_subject_launches=4 + new_subject,
            new_judge_launches=new_judge,
            total_judge_launches=new_judge,
            failing_call_id=failing_call_id,
            failure_category=failure_category,
            results=tuple(results),
        )
        self._persist_receipt(receipt_path, receipt)
        return receipt

    @staticmethod
    def _persist_receipt(
        path: Path, receipt: SmokeExecutionReceipt | SmokeContinuationReceipt
    ) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            handle.write(receipt.canonical_json() + "\n")
            temporary = Path(handle.name)
        os.replace(temporary, path)


class ProductionSmokeInvoker:
    """Exact runner dispatch. It has no arbitrary provider/model/task entry point."""

    def __init__(
        self,
        repository_root: Path,
        environment: Mapping[str, str],
        artifact_root: Path,
        smoke_plan_id: str = "core-real-smoke-v2",
    ) -> None:
        self.repository_root = repository_root.resolve()
        self.environment = dict(environment)
        self.artifact_root = artifact_root.resolve()
        self.smoke_plan_id = smoke_plan_id

    async def invoke(self, binding: ResolvedSmokeBinding) -> SmokeCallResult:
        call_id = binding.frozen.call.call_id
        if call_id in EXPECTED_CALL_IDS[:3]:
            return await self._direct(binding)
        if call_id in EXPECTED_CALL_IDS[3:5]:
            return await self._codex(binding)
        if call_id == EXPECTED_CALL_IDS[5]:
            return await self._claude(binding)
        if call_id == EXPECTED_CALL_IDS[6]:
            return await self._deepseek(binding)
        if call_id == EXPECTED_CALL_IDS[7]:
            return await self._judge(binding)
        raise SmokeCallFailure(SmokeFailureCategory.CONFIGURATION, "undeclared smoke call")

    def _credentials(self, call: RealSmokeCall) -> dict[str, str]:
        return {reference: self.environment[reference] for reference in call.credential_references}

    async def _direct(self, binding: ResolvedSmokeBinding) -> SmokeCallResult:
        profile = binding.runtime_profile
        assert isinstance(profile, ModelProfile)
        adapters = {
            Protocol.RESPONSES: OpenAIResponsesAdapter,
            Protocol.MESSAGES: AnthropicMessagesAdapter,
            Protocol.CHAT_COMPLETIONS: OpenAICompatibleChatAdapter,
        }
        adapter = adapters[profile.protocol](environment=self.environment)
        assert binding.frozen.task_path is not None
        result = await DirectModelRunner(
            artifact_root=self.artifact_root / binding.frozen.call.call_id,
            environment=self.environment,
            allow_custom_endpoint=True,
        ).run(
            binding.frozen.task_path,
            profile,
            adapter=adapter,
            run_id=binding.frozen.call.call_id,
        )
        evidence = result.evidence
        artifact = self._artifact_result(binding, result.artifact_directory)
        if evidence.provider_failure is not None:
            raise SmokeCallFailure(
                self._provider_failure_category(evidence.provider_failure),
                "direct provider smoke failed",
                artifact,
            )
        if evidence.outcome is DirectModelOutcome.INFRA_ERROR:
            raise SmokeCallFailure(
                SmokeFailureCategory.INFRASTRUCTURE,
                "direct smoke infrastructure failed",
                artifact,
            )
        if evidence.outcome is DirectModelOutcome.ARTIFACT_ERROR:
            raise SmokeCallFailure(
                SmokeFailureCategory.ARTIFACT_INTEGRITY,
                "direct smoke artifact integrity failed",
                artifact,
            )
        if evidence.observed_model != profile.requested_model:
            raise SmokeCallFailure(
                SmokeFailureCategory.OBSERVED_MODEL_CONFLICT,
                "direct observed model conflict",
                artifact,
            )
        return artifact

    async def _codex(self, binding: ResolvedSmokeBinding) -> SmokeCallResult:
        profile = binding.runtime_profile
        assert isinstance(profile, CodexHarnessProfile)
        assert binding.frozen.task_path is not None and binding.egress_boundary is not None
        backend = DockerCodexBackend(
            explicitly_enabled=True,
            credentials=self._credentials(binding.frozen.call),
            egress_boundary=binding.egress_boundary,
        )
        result = await CodexHarnessRunner(
            artifact_root=self.artifact_root / binding.frozen.call.call_id
        ).run(
            binding.frozen.task_path,
            profile,
            backend=backend,
            run_id=binding.frozen.call.call_id,
        )
        artifact = self._artifact_result(
            binding, result.artifact_directory, egress_attestation=backend.egress_attestation
        )
        if result.evidence.harness_failure is not None:
            if (
                result.evidence.outcome is not HarnessLaneOutcome.HARNESS_ERROR
                or not is_capability_harness_failure(result.evidence.harness_failure)
            ):
                raise SmokeCallFailure(
                    self._harness_failure_category(result.evidence.harness_failure),
                    "Codex smoke failed",
                    artifact,
                )
            if (
                result.evidence.observed_model is not None
                and result.evidence.observed_model != profile.requested_model
            ):
                raise SmokeCallFailure(
                    SmokeFailureCategory.OBSERVED_MODEL_CONFLICT,
                    "Codex observed model conflict",
                    artifact,
                )
            return artifact
        if result.evidence.outcome is HarnessLaneOutcome.INFRA_ERROR:
            raise SmokeCallFailure(
                SmokeFailureCategory.INFRASTRUCTURE,
                "Codex smoke infrastructure failed",
                artifact,
            )
        if result.evidence.outcome is HarnessLaneOutcome.ARTIFACT_ERROR:
            raise SmokeCallFailure(
                SmokeFailureCategory.ARTIFACT_INTEGRITY,
                "Codex smoke artifact integrity failed",
                artifact,
            )
        try:
            _validate_harness_observed_model(
                profile,
                trace_coverage=result.evidence.trace_coverage,
                observed_model_status=result.evidence.observed_model_status,
                observed_model=result.evidence.observed_model,
            )
        except SmokeCallFailure as exc:
            raise SmokeCallFailure(exc.category, str(exc), artifact) from exc
        return artifact

    async def _claude(self, binding: ResolvedSmokeBinding) -> SmokeCallResult:
        return await self._multi(binding, ClaudeCodeAdapter())

    async def _deepseek(self, binding: ResolvedSmokeBinding) -> SmokeCallResult:
        profile = binding.runtime_profile
        assert isinstance(profile, MultiHarnessProfile) and profile.config_digest is not None
        return await self._multi(
            binding, DeepSeekHarnessAdapter(observed_config_digest=profile.config_digest)
        )

    async def _multi(self, binding: ResolvedSmokeBinding, adapter: object) -> SmokeCallResult:
        profile = binding.runtime_profile
        assert isinstance(profile, MultiHarnessProfile)
        assert binding.frozen.task_path is not None and binding.egress_boundary is not None
        backend = DockerMultiHarnessBackend(
            explicitly_enabled=True,
            credentials=self._credentials(binding.frozen.call),
            egress_boundary=binding.egress_boundary,
        )
        result = await MultiHarnessRunner(
            artifact_root=self.artifact_root / binding.frozen.call.call_id
        ).run(
            binding.frozen.task_path,
            profile,
            adapter=adapter,  # type: ignore[arg-type]
            backend=backend,
            run_id=binding.frozen.call.call_id,
        )
        artifact = self._artifact_result(
            binding, result.artifact_directory, egress_attestation=backend.egress_attestation
        )
        if result.evidence.harness_failure is not None:
            if (
                result.evidence.outcome is not HarnessLaneOutcome.HARNESS_ERROR
                or not is_capability_harness_failure(result.evidence.harness_failure)
            ):
                raise SmokeCallFailure(
                    self._harness_failure_category(result.evidence.harness_failure),
                    "Harness smoke failed",
                    artifact,
                )
            if (
                result.evidence.observed_model is not None
                and result.evidence.observed_model != profile.requested_model
            ):
                raise SmokeCallFailure(
                    SmokeFailureCategory.OBSERVED_MODEL_CONFLICT,
                    "Harness observed model conflict",
                    artifact,
                )
            return artifact
        if result.evidence.outcome is HarnessLaneOutcome.INFRA_ERROR:
            raise SmokeCallFailure(
                SmokeFailureCategory.INFRASTRUCTURE,
                "Harness smoke infrastructure failed",
                artifact,
            )
        if result.evidence.outcome is HarnessLaneOutcome.ARTIFACT_ERROR:
            raise SmokeCallFailure(
                SmokeFailureCategory.ARTIFACT_INTEGRITY,
                "Harness smoke artifact integrity failed",
                artifact,
            )
        try:
            _validate_harness_observed_model(
                profile,
                trace_coverage=result.evidence.trace_coverage,
                observed_model_status=result.evidence.observed_model_status,
                observed_model=result.evidence.observed_model,
            )
        except SmokeCallFailure as exc:
            raise SmokeCallFailure(exc.category, str(exc), artifact) from exc
        return artifact

    async def _judge(self, binding: ResolvedSmokeBinding) -> SmokeCallResult:
        profile = binding.runtime_profile
        assert isinstance(profile, ModelProfile)
        suite_root = self.repository_root / "judge_suites/core-calibration/1.0.0"
        suite = load_judge_suite(suite_root)
        definition = load_judge_definition(suite_root / "definition.yaml")
        cases = {case.case_id: case for case in suite.public.cases}
        case = cases.get("label-l0-pass")
        if case is None:
            raise SmokeCallFailure(
                SmokeFailureCategory.CONFIGURATION, "bounded Judge case is unavailable"
            )
        profile_identity = judge_digest(profile)
        slot_identity = {
            "calibration_id": self.smoke_plan_id,
            "judge_cell_id": "judge-glm52-opencode-go-chat",
            "suite_digest": suite.suite_digest,
            "definition_digest": definition.definition_digest,
            "profile_identity": profile_identity,
            "case_id": case.case_id,
            "case_public_digest": case.public_digest,
            "repeat_index": 0,
            "order_variant": OrderVariant.NOT_APPLICABLE.value,
        }
        slot = JudgeEvaluationSlot(
            slot_id=judge_digest(slot_identity),
            slot_order=0,
            calibration_id=self.smoke_plan_id,
            judge_cell_id="judge-glm52-opencode-go-chat",
            case_id=case.case_id,
            case_mode=case.mode,
            case_public_digest=case.public_digest,
            repeat_index=0,
            order_variant=OrderVariant.NOT_APPLICABLE,
        )
        result = await JudgeRunner(self.artifact_root / binding.frozen.call.call_id).run(
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
        if result.artifact_path is None or result.artifact_digest is None:
            raise SmokeCallFailure(
                SmokeFailureCategory.JUDGE_PERSISTENCE, "bounded Judge evidence was not persisted"
            )
        artifact_directory = result.artifact_path.parent
        artifact = SmokeCallResult(
            call_id=binding.frozen.call.call_id,
            evidence_references=(str(artifact_directory.resolve()),),
            evidence_digests=(digest_tree(artifact_directory),),
        )
        if result.evidence.outcome is JudgeRunOutcome.PROVIDER_ERROR:
            assert result.evidence.provider_failure is not None
            raise SmokeCallFailure(
                self._provider_failure_category(result.evidence.provider_failure),
                "bounded Judge provider call failed",
                artifact,
            )
        if result.evidence.outcome is JudgeRunOutcome.JUDGE_OUTPUT_ERROR:
            raise SmokeCallFailure(
                SmokeFailureCategory.SCHEMA_MISMATCH,
                "bounded Judge output schema failed",
                artifact,
            )
        if result.evidence.observed_judge_model != "glm-5.2":
            raise SmokeCallFailure(
                SmokeFailureCategory.OBSERVED_MODEL_CONFLICT,
                "bounded Judge observed model conflict",
                artifact,
            )
        return artifact

    @staticmethod
    def _provider_failure_category(
        category: ProviderFailureCategory,
    ) -> SmokeFailureCategory:
        if category is ProviderFailureCategory.AUTHENTICATION:
            return SmokeFailureCategory.AUTHENTICATION
        if category in {
            ProviderFailureCategory.MALFORMED_RESPONSE,
            ProviderFailureCategory.INCOMPLETE_RESPONSE,
        }:
            return SmokeFailureCategory.SCHEMA_MISMATCH
        if category is ProviderFailureCategory.CONFIGURATION:
            return SmokeFailureCategory.CONFIGURATION
        return SmokeFailureCategory.PROVIDER_FAILURE

    @staticmethod
    def _harness_failure_category(category: HarnessFailureCategory) -> SmokeFailureCategory:
        if category is HarnessFailureCategory.AUTHENTICATION:
            return SmokeFailureCategory.AUTHENTICATION
        if category is HarnessFailureCategory.PROTOCOL_ERROR:
            return SmokeFailureCategory.SCHEMA_MISMATCH
        if category in {
            HarnessFailureCategory.CONFIGURATION,
            HarnessFailureCategory.PROFILE_VIOLATION,
        }:
            return SmokeFailureCategory.CONFIGURATION
        if category is HarnessFailureCategory.ARTIFACT_ERROR:
            return SmokeFailureCategory.ARTIFACT_INTEGRITY
        return SmokeFailureCategory.HARNESS_FAILURE

    @staticmethod
    def _artifact_result(
        binding: ResolvedSmokeBinding,
        path: Path,
        *,
        egress_attestation: ProxySecurityAttestation | None = None,
    ) -> SmokeCallResult:
        references = [str(path.resolve())]
        digests = [digest_tree(path)]
        if egress_attestation is not None:
            references.append(
                "egress-proxy:"
                f"{egress_attestation.image.reference}@{egress_attestation.image.image_id}"
            )
            digests.append(egress_attestation.digest)
            references.append(
                f"egress-network:{egress_attestation.internal_network_security.network}"
            )
            digests.append(egress_attestation.internal_network_security.digest)
        return SmokeCallResult(
            call_id=binding.frozen.call.call_id,
            evidence_references=tuple(references),
            evidence_digests=tuple(digests),
        )


async def resolve_runtime_identities() -> RuntimeIdentities:
    """Inspect every local runtime before call #1; this performs no provider request."""

    codex = await CodexRuntime().ensure_image()
    claude = await MultiHarnessRuntime(HarnessKind.CLAUDE_CODE).ensure_image()
    deepseek_doctor = await MultiHarnessRuntime(HarnessKind.DEEPSEEK).doctor()
    if deepseek_doctor.config_digest is None:
        raise SmokeControlPlaneError("DeepSeek effective config identity is unavailable")
    proxy = await EgressProxyRuntime().ensure_image()
    runtime = RuntimeIdentities(
        codex_image=codex,
        claude_image=claude,
        deepseek_image=deepseek_doctor.image,
        egress_proxy_image=proxy,
        deepseek_config_digest=deepseek_doctor.config_digest,
    )
    runtime.validate()
    return runtime


async def execute_real_smoke(
    repository_root: Path,
    *,
    allow_real_smoke: bool,
    environment: Mapping[str, str] | None = None,
    artifact_root: Path | None = None,
    plan_version: str = "v2",
) -> SmokeExecutionReceipt:
    """Future K-B1 entry point. Calling it without explicit authorization fails closed."""

    if not allow_real_smoke:
        raise SmokeControlPlaneError("real smoke requires --allow-real-smoke")
    selected_environment = environment if environment is not None else os.environ
    control = SmokeControlPlane.load(repository_root, plan_version=plan_version)
    control.validate_real_environment(selected_environment)
    await preflight_egress_network_isolation()
    runtime = await resolve_runtime_identities()
    bindings = control.resolve_real_bindings(selected_environment, runtime)
    output = (
        artifact_root
        if artifact_root is not None
        else Path(tempfile.gettempdir()) / "harnesslab-phase-k-smoke"
    ).resolve()
    invoker = ProductionSmokeInvoker(
        repository_root,
        selected_environment,
        output,
        smoke_plan_id=control.smoke_plan.plan_id,
    )
    return await control.execute(
        bindings,
        invoker,
        allow_real_smoke=True,
        receipt_path=output / "smoke-execution.json",
    )


def load_smoke_continuation_policy(path: Path) -> SmokeContinuationPolicy:
    try:
        return SmokeContinuationPolicy.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as exc:
        raise SmokeControlPlaneError("invalid R1 continuation policy") from exc


async def execute_real_smoke_continuation(
    repository_root: Path,
    *,
    allow_real_smoke: bool,
    environment: Mapping[str, str] | None = None,
    artifact_root: Path | None = None,
    policy_path: Path | None = None,
) -> SmokeContinuationReceipt:
    """Execute only v4 Calls 5-8 under append-only R1 authority."""

    if not allow_real_smoke:
        raise SmokeControlPlaneError("real suffix requires --allow-real-smoke")
    root = repository_root.resolve()
    selected_environment = environment if environment is not None else os.environ
    control = SmokeControlPlane.load(root, plan_version="v4")
    selected_policy_path = (
        policy_path
        if policy_path is not None
        else root / "release/kb2r-r1-continuation-policy.json"
    ).resolve()
    policy = load_smoke_continuation_policy(selected_policy_path)
    control.validate_continuation_policy(policy)
    control.validate_real_environment(selected_environment)
    await preflight_egress_network_isolation()
    runtime = await resolve_runtime_identities()
    bindings = control.resolve_real_bindings(selected_environment, runtime)
    output = (
        artifact_root
        if artifact_root is not None
        else root / "artifacts/core-real-matrix-v4-r1-suffix"
    ).resolve()
    invoker = ProductionSmokeInvoker(
        root,
        selected_environment,
        output,
        smoke_plan_id=control.smoke_plan.plan_id,
    )
    return await control.execute_continuation(
        bindings,
        invoker,
        policy,
        allow_real_smoke=True,
        receipt_path=output / "r1-smoke-execution.json",
    )
