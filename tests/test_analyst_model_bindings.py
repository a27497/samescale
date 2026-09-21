from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any
from uuid import uuid4

import httpx
import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from harnesslab.analyst import model_bindings as analyst_bindings
from harnesslab.analyst.api_models import AnalystSessionView, AnalystSmokePreflight
from harnesslab.analyst.real_backend import resolve_analyst_profile
from harnesslab.analyst.sessions import AnalystSession, AnalystSessions, CreateInvestigation
from harnesslab.api.workbench_errors import WorkbenchAPIError
from harnesslab.budget.models import AnalystSpendLimits
from harnesslab.db.models.analyst import AnalystSessionRecord
from harnesslab.experiment.plan import build_experiment_plan
from harnesslab.experiment.queue import enqueue_plan
from harnesslab.model_lane.providers import adapter_for_profile
from harnesslab.registry import model_bindings
from harnesslab.registry.model_bindings import ModelPurpose
from harnesslab.registry.vault import CredentialVault
from tests.phase_g_helpers import ROOT, basic_spec
from tests.test_local_connections import KEY, KEY_BODY, PREFIX, URL
from tests.test_local_connections import configured as configured
from tests.test_local_model_configuration import PATH, local_client
from tests.test_model_role_bindings import configure
from tests.test_registry_lite import isolated_registry_database, relay_environment


def limits(**updates: Any) -> AnalystSpendLimits:
    return AnalystSpendLimits.model_validate(
        dict(
            provider_requests=2,
            output_tokens_per_request=800,
            input_bytes_per_request=256000,
            cumulative_tokens=3000000,
            timeout_seconds=30,
            **updates,
        )
    )


@asynccontextmanager
async def setup(
    database_url: str, vault: CredentialVault, *, purpose: ModelPurpose = "ANALYST"
) -> AsyncIterator[
    tuple[AnalystSessions, str, async_sessionmaker[AsyncSession], httpx.AsyncClient, dict[str, Any]]
]:
    async with isolated_registry_database(database_url) as factory, local_client(factory) as client:
        body = await configure(client, purpose)
        experiment = "bound-analyst-" + uuid4().hex[:12]
        spec = basic_spec(repeat_count=1)
        spec = spec.model_copy(
            update={
                "experiment_id": experiment,
                "cells": (spec.cells[0],),
                "paired_comparisons": (),
            }
        )
        async with factory() as session, session.begin():
            await enqueue_plan(session, build_experiment_plan(spec, ROOT))
        service = AnalystSessions(
            factory.kw["bind"],
            repository_root=ROOT,
            artifact_roots=(),
            environment=relay_environment(),
            real_enabled=True,
            local_models_enabled=True,
            vault=vault,
        )
        yield service, experiment, factory, client, body


def request(experiment: str, **updates: Any) -> CreateInvestigation:
    values: dict[str, Any] = dict(
        experiment_id=experiment,
        question="Inspect this evidence.",
        backend="real",
        provider_profile_id="local-my-model-v1",
        spend_limits=limits(),
    )
    values.update(updates)
    return CreateInvestigation(**values)


async def test_local_session_persists_restores_and_reserves_before_bound_invocation(
    database_url: str, configured: CredentialVault, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_resolve = resolve_analyst_profile
    # Synthetic known context metadata for the keyless reservation fixture only.
    monkeypatch.setattr(
        analyst_bindings,
        "resolve_analyst_profile",
        lambda *a, **k: original_resolve(*a, **k).model_copy(
            update={"context_window_tokens": 1000}
        ),
    )
    async with setup(database_url, configured) as (service, experiment, _factory, _, _):
        calls: list[dict[str, Any]] = []
        value = await service.create(request(experiment))
        original = value.model_dump_json()
        assert value.model_binding is not None
        assert KEY not in original and URL not in original
        assert "credential_reference" not in json.dumps(value.public_view())
        AnalystSessionView.model_validate(value.public_view())
        saved = await service.get(value.session_id)
        assert saved.model_dump_json() == original
        restored = AnalystSessions(
            service.engine,
            repository_root=ROOT,
            artifact_roots=(),
            environment=relay_environment(),
            real_enabled=True,
            local_models_enabled=True,
            vault=configured,
        )
        check = await restored.preflight(value.session_id)
        AnalystSmokePreflight.model_validate(check)
        assert check["status"] == "READY", check["reasons"]
        assert check["execution_authorized"] is False
        assert check["model_binding"] == value.public_binding()
        assert not calls
        with pytest.raises(ValueError, match="confirmation"):
            await restored.resume(value.session_id)
        restored.real_enabled = False
        with pytest.raises(ValueError, match="enablement"):
            await restored.resume(value.session_id, confirm_real=True)
        restored.real_enabled = True

        async def handler(http_request: httpx.Request) -> httpx.Response:
            reserved = await service.get(value.session_id)
            assert reserved.usage[-1].status == "RESERVED"
            assert reserved.model_binding == value.model_binding
            payload = json.loads(http_request.content)
            assert payload["max_output_tokens"] == 800
            assert payload["reasoning"]["effort"] == "high"
            assert str(http_request.url) == URL + "/responses"
            calls.append(payload)
            return httpx.Response(
                200,
                json={
                    "id": "bound-decision",
                    "model": "gpt-5.6",
                    "status": "completed",
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps(
                                        {
                                            "decision": {
                                                "kind": "abstain",
                                                "reason": "Insufficient evidence.",
                                            }
                                        }
                                    ),
                                }
                            ],
                        }
                    ],
                    "usage": {"input_tokens": 20, "output_tokens": 20, "total_tokens": 40},
                },
            )

        actual = adapter_for_profile
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
            monkeypatch.setattr(
                model_bindings,
                "adapter_for_profile",
                lambda req, **kw: actual(req, client=http, environment=kw["environment"]),
            )
            result = await restored.resume(value.session_id, confirm_real=True)
        assert result.status == "ABSTAINED"
        assert len(calls) == len(result.usage) == 1
        assert result.model_binding == value.model_binding
        assert (await restored.get(result.session_id)).model_dump_json() == result.model_dump_json()
        assert KEY not in result.model_dump_json() and URL not in result.model_dump_json()
        # Terminal replay is a read, even if configuration later becomes unavailable.
        restored.local_models_enabled = False
        assert await restored.resume(result.session_id) == result


@pytest.mark.parametrize(
    "change", ["new_version", "disabled", "role", "key_rotation", "local_disabled", "missing_key"]
)
async def test_stale_local_binding_blocks_without_rewriting_history(
    database_url: str, configured: CredentialVault, monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    async with setup(database_url, configured) as (service, experiment, _, client, body):
        value = await service.create(request(experiment))
        original = value.model_dump_json()
        monkeypatch.setattr(
            model_bindings,
            "adapter_for_profile",
            lambda *a, **k: pytest.fail("unexpected provider call"),
        )
        if change in {"new_version", "disabled", "role"}:
            updates: dict[str, Any] = {"expected_revision": 1}
            if change == "disabled":
                updates["enabled"] = False
            if change == "role":
                updates["purpose"] = "JUDGE"
            assert (await client.put(PATH, json={**body, **updates})).status_code == 200
        elif change == "key_rotation":
            assert (
                await client.put(
                    PREFIX + "/credentials/test-key",
                    json={**KEY_BODY, "expected_revision": 1, "value": "test-rotated-placeholder"},
                )
            ).status_code == 200
        elif change == "local_disabled":
            service.local_models_enabled = False
        else:
            assert configured.root is not None
            for path in configured.root.iterdir():
                path.unlink()
        preflight = await service.preflight(value.session_id)
        assert preflight["status"] == "BLOCKED"
        assert "PROFILE_DRIFT_OR_UNAVAILABLE" in preflight["reasons"]
        with pytest.raises((ValueError, WorkbenchAPIError)):
            await service.resume(value.session_id, confirm_real=True)
        assert (await service.get(value.session_id)).model_dump_json() == original
        assert (await service.list(experiment))[0].model_dump_json() == original


@pytest.mark.parametrize("purpose", ["SUBJECT", "JUDGE"])
async def test_other_local_roles_cannot_create_analyst_session(
    database_url: str, configured: CredentialVault, purpose: ModelPurpose
) -> None:
    async with setup(database_url, configured, purpose=purpose) as (service, experiment, _, _, _):
        with pytest.raises(ValueError, match="purpose"):
            await service.create(request(experiment))
        assert await service.list(experiment) == ()


async def test_frozen_journal_rejects_binding_and_budget_tampering(
    database_url: str, configured: CredentialVault
) -> None:
    async with setup(database_url, configured) as (service, experiment, factory, _, _):
        value = await service.create(request(experiment))
        mutations: list[Callable[[dict[str, Any]], None]] = [
            lambda d: d["model_binding"].update(purpose="JUDGE"),
            lambda d: d["spend_limits"].update(output_tokens_per_request=900),
            lambda d: d.update(model_binding=None),
        ]
        for mutate in mutations:
            data = value.model_dump(mode="json")
            mutate(data)
            with pytest.raises(ValidationError):
                AnalystSession.model_validate(data)
        for budget in [
            limits().model_copy(update={"output_tokens_per_request": 1001}),
            limits().model_copy(update={"timeout_seconds": 46}),
        ]:
            with pytest.raises(ValueError):
                await service.create(request(experiment, spend_limits=budget))
        with pytest.raises(ValueError):
            await service.create(request(experiment, provider_profile_id="local-my-model-v2"))
        service.local_models_enabled = False
        with pytest.raises(ValueError):
            await service.create(request(experiment))
        async with factory() as session:
            row = await session.get(AnalystSessionRecord, value.session_id)
            assert row is not None and value.model_binding is not None
            assert row.state_json["model_binding"] == value.model_binding.model_dump(mode="json")
