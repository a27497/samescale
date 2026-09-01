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
from harnesslab.db.models.experiment import ExperimentRunRecord
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
    CampaignHTTPClientPool,
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

MATRIX_IDS = {
    "v2": "core-real-matrix-v2",
    "v3": "core-real-matrix-v3",
    "v5": "core-real-matrix-v5",
}
MATRIX_CANARY_TASK_ID = "core-python-deduplicate"
MATRIX_PILOT_TASK_IDS = (
    MATRIX_CANARY_TASK_ID,
    "core-java-deduplicate",
    "core-typescript-deduplicate",
)
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
    matrix_id: str
    cells: Literal[7] = 7
    tasks: Literal[18] = 18
    repeats: Literal[5] = 5
    logical_runs: Literal[630] = 630
    real_calls: Literal[0] = 0
    resume_idempotent: Literal[True] = True
    queue_executor: Literal["POSTGRESQL_EXISTING_PHASE_G"] = "POSTGRESQL_EXISTING_PHASE_G"
    default_concurrency: Literal[2] = 2
    max_concurrency: Literal[4] = 4
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
    def load(cls, repository_root: Path, *, plan_version: str = "v2") -> MatrixControlPlane:
        if plan_version not in MATRIX_IDS:
            raise MatrixControlPlaneError("plan version must be v2, v3, or v5")
        return cls(SmokeControlPlane.load(repository_root, plan_version=plan_version))

    @property
    def matrix_id(self) -> str:
        return self.release_plan.experiment_id

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
                    resource_envelope_identity=budget_identity,
                )
            )
        spec = ExperimentSpec(
            experiment_id=self.matrix_id,
            name=f"HarnessLab Core Real Matrix {self.matrix_id.rsplit('-', 1)[-1]}",
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
                    intent=ComparabilityIntent.CONTROLLED_ABLATION,
                ),
            ),
        )
        plan = build_experiment_plan(spec, self.repository_root)
        self._validate_plan(plan)
        return plan

    def _validate_plan(self, plan: ExperimentPlan) -> None:
        if (
            plan.experiment_id != self.matrix_id
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
            matrix_id=self.matrix_id,
            release_plan_digest=self.release_plan.digest,
            experiment_plan_digest=plan.digest,
            cells_detail=detail,
        )

    def select_slots(
        self,
        runtime: RuntimeIdentities,
        selection: Literal["canary", "pilot", "remaining"],
    ) -> tuple[str, tuple[str, ...]]:
        """Select logical slots from the immutable 630-slot v3 plan without re-identifying them."""

        if self.matrix_id != MATRIX_IDS["v3"]:
            raise MatrixControlPlaneError("Matrix slot selection is defined only for v3")
        full = self.build_plan(runtime)
        if selection == "canary":
            task_ids = {MATRIX_CANARY_TASK_ID}
            expected = MATRIX_CELL_COUNT
        elif selection == "pilot":
            task_ids = set(MATRIX_PILOT_TASK_IDS)
            expected = MATRIX_CELL_COUNT * len(MATRIX_PILOT_TASK_IDS)
        elif selection == "remaining":
            task_ids = {task.task_id for task in full.tasks}
            expected = MATRIX_LOGICAL_RUNS
        else:  # pragma: no cover - Literal is also checked at the CLI boundary
            raise MatrixControlPlaneError("selection must be canary, pilot, or remaining")
        available = {task.task_id for task in full.tasks}
        if not task_ids <= available:
            raise MatrixControlPlaneError("frozen Matrix representative task is unavailable")
        selected = tuple(
            slot.slot_id
            for slot in full.run_slots
            if slot.task.task_id in task_ids
            and (selection == "remaining" or slot.repeat_index == 0)
        )
        if len(selected) != expected or len(set(selected)) != expected:
            raise MatrixControlPlaneError(
                "Matrix selection does not contain the exact logical slots"
            )
        return full.digest, selected


class _DirectProductionBinding:
    def __init__(
        self,
        *,
        profile: ModelProfile,
        provider: ProviderAdapter,
        environment: Mapping[str, str],
        artifact_root: Path,
        runtime_root: Path,
        plan_profile_identity: str | None = None,
        plan_harness_config_identity: str | None = None,
    ) -> None:
        self.profile = profile
        self.provider = provider
        self.environment = dict(environment)
        self.artifact_root = artifact_root
        self.runtime_root = runtime_root
        self.plan_profile_identity = plan_profile_identity
        self.plan_harness_config_identity = plan_harness_config_identity

    async def run(self, task_path: Path, run_id: str) -> DirectModelRunResult:
        return await DirectModelRunner(
            artifact_root=self.artifact_root,
            runtime_root=self.runtime_root,
            environment=self.environment,
            allow_custom_endpoint=True,
            plan_profile_identity=self.plan_profile_identity,
            plan_harness_config_identity=self.plan_harness_config_identity,
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
        plan_profile_identity: str | None = None,
        plan_harness_config_identity: str | None = None,
    ) -> None:
        self.profile = profile
        self.provider_url = provider_url
        self.proxy_image = proxy_image
        self.credentials = dict(credentials)
        self.artifact_root = artifact_root
        self.runtime_root = runtime_root
        self.plan_profile_identity = plan_profile_identity
        self.plan_harness_config_identity = plan_harness_config_identity

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
            plan_profile_identity=self.plan_profile_identity,
            plan_harness_config_identity=self.plan_harness_config_identity,
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
        plan_profile_identity: str | None = None,
        plan_harness_config_identity: str | None = None,
    ) -> None:
        self.profile = profile
        self.adapter = adapter
        self.provider_url = provider_url
        self.proxy_image = proxy_image
        self.credentials = dict(credentials)
        self.artifact_root = artifact_root
        self.runtime_root = runtime_root
        self.plan_profile_identity = plan_profile_identity
        self.plan_harness_config_identity = plan_harness_config_identity

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
            plan_profile_identity=self.plan_profile_identity,
            plan_harness_config_identity=self.plan_harness_config_identity,
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
    http_pool: CampaignHTTPClientPool | None = None,
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
            client = None
            if http_pool is not None:
                if profile.credential_reference is None:
                    raise MatrixControlPlaneError(
                        "Direct Matrix profile lacks a credential reference"
                    )
                client = http_pool.client_for(
                    profile.provider_route_identity,
                    profile.credential_reference,
                )
            direct_adapter = adapters[profile.protocol.value](
                client=client,
                environment=environment,
            )
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
    matrix_id: str
    plan_digest: str
    logical_runs: int
    executed_runs: int
    concurrency: int
    selection: str
    selected_slots: int
    terminal_selected_slots: int
    pending_selected_slots: int


@dataclass(frozen=True)
class MatrixCanaryRunResult:
    cell_id: str
    task_id: str
    status: str
    normalized_outcome: str | None
    source_outcome: str | None
    evidence_digest: str | None


@dataclass(frozen=True)
class MatrixCanaryExecutionResult:
    matrix_id: str
    plan_digest: str
    logical_runs: int
    executed_runs: int
    technical_pass: bool
    results: tuple[MatrixCanaryRunResult, ...]


async def execute_real_matrix(
    repository_root: Path,
    *,
    allow_real_matrix: bool,
    max_runs: int | None,
    concurrency: int = 1,
    artifact_root: Path,
    runtime_root: Path,
    environment: Mapping[str, str] | None = None,
    plan_version: str = "v2",
    selection: Literal["canary", "pilot", "remaining"] = "remaining",
) -> MatrixExecutionResult:
    if not allow_real_matrix:
        raise MatrixControlPlaneError("real Matrix requires --allow-real-matrix")
    if max_runs is None:
        raise MatrixControlPlaneError("real Matrix requires an explicit --max-runs bound")
    if not 1 <= max_runs <= MATRIX_LOGICAL_RUNS:
        raise MatrixControlPlaneError("--max-runs must be between 1 and 630")
    if not 1 <= concurrency <= 4:
        raise MatrixControlPlaneError("--concurrency must be between 1 and 4")
    selected_environment = environment if environment is not None else os.environ
    control = MatrixControlPlane.load(repository_root, plan_version=plan_version)
    control.smoke.validate_real_environment(selected_environment)
    await preflight_egress_network_isolation()
    runtime = await resolve_runtime_identities()
    plan = control.build_plan(runtime)
    if plan_version == "v3":
        selection_digest, selected_slot_ids = control.select_slots(runtime, selection)
        if selection_digest != plan.digest:
            raise MatrixControlPlaneError("Matrix selection plan identity drifted")
    elif selection != "remaining":
        raise MatrixControlPlaneError("subset selection is defined only for v3")
    else:
        selected_slot_ids = tuple(slot.slot_id for slot in plan.run_slots)
    engine = create_engine(Settings())
    factory = create_session_factory(engine)
    try:
        async with CampaignHTTPClientPool(max_connections_per_route=2) as http_pool:
            bindings = production_matrix_bindings(
                control,
                runtime,
                selected_environment,
                artifact_root=artifact_root,
                runtime_root=runtime_root,
                http_pool=http_pool,
            )
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
                slot_ids=selected_slot_ids,
            )
        terminal_statuses = {"completed", "failed_infra", "failed_subject", "cancelled"}
        async with factory() as session:
            persisted: list[ExperimentRunRecord | None] = []
            for slot_id in selected_slot_ids:
                persisted.append(
                    await session.get(ExperimentRunRecord, f"run-{slot_id.removeprefix('sha256:')}")
                )
        terminal_selected = sum(
            record is not None and record.status in terminal_statuses for record in persisted
        )
        return MatrixExecutionResult(
            matrix_id=control.matrix_id,
            plan_digest=plan.digest,
            logical_runs=enqueued.logical_run_count,
            executed_runs=len(executed),
            concurrency=concurrency,
            selection=selection,
            selected_slots=len(selected_slot_ids),
            terminal_selected_slots=terminal_selected,
            pending_selected_slots=len(selected_slot_ids) - terminal_selected,
        )
    finally:
        await engine.dispose()


async def execute_real_matrix_canary(
    repository_root: Path,
    *,
    allow_real_matrix_canary: bool,
    concurrency: int = 1,
    artifact_root: Path,
    runtime_root: Path,
    environment: Mapping[str, str] | None = None,
) -> MatrixCanaryExecutionResult:
    if not allow_real_matrix_canary:
        raise MatrixControlPlaneError("real Matrix canary requires --allow-real-matrix-canary")
    if not 1 <= concurrency <= 7:
        raise MatrixControlPlaneError("--concurrency must be between 1 and 7")
    selected_environment = environment if environment is not None else os.environ
    control = MatrixControlPlane.load(repository_root, plan_version="v3")
    control.smoke.validate_real_environment(selected_environment)
    await preflight_egress_network_isolation()
    runtime = await resolve_runtime_identities()
    plan = control.build_plan(runtime)
    selection_digest, selected_slot_ids = control.select_slots(runtime, "canary")
    if selection_digest != plan.digest:
        raise MatrixControlPlaneError("Matrix canary selection plan identity drifted")
    engine = create_engine(Settings())
    factory = create_session_factory(engine)
    try:
        async with CampaignHTTPClientPool(max_connections_per_route=2) as http_pool:
            bindings = production_matrix_bindings(
                control,
                runtime,
                selected_environment,
                artifact_root=artifact_root,
                runtime_root=runtime_root,
                http_pool=http_pool,
            )
            async with factory() as session, session.begin():
                enqueued = await enqueue_plan(session, plan)
            worker = ExperimentRunExecutor(
                repository_root=control.repository_root,
                session_factory=factory,
                bindings=bindings,
                owner="harnesslab-phase-k-matrix-canary",
            )
            executed = await worker.run_bounded(
                plan.experiment_id,
                max_runs=MATRIX_CELL_COUNT,
                concurrency=concurrency,
                slot_ids=selected_slot_ids,
            )
        safe_results = tuple(
            MatrixCanaryRunResult(
                cell_id=item.cell_id,
                task_id=item.slot.task.task_id,
                status=item.status.value,
                normalized_outcome=(
                    item.normalized_outcome.value if item.normalized_outcome is not None else None
                ),
                source_outcome=item.source_outcome,
                evidence_digest=item.evidence_digest,
            )
            for item in sorted(executed, key=lambda snapshot: snapshot.cell_id)
        )
        expected_cells = {cell.id for cell in plan.cells}
        technical_pass = (
            enqueued.logical_run_count == MATRIX_LOGICAL_RUNS
            and len(executed) == MATRIX_CELL_COUNT
            and {item.cell_id for item in executed} == expected_cells
            and all(
                item.slot.task.task_id == MATRIX_CANARY_TASK_ID
                and item.slot.repeat_index == 0
                and item.status.value in {"completed", "failed_subject"}
                and item.artifact_manifest_path is not None
                and item.evidence_digest is not None
                for item in executed
            )
        )
        return MatrixCanaryExecutionResult(
            matrix_id=control.matrix_id,
            plan_digest=plan.digest,
            logical_runs=len(selected_slot_ids),
            executed_runs=len(executed),
            technical_pass=technical_pass,
            results=safe_results,
        )
    finally:
        await engine.dispose()
