from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.schema import CreateSchema, DropSchema

from harnesslab.api.app import create_app
from harnesslab.api.workbench_dependencies import workbench_session
from harnesslab.contracts.common import Protocol
from harnesslab.core.config import Settings
from harnesslab.db.base import Base
from harnesslab.db.models.experiment import ExperimentRecord, ExperimentRunRecord
from harnesslab.db.models.registry import RegistryExperimentSnapshotRecord
from harnesslab.db.session import create_engine, create_session_factory
from harnesslab.egress import EGRESS_PROXY_IMAGE
from harnesslab.experiment.methodology import (
    BudgetContract,
    BudgetDimension,
    BudgetDimensionStatus,
    BudgetScope,
    ComparisonType,
    EvaluationMode,
    RecoveryEligibility,
    load_evaluation_methodology,
    recovery_authorization,
)
from harnesslab.experiment.outcomes import StatisticalOutcome
from harnesslab.experiment.plan import ExperimentPlan
from harnesslab.experiment.queue import enqueue_plan
from harnesslab.harness_lane.profile import CODEX_IMAGE
from harnesslab.model_lane.models import ProviderRequest
from harnesslab.model_lane.providers import adapter_for_profile
from harnesslab.multi_harness.adapter import ClaudeCodeAdapter
from harnesslab.multi_harness.models import HarnessKind
from harnesslab.multi_harness.profile import (
    CLAUDE_IMAGE,
    DEEPSEEK_IMAGE,
    configured_qwen_alibaba_bailian_claude_profile,
)
from harnesslab.multi_harness.prompt import render_harness_prompt
from harnesslab.registry.alibaba import configured_alibaba_bailian_profile
from harnesslab.registry.models import (
    BillingMode,
    CompatibilityStatus,
    ExperimentBuilderRequest,
    ExperimentCellSelection,
    PreflightStatus,
)
from harnesslab.registry.seeds import build_registry_catalog
from harnesslab.registry.service import (
    assess_capability,
    build_experiment_snapshot,
    preflight_experiment,
    registry_settings,
)
from harnesslab.release.matrix import MatrixControlPlane
from harnesslab.release.smoke import RuntimeIdentities
from harnesslab.sandbox.models import ImageIdentity
from tests.phase_g_helpers import ROOT

METHODOLOGY = load_evaluation_methodology(ROOT / "release/evaluation-methodology-v2.json")
ALIBABA_OPENAI_RUNTIME_URL = (
    "https://workspace-sentinel.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
)
ALIBABA_ANTHROPIC_RUNTIME_URL = (
    "https://workspace-sentinel.cn-beijing.maas.aliyuncs.com/apps/anthropic"
)
ALIBABA_KEY = "fake-alibaba-key-sentinel"


def frozen_matrix_plan() -> ExperimentPlan:
    runtime = RuntimeIdentities(
        codex_image=ImageIdentity(reference=CODEX_IMAGE, image_id="sha256:" + "1" * 64),
        claude_image=ImageIdentity(reference=CLAUDE_IMAGE, image_id="sha256:" + "2" * 64),
        deepseek_image=ImageIdentity(reference=DEEPSEEK_IMAGE, image_id="sha256:" + "3" * 64),
        egress_proxy_image=ImageIdentity(
            reference=EGRESS_PROXY_IMAGE, image_id="sha256:" + "4" * 64
        ),
        deepseek_config_digest="sha256:" + "5" * 64,
    )
    return MatrixControlPlane.load(ROOT, plan_version="v3").build_plan(runtime)


@asynccontextmanager
async def isolated_registry_database(
    database_url: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Create a fresh test-only schema without touching operator campaign rows."""

    schema = f"registry_lite_{uuid4().hex}"
    administrative = create_engine(Settings.without_dotenv(database_url=database_url))
    try:
        async with administrative.begin() as connection:
            await connection.execute(CreateSchema(schema))
    finally:
        await administrative.dispose()

    engine = create_engine(Settings.without_dotenv(database_url=database_url)).execution_options(
        schema_translate_map={None: schema}
    )
    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        yield create_session_factory(engine)
    finally:
        await engine.dispose()
        cleanup = create_engine(Settings.without_dotenv(database_url=database_url))
        try:
            async with cleanup.begin() as connection:
                await connection.execute(DropSchema(schema, cascade=True))
        finally:
            await cleanup.dispose()


@asynccontextmanager
async def registry_client(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with factory() as session:
            yield session

    app.dependency_overrides[workbench_session] = override_session
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def budget() -> BudgetContract:
    return BudgetContract(
        max_wall_time=BudgetDimension(
            status=BudgetDimensionStatus.ENFORCED,
            value=90,
            unit="seconds",
            scopes=(BudgetScope.PER_LOGICAL_RUN,),
        ),
        max_output_tokens=BudgetDimension(
            status=BudgetDimensionStatus.ENFORCED,
            value=2000,
            unit="tokens",
            scopes=(BudgetScope.PER_PROVIDER_REQUEST, BudgetScope.PER_LOGICAL_RUN),
        ),
        max_model_turns=BudgetDimension(
            status=BudgetDimensionStatus.ENFORCED,
            value=1,
            unit="turns",
            scopes=(BudgetScope.PER_LOGICAL_RUN,),
        ),
        max_tool_calls=BudgetDimension(
            status=BudgetDimensionStatus.ENFORCED,
            value=0,
            unit="calls",
            scopes=(BudgetScope.PER_LOGICAL_RUN,),
        ),
        max_provider_requests=BudgetDimension(
            status=BudgetDimensionStatus.ENFORCED,
            value=1,
            unit="requests",
            scopes=(BudgetScope.PER_LOGICAL_RUN,),
        ),
        max_cost=BudgetDimension(
            status=BudgetDimensionStatus.NOT_AVAILABLE,
            value=None,
            unit="USD",
            scopes=(BudgetScope.NOT_AVAILABLE,),
        ),
    )


def relay_environment(*, status: str = "AVAILABLE") -> dict[str, str]:
    return {
        "HARNESSLAB_GPT56_RELAY_BASE_URL": "https://relay.registry.test/v1",
        "HARNESSLAB_GPT56_RELAY_API_KEY": "fake-relay-key",
        "HARNESSLAB_GPT56_RELAY_STATUS": status,
    }


def alibaba_environment(*, model_id: str = "operator-model-a") -> dict[str, str]:
    return {
        "HARNESSLAB_ALIBABA_BAILIAN_OPENAI_BASE_URL": ALIBABA_OPENAI_RUNTIME_URL,
        "HARNESSLAB_ALIBABA_BAILIAN_ANTHROPIC_BASE_URL": ALIBABA_ANTHROPIC_RUNTIME_URL,
        "HARNESSLAB_ALIBABA_BAILIAN_API_KEY": ALIBABA_KEY,
        "HARNESSLAB_ALIBABA_BAILIAN_MODEL_IDS": model_id,
        "HARNESSLAB_ALIBABA_BAILIAN_STATUS": "AVAILABLE",
    }


def builder_request(
    *,
    mode: EvaluationMode = EvaluationMode.QUICK,
    comparison: ComparisonType = ComparisonType.HARNESS_UPLIFT,
    left_profile: str = "gpt56-relay-gpt56-responses",
    left_harness: str = "direct-gpt56-relay-gpt56-responses",
    right_profile: str = "gpt56-relay-gpt56-responses",
    right_harness: str = "codex-gpt56-medium",
    billing_modes: dict[str, BillingMode] | None = None,
) -> ExperimentBuilderRequest:
    return ExperimentBuilderRequest(
        name="Registry Lite keyless plan",
        methodology_id=METHODOLOGY.methodology_id,
        methodology_digest=METHODOLOGY.digest,
        evaluation_mode=mode,
        comparison_type=comparison,
        task_ids=("core-python-deduplicate",),
        cells=(
            ExperimentCellSelection(
                cell_id="left",
                provider_model_profile_id=left_profile,
                harness_profile_id=left_harness,
            ),
            ExperimentCellSelection(
                cell_id="right",
                provider_model_profile_id=right_profile,
                harness_profile_id=right_harness,
            ),
        ),
        budget=budget(),
        schedule_seed=20260828,
        max_parallel_runs=1,
        billing_modes=billing_modes or {},
    )


def test_registry_seeds_four_providers_and_keeps_model_provider_separate() -> None:
    catalog = build_registry_catalog(ROOT, {})
    assert {item.provider_id for item in catalog.providers} == {
        "gpt56-relay",
        "opencode-go",
        "deepseek-official",
        "alibaba-bailian",
    }
    assert len(catalog.tasks) == 18
    assert all(
        profile.model_id != profile.provider_id for profile in catalog.provider_model_profiles
    )
    alibaba = next(item for item in catalog.providers if item.provider_id == "alibaba-bailian")
    assert alibaba.billing_mode is BillingMode.PAY_AS_YOU_GO
    assert alibaba.region == "cn-beijing"
    assert "RUNTIME_ENDPOINT_REFERENCE_MISSING" in alibaba.configuration_reason_codes
    assert {
        item.profile_id
        for item in catalog.provider_model_profiles
        if item.provider_id == "alibaba-bailian"
    } == {
        "alibaba-bailian-qwen3.8-max-responses",
        "alibaba-bailian-qwen3.8-max-messages",
        "alibaba-bailian-qwen3.8-max-chat",
        "alibaba-bailian-deepseek-v4-pro-chat",
        "alibaba-bailian-deepseek-v4-pro-responses",
        "alibaba-bailian-glm-5.2-chat",
    }


def test_registry_and_settings_never_serialize_runtime_values_or_credentials() -> None:
    environment = alibaba_environment()
    catalog = build_registry_catalog(ROOT, environment)
    settings = registry_settings(catalog, environment)
    serialized = json.dumps(
        {"catalog": catalog.model_dump(mode="json"), "settings": settings.model_dump(mode="json")}
    )
    assert ALIBABA_OPENAI_RUNTIME_URL not in serialized
    assert ALIBABA_ANTHROPIC_RUNTIME_URL not in serialized
    assert ALIBABA_KEY not in serialized
    assert "workspace-sentinel" not in serialized
    assert "HARNESSLAB_ALIBABA_BAILIAN_API_KEY" in serialized
    assert settings.secret_editing_supported is False
    assert (
        next(
            item.status.value
            for item in settings.credentials
            if item.credential_reference == "HARNESSLAB_ALIBABA_BAILIAN_API_KEY"
        )
        == "SET"
    )


def test_alibaba_claude_profile_uses_only_protected_bailian_references(
    tmp_path: Path,
) -> None:
    profile = configured_qwen_alibaba_bailian_claude_profile(
        ImageIdentity(reference=CLAUDE_IMAGE, image_id="sha256:" + "2" * 64)
    )
    prompt = render_harness_prompt(
        HarnessKind.CLAUDE_CODE,
        task_instruction="Fix retry deduplication.",
        task_digest="sha256:" + "1" * 64,
        workspace_input_digest="sha256:" + "2" * 64,
        context_digest=None,
        network_policy=profile.network_policy,
    )
    plan = ClaudeCodeAdapter().prepare(
        profile,
        prompt,
        workspace=tmp_path,
        context=None,
        task_id="core-python-deduplicate",
    )

    assert profile.provider_fixed_base_url is None
    assert profile.provider_base_url_reference == ("HARNESSLAB_ALIBABA_BAILIAN_ANTHROPIC_BASE_URL")
    assert profile.provider_credential_reference == "HARNESSLAB_ALIBABA_BAILIAN_API_KEY"
    assert dict(plan.environment_references) == {
        "ANTHROPIC_BASE_URL": "HARNESSLAB_ALIBABA_BAILIAN_ANTHROPIC_BASE_URL",
        "ANTHROPIC_API_KEY": "HARNESSLAB_ALIBABA_BAILIAN_API_KEY",
    }
    literals = dict(plan.environment_literals)
    assert literals["ANTHROPIC_MODEL"] == "qwen3.8-max"
    assert literals["CLAUDE_CODE_NO_MODEL_FALLBACK"] == "1"
    assert "api.anthropic.com" not in profile.canonical_json()


def test_alibaba_preflight_rejects_cross_workspace_endpoint_binding() -> None:
    environment = alibaba_environment(model_id="qwen3.8-max")
    environment["HARNESSLAB_ALIBABA_BAILIAN_ANTHROPIC_BASE_URL"] = (
        "https://workspace-other.cn-beijing.maas.aliyuncs.com/apps/anthropic"
    )
    request = builder_request(
        comparison=ComparisonType.END_TO_END_SYSTEM_COMPARISON,
        left_profile="alibaba-bailian-qwen3.8-max-responses",
        left_harness="direct-alibaba-bailian-qwen3.8-max-responses",
        right_profile="alibaba-bailian-qwen3.8-max-messages",
        right_harness="claude-qwen38-alibaba-bailian",
    )

    result = preflight_experiment(request, ROOT, environment)

    assert result.status is PreflightStatus.BLOCKED
    assert any(item.reason_code == "RUNTIME_ENDPOINT_WORKSPACE_MISMATCH" for item in result.checks)


def test_capability_registry_fails_closed_and_exposes_trace_limits() -> None:
    catalog = build_registry_catalog(ROOT, relay_environment())
    supported = assess_capability(catalog, "gpt56-relay-gpt56-responses", "codex-gpt56-medium")
    unsupported = assess_capability(catalog, "opencode-go-qwen38-messages", "codex-gpt56-medium")
    limited = assess_capability(
        catalog,
        "deepseek-official-v4flash-chat",
        "deepseek-harness-v4flash",
    )
    assert supported.status is CompatibilityStatus.SUPPORTED
    assert supported.trace_coverage.value == "FULL_STREAM"
    assert unsupported.status is CompatibilityStatus.UNSUPPORTED
    assert "PROVIDER_MODEL_PROFILE_UNSUPPORTED_BY_HARNESS" in unsupported.reason_codes
    assert limited.status is CompatibilityStatus.PARTIALLY_SUPPORTED
    assert "TRACE_COVERAGE_LIMITED" in limited.reason_codes


@pytest.mark.parametrize(
    ("mode", "expected_repeats", "expected_slots"),
    (
        (EvaluationMode.QUICK, 1, 2),
        (EvaluationMode.INFORMAL, 3, 6),
        (EvaluationMode.FORMAL_EXHAUSTIVE, 5, 10),
    ),
)
def test_builder_enforces_mode_repeats_and_blocked_interleaving(
    mode: EvaluationMode, expected_repeats: int, expected_slots: int
) -> None:
    result = preflight_experiment(builder_request(mode=mode), ROOT, relay_environment())
    assert result.status is PreflightStatus.READY_WITH_WARNINGS
    assert result.repeat_count == expected_repeats
    assert result.estimated_logical_slots == expected_slots
    assert len(result.schedule_preview) == expected_repeats
    assert all(
        set(item.cell_execution_order) == {"left", "right"} for item in result.schedule_preview
    )


def test_builder_blocks_false_harness_uplift_and_allows_controlled_ablation() -> None:
    deepseek_env = {"DEEPSEEK_API_KEY": "fake", "HARNESSLAB_DEEPSEEK_OFFICIAL_STATUS": "AVAILABLE"}
    false_uplift = builder_request(
        left_profile="deepseek-official-v4pro-chat",
        left_harness="direct-deepseek-official-v4pro-chat",
        right_profile="deepseek-official-v4flash-chat",
        right_harness="deepseek-harness-v4flash",
    )
    blocked = preflight_experiment(false_uplift, ROOT, deepseek_env)
    assert blocked.status is PreflightStatus.BLOCKED
    assert any(item.reason_code == "INVALID_EXPERIMENT_SELECTION" for item in blocked.checks)

    ablation = builder_request(
        comparison=ComparisonType.CONTROLLED_ABLATION,
        left_harness="codex-gpt56-medium",
        right_harness="codex-gpt56-high",
    )
    allowed = preflight_experiment(ablation, ROOT, relay_environment())
    assert allowed.status is PreflightStatus.READY_WITH_WARNINGS
    assert allowed.candidate_plan_digest is not None


def test_alibaba_requires_payg_and_quota_blocks_new_blocks() -> None:
    environment = alibaba_environment()
    request = builder_request(
        comparison=ComparisonType.END_TO_END_SYSTEM_COMPARISON,
        left_profile="alibaba-bailian-operator-model-a-chat",
        left_harness="direct-alibaba-bailian-operator-model-a-chat",
        right_profile="alibaba-bailian-operator-model-a-responses",
        right_harness="direct-alibaba-bailian-operator-model-a-responses",
        billing_modes={"alibaba-bailian": BillingMode.CODING_PLAN},
    )
    result = preflight_experiment(request, ROOT, environment)
    assert result.status is PreflightStatus.BLOCKED
    assert any(
        item.reason_code == "AUTOMATION_NOT_ALLOWED_FOR_BILLING_PLAN" for item in result.checks
    )

    quota_environment = relay_environment(status="QUOTA_EXHAUSTED")
    quota = preflight_experiment(builder_request(), ROOT, quota_environment)
    assert quota.status is PreflightStatus.BLOCKED
    assert any(item.reason_code == "QUOTA_EXHAUSTED" for item in quota.checks)
    assert all(item.provider_status == "PROVIDER_UNAVAILABLE" for item in quota.schedule_preview)


def test_provider_switch_and_runtime_endpoint_change_snapshot_identity() -> None:
    opencode_environment = {
        "HARNESSLAB_OPENCODE_GO_API_KEY": "fake",
        "HARNESSLAB_OPENCODE_GO_STATUS": "AVAILABLE",
    }
    opencode = builder_request(
        comparison=ComparisonType.END_TO_END_SYSTEM_COMPARISON,
        left_profile="opencode-go-qwen38-messages",
        left_harness="direct-opencode-go-qwen38-messages",
        right_profile="opencode-go-qwen38-messages",
        right_harness="direct-opencode-go-qwen38-messages",
    )
    alibaba = builder_request(
        comparison=ComparisonType.END_TO_END_SYSTEM_COMPARISON,
        left_profile="alibaba-bailian-qwen3.8-max-responses",
        left_harness="direct-alibaba-bailian-qwen3.8-max-responses",
        right_profile="alibaba-bailian-qwen3.8-max-responses",
        right_harness="direct-alibaba-bailian-qwen3.8-max-responses",
    )
    opencode_snapshot = build_experiment_snapshot(opencode, ROOT, opencode_environment)
    environment = alibaba_environment(model_id="qwen3.8-max")
    alibaba_snapshot = build_experiment_snapshot(alibaba, ROOT, environment)
    assert opencode_snapshot.snapshot_id != alibaba_snapshot.snapshot_id
    assert opencode_snapshot.plan.run_slots[0].slot_id != alibaba_snapshot.plan.run_slots[0].slot_id
    assert {item.provider_id for item in alibaba_snapshot.provider_selections} == {
        "alibaba-bailian"
    }

    changed = dict(environment)
    changed["HARNESSLAB_ALIBABA_BAILIAN_OPENAI_BASE_URL"] = (
        "https://workspace-second.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
    )
    changed["HARNESSLAB_ALIBABA_BAILIAN_ANTHROPIC_BASE_URL"] = (
        "https://workspace-second.cn-beijing.maas.aliyuncs.com/apps/anthropic"
    )
    changed_snapshot = build_experiment_snapshot(alibaba, ROOT, changed)
    assert changed_snapshot.snapshot_id != alibaba_snapshot.snapshot_id
    serialized = changed_snapshot.model_dump_json()
    assert changed["HARNESSLAB_ALIBABA_BAILIAN_OPENAI_BASE_URL"] not in serialized
    assert changed["HARNESSLAB_ALIBABA_BAILIAN_ANTHROPIC_BASE_URL"] not in serialized
    assert "workspace-second" not in serialized


def test_provider_status_change_does_not_change_experiment_identity() -> None:
    available = build_experiment_snapshot(builder_request(), ROOT, relay_environment())
    unavailable = build_experiment_snapshot(
        builder_request(), ROOT, relay_environment(status="UNAVAILABLE")
    )
    assert available.snapshot_id == unavailable.snapshot_id
    assert {item.slot_id for item in available.plan.run_slots} == {
        item.slot_id for item in unavailable.plan.run_slots
    }
    assert available.preflight.status is PreflightStatus.READY_WITH_WARNINGS
    assert unavailable.preflight.status is PreflightStatus.BLOCKED


def test_methodology_recovery_contract_remains_authoritative() -> None:
    capability = recovery_authorization(
        slot_id="sha256:" + "1" * 64,
        original_attempt_identity="sha256:" + "2" * 64,
        outcome=StatisticalOutcome.CAPABILITY_FAIL,
        recovery_attempt_count=0,
    )
    first = recovery_authorization(
        slot_id="sha256:" + "1" * 64,
        original_attempt_identity="sha256:" + "2" * 64,
        outcome=StatisticalOutcome.INFRA_FAILURE,
        recovery_attempt_count=0,
    )
    second = recovery_authorization(
        slot_id="sha256:" + "1" * 64,
        original_attempt_identity="sha256:" + "2" * 64,
        outcome=StatisticalOutcome.INFRA_FAILURE,
        recovery_attempt_count=1,
    )
    assert capability.eligibility is RecoveryEligibility.CAPABILITY_TERMINAL_NO_RETRY
    assert first.eligibility is RecoveryEligibility.ELIGIBLE
    assert second.eligibility is RecoveryEligibility.INFRA_RECOVERY_EXHAUSTED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "protocol", (Protocol.CHAT_COMPLETIONS, Protocol.RESPONSES, Protocol.MESSAGES)
)
async def test_fake_alibaba_profile_uses_openai_shapes_and_reference_only_bearer_auth(
    protocol: Protocol,
) -> None:
    profile = configured_alibaba_bailian_profile("operator-model-a", protocol)

    async def handler(request: httpx.Request) -> httpx.Response:
        expected_base = (
            ALIBABA_ANTHROPIC_RUNTIME_URL
            if protocol is Protocol.MESSAGES
            else ALIBABA_OPENAI_RUNTIME_URL
        )
        assert str(request.url).startswith(expected_base)
        body = json.loads(request.content)
        assert body["model"] == "operator-model-a"
        if protocol is Protocol.MESSAGES:
            assert request.headers["x-api-key"] == ALIBABA_KEY
            assert body["system"] == "system"
            return httpx.Response(
                200,
                json={
                    "id": "messages-local",
                    "model": "observed-alibaba-model",
                    "content": [{"type": "text", "text": "ok"}],
                    "stop_reason": "end_turn",
                    "usage": {},
                },
            )
        assert request.headers["Authorization"] == f"Bearer {ALIBABA_KEY}"
        if protocol is Protocol.CHAT_COMPLETIONS:
            assert [item["role"] for item in body["messages"]] == ["system", "user"]
            return httpx.Response(
                200,
                json={
                    "id": "chat-local",
                    "model": "observed-alibaba-model",
                    "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                    "usage": {},
                },
            )
        assert body["instructions"] == "system"
        assert body["input"] == "user"
        return httpx.Response(
            200,
            json={
                "id": "responses-local",
                "model": "observed-alibaba-model",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "ok"}],
                    }
                ],
                "usage": {},
            },
        )

    request = ProviderRequest(profile=profile, instructions="system", input="user")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await adapter_for_profile(
            request,
            client=client,
            environment={
                "HARNESSLAB_ALIBABA_BAILIAN_OPENAI_BASE_URL": ALIBABA_OPENAI_RUNTIME_URL,
                "HARNESSLAB_ALIBABA_BAILIAN_ANTHROPIC_BASE_URL": (ALIBABA_ANTHROPIC_RUNTIME_URL),
                "HARNESSLAB_ALIBABA_BAILIAN_API_KEY": ALIBABA_KEY,
            },
        ).invoke(request)
    assert result.provider == "alibaba-bailian"
    assert result.requested_model == "operator-model-a"
    assert result.observed_model == "observed-alibaba-model"
    serialized = profile.model_dump_json() + result.model_dump_json()
    assert ALIBABA_OPENAI_RUNTIME_URL not in serialized
    assert ALIBABA_ANTHROPIC_RUNTIME_URL not in serialized
    assert ALIBABA_KEY not in serialized


@pytest.mark.integration
async def test_registry_api_does_not_seed_or_mutate_real_matrix_on_fresh_database(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = relay_environment()
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("REAL_CALLS_ALLOWED", "0")
    request = builder_request()
    expected = build_experiment_snapshot(request, ROOT, environment)
    matrix_plan = frozen_matrix_plan()
    assert matrix_plan.experiment_id == "core-real-matrix-v3"
    assert (len(matrix_plan.cells), len(matrix_plan.tasks), matrix_plan.repeat_count) == (7, 18, 5)
    assert len(matrix_plan.run_slots) == 630

    async with isolated_registry_database(database_url) as factory:
        async with factory() as session:
            matrix_before = await session.scalar(
                select(func.count())
                .select_from(ExperimentRunRecord)
                .where(ExperimentRunRecord.experiment_id == matrix_plan.experiment_id)
            )
            existing_matrix = await session.get(ExperimentRecord, matrix_plan.experiment_id)
        assert matrix_before == 0
        assert existing_matrix is None

        async with registry_client(factory) as client:
            providers = await client.get("/api/registry/providers")
            preflight = await client.post(
                "/api/experiments/preflight", json=request.model_dump(mode="json")
            )
            first = await client.post(
                "/api/experiments/snapshot", json=request.model_dump(mode="json")
            )
            second = await client.post(
                "/api/experiments/snapshot", json=request.model_dump(mode="json")
            )
            malicious = request.model_dump(mode="json")
            malicious["base_url"] = "https://raw-url-sentinel.invalid"
            rejected = await client.post("/api/experiments/preflight", json=malicious)
            unknown_selection = request.model_dump(mode="json")
            unknown_selection["cells"][0]["provider_model_profile_id"] = "unknown-profile"
            rejected_snapshot = await client.post(
                "/api/experiments/snapshot", json=unknown_selection
            )
        assert providers.status_code == 200
        assert all("credential_ref" in item for item in providers.json()["items"])
        assert "credential_reference" not in providers.text
        assert preflight.status_code == 200
        assert first.status_code == second.status_code == 200
        assert first.json()["snapshot_digest"] == second.json()["snapshot_digest"]
        assert rejected.status_code == 422
        assert "raw-url-sentinel" not in rejected.text
        assert rejected_snapshot.status_code == 422
        assert rejected_snapshot.json() == {
            "error": {
                "code": "INVALID_REGISTRY_SELECTION",
                "message": "snapshot selection failed backend validation",
            }
        }
        response_text = providers.text + first.text
        assert environment["HARNESSLAB_GPT56_RELAY_BASE_URL"] not in response_text
        assert environment["HARNESSLAB_GPT56_RELAY_API_KEY"] not in response_text

        async with factory() as session:
            persisted = await session.scalar(
                select(RegistryExperimentSnapshotRecord).where(
                    RegistryExperimentSnapshotRecord.id == expected.snapshot_id
                )
            )
            snapshot_count = await session.scalar(
                select(func.count())
                .select_from(RegistryExperimentSnapshotRecord)
                .where(RegistryExperimentSnapshotRecord.id == expected.snapshot_id)
            )
            matrix_after = await session.scalar(
                select(func.count())
                .select_from(ExperimentRunRecord)
                .where(ExperimentRunRecord.experiment_id == matrix_plan.experiment_id)
            )
            matrix_experiment_after = await session.get(ExperimentRecord, matrix_plan.experiment_id)
            no_run_experiment = await session.get(ExperimentRecord, expected.plan.experiment_id)
        assert persisted is not None
        persisted_json = json.dumps(persisted.snapshot_json)
        assert environment["HARNESSLAB_GPT56_RELAY_BASE_URL"] not in persisted_json
        assert environment["HARNESSLAB_GPT56_RELAY_API_KEY"] not in persisted_json
        assert snapshot_count == 1
        assert matrix_before == matrix_after == 0
        assert matrix_experiment_after is None
        assert no_run_experiment is None


@pytest.mark.integration
async def test_registry_snapshot_preserves_explicitly_enqueued_real_matrix_fixture(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = relay_environment()
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("REAL_CALLS_ALLOWED", "0")
    request = builder_request()
    expected = build_experiment_snapshot(request, ROOT, environment)
    matrix_plan = frozen_matrix_plan()
    assert expected.plan.experiment_id != matrix_plan.experiment_id
    assert len(matrix_plan.run_slots) == 630

    async with isolated_registry_database(database_url) as factory:
        async with factory() as session, session.begin():
            enqueued = await enqueue_plan(session, matrix_plan)
        assert enqueued.logical_run_count == 630
        assert enqueued.created is True

        async with factory() as session:
            existing_before = await session.get(ExperimentRecord, matrix_plan.experiment_id)
            rows_before = tuple(
                (
                    row.run_id,
                    row.slot_id,
                    row.cell_id,
                    row.task_id,
                    row.task_version,
                    row.task_digest,
                    row.repeat_index,
                    row.paired_slot_identity,
                    row.status,
                    row.normalized_outcome,
                    row.source_outcome,
                    row.attempt,
                    row.evidence_digest,
                )
                for row in (
                    await session.scalars(
                        select(ExperimentRunRecord)
                        .where(ExperimentRunRecord.experiment_id == matrix_plan.experiment_id)
                        .order_by(ExperimentRunRecord.slot_order)
                    )
                ).all()
            )
        assert existing_before is not None
        assert existing_before.plan_digest == matrix_plan.digest
        assert len(rows_before) == 630
        assert {item[1] for item in rows_before} == {slot.slot_id for slot in matrix_plan.run_slots}
        assert {item[8] for item in rows_before} == {"queued"}
        assert {item[9] for item in rows_before} == {None}
        assert {item[11] for item in rows_before} == {0}

        async with registry_client(factory) as client:
            response = await client.post(
                "/api/experiments/snapshot", json=request.model_dump(mode="json")
            )
        assert response.status_code == 200
        assert response.json()["snapshot_id"] == expected.snapshot_id

        async with factory() as session:
            existing_after = await session.get(ExperimentRecord, matrix_plan.experiment_id)
            rows_after = tuple(
                (
                    row.run_id,
                    row.slot_id,
                    row.cell_id,
                    row.task_id,
                    row.task_version,
                    row.task_digest,
                    row.repeat_index,
                    row.paired_slot_identity,
                    row.status,
                    row.normalized_outcome,
                    row.source_outcome,
                    row.attempt,
                    row.evidence_digest,
                )
                for row in (
                    await session.scalars(
                        select(ExperimentRunRecord)
                        .where(ExperimentRunRecord.experiment_id == matrix_plan.experiment_id)
                        .order_by(ExperimentRunRecord.slot_order)
                    )
                ).all()
            )
            registry_snapshot = await session.get(
                RegistryExperimentSnapshotRecord, expected.snapshot_id
            )
            no_registry_experiment = await session.get(
                ExperimentRecord, expected.plan.experiment_id
            )
        assert existing_after is not None
        assert existing_after.plan_digest == matrix_plan.digest
        assert rows_after == rows_before
        assert registry_snapshot is not None
        assert no_registry_experiment is None
