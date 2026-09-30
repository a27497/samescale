from __future__ import annotations

from pathlib import Path

from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.common import EvaluationLane
from harnesslab.experiment.executor import (
    CodexHarnessBinding,
    ExperimentLaneBinding,
    resolved_comparison_profile_identity,
)
from harnesslab.experiment.plan import ExperimentPlan, build_experiment_plan
from harnesslab.experiment.spec import ExperimentCellSpec, ExperimentSpec
from harnesslab.harness_lane.adapter import CodexExecutionPlan
from harnesslab.harness_lane.fake import FakeCodexBackend, FakeCodexScenario
from harnesslab.harness_lane.models import CodexProcessCapture
from harnesslab.harness_lane.profile import canonical_codex_profile
from harnesslab.harness_lane.runner import CodexHarnessRunner
from harnesslab.sandbox.models import ImageIdentity
from harnesslab.tasks.package import TaskPackage


class DemoFakeBackend:
    def __init__(self, candidate: bool) -> None:
        self.candidate = candidate

    @property
    def artifact_secret_values(self) -> tuple[str, ...]:
        return ()

    async def run(self, plan: CodexExecutionPlan) -> CodexProcessCapture:
        scenario = (
            FakeCodexScenario.SOLVE
            if self.candidate or plan.task_id == "micro-python-clamp"
            else FakeCodexScenario.FILE_CHANGE_LIE
        )
        return await FakeCodexBackend(scenario).run(plan)


def demo_plan(
    repository: Path,
    experiment_id: str,
    artifact_root: Path,
    runtime_root: Path,
    *,
    candidate: bool,
) -> tuple[ExperimentPlan, dict[str, ExperimentLaneBinding]]:
    """New plans and IDs, using Fake adapters plus the existing independent verifier."""
    package = TaskPackage.load(repository / "tasks/micro-python-clamp/1.0.0")
    profile = canonical_codex_profile(
        ImageIdentity(reference="public-demo-fake:1", image_id="sha256:" + "7" * 64),
        requested_model="fake-public-demo-model",
        reasoning_effort="low",
    )
    cell = ExperimentCellSpec(
        id="fixture-codex",
        lane=EvaluationLane.HARNESS,
        requested_model=profile.requested_model,
        provider_route=profile.provider_route,
        profile_reference="builtin:public-demo-fake",
        profile_identity=resolved_comparison_profile_identity(profile),
        harness="codex",
        harness_version=profile.codex_cli_version,
        harness_config_identity=profile.fingerprint,
        reasoning_effort="low",
        resource_budget_identity=canonical_digest(
            package.definition.budget.model_dump(mode="json")
        ),
        network_policy="deny",
        runner_contract="codex-harness-v1",
    )
    spec = ExperimentSpec(
        experiment_id=experiment_id,
        name="Public Demo — offline fixture " + ("candidate" if candidate else "baseline"),
        task_packages=("tasks/micro-python-clamp/1.0.0", "tasks/micro-typescript-clamp/1.0.0"),
        cells=(cell,),
        repeat_count=3,
        execution_seed=20260930,
        comparison_intent="GENERAL",
    )
    return build_experiment_plan(spec, repository), {
        cell.id: CodexHarnessBinding(
            CodexHarnessRunner(
                artifact_root=artifact_root, runtime_root=runtime_root / experiment_id
            ),
            profile,
            DemoFakeBackend(candidate),
        )
    }
