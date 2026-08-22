from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from harnesslab.contracts.common import EvaluationLane, NetworkPolicy, Protocol
from harnesslab.contracts.experiment import ExperimentConfig, ExperimentDefinition
from harnesslab.contracts.harness import HarnessProfile
from harnesslab.contracts.model import ModelProfile, ReasoningProfile
from harnesslab.contracts.run import RunRecord, RunStatus
from harnesslab.contracts.task import (
    ResourceBudget,
    TaskDefinition,
    VerifierReference,
    WorkspaceReference,
)

DIGEST_A = "sha256:" + "a" * 64
DIGEST_B = "sha256:" + "b" * 64
DIGEST_C = "sha256:" + "c" * 64


def make_task() -> TaskDefinition:
    return TaskDefinition(
        id="task.python.refactor",
        version="1.0.0",
        domain="software-engineering",
        lane_support={EvaluationLane.MODEL, EvaluationLane.HARNESS},
        instruction="Refactor the supplied module without changing behavior.",
        workspace=WorkspaceReference(uri="artifact://workspaces/example", digest=DIGEST_A),
        verifier=VerifierReference(kind="hidden-tests", version="tests-v1"),
        budget=ResourceBudget(timeout_seconds=600, network_policy=NetworkPolicy.DENY),
        content_digest=DIGEST_B,
    )


def make_model() -> ModelProfile:
    return ModelProfile(
        requested_model="example-model-2026",
        provider="example-provider",
        route="/v1/responses",
        protocol=Protocol.RESPONSES,
        reasoning=ReasoningProfile(effort="high", max_output_tokens=4096),
        credential_reference="EXAMPLE_API_KEY",
    )


def make_harness() -> HarnessProfile:
    return HarnessProfile(
        id="reference-cli",
        adapter_type="cli",
        version="0.1.0",
        git_sha="abcdef1",
        model_mapping={"example-model-2026": "provider-model-id"},
        instruction_profile="base-v1",
        tool_profile="shell-v1",
        network_policy=NetworkPolicy.DENY,
        trace_parser_version="trace-v1",
    )


def test_experiment_serializes_task_model_harness_and_config() -> None:
    experiment = ExperimentDefinition(
        id="experiment-a",
        task=make_task(),
        model=make_model(),
        harness=make_harness(),
        config=ExperimentConfig(
            repetitions=3,
            prompt_hash=DIGEST_A,
            harness_config_digest=DIGEST_B,
            sandbox_image="harnesslab/sandbox@sha256:placeholder",
            judge_definition=None,
            seed=42,
        ),
    )

    payload = experiment.model_dump(mode="json")
    assert payload["task"]["version"] == "1.0.0"
    assert payload["model"]["requested_model"] == "example-model-2026"
    assert payload["harness"]["trace_parser_version"] == "trace-v1"
    assert payload["config"]["repetitions"] == 3


def test_task_rejects_empty_lane_support() -> None:
    with pytest.raises(ValidationError, match="lane_support"):
        TaskDefinition(
            id="task-a",
            version="1",
            domain="code",
            lane_support=set(),
            instruction="Do work.",
            workspace=WorkspaceReference(uri="artifact://workspace", digest=DIGEST_A),
            verifier=VerifierReference(kind="tests", version="1"),
            budget=ResourceBudget(timeout_seconds=60),
            content_digest=DIGEST_B,
        )


def test_model_rejects_credential_value_in_reference_field() -> None:
    with pytest.raises(ValidationError, match="credential_reference"):
        ModelProfile(
            requested_model="model",
            provider="provider",
            route="/responses",
            protocol=Protocol.RESPONSES,
            credential_reference="not-a-reference-value",
        )


def test_succeeded_run_keeps_requested_and_observed_models_distinct() -> None:
    now = datetime.now(UTC)
    run = RunRecord(
        id=uuid4(),
        experiment_id="experiment-a",
        status=RunStatus.SUCCEEDED,
        task_id="task.python.refactor",
        task_version="1.0.0",
        workspace_digest=DIGEST_A,
        prompt_hash=DIGEST_B,
        verifier_version="tests-v1",
        requested_model="friendly-alias",
        observed_model="provider-model-2026-08-01",
        provider="example-provider",
        route="/v1/responses",
        protocol=Protocol.RESPONSES,
        harness_id="reference-cli",
        harness_version="0.1.0",
        harness_config_digest=DIGEST_C,
        reasoning_budget="high/4096",
        network_policy=NetworkPolicy.DENY,
        sandbox_image="harnesslab/sandbox@sha256:placeholder",
        judge_definition=None,
        started_at=now,
        finished_at=now + timedelta(seconds=1),
    )

    assert run.requested_model != run.observed_model
    assert run.model_dump(mode="json")["status"] == "succeeded"


def test_succeeded_run_requires_observed_model() -> None:
    with pytest.raises(ValidationError, match="observed_model"):
        RunRecord(
            id=uuid4(),
            experiment_id="experiment-a",
            status=RunStatus.SUCCEEDED,
            task_id="task-a",
            task_version="1",
            workspace_digest=DIGEST_A,
            prompt_hash=DIGEST_B,
            verifier_version="v1",
            requested_model="alias",
            provider="provider",
            route="/responses",
            protocol=Protocol.RESPONSES,
            harness_id="harness-a",
            harness_version="1",
            harness_config_digest=DIGEST_C,
            network_policy=NetworkPolicy.DENY,
            sandbox_image="sandbox:planned",
        )
