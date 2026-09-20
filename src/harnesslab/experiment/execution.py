from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field, model_validator

from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.common import EvaluationLane
from harnesslab.contracts.model import ModelProfile
from harnesslab.experiment.plan import ExperimentRunSlot, _resolve_task
from harnesslab.harness_lane.adapter import CodexBackend
from harnesslab.harness_lane.models import (
    CodexHarnessProfile,
    HarnessLaneEvidence,
    HarnessLaneRunResult,
)
from harnesslab.harness_lane.runner import CodexHarnessRunner
from harnesslab.model_lane.models import DirectModelEvidence, DirectModelRunResult, ProviderAdapter
from harnesslab.model_lane.profiles import model_profile_control_identity
from harnesslab.model_lane.runner import DirectModelRunner
from harnesslab.multi_harness.adapter import MultiHarnessAdapter, MultiHarnessBackend
from harnesslab.multi_harness.models import (
    MultiHarnessEvidence,
    MultiHarnessProfile,
    MultiHarnessRunResult,
)
from harnesslab.multi_harness.runner import MultiHarnessRunner

type LaneRunResult = DirectModelRunResult | HarnessLaneRunResult | MultiHarnessRunResult
type LaneEvidence = DirectModelEvidence | HarnessLaneEvidence | MultiHarnessEvidence
type LaneProfile = ModelProfile | CodexHarnessProfile | MultiHarnessProfile


def resolved_comparison_profile_identity(profile: LaneProfile) -> str:
    """Match extraction; reasoning effort remains an explicit intent-specific field."""

    if isinstance(profile, ModelProfile):
        return model_profile_control_identity(profile)
    controls = profile.model_dump(mode="json")
    controls.pop("requested_model", None)
    controls.pop("reasoning_effort", None)
    return canonical_digest(controls)


class ExperimentLaneBinding(Protocol):
    async def run(self, task_path: Path, run_id: str) -> LaneRunResult: ...


@dataclass(frozen=True)
class DirectModelBinding:
    runner: DirectModelRunner
    profile: ModelProfile
    provider: ProviderAdapter

    async def run(self, task_path: Path, run_id: str) -> DirectModelRunResult:
        return await self.runner.run(task_path, self.profile, adapter=self.provider, run_id=run_id)


@dataclass(frozen=True)
class CodexHarnessBinding:
    runner: CodexHarnessRunner
    profile: CodexHarnessProfile
    backend: CodexBackend

    async def run(self, task_path: Path, run_id: str) -> HarnessLaneRunResult:
        return await self.runner.run(task_path, self.profile, backend=self.backend, run_id=run_id)


@dataclass(frozen=True)
class MultiHarnessBinding:
    runner: MultiHarnessRunner
    profile: MultiHarnessProfile
    adapter: MultiHarnessAdapter
    backend: MultiHarnessBackend

    async def run(self, task_path: Path, run_id: str) -> MultiHarnessRunResult:
        return await self.runner.run(
            task_path,
            self.profile,
            adapter=self.adapter,
            backend=self.backend,
            run_id=run_id,
        )


class ExecutionContractError(ValueError):
    """Dispatch was rejected before entering a subject runner."""


class ExecutionControlMismatch(ExecutionContractError):
    """Frozen treatment controls changed before dispatch."""


@runtime_checkable
class ProfiledLaneBinding(Protocol):
    """Existing lazy production bindings expose these secret-free controls."""

    @property
    def profile(self) -> LaneProfile: ...

    @property
    def plan_profile_identity(self) -> str | None: ...

    @property
    def plan_harness_config_identity(self) -> str | None: ...


@dataclass(frozen=True)
class _BindingControls:
    profile: LaneProfile
    plan_profile_identity: str | None
    plan_harness_config_identity: str | None


def _binding_controls(binding: ExperimentLaneBinding) -> _BindingControls | None:
    if isinstance(binding, (DirectModelBinding, CodexHarnessBinding, MultiHarnessBinding)):
        return _BindingControls(
            binding.profile,
            binding.runner.plan_profile_identity,
            binding.runner.plan_harness_config_identity,
        )
    if isinstance(binding, ProfiledLaneBinding):
        return _BindingControls(
            binding.profile,
            binding.plan_profile_identity,
            binding.plan_harness_config_identity,
        )
    return None


class ExecutionCapabilities(BaseModel):
    """Declared interface support, never runtime health or execution permission."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    transport: Literal["PROVIDER", "CLI", "LEGACY"]
    streaming: Literal[False] = False
    active_cancellation: Literal[False] = False
    session_resume: Literal[False] = False
    isolated_workspace: bool
    observed_model: Literal["WHEN_REPORTED", "NOT_EXPOSED", "UNKNOWN"]
    trace: Literal["NORMALIZED_EVENTS", "FINAL_ONLY", "NOT_APPLICABLE", "UNKNOWN"]


def execution_capabilities() -> dict[str, ExecutionCapabilities]:
    """The current entry points return after the attempt; no live control protocol exists."""
    return {
        "direct-model": ExecutionCapabilities(
            transport="PROVIDER",
            isolated_workspace=True,
            observed_model="WHEN_REPORTED",
            trace="NOT_APPLICABLE",
        ),
        "codex": ExecutionCapabilities(
            transport="CLI",
            isolated_workspace=True,
            observed_model="WHEN_REPORTED",
            trace="NORMALIZED_EVENTS",
        ),
        "claude-code": ExecutionCapabilities(
            transport="CLI",
            isolated_workspace=True,
            observed_model="WHEN_REPORTED",
            trace="NORMALIZED_EVENTS",
        ),
        "deepseek-harness": ExecutionCapabilities(
            transport="CLI",
            isolated_workspace=True,
            observed_model="NOT_EXPOSED",
            trace="FINAL_ONLY",
        ),
    }


class ExecutionRequest(BaseModel):
    """One already-claimed attempt, with frozen task/config/budget references.

    The caller supplies no argv, environment values, or host workspace paths.
    Queue ownership, authorization and resource reservations remain with the executor.
    Constructing this object does not authorize or enqueue anything.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    execution_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9-]+$")
    slot: ExperimentRunSlot
    required_capabilities: tuple[
        Literal["streaming", "active_cancellation", "session_resume", "isolated_workspace"], ...
    ] = ()

    @model_validator(mode="after")
    def task_reference_is_relative(self) -> ExecutionRequest:
        reference = self.slot.task.package_path
        path = PurePosixPath(reference)
        if (
            not reference
            or "\\" in reference
            or path.is_absolute()
            or PureWindowsPath(reference).drive
            or ".." in path.parts
            or not path.parts
            or path.parts[0] != "tasks"
        ):
            raise ValueError("execution requires a repository-relative task reference")
        return self


def _validate_binding(controls: _BindingControls, slot: ExperimentRunSlot) -> None:
    profile = controls.profile
    expected: dict[str, object] = {
        "requested_model": profile.requested_model,
        "profile_identity": (
            controls.plan_profile_identity or resolved_comparison_profile_identity(profile)
        ),
        "harness_config_identity": (
            controls.plan_harness_config_identity
            or canonical_digest(profile.model_dump(mode="json"))
        ),
    }
    if isinstance(profile, ModelProfile):
        expected.update(
            lane=EvaluationLane.MODEL,
            harness="direct-model",
            provider_route=profile.provider_route_identity,
            reasoning_effort=profile.reasoning.effort,
        )
        if slot.effective_runtime_profile_identity is not None:
            expected["effective_runtime_profile_identity"] = canonical_digest(
                profile.model_dump(mode="json")
            )
    else:
        expected.update(
            lane=EvaluationLane.HARNESS,
            provider_route=profile.provider_route,
            reasoning_effort=(
                profile.reasoning_effort if isinstance(profile, CodexHarnessProfile) else None
            ),
        )
        if isinstance(profile, CodexHarnessProfile):
            expected.update(harness="codex", harness_version=profile.codex_cli_version)
        else:
            expected.update(harness=profile.harness.value, harness_version=profile.cli_version)
            if slot.harness == "deepseek" and profile.harness.value == "deepseek-harness":
                expected["harness"] = "deepseek"  # Existing frozen one-way alias.
    mismatches = sorted(name for name, value in expected.items() if getattr(slot, name) != value)
    if mismatches:
        # Never include configured values or provider diagnostics in this error.
        raise ExecutionControlMismatch("execution configuration mismatch: " + ",".join(mismatches))


class ExecutionDispatcher:
    """Resolve trusted references and invoke existing runners; no queue or retry loop."""

    def __init__(
        self, repository_root: Path, bindings: Mapping[str, ExperimentLaneBinding]
    ) -> None:
        self.repository_root = repository_root.resolve()
        self.bindings = dict(bindings)

    def capabilities(self, cell_id: str) -> ExecutionCapabilities:
        binding = self.bindings.get(cell_id)
        if binding is None:
            raise ExecutionContractError("no execution binding for the selected cell")
        catalog = execution_capabilities()
        controls = _binding_controls(binding)
        if controls is not None and isinstance(controls.profile, ModelProfile):
            return catalog["direct-model"]
        if controls is not None and isinstance(controls.profile, CodexHarnessProfile):
            return catalog["codex"]
        if controls is not None and isinstance(controls.profile, MultiHarnessProfile):
            return catalog[controls.profile.harness.value]
        return ExecutionCapabilities(
            transport="LEGACY",
            isolated_workspace=False,
            observed_model="UNKNOWN",
            trace="UNKNOWN",
        )

    async def execute(self, request: ExecutionRequest) -> LaneRunResult:
        capabilities = self.capabilities(request.slot.cell_id)
        unsupported = [
            name for name in request.required_capabilities if not getattr(capabilities, name)
        ]
        if unsupported:
            raise ExecutionContractError(
                "unsupported execution capabilities: " + ",".join(unsupported)
            )
        binding = self.bindings[request.slot.cell_id]
        controls = _binding_controls(binding)
        if controls is not None:
            _validate_binding(controls, request.slot)
        # Re-resolve at dispatch: edited packages, verifier, budget or escaping symlinks
        # must not reach a provider simply because the earlier plan was valid.
        resolved = _resolve_task(self.repository_root, request.slot.task.package_path)
        if resolved.task != request.slot.task or request.slot.lane not in resolved.lane_support:
            raise ExecutionControlMismatch("execution task, verifier or task budget changed")
        task_path = (self.repository_root / request.slot.task.package_path).resolve()
        return await binding.run(task_path, request.execution_id)
