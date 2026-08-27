from __future__ import annotations

import hashlib
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from harnesslab.comparability.models import ComparabilityIntent, canonical_digest
from harnesslab.contracts.common import EvaluationLane
from harnesslab.contracts.model import ModelProfile
from harnesslab.core.config import Settings
from harnesslab.db.session import create_engine, create_session_factory
from harnesslab.egress import (
    ProviderScopedDockerBoundary,
    boundary_for_provider_url,
    preflight_egress_network_isolation,
)
from harnesslab.experiment.executor import (
    ExperimentLaneBinding,
    ExperimentRunExecutor,
    resolved_comparison_profile_identity,
)
from harnesslab.experiment.plan import ExperimentPlan, build_experiment_plan
from harnesslab.experiment.queue import enqueue_plan
from harnesslab.experiment.spec import (
    AblationSpec,
    ExperimentCellSpec,
    ExperimentSpec,
    PairedComparisonSpec,
)
from harnesslab.harness_lane.docker_backend import DockerCodexBackend
from harnesslab.harness_lane.models import CodexHarnessProfile, HarnessLaneRunResult
from harnesslab.harness_lane.profile import CODEX_CLI_VERSION
from harnesslab.harness_lane.runner import CodexHarnessRunner
from harnesslab.model_lane.models import DirectModelRunResult, ProviderAdapter
from harnesslab.model_lane.providers import (
    AnthropicMessagesAdapter,
    OpenAICompatibleChatAdapter,
    OpenAIResponsesAdapter,
)
from harnesslab.model_lane.runner import DirectModelRunner
from harnesslab.multi_harness.adapter import (
    ClaudeCodeAdapter,
    DeepSeekHarnessAdapter,
    MultiHarnessAdapter,
)
from harnesslab.multi_harness.docker_backend import DockerMultiHarnessBackend
from harnesslab.multi_harness.models import MultiHarnessProfile, MultiHarnessRunResult
from harnesslab.multi_harness.runner import MultiHarnessRunner
from harnesslab.release.contracts import load_core_corpus
from harnesslab.release.smoke import (
    REQUIRED_CONFIGURATION_REFERENCES,
    RuntimeIdentities,
    SmokeControlPlane,
    SmokeControlPlaneError,
    resolve_runtime_identities,
)
from harnesslab.sandbox.models import ImageIdentity
from harnesslab.tasks.package import TaskPackage

MATRIX_ID = "core-real-matrix-v2"
MATRIX_CELL_COUNT = 7
MATRIX_TASK_COUNT = 18
MATRIX_REPEAT_COUNT = 5
MATRIX_LOGICAL_RUNS = 630
MATRIX_RUNNER_CONTRACTS = {
    "direct-model": "phase-k-real-direct-v1",
    "codex": "phase-k-real-codex-v1",
    "claude-code": "phase-k-real-claude-v1",
    "deepseek-e1": "phase-k-real-deepseek-v1",
}


class MatrixControlPlaneError(SmokeControlPlaneError):
    """The strict frozen Phase-K Matrix cannot be planned or executed safely."""


class MatrixCellPreflight(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    cell_id: str
    lane: str
    runner_contract: str
    requested_model: str
    provider_route: str
    harness: str
    harness_version: str
    reasoning_effort: str | None
    profile_identity: str
    harness_config_identity: str
    credential_references: tuple[str, ...]


class MatrixPreflightReceipt(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    matrix_id: Literal["core-real-matrix-v2"] = "core-real-matrix-v2"
    cells: Literal[7] = 7
    tasks: Literal[18] = 18
    repeats: Literal[5] = 5
    logical_runs: Literal[630] = 630
    real_calls: Literal[0] = 0
    resume_idempotent: Literal[True] = True
    queue_executor: Literal["POSTGRESQL_EXISTING_PHASE_G"] = "POSTGRESQL_EXISTING_PHASE_G"
    default_concurrency: Literal[1] = 1
    max_concurrency: Literal[8] = 8
    max_runs_required_for_execution: Literal[True] = True
    release_plan_digest: str
    experiment_plan_digest: str
    output_token_ceiling: Literal[1260000] = 1_260_000
    cells_detail: tuple[MatrixCellPreflight, ...]


def _profile_environment() -> dict[str, str]:
    """Resolve URL references to a non-routable placeholder without credentials or networking."""

    return {"HARNESSLAB_GPT56_RELAY_BASE_URL": "https://matrix-preflight.invalid"}


class MatrixControlPlane:
    def __init__(self, smoke: SmokeControlPlane) -> None:
        self.smoke = smoke
        self.repository_root = smoke.repository_root
        self.release_plan = smoke.release_plan

    @classmethod
    def load(cls, repository_root: Path) -> MatrixControlPlane:
        return cls(SmokeControlPlane.load(repository_root))

    def _profiles(
        self, runtime: RuntimeIdentities
    ) -> dict[str, ModelProfile | CodexHarnessProfile | MultiHarnessProfile]:
        runtime.validate()
        profiles: dict[str, ModelProfile | CodexHarnessProfile | MultiHarnessProfile] = {}
        by_id = {
            item.frozen.call.profile_id: item
            for item in self.smoke.resolve_real_bindings(
                {
                    **_profile_environment(),
                    "HARNESSLAB_GPT56_RELAY_API_KEY": "REFERENCE_ONLY",
                    "HARNESSLAB_OPENCODE_GO_API_KEY": "REFERENCE_ONLY",
                    "DEEPSEEK_API_KEY": "REFERENCE_ONLY",
                },
                runtime,
            )
        }
        for cell in self.release_plan.cells:
            if cell.profile_slot is None:
                raise MatrixControlPlaneError("Matrix cell has no frozen profile slot")
            resolved = by_id.get(cell.profile_slot)
            if resolved is None:
                raise MatrixControlPlaneError("Matrix cell profile is not smoke-bound")
            profiles[cell.cell_id] = resolved.runtime_profile
        return profiles

    def build_plan(self, runtime: RuntimeIdentities) -> ExperimentPlan:
        profiles = self._profiles(runtime)
        corpus = self.smoke.release_plan.corpus_reference
        corpus_manifest = load_core_corpus(self.repository_root / corpus)
        task_paths = tuple(task.package_path for task in corpus_manifest.tasks)
        first = TaskPackage.load(self.repository_root / task_paths[0])
        budget_identity = canonical_digest(first.definition.budget.model_dump(mode="json"))
        cells: list[ExperimentCellSpec] = []
        selected = {profile.profile_id: profile for profile in self.release_plan.selected_profiles}
        for frozen in self.release_plan.cells:
            profile = profiles[frozen.cell_id]
            provider = selected[frozen.cell_id]
            if isinstance(profile, ModelProfile):
                harness = "direct-model"
                harness_version = "evidence-schema-1"
                config_identity = canonical_digest(profile.model_dump(mode="json"))
                profile_reference = f"builtin:phase-k-{frozen.cell_id}"
            elif isinstance(profile, CodexHarnessProfile):
                harness = "codex"
                harness_version = CODEX_CLI_VERSION
                config_identity = profile.fingerprint
                profile_reference = "builtin:phase-k-codex-gpt56"
            else:
                harness = "claude-code" if frozen.runtime == "claude-code" else "deepseek"
                harness_version = profile.cli_version
                config_identity = profile.fingerprint
                profile_reference = f"builtin:phase-k-{frozen.runtime}"
            expected_harness = {
                "direct-model": "direct-model",
                "codex": "codex",
                "claude-code": "claude-code",
                "deepseek-e1": "deepseek",
            }[frozen.runtime]
            if harness != expected_harness:
                raise MatrixControlPlaneError(f"Matrix runtime drifted: {frozen.cell_id}")
            references = tuple(
                reference
                for reference in (provider.base_url_reference, provider.credential_reference)
                if reference is not None
            )
            if any(reference not in REQUIRED_CONFIGURATION_REFERENCES for reference in references):
                raise MatrixControlPlaneError(
                    "Matrix contains an undeclared configuration reference"
                )
            cells.append(
                ExperimentCellSpec(
                    id=frozen.cell_id,
                    lane=(EvaluationLane.MODEL if frozen.lane == "M" else EvaluationLane.HARNESS),
                    requested_model=profile.requested_model,
                    provider_route=provider.route_identity,
                    profile_reference=profile_reference,
                    profile_identity=resolved_comparison_profile_identity(profile),
                    harness=harness,
                    harness_version=harness_version,
                    harness_config_identity=config_identity,
                    reasoning_effort=frozen.reasoning_effort,
                    resource_budget_identity=budget_identity,
                    network_policy=first.definition.budget.network_policy,
                    runner_contract=MATRIX_RUNNER_CONTRACTS[frozen.runtime],
                    credential_reference=provider.credential_reference,
                )
            )
        spec = ExperimentSpec(
            experiment_id=MATRIX_ID,
            name="HarnessLab Core Real Matrix v2",
            task_packages=task_paths,
            cells=tuple(cells),
            repeat_count=MATRIX_REPEAT_COUNT,
            execution_seed=self.release_plan.execution_seed,
            comparison_intent=ComparabilityIntent.HARNESS_UPLIFT,
            paired_comparisons=(
                PairedComparisonSpec(
                    id=self.release_plan.paired_lane.pair_id,
                    left_cell_id=self.release_plan.paired_lane.left_cell_id,
                    right_cell_id=self.release_plan.paired_lane.right_cell_id,
                ),
            ),
            ablations=(
                AblationSpec(
                    id=self.release_plan.ablation.ablation_id,
                    base_cell_id=self.release_plan.ablation.base_cell_id,
                    variant_cell_id=self.release_plan.ablation.variant_cell_id,
                    changed_dimension="reasoning_effort",
                ),
            ),
        )
        plan = build_experiment_plan(spec, self.repository_root)
        self._validate_plan(plan)
        return plan

    def _validate_plan(self, plan: ExperimentPlan) -> None:
        if (
            plan.experiment_id != MATRIX_ID
            or len(plan.cells) != MATRIX_CELL_COUNT
            or len(plan.tasks) != MATRIX_TASK_COUNT
            or plan.repeat_count != MATRIX_REPEAT_COUNT
            or len(plan.run_slots) != MATRIX_LOGICAL_RUNS
            or len({slot.slot_id for slot in plan.run_slots}) != MATRIX_LOGICAL_RUNS
        ):
            raise MatrixControlPlaneError("Matrix expansion is not exactly 7x18x5=630")
        corpus_by_id = {
            task.task_id: task
            for task in load_core_corpus(
                self.repository_root / self.release_plan.corpus_reference
            ).tasks
        }
        if any(corpus_by_id[task.task_id].task_digest != task.task_digest for task in plan.tasks):
            raise MatrixControlPlaneError("Matrix task digest drifted from frozen Core corpus")

    def preflight(self, runtime: RuntimeIdentities) -> MatrixPreflightReceipt:
        plan = self.build_plan(runtime)
        selected = {profile.profile_id: profile for profile in self.release_plan.selected_profiles}
        detail = tuple(
            MatrixCellPreflight(
                cell_id=cell.id,
                lane=cell.lane.value,
                runner_contract=cell.runner_contract,
                requested_model=cell.requested_model,
                provider_route=cell.provider_route,
                harness=cell.harness,
                harness_version=cell.harness_version,
                reasoning_effort=cell.reasoning_effort,
                profile_identity=cell.profile_identity,
                harness_config_identity=cell.harness_config_identity,
                credential_references=tuple(
                    reference
                    for reference in (
                        selected[cell.id].base_url_reference,
                        selected[cell.id].credential_reference,
                    )
                    if reference is not None
                ),
            )
            for cell in plan.cells
        )
        return MatrixPreflightReceipt(
            release_plan_digest=self.release_plan.digest,
            experiment_plan_digest=plan.digest,
            cells_detail=detail,
        )


class _DirectProductionBinding:
    def __init__(
        self,
        *,
        profile: ModelProfile,
        provider: ProviderAdapter,
        environment: Mapping[str, str],
        artifact_root: Path,
        runtime_root: Path,
    ) -> None:
        self.profile = profile
        self.provider = provider
        self.environment = dict(environment)
        self.artifact_root = artifact_root
        self.runtime_root = runtime_root

    async def run(self, task_path: Path, run_id: str) -> DirectModelRunResult:
        return await DirectModelRunner(
            artifact_root=self.artifact_root,
            runtime_root=self.runtime_root,
            environment=self.environment,
            allow_custom_endpoint=True,
        ).run(task_path, self.profile, adapter=self.provider, run_id=run_id)


class _CodexProductionBinding:
    def __init__(
        self,
        *,
        profile: CodexHarnessProfile,
        provider_url: str,
        proxy_image: ImageIdentity,
        credentials: Mapping[str, str],
        artifact_root: Path,
        runtime_root: Path,
    ) -> None:
        self.profile = profile
        self.provider_url = provider_url
        self.proxy_image = proxy_image
        self.credentials = dict(credentials)
        self.artifact_root = artifact_root
        self.runtime_root = runtime_root

    def _boundary(self, run_id: str) -> ProviderScopedDockerBoundary:
        token = hashlib.sha256(run_id.encode()).hexdigest()[:16]
        return boundary_for_provider_url(
            self.provider_url,
            network_name=f"hl-matrix-{token}-internal",
            proxy_name=f"hl-matrix-{token}-proxy",
            proxy_image=self.proxy_image,
        )

    async def run(self, task_path: Path, run_id: str) -> HarnessLaneRunResult:
        backend = DockerCodexBackend(
            explicitly_enabled=True,
            credentials=self.credentials,
            egress_boundary=self._boundary(run_id),
        )
        return await CodexHarnessRunner(
            artifact_root=self.artifact_root,
            runtime_root=self.runtime_root,
        ).run(task_path, self.profile, backend=backend, run_id=run_id)


class _MultiProductionBinding:
    def __init__(
        self,
        *,
        profile: MultiHarnessProfile,
        adapter: MultiHarnessAdapter,
        provider_url: str,
        proxy_image: ImageIdentity,
        credentials: Mapping[str, str],
        artifact_root: Path,
        runtime_root: Path,
    ) -> None:
        self.profile = profile
        self.adapter = adapter
        self.provider_url = provider_url
        self.proxy_image = proxy_image
        self.credentials = dict(credentials)
        self.artifact_root = artifact_root
        self.runtime_root = runtime_root

    def _boundary(self, run_id: str) -> ProviderScopedDockerBoundary:
        token = hashlib.sha256(run_id.encode()).hexdigest()[:16]
        return boundary_for_provider_url(
            self.provider_url,
            network_name=f"hl-matrix-{token}-internal",
            proxy_name=f"hl-matrix-{token}-proxy",
            proxy_image=self.proxy_image,
        )

    async def run(self, task_path: Path, run_id: str) -> MultiHarnessRunResult:
        backend = DockerMultiHarnessBackend(
            explicitly_enabled=True,
            credentials=self.credentials,
            egress_boundary=self._boundary(run_id),
        )
        return await MultiHarnessRunner(
            artifact_root=self.artifact_root,
            runtime_root=self.runtime_root,
        ).run(
            task_path,
            self.profile,
            adapter=self.adapter,
            backend=backend,
            run_id=run_id,
        )


def production_matrix_bindings(
    control: MatrixControlPlane,
    runtime: RuntimeIdentities,
    environment: Mapping[str, str],
    *,
    artifact_root: Path,
    runtime_root: Path,
) -> dict[str, ExperimentLaneBinding]:
    control.smoke.validate_real_environment(environment)
    profiles = control._profiles(runtime)
    providers = {item.profile_id: item for item in control.release_plan.selected_profiles}
    bindings: dict[str, ExperimentLaneBinding] = {}
    for frozen in control.release_plan.cells:
        profile = profiles[frozen.cell_id]
        provider = providers[frozen.cell_id]
        artifacts = artifact_root / frozen.cell_id
        runtimes = runtime_root / frozen.cell_id
        if isinstance(profile, ModelProfile):
            adapters = {
                "responses": OpenAIResponsesAdapter,
                "messages": AnthropicMessagesAdapter,
                "chat_completions": OpenAICompatibleChatAdapter,
            }
            direct_adapter = adapters[profile.protocol.value](environment=environment)
            bindings[frozen.cell_id] = _DirectProductionBinding(
                profile=profile,
                provider=direct_adapter,
                environment=environment,
                artifact_root=artifacts,
                runtime_root=runtimes,
            )
        elif isinstance(profile, CodexHarnessProfile):
            bindings[frozen.cell_id] = _CodexProductionBinding(
                profile=profile,
                provider_url=provider.resolve_base_url(environment),
                proxy_image=runtime.egress_proxy_image,
                credentials={
                    reference: environment[reference]
                    for reference in (provider.base_url_reference, provider.credential_reference)
                    if reference is not None
                },
                artifact_root=artifacts,
                runtime_root=runtimes,
            )
        else:
            multi_adapter: MultiHarnessAdapter = (
                ClaudeCodeAdapter()
                if frozen.runtime == "claude-code"
                else DeepSeekHarnessAdapter(observed_config_digest=profile.config_digest or "")
            )
            bindings[frozen.cell_id] = _MultiProductionBinding(
                profile=profile,
                adapter=multi_adapter,
                provider_url=provider.resolve_base_url(environment),
                proxy_image=runtime.egress_proxy_image,
                credentials={
                    provider.credential_reference: environment[provider.credential_reference]
                },
                artifact_root=artifacts,
                runtime_root=runtimes,
            )
    return bindings


@dataclass(frozen=True)
class MatrixExecutionResult:
    plan_digest: str
    logical_runs: int
    executed_runs: int
    concurrency: int


async def execute_real_matrix(
    repository_root: Path,
    *,
    allow_real_matrix: bool,
    max_runs: int | None,
    concurrency: int = 1,
    artifact_root: Path,
    runtime_root: Path,
    environment: Mapping[str, str] | None = None,
) -> MatrixExecutionResult:
    if not allow_real_matrix:
        raise MatrixControlPlaneError("real Matrix requires --allow-real-matrix")
    if max_runs is None:
        raise MatrixControlPlaneError("real Matrix requires an explicit --max-runs bound")
    if not 1 <= max_runs <= MATRIX_LOGICAL_RUNS:
        raise MatrixControlPlaneError("--max-runs must be between 1 and 630")
    if not 1 <= concurrency <= 8:
        raise MatrixControlPlaneError("--concurrency must be between 1 and 8")
    selected_environment = environment if environment is not None else os.environ
    control = MatrixControlPlane.load(repository_root)
    control.smoke.validate_real_environment(selected_environment)
    await preflight_egress_network_isolation()
    runtime = await resolve_runtime_identities()
    plan = control.build_plan(runtime)
    bindings = production_matrix_bindings(
        control,
        runtime,
        selected_environment,
        artifact_root=artifact_root,
        runtime_root=runtime_root,
    )
    engine = create_engine(Settings())
    factory = create_session_factory(engine)
    try:
        async with factory() as session, session.begin():
            enqueued = await enqueue_plan(session, plan)
        worker = ExperimentRunExecutor(
            repository_root=control.repository_root,
            session_factory=factory,
            bindings=bindings,
            owner="harnesslab-phase-k-matrix",
        )
        executed = await worker.run_bounded(
            plan.experiment_id,
            max_runs=max_runs,
            concurrency=concurrency,
        )
        return MatrixExecutionResult(
            plan_digest=plan.digest,
            logical_runs=enqueued.logical_run_count,
            executed_runs=len(executed),
            concurrency=concurrency,
        )
    finally:
        await engine.dispose()
