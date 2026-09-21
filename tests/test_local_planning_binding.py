"""Planning freezes the same SUBJECT revision and parameters as the role consumer."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from harnesslab.db.models.experiment import ExperimentRecord, ExperimentRunRecord
from harnesslab.db.models.registry import RegistryExperimentSnapshotRecord
from harnesslab.registry.model_bindings import ModelBindingError
from harnesslab.registry.models import ExperimentSnapshot
from harnesslab.registry.service import resolve_frozen_direct_runtime
from harnesslab.registry.vault import CredentialVault
from tests.test_local_connections import configured as configured
from tests.test_local_model_configuration import PATH, local_client
from tests.test_local_model_harness import HARNESS, HARNESS_PATH
from tests.test_model_role_bindings import configure, freeze
from tests.test_registry_lite import builder_request, isolated_registry_database


@pytest.mark.integration
async def test_plan_matches_subject_binding_and_rejects_stale_selection(
    database_url: str, configured: CredentialVault
) -> None:
    async with isolated_registry_database(database_url) as factory:
        async with local_client(factory) as client:
            body = await configure(client, "SUBJECT")
            created = await client.put(HARNESS_PATH, json=HARNESS)
            assert created.status_code == 200, created.text
            profiles = (await client.get("/api/registry/models")).json()["provider_profiles"]
            selected = next(p for p in profiles if p["profile_id"] == "local-my-model-v1")
            # The Registry serialization intentionally omits the default SUBJECT role.
            assert selected.get("purpose", "SUBJECT") == "SUBJECT"
            request = builder_request(
                left_profile=selected["profile_id"],
                left_harness="local-harness-my-runtime-v1",
                right_harness="codex-gpt56-high",
            ).model_dump(mode="json")
            request["comparison_type"] = "END_TO_END_SYSTEM_COMPARISON"
            request["budget"]["max_output_tokens"]["value"] = 800
            preflight = (await client.post("/api/experiments/preflight", json=request)).json()
            assert preflight["status"] in ("READY", "READY_WITH_WARNINGS")
            response = await client.post("/api/experiments/snapshot", json=request)
            assert response.status_code == 200, response.text
            async with factory() as session:
                row = await session.get(
                    RegistryExperimentSnapshotRecord, response.json()["snapshot_id"]
                )
                assert row is not None
                frozen = ExperimentSnapshot.model_validate(row.snapshot_json)
                assert frozen.model_dump(mode="json", by_alias=True) == response.json()
            selection = frozen.provider_selections[0]
            assert selection.provider_profile_id == selected["profile_id"]
            assert selection.provider_profile_identity == selected["profile_identity"]
            assert selection.harness_profile_id == "local-harness-my-runtime-v1"
            runtime = resolve_frozen_direct_runtime(selection, frozen.plan.budget_contract)
            binding = await freeze(factory, configured, "SUBJECT", timeout_seconds=45)
            assert binding.configuration_id == "my-model"
            assert binding.configuration_revision == 1
            assert (binding.connection_id, binding.connection_revision) == ("test-service", 1)
            assert binding.provider_profile_identity == selection.provider_profile_identity
            assert binding.runtime == runtime
            assert runtime.reasoning.max_output_tokens == 800
            assert runtime.reasoning.effort == "high"
            assert runtime.request_timeout_seconds == 45
            assert frozen.plan.cells[0].harness_version
            assert frozen.plan.cells[0].effective_runtime_profile_identity
            assert frozen.plan.cells[0].resource_envelope_identity
            assert frozen.plan.budget_contract.model_dump(mode="json") == request["budget"]
            # An oversized request cannot bypass the UI guard to create a snapshot.
            request["budget"]["max_output_tokens"]["value"] = 1001
            assert (await client.post("/api/experiments/preflight", json=request)).json()[
                "status"
            ] == "BLOCKED"
            assert (await client.post("/api/experiments/snapshot", json=request)).status_code == 422
            request["budget"]["max_output_tokens"]["value"] = 800
            revised = await client.put(PATH, json={**body, "expected_revision": 1})
            assert revised.status_code == 200
            assert (await client.post("/api/experiments/preflight", json=request)).json()[
                "status"
            ] == "BLOCKED"
            assert (await client.post("/api/experiments/snapshot", json=request)).status_code == 422
            with pytest.raises(ModelBindingError, match="stale"):
                await freeze(factory, configured, "SUBJECT", timeout_seconds=45)
            assert (
                await client.get("/api/experiments/snapshots/" + frozen.snapshot_id)
            ).json() == response.json()
        async with factory() as session:
            assert (
                await session.scalar(
                    select(func.count()).select_from(RegistryExperimentSnapshotRecord)
                )
                == 1
            )
            for table in (ExperimentRecord, ExperimentRunRecord):
                assert await session.scalar(select(func.count()).select_from(table)) == 0


@pytest.mark.integration
@pytest.mark.parametrize("purpose", ["ANALYST", "JUDGE"])
async def test_planning_cannot_consume_other_model_roles(
    database_url: str, configured: CredentialVault, purpose: str
) -> None:
    async with isolated_registry_database(database_url) as factory, local_client(factory) as client:
        body = await configure(client, "SUBJECT")
        response = await client.put(PATH, json={**body, "purpose": purpose, "expected_revision": 1})
        assert response.status_code == 200
        request = builder_request(
            left_profile="local-my-model-v2", left_harness="direct-local-my-model-v2"
        ).model_dump(mode="json")
        request["budget"]["max_output_tokens"]["value"] = 800
        assert (await client.post("/api/experiments/preflight", json=request)).json()[
            "status"
        ] == "BLOCKED"
        assert (await client.post("/api/experiments/snapshot", json=request)).status_code == 422
        with pytest.raises(ModelBindingError, match="purpose"):
            await freeze(factory, configured, "SUBJECT", revision=2)
        async with factory() as session:
            assert (
                await session.scalar(
                    select(func.count()).select_from(RegistryExperimentSnapshotRecord)
                )
                == 0
            )
