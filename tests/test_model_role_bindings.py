from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from harnesslab.model_lane.models import ProviderInvocationError, ProviderRequest
from harnesslab.registry.model_bindings import (
    ModelBindingError,
    ModelPurpose,
    ModelRoleBinding,
    RoleBoundProvider,
    freeze_model_role,
    resolve_model_role_environment,
)
from harnesslab.registry.service import registry_catalog
from harnesslab.registry.vault import CredentialVault
from tests.phase_g_helpers import ROOT
from tests.test_local_connections import CONNECTION, KEY, KEY_BODY, PREFIX, URL
from tests.test_local_connections import configured as configured
from tests.test_local_model_configuration import BODY, PATH, local_client
from tests.test_registry_lite import isolated_registry_database, relay_environment


async def configure(
    client: httpx.AsyncClient, purpose: ModelPurpose, *, connected: bool = True
) -> dict[str, Any]:
    if connected:
        assert (
            await client.put(PREFIX + "/credentials/test-key", json=KEY_BODY)
        ).status_code == 200
        assert (
            await client.put(PREFIX + "/connections/test-service", json=CONNECTION)
        ).status_code == 200
    body = {**BODY, "purpose": purpose, "max_output_tokens": 1000, "reasoning_effort": "high"}
    if connected:
        body.update(connection_id="test-service", connection_revision=1)
    assert (await client.put(PATH, json=body)).status_code == 200
    return body


async def freeze(
    factory: async_sessionmaker[AsyncSession],
    vault: CredentialVault,
    selected_purpose: ModelPurpose,
    **overrides: Any,
) -> ModelRoleBinding:
    arguments: dict[str, Any] = dict(
        configuration_id="my-model",
        revision=1,
        purpose=selected_purpose,
        output_tokens=800,
        timeout_seconds=30,
        environment=relay_environment(),
        vault=vault,
    )
    arguments.update(overrides)
    async with factory() as session:
        return await freeze_model_role(
            session, registry_catalog(ROOT, relay_environment()), **arguments
        )


def provider(
    factory: async_sessionmaker[AsyncSession],
    vault: CredentialVault,
    binding: Any,
    client: httpx.AsyncClient,
    *,
    enabled: bool = True,
    purpose: ModelPurpose | None = None,
) -> RoleBoundProvider:
    return RoleBoundProvider(
        session_factory=factory,
        repository_root=ROOT,
        binding=binding,
        purpose=purpose or binding.purpose,
        environment=relay_environment(),
        vault=vault,
        client=client,
        execution_enabled=enabled,
    )


def reply(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "role-binding-test",
            "model": "gpt-5.6",
            "status": "completed",
            "output": [
                {"type": "message", "content": [{"type": "output_text", "text": "bounded reply"}]}
            ],
            "usage": {"input_tokens": 5, "output_tokens": 3, "total_tokens": 8},
        },
    )


@pytest.mark.parametrize("purpose", ["SUBJECT", "ANALYST", "JUDGE"])
@pytest.mark.parametrize("connected", [True, False])
async def test_role_binding_round_trip_exact_payload_and_private_environment(
    database_url: str,
    configured: CredentialVault,
    purpose: ModelPurpose,
    connected: bool,
) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return reply(request)

    async with isolated_registry_database(database_url) as factory, local_client(factory) as client:
        await configure(client, purpose, connected=connected)
        binding = await freeze(factory, configured, purpose)
        frozen = binding.model_dump_json()
        assert KEY not in frozen and URL not in frozen
        rebound = ModelRoleBinding.model_validate_json(frozen)
        assert rebound.digest == binding.digest
        assert calls == []
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            adapter = provider(factory, configured, rebound, http)
            result = await adapter.invoke(
                ProviderRequest(profile=rebound.runtime, instructions="test", input="test")
            )
        assert result.requested_model == rebound.runtime.requested_model
        assert len(calls) == 1
        payload = json.loads(calls[0].content)
        assert payload["max_output_tokens"] == 800
        assert payload["reasoning"]["effort"] == "high"
        assert (
            str(calls[0].url)
            == (URL if connected else relay_environment()["HARNESSLAB_GPT56_RELAY_BASE_URL"])
            + "/responses"
        )
        async with factory() as session:
            resolved = await resolve_model_role_environment(
                session,
                registry_catalog(ROOT, relay_environment()),
                rebound,
                purpose=purpose,
                environment=relay_environment(),
                vault=configured,
            )
        assert len(resolved) == 2
        assert set(resolved) == {
            rebound.runtime.credential_reference,
            rebound.runtime.base_url_reference,
        }


@pytest.mark.parametrize(
    "change", ["model_version", "disabled", "purpose", "connection_version", "credential_rotation"]
)
async def test_stale_binding_blocks_network_and_preserves_original_json(
    database_url: str, configured: CredentialVault, change: str
) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return reply(request)

    async with isolated_registry_database(database_url) as factory, local_client(factory) as client:
        body = await configure(client, "ANALYST")
        binding = await freeze(factory, configured, "ANALYST")
        before = binding.model_dump_json()
        if change in {"model_version", "disabled", "purpose"}:
            updates: dict[str, Any] = {"expected_revision": 1, "name": "New version"}
            if change == "disabled":
                updates["enabled"] = False
            if change == "purpose":
                updates["purpose"] = "JUDGE"
            assert (await client.put(PATH, json={**body, **updates})).status_code == 200
        elif change == "connection_version":
            assert (
                await client.put(
                    PREFIX + "/connections/test-service",
                    json={**CONNECTION, "expected_revision": 1},
                )
            ).status_code == 200
        else:
            assert (
                await client.put(
                    PREFIX + "/credentials/test-key",
                    json={**KEY_BODY, "expected_revision": 1, "value": "rotated-test-only-key"},
                )
            ).status_code == 200
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            with pytest.raises(ProviderInvocationError, match="no longer executable"):
                await provider(factory, configured, binding, http).invoke(
                    ProviderRequest(profile=binding.runtime, instructions="test", input="test")
                )
        assert calls == []
        assert binding.model_dump_json() == before
        assert ModelRoleBinding.model_validate_json(before).digest == binding.digest


@pytest.mark.parametrize(
    "overrides",
    [
        {"purpose": "JUDGE"},
        {"revision": 2},
        {"output_tokens": 1001},
        {"output_tokens": True},
        {"timeout_seconds": 46},
        {"timeout_seconds": float("nan")},
    ],
)
async def test_role_revision_and_budget_mismatch_fail_before_binding(
    database_url: str, configured: CredentialVault, overrides: Any
) -> None:
    async with isolated_registry_database(database_url) as factory, local_client(factory) as client:
        await configure(client, "ANALYST")
        with pytest.raises(ModelBindingError):
            await freeze(factory, configured, "ANALYST", **overrides)


async def test_adapter_requires_separate_enablement_exact_role_and_request(
    database_url: str, configured: CredentialVault
) -> None:
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return reply(request)

    async with isolated_registry_database(database_url) as factory, local_client(factory) as client:
        await configure(client, "JUDGE")
        binding = await freeze(factory, configured, "JUDGE")
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            with pytest.raises(ModelBindingError, match="role"):
                provider(factory, configured, binding, http, purpose="SUBJECT")
            with pytest.raises(ProviderInvocationError, match="not enabled"):
                await provider(factory, configured, binding, http, enabled=False).invoke(
                    ProviderRequest(profile=binding.runtime, instructions="test", input="test")
                )
            changed = binding.runtime.model_copy(
                update={
                    "reasoning": binding.runtime.reasoning.model_copy(
                        update={"max_output_tokens": 801}
                    )
                }
            )
            with pytest.raises(ProviderInvocationError, match="does not match"):
                await provider(factory, configured, binding, http).invoke(
                    ProviderRequest(profile=changed, instructions="test", input="test")
                )
        assert not calls
        invalid = binding.model_dump(mode="json")
        invalid["runtime"]["requested_model"] = "changed"
        with pytest.raises(ValidationError):
            ModelRoleBinding.model_validate(invalid)


@pytest.mark.parametrize("field", ["output", "request_id", "model"])
async def test_bound_provider_never_returns_vault_values_to_consumers(
    database_url: str, configured: CredentialVault, field: str
) -> None:
    async with isolated_registry_database(database_url) as factory, local_client(factory) as client:
        await configure(client, "JUDGE")
        binding = await freeze(factory, configured, "JUDGE")

        def handler(request: httpx.Request) -> httpx.Response:
            data = reply(request).json()
            if field == "output":
                data["output"][0]["content"][0]["text"] = KEY + URL
            if field == "request_id":
                data["id"] = KEY
            if field == "model":
                data["model"] = URL
            return httpx.Response(200, json=data)

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            with pytest.raises(ProviderInvocationError) as error:
                await provider(factory, configured, binding, http).invoke(
                    ProviderRequest(profile=binding.runtime, instructions="test", input="test")
                )
        assert KEY not in str(error.value) and URL not in str(error.value)


@pytest.mark.parametrize("purpose", ["SUBJECT", "ANALYST", "JUDGE"])
async def test_existing_consumers_use_bound_role_without_changing_their_evidence_authority(
    database_url: str,
    configured: CredentialVault,
    purpose: ModelPurpose,
    tmp_path: Path,
) -> None:
    from harnesslab.analyst.models import AbstainDecision
    from harnesslab.analyst.real_backend import AnalystProfile, RealAnalystBackend
    from harnesslab.judgelab.models import JudgeRunOutcome
    from harnesslab.judgelab.runner import JudgeRunner
    from harnesslab.model_lane.runner import DirectModelRunner
    from tests.test_analyst_contracts import _request, _scope
    from tests.test_analyst_sessions import spend_limits
    from tests.test_judge_contracts import _dependencies, _plan
    from tests.test_model_lane import correct_patch

    calls: list[httpx.Request] = []
    reservations = []

    async def reserve(value: Any) -> None:
        reservations.append(value)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if purpose == "ANALYST":
            assert len(reservations) == 1
        data = reply(request).json()
        text = (
            correct_patch()
            if purpose == "SUBJECT"
            else json.dumps({"decision": {"kind": "abstain", "reason": "Insufficient evidence."}})
            if purpose == "ANALYST"
            else json.dumps(
                {"schema_version": 1, "label": "UNKNOWN", "reason": "Insufficient evidence."}
            )
        )
        data["output"][0]["content"][0]["text"] = text
        return httpx.Response(200, json=data)

    async with isolated_registry_database(database_url) as factory, local_client(factory) as client:
        await configure(client, purpose)
        binding = await freeze(factory, configured, purpose)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            adapter = provider(factory, configured, binding, http)
            if purpose == "SUBJECT":
                result = await DirectModelRunner(
                    artifact_root=tmp_path / "subject-artifacts",
                    runtime_root=tmp_path / "subject-runtime",
                    environment={},
                    allow_custom_endpoint=True,
                ).run(
                    ROOT / "tasks/micro-python-clamp/1.0.0",
                    binding.runtime,
                    adapter=adapter,
                    run_id="bound-subject-a1",
                )
                assert result.evidence.verifier_passed is True
                assert result.evidence.generation_settings.max_output_tokens == 800
            elif purpose == "ANALYST":
                backend = RealAnalystBackend(
                    AnalystProfile(
                        profile_id="local-my-model-v1",
                        profile_digest=binding.provider_profile_identity,
                        runtime=binding.runtime,
                        context_window_tokens=1000,
                    ),
                    environment={},
                    adapter=adapter,
                    budget=spend_limits(output_tokens_per_request=800, timeout_seconds=30),
                    reserve=reserve,
                )
                decision = await backend.decide(
                    request=_request(),
                    scope=_scope(),
                    evidence=(),
                    iteration=1,
                    remaining_tool_calls=1,
                )
                assert isinstance(decision, AbstainDecision)
                assert len(reservations) == 1
                assert backend.last_usage is not None
                assert backend.last_usage.invocation_started is True
            else:
                suite, definition, spec = _dependencies()
                plan = _plan(suite, definition, spec)
                slot = next(s for s in plan.slots if s.case_id == "label-l0-pass")
                case = next(c for c in suite.public.cases if c.case_id == slot.case_id)
                judged = await JudgeRunner(tmp_path / "judge-artifacts").run(
                    slot=slot,
                    case=case,
                    suite_id=suite.public.suite_id,
                    suite_version=suite.public.version,
                    suite_digest=suite.suite_digest,
                    definition=definition,
                    profile_identity=binding.runtime_digest,
                    profile=binding.runtime,
                    adapter=adapter,
                )
                assert judged.evidence.outcome is JudgeRunOutcome.ABSTAINED
                assert judged.evidence.requested_judge_model == binding.runtime.requested_model
                assert judged.artifact_path is not None
                artifact = judged.artifact_path.read_text()
                assert KEY not in artifact and URL not in artifact
        assert len(calls) == 1


async def test_provider_error_metadata_is_sanitized_with_category_preserved(
    database_url: str, configured: CredentialVault
) -> None:
    from harnesslab.model_lane.models import ProviderFailureCategory

    async with isolated_registry_database(database_url) as factory, local_client(factory) as client:
        await configure(client, "ANALYST")
        binding = await freeze(factory, configured, "ANALYST")

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                429, headers={"x-request-id": KEY}, json={"error": {"message": KEY + URL}}
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            with pytest.raises(ProviderInvocationError) as error:
                await provider(factory, configured, binding, http).invoke(
                    ProviderRequest(profile=binding.runtime, instructions="test", input="test")
                )
        assert error.value.category is ProviderFailureCategory.RATE_LIMIT
        assert error.value.status_code == 429
        assert KEY not in str(error.value.__dict__) and URL not in str(error.value.__dict__)
