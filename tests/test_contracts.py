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
    ContextBundleReference,
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
        context_bundle=ContextBundleReference(uri="artifact://context/example", digest=DIGEST_C),
        verifier=VerifierReference(kind="hidden-tests", version="tests-v1"),
        budget=ResourceBudget(timeout_seconds=600, network_policy=NetworkPolicy.DENY),
        content_digest=DIGEST_B,
    )


def make_model() -> ModelProfile:
    return ModelProfile(
        requested_model="example-model-2026",
        provider="example-provider",
        base_url="https://provider.example/v1",
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


def make_run(
    *,
    status: RunStatus = RunStatus.COMPLETED,
    observed_model: str | None = "provider-model-2026-08-01",
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
) -> RunRecord:
    return RunRecord(
        id=uuid4(),
        experiment_id="experiment-a",
        status=status,
        task_id="task.python.refactor",
        task_version="1.0.0",
        workspace_digest=DIGEST_A,
        prompt_hash=DIGEST_B,
        verifier_version="tests-v1",
        requested_model="friendly-alias",
        observed_model=observed_model,
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
        started_at=started_at,
        finished_at=finished_at,
    )


def test_evaluation_lanes_use_paired_not_product() -> None:
    assert {lane.name: lane.value for lane in EvaluationLane} == {
        "MODEL": "M",
        "HARNESS": "H",
        "PAIRED": "P",
        "JUDGE": "J",
    }
    assert not hasattr(EvaluationLane, "PRODUCT")


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
    assert payload["task"]["context_bundle"] == {
        "uri": "artifact://context/example",
        "digest": DIGEST_C,
    }
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


def test_context_bundle_remains_optional_for_paired_lane() -> None:
    payload = make_task().model_dump(mode="json")
    payload["lane_support"] = ["P"]
    payload["context_bundle"] = None

    task = TaskDefinition.model_validate(payload)

    assert task.lane_support == frozenset({EvaluationLane.PAIRED})
    assert task.context_bundle is None


def test_model_rejects_credential_value_in_reference_field() -> None:
    with pytest.raises(ValidationError, match="credential_reference"):
        ModelProfile(
            requested_model="model",
            provider="provider",
            base_url="https://provider.example/v1",
            route="/responses",
            protocol=Protocol.RESPONSES,
            credential_reference="not-a-reference-value",
        )


def test_model_route_rejects_embedded_credentials_and_cross_origin_route() -> None:
    with pytest.raises(ValidationError, match="credentials"):
        ModelProfile(
            requested_model="model",
            provider="provider",
            base_url="https://user:secret@provider.example/v1",
            route="/responses",
            protocol=Protocol.RESPONSES,
        )
    with pytest.raises(ValidationError, match="route"):
        ModelProfile(
            requested_model="model",
            provider="provider",
            base_url="https://provider.example/v1",
            route="//attacker.example/responses",
            protocol=Protocol.RESPONSES,
        )


@pytest.mark.parametrize(
    ("base_url", "route"),
    [
        pytest.param("http://provider.example/v1", "/responses", id="cleartext"),
        pytest.param("https://provider.example/v1/..", "/responses", id="base-dot-segment"),
        pytest.param("https://provider.example/v1", "/v1/../responses", id="route-dot-segment"),
        pytest.param("https://provider.example/v1", "/v1/%2e%2e/responses", id="encoded-dot"),
    ],
)
def test_model_endpoint_requires_tls_and_canonical_route(base_url: str, route: str) -> None:
    with pytest.raises(ValidationError):
        ModelProfile(
            requested_model="model",
            provider="provider",
            base_url=base_url,
            route=route,
            protocol=Protocol.RESPONSES,
        )


def test_model_endpoint_identity_canonicalizes_hostname_case() -> None:
    profile = ModelProfile(
        requested_model="model",
        provider="provider",
        base_url="https://PROVIDER.Example/v1/",
        route="/responses",
        protocol=Protocol.RESPONSES,
    )

    assert profile.base_url == "https://provider.example/v1"
    assert f"{profile.base_url}{profile.route}" == "https://provider.example/v1/responses"


def test_completed_run_with_observed_model_keeps_identities_distinct() -> None:
    now = datetime.now(UTC)
    run = make_run(
        started_at=now,
        finished_at=now + timedelta(seconds=1),
    )

    assert run.requested_model != run.observed_model
    assert run.requested_model == "friendly-alias"
    assert run.observed_model == "provider-model-2026-08-01"
    assert run.model_dump(mode="json")["status"] == "completed"


def test_completed_run_without_observed_model_is_valid() -> None:
    run = make_run(observed_model=None)

    assert run.status is RunStatus.COMPLETED
    assert run.requested_model == "friendly-alias"
    assert run.observed_model is None


def test_run_status_taxonomy_distinguishes_infra_and_subject_failures() -> None:
    assert {status.value for status in RunStatus} == {
        "planned",
        "queued",
        "claimed",
        "preparing",
        "running",
        "verifying",
        "scoring",
        "completed",
        "failed_infra",
        "failed_subject",
        "cancelled",
        "budget_exhausted",
    }
    assert len({RunStatus.FAILED_INFRA, RunStatus.FAILED_SUBJECT}) == 2


def test_run_rejects_finished_time_before_started_time() -> None:
    now = datetime.now(UTC)
    with pytest.raises(ValidationError, match="finished_at must not precede started_at"):
        make_run(started_at=now, finished_at=now - timedelta(seconds=1))
