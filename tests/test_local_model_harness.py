from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select

from harnesslab.api.app import create_app
from harnesslab.db.models.experiment import ExperimentRecord, ExperimentRunRecord
from harnesslab.db.models.registry import RegistryExperimentSnapshotRecord
from harnesslab.productization.demo import create_demo_app
from harnesslab.registry.models import ExperimentSnapshot
from harnesslab.registry.runtime import (
    DirectRuntimeContractError,
    DirectRuntimeProfileSource,
    resolve_direct_runtime_profile,
)
from harnesslab.registry.service import resolve_frozen_direct_runtime
from tests.test_local_model_configuration import BODY, HEADERS, PATH, TOKEN, local_client
from tests.test_registry_lite import (
    budget,
    builder_request,
    isolated_registry_database,
    relay_environment,
)

HARNESS_PATH = "/api/local-configuration/harnesses/my-runtime"
HARNESS = {
    "name": "My runtime",
    "expected_revision": 0,
    "enabled": True,
    "template_profile_id": "direct-gpt56-relay-gpt56-responses",
    "provider_profile_ids": ["local-my-model-v1"],
}


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HARNESSLAB_LOCAL_CONFIGURATION_TOKEN", TOKEN)
    for key, value in relay_environment().items():
        monkeypatch.setenv(key, value)


def test_direct_source_preserves_legacy_bytes_and_binds_generation_limit() -> None:
    old = {
        "provider": "fake-provider",
        "requested_model": "fake-model",
        "protocol": "responses",
        "route": "/responses",
        "base_url": "https://provider.example/v1",
        "credential_reference": "TEST_KEY",
        "reasoning_effort": "medium",
        "request_timeout_seconds": 45,
    }
    source = DirectRuntimeProfileSource.model_validate(old)
    assert source.model_dump(mode="json") == old
    constrained = source.model_copy(update={"max_output_tokens_limit": 1000, "temperature": 0.3})
    with pytest.raises(DirectRuntimeContractError, match="exceeds"):
        resolve_direct_runtime_profile(constrained, budget())
    selected = budget().model_copy(
        update={"max_output_tokens": budget().max_output_tokens.model_copy(update={"value": 1000})}
    )
    runtime = resolve_direct_runtime_profile(constrained, selected)
    assert runtime.profile.reasoning.max_output_tokens == 1000
    assert runtime.profile.reasoning.temperature == 0.3


@pytest.mark.integration
async def test_roles_controls_harness_revisions_and_frozen_runtime(
    database_url: str, configured: None
) -> None:
    async with isolated_registry_database(database_url) as factory:
        async with local_client(factory) as client:
            options = await client.get("/api/local-configuration/options")
            assert options.status_code == 200 and options.headers["cache-control"] == "no-store"
            control = next(
                p
                for p in options.json()["model_controls"]
                if p["profile_id"] == BODY["template_profile_id"]
            )
            assert control["reasoning_efforts"] == ["low", "medium", "high"]
            assert not control["temperature_supported"]
            body = {
                **BODY,
                "purpose": "SUBJECT",
                "max_output_tokens": 1000,
                "reasoning_effort": "high",
            }
            model = await client.put(PATH, json=body)
            assert model.status_code == 200, model.text
            assert model.json()["profile"]["max_output_tokens_limit"] == 1000
            created = await client.put(HARNESS_PATH, json=HARNESS)
            assert created.status_code == 200, created.text
            request = builder_request(
                left_profile="local-my-model-v1", left_harness="local-harness-my-runtime-v1"
            ).model_dump(mode="json")
            assert (await client.post("/api/experiments/preflight", json=request)).json()[
                "status"
            ] == "BLOCKED"
            request["budget"]["max_output_tokens"]["value"] = 1000
            # Match right Codex preset's reasoning control to the chosen model.
            request["cells"][1]["harness_profile_id"] = "codex-gpt56-high"
            request["comparison_type"] = "END_TO_END_SYSTEM_COMPARISON"
            snapshot = await client.post("/api/experiments/snapshot", json=request)
            assert snapshot.status_code == 200, snapshot.text
            frozen = snapshot.json()
            assert frozen["plan"]["cells"][0]["reasoning_effort"] == "high"
            async with factory() as session:
                row = await session.get(RegistryExperimentSnapshotRecord, frozen["snapshot_id"])
                assert row is not None
                parsed = ExperimentSnapshot.model_validate(row.snapshot_json)
                profile = resolve_frozen_direct_runtime(
                    parsed.provider_selections[0], parsed.plan.budget_contract
                )
                assert profile.reasoning.effort == "high"
                assert profile.reasoning.max_output_tokens == 1000
            disabled = await client.put(
                HARNESS_PATH, json={**HARNESS, "expected_revision": 1, "enabled": False}
            )
            assert disabled.status_code == 200
            request["cells"][0]["harness_profile_id"] = "local-harness-my-runtime-v2"
            assert (await client.post("/api/experiments/preflight", json=request)).json()[
                "status"
            ] == "BLOCKED"
            for i, purpose in enumerate(["ANALYST", "JUDGE"], start=1):
                revised = await client.put(
                    PATH, json={**body, "purpose": purpose, "expected_revision": i}
                )
                assert revised.status_code == 200
                version = f"local-my-model-v{i + 1}"
                request["cells"][0].update(
                    provider_model_profile_id=version, harness_profile_id=f"direct-{version}"
                )
                assert (await client.post("/api/experiments/preflight", json=request)).json()[
                    "status"
                ] == "BLOCKED"
                profiles = (await client.get("/api/registry/models")).json()["provider_profiles"]
                assert next(p for p in profiles if p["profile_id"] == version)["purpose"] == purpose
                rejected = await client.put(
                    HARNESS_PATH,
                    json={**HARNESS, "expected_revision": 2, "provider_profile_ids": [version]},
                )
                assert rejected.status_code == 422
            assert (
                await client.get("/api/experiments/snapshots/" + frozen["snapshot_id"])
            ).json() == frozen
        async with local_client(factory) as restarted:
            assert (await restarted.get("/api/local-configuration/harnesses")).json()["items"][0][
                "revision"
            ] == 2
            assert (
                await restarted.get("/api/experiments/snapshots/" + frozen["snapshot_id"])
            ).json() == frozen
        async with factory() as session:
            for table in [ExperimentRecord, ExperimentRunRecord]:
                assert await session.scalar(select(func.count()).select_from(table)) == 0


@pytest.mark.integration
async def test_invalid_controls_and_harness_bindings_fail_closed(
    database_url: str, configured: None
) -> None:
    async with isolated_registry_database(database_url) as factory, local_client(factory) as client:
        invalid_model_controls: list[dict[str, Any]] = [
            {"purpose": "UNKNOWN"},
            {"temperature": 0.3},
            {"max_output_tokens": 2001},
            {"max_output_tokens": True},
            {"reasoning_effort": "extreme"},
            {"command": "private-sentinel"},
        ]
        for extra in invalid_model_controls:
            response = await client.put(PATH, json={**BODY, **extra})
            assert response.status_code == 422 and "private-sentinel" not in response.text
        await client.put(PATH, json=BODY)
        invalid_harness_controls: list[dict[str, Any]] = [
            {"template_profile_id": "codex-gpt56-high"},
            {"provider_profile_ids": ["missing"]},
            {"provider_profile_ids": ["local-my-model-v1", "local-my-model-v1"]},
            {"argv": ["private-sentinel"]},
            {"image": "private-sentinel"},
            {"transport": "api"},
        ]
        for extra in invalid_harness_controls:
            response = await client.put(HARNESS_PATH, json={**HARNESS, **extra})
            assert response.status_code == 422 and "private-sentinel" not in response.text
        responses = await asyncio.gather(
            *[client.put(HARNESS_PATH, json=HARNESS) for _ in range(2)]
        )
        assert sorted(r.status_code for r in responses) == [200, 409]
        # Changing the model never silently changes the old Harness binding.
        await client.put(PATH, json={**BODY, "expected_revision": 1})
        catalog = (await client.get("/api/registry/harnesses")).json()
        assert all(
            p["profile_id"] != "local-harness-my-runtime-v1"
            for h in catalog["items"]
            for p in h["profiles"]
        )
        assert (
            await client.put(HARNESS_PATH, json={**HARNESS, "expected_revision": 1})
        ).status_code == 422
        rebound = await client.put(
            HARNESS_PATH,
            json={**HARNESS, "expected_revision": 1, "provider_profile_ids": ["local-my-model-v2"]},
        )
        assert rebound.status_code == 200
        # CLI presets retain the built-in compatibility whitelist.
        codex = await client.put(
            "/api/local-configuration/harnesses/my-codex",
            json={
                **HARNESS,
                "template_profile_id": "codex-gpt56-high",
                "provider_profile_ids": ["gpt56-relay-gpt56-responses"],
            },
        )
        assert codex.status_code == 200
        request = builder_request(right_harness="local-harness-my-codex-v1").model_dump(mode="json")
        request["comparison_type"] = "END_TO_END_SYSTEM_COMPARISON"
        snapshot = await client.post("/api/experiments/snapshot", json=request)
        assert snapshot.status_code == 200, snapshot.text
        assert snapshot.json()["plan"]["cells"][1]["reasoning_effort"] == "high"
        # Stale bindings can be disabled without replacing their recorded model revisions.
        await client.put(PATH, json={**BODY, "expected_revision": 2})
        disabled = await client.put(
            HARNESS_PATH,
            json={
                **HARNESS,
                "expected_revision": 2,
                "provider_profile_ids": ["local-my-model-v2"],
                "enabled": False,
            },
        )
        assert disabled.status_code == 200


@pytest.mark.parametrize(
    "path,method",
    [
        ("/api/local-configuration/options", "GET"),
        ("/api/local-configuration/harnesses", "GET"),
        (HARNESS_PATH, "PUT"),
    ],
)
async def test_harness_operator_and_demo_boundaries(
    path: str, method: str, configured: None, tmp_path: Path
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://localhost"
    ) as client:
        result = await client.request(method, path, json=HARNESS)
        assert result.status_code == 403
        result = await client.request(
            method, path, json=HARNESS, headers={**HEADERS, "Origin": "null"}
        )
        assert result.status_code == 403
    demo = create_demo_app(tmp_path)
    assert not any(
        getattr(r, "path", "").startswith("/api/local-configuration") for r in demo.routes
    )
    async with AsyncClient(
        transport=ASGITransport(app=demo), base_url="http://localhost", headers=HEADERS
    ) as client:
        assert (await client.request(method, path, json=HARNESS)).status_code == 503
