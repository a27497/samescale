from __future__ import annotations

import json
from functools import cache

import httpx
import pytest

from harnesslab.experiment.methodology import (
    BudgetDimension,
    ComparisonType,
    classify_comparison,
    load_evaluation_methodology,
)
from harnesslab.experiment.plan import load_experiment_plan_payload
from harnesslab.experiment.spec import ExperimentCellSpec
from harnesslab.model_lane.models import ProviderRequest
from harnesslab.model_lane.providers import adapter_for_profile
from harnesslab.registry.model_chat import model_chat_v2_builder_request
from harnesslab.registry.models import (
    ExperimentBuilderRequest,
    ExperimentSnapshot,
    PreflightStatus,
    RegistryError,
    canonical_digest,
)
from harnesslab.registry.runtime import direct_harness_control_identity
from harnesslab.registry.seeds import build_registry_catalog
from harnesslab.registry.service import (
    build_experiment_snapshot,
    preflight_experiment,
    resolve_frozen_direct_runtime,
    validate_frozen_runtime_contract,
)
from tests.phase_g_helpers import ROOT

OPENAI_URL = "https://workspace-sentinel.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
ANTHROPIC_URL = "https://workspace-sentinel.cn-beijing.maas.aliyuncs.com/apps/anthropic"
FAKE_KEY = "fake-model-chat-v2-key"


def environment() -> dict[str, str]:
    return {
        "HARNESSLAB_ALIBABA_BAILIAN_OPENAI_BASE_URL": OPENAI_URL,
        "HARNESSLAB_ALIBABA_BAILIAN_ANTHROPIC_BASE_URL": ANTHROPIC_URL,
        "HARNESSLAB_ALIBABA_BAILIAN_API_KEY": FAKE_KEY,
        "HARNESSLAB_ALIBABA_BAILIAN_STATUS": "AVAILABLE",
    }


@cache
def frozen_v2() -> tuple[ExperimentSnapshot, ExperimentBuilderRequest]:
    env = environment()
    catalog = build_registry_catalog(ROOT, env)
    methodology = load_evaluation_methodology(ROOT / "release/evaluation-methodology-v2.json")
    request = model_chat_v2_builder_request(catalog, methodology)
    return build_experiment_snapshot(request, ROOT, env), request


def test_model_chat_v2_keyless_builder_freeze_load_preflight_and_runtime_round_trip() -> None:
    snapshot, request = frozen_v2()
    loaded_plan = load_experiment_plan_payload(json.loads(snapshot.plan.canonical_json()))
    loaded = ExperimentSnapshot.model_validate_json(snapshot.model_dump_json())
    preflight = preflight_experiment(request, ROOT, environment())
    profiles = validate_frozen_runtime_contract(loaded.plan, loaded.provider_selections)

    assert loaded_plan.digest == snapshot.plan.digest
    assert loaded.snapshot_digest == snapshot.snapshot_digest
    assert preflight.status is PreflightStatus.READY_WITH_WARNINGS
    assert snapshot.plan.experiment_id == "portfolio-alibaba-model-chat-v2"
    assert snapshot.plan.evaluation_mode.value == "QUICK"
    assert snapshot.plan.repeat_count == 1
    assert snapshot.plan.schedule_seed == 20260829
    assert len(snapshot.plan.tasks) == 18
    assert (
        len(snapshot.plan.run_slots)
        == len({slot.slot_id for slot in snapshot.plan.run_slots})
        == 36
    )
    assert len(snapshot.plan.schedule_blocks) == 18
    assert set(profiles) == {"Q", "D"}
    assert profiles["Q"].requested_model == "qwen3.8-max"
    assert profiles["D"].requested_model == "deepseek-v4-pro"
    assert all(profile.protocol.value == "chat_completions" for profile in profiles.values())
    assert all(profile.route == "/chat/completions" for profile in profiles.values())
    assert all(profile.reasoning.max_output_tokens == 4000 for profile in profiles.values())
    assert all(profile.request_timeout_seconds == 180 for profile in profiles.values())

    cells = {cell.id: cell for cell in snapshot.plan.cells}
    assert cells["Q"].profile_identity == cells["D"].profile_identity
    assert (
        cells["Q"].effective_runtime_profile_identity
        != cells["D"].effective_runtime_profile_identity
    )
    assert cells["Q"].resource_envelope_identity == cells["D"].resource_envelope_identity
    assert cells["Q"].harness_config_identity == cells["D"].harness_config_identity
    assert cells["Q"].harness_config_identity == direct_harness_control_identity()
    assert (
        classify_comparison(
            ExperimentCellSpec.model_validate(cells["Q"].model_dump(mode="json")),
            ExperimentCellSpec.model_validate(cells["D"].model_dump(mode="json")),
        )
        is ComparisonType.MODEL_COMPARISON
    )


@pytest.mark.asyncio
async def test_model_chat_v2_fake_chat_payloads_bind_model_and_4000_once() -> None:
    snapshot, _request = frozen_v2()
    profiles = validate_frozen_runtime_contract(snapshot.plan, snapshot.provider_selections)
    payloads: list[dict[str, object]] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        payloads.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "fake-chat",
                "model": payloads[-1]["model"],
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        for cell_id in ("Q", "D"):
            provider_request = ProviderRequest(
                profile=profiles[cell_id], instructions="system", input="user"
            )
            result = await adapter_for_profile(
                provider_request,
                client=client,
                environment={
                    "HARNESSLAB_ALIBABA_BAILIAN_OPENAI_BASE_URL": OPENAI_URL,
                    "HARNESSLAB_ALIBABA_BAILIAN_API_KEY": FAKE_KEY,
                },
            ).invoke(provider_request)
            assert result.public_output_text == "ok"

    assert payloads == [
        {
            "model": "qwen3.8-max",
            "messages": [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "user"},
            ],
            "max_tokens": 4000,
        },
        {
            "model": "deepseek-v4-pro",
            "messages": [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "user"},
            ],
            "max_tokens": 4000,
        },
    ]
    budget = snapshot.plan.budget_contract
    assert budget.max_provider_requests.value == 1
    assert budget.max_model_turns.value == 1
    assert budget.max_tool_calls.value == 0


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("requested_model", "deepseek-v4-pro"),
        ("provider", "different-provider"),
        ("route", "/v1/chat/completions"),
        ("request_timeout_seconds", 179),
    ),
)
def test_frozen_runtime_rejects_source_identity_drift(field: str, value: object) -> None:
    snapshot, _request = frozen_v2()
    selection = next(item for item in snapshot.provider_selections if item.cell_id == "Q")
    assert selection.runtime_profile_source is not None
    changed = selection.model_copy(
        update={
            "runtime_profile_source": selection.runtime_profile_source.model_copy(
                update={field: value}
            )
        }
    )
    with pytest.raises((RegistryError, ValueError), match=r"drift|route|protocol"):
        resolve_frozen_direct_runtime(changed, snapshot.plan.budget_contract)


def test_frozen_runtime_rejects_protocol_drift() -> None:
    snapshot, _request = frozen_v2()
    selection = next(item for item in snapshot.provider_selections if item.cell_id == "Q")
    assert selection.runtime_profile_source is not None
    source = selection.runtime_profile_source.model_copy(
        update={"protocol": "responses", "route": "/responses"}
    )
    with pytest.raises((RegistryError, ValueError)):
        resolve_frozen_direct_runtime(
            selection.model_copy(update={"runtime_profile_source": source}),
            snapshot.plan.budget_contract,
        )


def test_frozen_runtime_rejects_budget_envelope_and_runner_drift() -> None:
    snapshot, _request = frozen_v2()
    selection = next(item for item in snapshot.provider_selections if item.cell_id == "Q")
    budget = snapshot.plan.budget_contract
    two_thousand = budget.model_copy(
        update={
            "max_output_tokens": BudgetDimension(
                status=budget.max_output_tokens.status,
                value=2000,
                unit=budget.max_output_tokens.unit,
                scopes=budget.max_output_tokens.scopes,
            )
        }
    )
    with pytest.raises(RegistryError, match=r"runtime profile control|effective runtime profile"):
        resolve_frozen_direct_runtime(selection, two_thousand)

    changed_envelope = selection.model_copy(
        update={"resource_envelope_identity": "sha256:" + "0" * 64}
    )
    with pytest.raises(RegistryError, match="resource envelope"):
        resolve_frozen_direct_runtime(changed_envelope, budget)

    cells = tuple(
        cell.model_copy(update={"runner_contract": "direct-model-v2"}) if cell.id == "Q" else cell
        for cell in snapshot.plan.cells
    )
    changed_plan = snapshot.plan.model_copy(update={"cells": cells})
    with pytest.raises(RegistryError, match="runner contract"):
        validate_frozen_runtime_contract(changed_plan, snapshot.provider_selections)


def test_snapshot_loader_rejects_rehashed_runtime_drift() -> None:
    snapshot, _request = frozen_v2()
    raw = snapshot.model_dump(mode="json")
    raw["provider_selections"][0]["runtime_profile_source"]["requested_model"] = "deepseek-v4-pro"
    raw["snapshot_digest"] = canonical_digest(
        {key: value for key, value in raw.items() if key not in {"snapshot_digest", "preflight"}}
    )
    with pytest.raises(ValueError, match="Direct runtime identities"):
        ExperimentSnapshot.model_validate(raw)
