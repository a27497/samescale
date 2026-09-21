from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import httpx
import pytest
from sqlalchemy import func, select

from harnesslab.api.app import create_app
from harnesslab.api.workbench_errors import WorkbenchAPIError
from harnesslab.db.models.experiment import ExperimentRecord, ExperimentRunRecord
from harnesslab.db.models.registry import (
    LocalConnectionRecord,
    LocalCredentialRecord,
    RegistryExperimentSnapshotRecord,
)
from harnesslab.experiment.methodology import ComparisonType
from harnesslab.model_lane.models import ProviderRequest
from harnesslab.model_lane.providers import adapter_for_profile
from harnesslab.registry.connections import resolve_connection_environment
from harnesslab.registry.models import ExperimentSnapshot
from harnesslab.registry.service import resolve_frozen_direct_runtime
from harnesslab.registry.vault import CredentialVault
from tests.test_local_model_configuration import BODY, HEADERS, PATH, TOKEN, local_client
from tests.test_registry_lite import builder_request, isolated_registry_database, relay_environment

PREFIX = "/api/local-configuration"
KEY = "test-only-secret-sentinel-no-live-provider"
URL = "https://private-sentinel.provider.example/v1"
KEY_BODY = {"name": "Test credential", "expected_revision": 0, "enabled": True, "value": KEY}
CONNECTION = {
    "name": "Test service",
    "expected_revision": 0,
    "enabled": True,
    "template_provider_id": "gpt56-relay",
    "protocol": "responses",
    "base_url": URL,
    "credential_id": "test-key",
    "credential_revision": 1,
}


@pytest.fixture
def configured(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> CredentialVault:
    monkeypatch.setenv("HARNESSLAB_LOCAL_CONFIGURATION_TOKEN", TOKEN)
    monkeypatch.setenv("HARNESSLAB_CREDENTIAL_STORE", str(tmp_path / "vault"))
    for key, value in relay_environment().items():
        monkeypatch.setenv(key, value)

    async def no_network(*args: object, **kwargs: object) -> None:
        raise AssertionError("Configuration must not use network transport")

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", no_network)
    return CredentialVault.from_environment()


def test_vault_is_private_and_rejects_unsafe_files(tmp_path: Path) -> None:
    vault = CredentialVault(tmp_path / "vault")
    reference = vault.put(KEY)
    assert vault.read(reference) == KEY
    assert vault.root is not None
    assert vault.root.stat().st_mode & 0o777 == 0o700
    path = vault.root / reference
    assert path.stat().st_mode & 0o777 == 0o600
    path.chmod(0o644)
    assert not vault.present(reference)
    path.chmod(0o600)
    os.link(path, tmp_path / "hardlink")
    assert not vault.present(reference)
    (tmp_path / "hardlink").unlink()
    path.unlink()
    path.symlink_to(tmp_path / "outside")
    assert not vault.present(reference)
    for invalid in ["../outside", "/etc/passwd", "not-a-reference"]:
        with pytest.raises(WorkbenchAPIError):
            vault.read(invalid)
    with pytest.raises(WorkbenchAPIError):
        vault.put("x" * 8193)


def test_vault_rejects_missing_or_public_roots(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    unsafe = tmp_path / "public"
    unsafe.mkdir(mode=0o755)
    symlink = tmp_path / "link"
    symlink.symlink_to(unsafe)
    for root in [None, Path("."), Path("/"), Path.cwd() / "secrets", unsafe, symlink]:
        with pytest.raises(WorkbenchAPIError):
            CredentialVault(root).put(KEY)
    monkeypatch.setenv("HARNESSLAB_WORKBENCH_ARTIFACT_ROOTS", json.dumps([str(tmp_path)]))
    with pytest.raises(WorkbenchAPIError):
        CredentialVault(tmp_path / "vault").put(KEY)


@pytest.mark.parametrize(
    "route,method",
    [
        ("/credentials", "GET"),
        ("/credentials/key", "PUT"),
        ("/connections", "GET"),
        ("/connections/service", "PUT"),
        ("/connections/service/check", "POST"),
    ],
)
async def test_new_routes_require_local_operator(
    route: str, method: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HARNESSLAB_LOCAL_CONFIGURATION_TOKEN", TOKEN)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://localhost"
    ) as client:
        result = await client.request(
            method, PREFIX + route, json={}, headers={"Origin": "http://localhost"}
        )
        assert result.status_code == 403
        result = await client.request(
            method, PREFIX + route, json={}, headers={**HEADERS, "Origin": "null"}
        )
        assert result.status_code == 403


@pytest.mark.integration
async def test_connection_rotation_pins_versions_and_preserves_snapshot(
    database_url: str,
    configured: CredentialVault,
    caplog: pytest.LogCaptureFixture,
) -> None:
    async with isolated_registry_database(database_url) as factory:
        async with local_client(factory) as client:
            key = await client.put(PREFIX + "/credentials/test-key", json=KEY_BODY)
            assert key.status_code == 200, key.text
            assert key.json()["present"] and key.headers["cache-control"] == "no-store"
            created = await client.put(PREFIX + "/connections/test-service", json=CONNECTION)
            assert created.status_code == 200, created.text
            service = created.json()
            assert service["ready_for_planning"] and service["health_status"] == "NOT_VERIFIED"
            assert (
                await client.put(PREFIX + "/connections/test-service", json=CONNECTION)
            ).status_code == 409
            binding = {**BODY, "connection_id": "test-service", "connection_revision": 1}
            model = await client.put(PATH, json=binding)
            assert model.status_code == 200, model.text
            request = builder_request(
                comparison=ComparisonType.END_TO_END_SYSTEM_COMPARISON,
                left_profile="local-my-model-v1",
                left_harness="direct-local-my-model-v1",
            ).model_dump(mode="json")
            snapshot = await client.post("/api/experiments/snapshot", json=request)
            assert snapshot.status_code == 200, snapshot.text
            frozen = snapshot.json()
            # Exercise the existing adapter with the pinned connection and a mock transport.
            async with factory() as session:
                private_environment = await resolve_connection_environment(
                    session, "test-service", 1, relay_environment(), configured
                )
                record = await session.get(RegistryExperimentSnapshotRecord, frozen["snapshot_id"])
                assert record is not None
                parsed = ExperimentSnapshot.model_validate(record.snapshot_json)
            profile = resolve_frozen_direct_runtime(
                parsed.provider_selections[0], parsed.plan.budget_contract
            )
            calls = []

            async def handler(outbound: httpx.Request) -> httpx.Response:
                calls.append(outbound.url.path)
                assert str(outbound.url) == URL + "/responses"
                assert outbound.headers["authorization"] == "Bearer " + KEY
                return httpx.Response(
                    200,
                    json={
                        "id": "mock-only",
                        "model": "gpt-5.6",
                        "status": "completed",
                        "output": [
                            {"type": "message", "content": [{"type": "output_text", "text": "ok"}]}
                        ],
                        "usage": {},
                    },
                )

            provider_request = ProviderRequest(profile=profile, instructions="system", input="user")
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as mock:
                result = await adapter_for_profile(
                    provider_request, client=mock, environment=private_environment
                ).invoke(provider_request)
            assert calls == ["/v1/responses"]
            assert KEY not in result.model_dump_json() and URL not in result.model_dump_json()
            check = await client.post(PREFIX + "/connections/test-service/check", json={})
            assert check.json()["provider_requests"] == check.json()["network_requests"] == 0
            assert check.json()["connection_health"] == "NOT_VERIFIED"
            rotated = await client.put(
                PREFIX + "/credentials/test-key",
                json={**KEY_BODY, "expected_revision": 1, "value": KEY + "-rotated"},
            )
            assert rotated.status_code == 200 and rotated.json()["revision"] == 2
            assert not (await client.get(PREFIX + "/connections")).json()["items"][0][
                "ready_for_planning"
            ]
            assert (await client.post("/api/experiments/preflight", json=request)).json()[
                "status"
            ] == "BLOCKED"
            async with factory() as session:
                with pytest.raises(WorkbenchAPIError):
                    await resolve_connection_environment(
                        session, "test-service", 1, relay_environment(), configured
                    )
            rebound = await client.put(
                PREFIX + "/connections/test-service",
                json={**CONNECTION, "expected_revision": 1, "credential_revision": 2},
            )
            assert rebound.status_code == 200 and rebound.json()["ready_for_planning"]
            assert (
                await client.put(PATH, json={**binding, "expected_revision": 1})
            ).status_code == 409
            model = await client.put(
                PATH, json={**binding, "expected_revision": 1, "connection_revision": 2}
            )
            assert model.status_code == 200
            request["cells"][0].update(
                provider_model_profile_id="local-my-model-v2",
                harness_profile_id="direct-local-my-model-v2",
            )
            assert (await client.post("/api/experiments/preflight", json=request)).json()[
                "status"
            ] != "BLOCKED"
            disabled = await client.put(
                PREFIX + "/credentials/test-key",
                json={"name": "Disabled key", "expected_revision": 2, "enabled": False},
            )
            assert disabled.status_code == 200 and not disabled.json()["present"]
            assert (await client.post("/api/experiments/preflight", json=request)).json()[
                "status"
            ] == "BLOCKED"
            assert (
                await client.get("/api/experiments/snapshots/" + frozen["snapshot_id"])
            ).json() == frozen
            for route in ["/credentials", "/connections", "/models"]:
                data = await client.get(PREFIX + route)
                assert KEY not in data.text and URL not in data.text and TOKEN not in data.text
            assert (
                KEY not in snapshot.text and URL not in snapshot.text and TOKEN not in snapshot.text
            )
        async with local_client(factory) as restarted:
            assert (await restarted.get(PREFIX + "/credentials")).json()["items"][0][
                "revision"
            ] == 3
            assert (
                await restarted.get("/api/experiments/snapshots/" + frozen["snapshot_id"])
            ).json() == frozen
        async with factory() as session:
            for table in [LocalCredentialRecord, LocalConnectionRecord]:
                rows = (await session.scalars(select(table))).all()
                stored_data = repr(
                    [
                        {c.name: getattr(row, c.name) for c in table.__table__.columns}
                        for row in rows
                    ]
                )
                assert KEY not in stored_data and URL not in stored_data
            for table in [ExperimentRecord, ExperimentRunRecord]:
                assert await session.scalar(select(func.count()).select_from(table)) == 0
        assert KEY not in caplog.text and URL not in caplog.text


@pytest.mark.integration
async def test_conflicts_invalid_secrets_environment_references_and_endpoint_tamper(
    database_url: str,
    configured: CredentialVault,
) -> None:
    async with (
        isolated_registry_database(database_url) as factory,
        local_client(factory) as client,
    ):
        concurrent = await asyncio.gather(
            *[client.put(PREFIX + "/credentials/test-key", json=KEY_BODY) for _ in range(2)]
        )
        assert sorted(r.status_code for r in concurrent) == [200, 409]
        assert configured.root is not None
        assert len(list(configured.root.iterdir())) == 1
        for value in ["", KEY + "\n", KEY + " " * 9000]:
            invalid = await client.put(
                PREFIX + "/credentials/invalid", json={**KEY_BODY, "value": value}
            )
            assert invalid.status_code == 422 and KEY not in invalid.text
        for url in [
            "http://provider.example",
            "https://127.0.0.1",
            "https://" + KEY + "@provider.example",
            URL + "?key=" + KEY,
        ]:
            invalid = await client.put(
                PREFIX + "/connections/invalid", json={**CONNECTION, "base_url": url}
            )
            assert invalid.status_code == 422 and KEY not in invalid.text
        env_connection = {
            **CONNECTION,
            "credential_id": None,
            "credential_revision": None,
            "environment_reference": "DATABASE_URL",
        }
        assert (
            await client.put(PREFIX + "/connections/invalid", json=env_connection)
        ).status_code == 422
        good = await client.put(
            PREFIX + "/connections/env-service",
            json={**env_connection, "environment_reference": "HARNESSLAB_GPT56_RELAY_API_KEY"},
        )
        assert good.status_code == 200 and good.json()["ready_for_planning"]
        mismatch = await client.put(
            PATH, json={**BODY, "connection_id": "env-service", "connection_revision": 100}
        )
        assert mismatch.status_code == 409
        async with factory() as session:
            row = (await session.scalars(select(LocalConnectionRecord))).one()
            (configured.root / row.endpoint_storage_reference).write_text(
                "https://changed.example/v1"
            )
        checked = await client.post(PREFIX + "/connections/env-service/check", json={})
        assert not checked.json()["connection"]["endpoint_present"]
        assert not checked.json()["connection"]["ready_for_planning"]


@pytest.mark.integration
@pytest.mark.parametrize(
    "provider,protocol",
    [
        ("gpt56-relay", "responses"),
        ("opencode-go", "chat_completions"),
        ("opencode-go", "messages"),
    ],
)
async def test_protocol_connections_disable_and_reject_template_mismatch(
    database_url: str,
    configured: CredentialVault,
    provider: str,
    protocol: str,
) -> None:
    async with isolated_registry_database(database_url) as factory, local_client(factory) as client:
        assert (
            await client.put(PREFIX + "/credentials/test-key", json=KEY_BODY)
        ).status_code == 200
        body = {**CONNECTION, "template_provider_id": provider, "protocol": protocol}
        saved = await client.put(PREFIX + "/connections/protocol-service", json=body)
        assert saved.status_code == 200 and saved.json()["ready_for_planning"]
        model = await client.put(
            PATH, json={**BODY, "connection_id": "protocol-service", "connection_revision": 1}
        )
        assert model.status_code == (200 if provider == "gpt56-relay" else 422)
        body.pop("base_url")
        disabled = await client.put(
            PREFIX + "/connections/protocol-service",
            json={**body, "expected_revision": 1, "enabled": False},
        )
        assert disabled.status_code == 200
        assert disabled.json()["revision"] == 2 and not disabled.json()["ready_for_planning"]
        async with factory() as session:
            with pytest.raises(WorkbenchAPIError):
                await resolve_connection_environment(
                    session, "protocol-service", 1, relay_environment(), configured
                )


@pytest.mark.integration
async def test_missing_vault_fails_closed_and_rollback_discards_new_secret(
    database_url: str,
    configured: CredentialVault,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from harnesslab.registry.connections import CredentialWrite, save_credential

    async with isolated_registry_database(database_url) as factory:
        async with factory() as session:

            async def failed_commit() -> None:
                raise RuntimeError("test database write failure")

            monkeypatch.setattr(session, "commit", failed_commit)
            with pytest.raises(RuntimeError, match="test database write failure"):
                await save_credential(
                    session, "test-key", CredentialWrite.model_validate(KEY_BODY), configured
                )
        assert configured.root is not None
        assert list(configured.root.iterdir()) == []
        monkeypatch.delenv("HARNESSLAB_CREDENTIAL_STORE")
        async with local_client(factory) as client:
            result = await client.put(PREFIX + "/credentials/test-key", json=KEY_BODY)
            assert result.status_code == 503 and KEY not in result.text
