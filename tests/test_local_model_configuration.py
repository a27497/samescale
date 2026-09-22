from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from harnesslab.api.app import create_app
from harnesslab.api.local_configuration import local_catalog_session
from harnesslab.api.workbench_dependencies import workbench_session
from harnesslab.db.models.experiment import ExperimentRecord, ExperimentRunRecord
from harnesslab.db.models.registry import LocalModelConfigurationRecord
from harnesslab.productization.demo import create_demo_app
from harnesslab.registry.local_models import (
    LocalModelConfiguration,
    configurations,
    effective_catalog,
)
from harnesslab.registry.models import CompatibilityStatus, freeze_provider_model_profile
from harnesslab.registry.service import assess_capability, registry_catalog
from tests.phase_g_helpers import ROOT
from tests.test_registry_lite import (
    alibaba_environment,
    builder_request,
    isolated_registry_database,
    relay_environment,
)

TOKEN = "local-operator-test-placeholder-1234567890"
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Origin": "http://localhost"}
PATH = "/api/local-configuration/models/my-model"
BODY = {
    "name": "Local model",
    "template_profile_id": "gpt56-relay-gpt56-responses",
    "request_timeout_seconds": 45,
    "enabled": True,
    "expected_revision": 0,
}


def test_removed_environment_template_does_not_break_remaining_catalog() -> None:
    original = registry_catalog(ROOT, alibaba_environment(model_id="custom-original-model"))
    template = next(
        p for p in original.provider_model_profiles if p.requested_model == "custom-original-model"
    )
    profile_values = template.model_dump(exclude={"profile_identity"})
    profile_values.update(profile_id="local-removed-v1", enabled=True, request_timeout_seconds=45)
    item = LocalModelConfiguration(
        configuration_id="removed",
        revision=1,
        name="Removed template",
        template_profile_id=template.profile_id,
        template_digest=template.profile_identity,
        request_timeout_seconds=45,
        enabled=True,
        profile=freeze_provider_model_profile(**profile_values),
    )
    current = registry_catalog(ROOT, alibaba_environment(model_id="custom-replacement-model"))
    effective = effective_catalog(current, (item,))
    assert effective.digest == current.digest
    assert all(p.profile_id != item.profile.profile_id for p in effective.provider_model_profiles)


@asynccontextmanager
async def local_client(factory: async_sessionmaker[AsyncSession]) -> AsyncIterator[AsyncClient]:
    app = create_app()

    async def session() -> AsyncIterator[AsyncSession]:
        async with factory() as current:
            yield current

    app.dependency_overrides[workbench_session] = session
    app.dependency_overrides[local_catalog_session] = session
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://localhost", headers=HEADERS
    ) as client:
        yield client


@pytest.mark.parametrize(
    "token,headers,status",
    [
        (None, HEADERS, 403),
        ("short", HEADERS, 403),
        (TOKEN, {"Origin": "http://localhost"}, 403),
        (TOKEN, {**HEADERS, "Origin": "https://outside.example"}, 403),
        (TOKEN, {**HEADERS, "Origin": "null"}, 403),
        (TOKEN, {"Authorization": f"Bearer {TOKEN}"}, 403),
        (TOKEN, {**HEADERS, "Sec-Fetch-Site": "cross-site"}, 403),
        (TOKEN, {**HEADERS, "Host": "outside.example", "Origin": "http://outside.example"}, 403),
        (TOKEN, {**HEADERS, "Host": "[invalid"}, 403),
    ],
)
async def test_operator_boundary_precedes_database_access(
    token: str | None, headers: dict[str, str], status: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HARNESSLAB_LOCAL_CONFIGURATION_TOKEN", raising=False)
    if token is not None:
        monkeypatch.setenv("HARNESSLAB_LOCAL_CONFIGURATION_TOKEN", token)
    app = create_app()

    async def forbidden_session() -> AsyncIterator[AsyncSession]:
        raise AssertionError("denied request reached the database")
        yield  # pragma: no cover

    app.dependency_overrides[workbench_session] = forbidden_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as client:
        response = await client.put(PATH, json=BODY, headers=headers)
        assert response.status_code == status
        assert TOKEN not in response.text


@pytest.mark.parametrize(
    "extra",
    [
        {"api_key": "secret-sentinel"},
        {"argv": ["shell"]},
        {"request_timeout_seconds": 601},
        {"enabled": "true"},
    ],
)
async def test_write_schema_does_not_accept_secrets_commands_or_unbounded_values(
    extra: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HARNESSLAB_LOCAL_CONFIGURATION_TOKEN", TOKEN)
    app = create_app()

    async def unused_session() -> AsyncIterator[None]:
        yield None

    app.dependency_overrides[workbench_session] = unused_session
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as client:
        response = await client.put(PATH, json={**BODY, **extra}, headers=HEADERS)
        assert response.status_code == 422
        assert "secret-sentinel" not in response.text


async def test_demo_never_registers_local_configuration_or_loads_database(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HARNESSLAB_LOCAL_CONFIGURATION_TOKEN", TOKEN)
    app = create_demo_app(tmp_path)
    assert not any(
        getattr(route, "path", "").startswith("/api/local-configuration") for route in app.routes
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as client:
        response = await client.put(PATH, json=BODY, headers=HEADERS)
        assert response.status_code == 503
        catalog = await client.get("/api/registry/models")
        assert catalog.status_code == 200
        assert not any(
            p["profile_id"].startswith("local-") for p in catalog.json()["provider_profiles"]
        )


@pytest.mark.integration
async def test_revision_persistence_planning_disable_and_immutable_snapshot(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HARNESSLAB_LOCAL_CONFIGURATION_TOKEN", TOKEN)
    for key, value in relay_environment().items():
        monkeypatch.setenv(key, value)
    async with isolated_registry_database(database_url) as factory:
        async with local_client(factory) as client:
            created = await client.put(PATH, json=BODY)
            assert created.status_code == 200, created.text
            first = created.json()
            assert first["revision"] == 1
            assert first["profile"]["profile_id"] == "local-my-model-v1"
            assert (await client.put(PATH, json=BODY)).status_code == 409
            model_data = (await client.get("/api/registry/models")).json()
            assert any(
                p["profile_id"] == "local-my-model-v1" for p in model_data["provider_profiles"]
            )
            request = builder_request(
                left_profile="local-my-model-v1", left_harness="direct-local-my-model-v1"
            ).model_dump(mode="json")
            preflight = await client.post("/api/experiments/preflight", json=request)
            assert preflight.status_code == 200
            assert preflight.json()["status"] != "BLOCKED", preflight.text
            snapshot = await client.post("/api/experiments/snapshot", json=request)
            assert snapshot.status_code == 200, snapshot.text
            frozen = snapshot.json()
            revised = await client.put(
                PATH, json={**BODY, "expected_revision": 1, "request_timeout_seconds": 90}
            )
            assert revised.status_code == 200
            second = revised.json()
            assert second["profile"]["profile_identity"] != first["profile"]["profile_identity"]
            assert (await client.post("/api/experiments/preflight", json=request)).json()[
                "status"
            ] == "BLOCKED"
            request["cells"][0].update(
                provider_model_profile_id="local-my-model-v2",
                harness_profile_id="direct-local-my-model-v2",
            )
            second_snapshot = await client.post("/api/experiments/snapshot", json=request)
            assert second_snapshot.status_code == 200, second_snapshot.text
            assert second_snapshot.json()["snapshot_id"] != frozen["snapshot_id"]
            disabled = await client.put(
                PATH, json={**BODY, "expected_revision": 2, "enabled": False}
            )
            assert disabled.status_code == 200
            request["cells"][0].update(
                provider_model_profile_id="local-my-model-v3",
                harness_profile_id="direct-local-my-model-v3",
            )
            assert (await client.post("/api/experiments/preflight", json=request)).json()[
                "status"
            ] == "BLOCKED"
            assert (
                await client.get(f"/api/experiments/snapshots/{frozen['snapshot_id']}")
            ).json() == frozen
            assert TOKEN not in snapshot.text
            assert "fake-relay-key" not in snapshot.text
        # Recreate the API/session to verify data comes from PostgreSQL, not process memory.
        async with local_client(factory) as restarted:
            readback = await restarted.get("/api/local-configuration/models")
            assert readback.status_code == 200
            assert readback.json()["items"][0]["revision"] == 3
            assert readback.json()["items"][0]["enabled"] is False
            assert (
                await restarted.get(f"/api/experiments/snapshots/{frozen['snapshot_id']}")
            ).json() == frozen
        async with factory() as session:
            assert (
                await session.scalar(
                    select(func.count()).select_from(LocalModelConfigurationRecord)
                )
                == 3
            )
            assert await session.scalar(select(func.count()).select_from(ExperimentRecord)) == 0
            assert await session.scalar(select(func.count()).select_from(ExperimentRunRecord)) == 0
            builtin = registry_catalog(ROOT, relay_environment())
            before = builtin.model_dump(mode="json")
            stored = await configurations(session)
            effective = effective_catalog(builtin, stored)
            assert builtin.model_dump(mode="json") == before
            assert (
                assess_capability(effective, "local-my-model-v3", "codex-gpt56-medium").status
                == CompatibilityStatus.UNSUPPORTED
            )


@pytest.mark.integration
async def test_template_drift_blocks_new_planning_and_unknown_template_is_rejected(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HARNESSLAB_LOCAL_CONFIGURATION_TOKEN", TOKEN)
    for key, value in relay_environment().items():
        monkeypatch.setenv(key, value)
    async with isolated_registry_database(database_url) as factory:
        async with local_client(factory) as client:
            assert (
                await client.put(PATH, json={**BODY, "template_profile_id": "unregistered"})
            ).status_code == 422
            assert (await client.put(PATH, json=BODY)).status_code == 200
        async with factory() as session:
            records = await configurations(session)
            environment = {
                **relay_environment(),
                "HARNESSLAB_GPT56_RELAY_BASE_URL": "https://changed.example/v1",
            }
            effective = effective_catalog(registry_catalog(ROOT, environment), records)
            assert not next(
                p for p in effective.provider_model_profiles if p.profile_id == "local-my-model-v1"
            ).enabled


@pytest.mark.integration
async def test_simultaneous_edits_preserve_one_revision(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HARNESSLAB_LOCAL_CONFIGURATION_TOKEN", TOKEN)
    async with isolated_registry_database(database_url) as factory:
        async with local_client(factory) as client:
            assert (await client.put(PATH, json=BODY)).status_code == 200
            results = await asyncio.gather(
                client.put(PATH, json={**BODY, "expected_revision": 1, "name": "Writer one"}),
                client.put(PATH, json={**BODY, "expected_revision": 1, "name": "Writer two"}),
            )
            assert sorted(r.status_code for r in results) == [200, 409]
        async with factory() as session:
            assert (
                await session.scalar(
                    select(func.count()).select_from(LocalModelConfigurationRecord)
                )
                == 2
            )
