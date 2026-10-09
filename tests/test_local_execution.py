from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from harnesslab.db.models.execution_lease import ExecutionLease
from harnesslab.db.models.local_execution import (
    LocalExecutionAttemptRecord,
    LocalExecutionAuthorizationRecord,
    LocalExecutionResultRecord,
)
from harnesslab.local_execution.worker import LocalWorker
from harnesslab.registry.models import canonical_digest
from tests.test_local_model_configuration import local_client
from tests.test_local_plans import checked, confirmation, ingest
from tests.test_local_plans import configured as configured
from tests.test_registry_lite import isolated_registry_database

PREFIX = "/api/local-execution/plans/"


@pytest.fixture
def execution_policy(configured: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch) -> Path:
    root = configured[0].parent
    admission = json.loads(configured[0].read_text())["admissions"][0]
    path = root / "execution.json"
    path.write_text(
        json.dumps(
            {
                "artifact_root": str(root / "worker/artifacts"),
                "runtime_root": str(root / "worker/runtime"),
                "subject_image_identity": "sha256:" + "a" * 64,
                "verifier_image_identity": "sha256:" + "b" * 64,
                "fixture_task_identities": [admission["task_identity"]],
                "lease_seconds": 5,
            }
        )
    )
    path.chmod(0o600)
    monkeypatch.setenv("HARNESSLAB_LOCAL_EXECUTION_POLICY", str(path))
    return path


async def save_plan(client: AsyncClient) -> dict[str, Any]:
    await ingest(client)
    receipt = await checked(client)
    response = await client.post("/api/local-plans/plans", json=confirmation(receipt))
    assert response.status_code == 200, response.text
    return cast(dict[str, Any], response.json())


def authorization(plan: dict[str, Any]) -> dict[str, Any]:
    material = plan["preflight"]["material"]
    return {
        "plan_digest": plan["plan_digest"],
        "run_slot_digest": canonical_digest(material["custom_plan"]["run_slots"][0]),
        "idempotency_key": str(uuid4()),
        "mode": "FAKE_CODEX",
        "confirmed_budget": material["request"]["budget"],
        "max_model_cost_usd": 0,
        "confirm_one_attempt": True,
        "acknowledge_reference_budgets": True,
    }


@pytest.mark.integration
async def test_separate_authorization_idempotence_concurrent_claim_cancel_and_restart(
    database_url: str, execution_policy: Path
) -> None:
    async with isolated_registry_database(database_url) as factory:
        async with local_client(factory) as client:
            plan = await save_plan(client)
            url = PREFIX + plan["plan_id"]
            assert (await client.get(url)).json()["status"] == "NOT_AUTHORIZED"
            worker1, worker2 = LocalWorker(factory), LocalWorker(factory)
            assert await worker1.claim() is None
            body = authorization(plan)
            responses = await asyncio.gather(
                *[client.post(url + "/authorize", json=body) for _ in range(3)]
            )
            assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
            assert responses[0].json() == responses[1].json() == responses[2].json()
            assert responses[0].json()["status"] == "QUEUED"
            claims = await asyncio.gather(worker1.claim(), worker2.claim())
            assert sum(c is not None for c in claims) == 1
            cancelled = await client.post(url + "/cancel", json={"action": "CANCEL"})
            assert (
                cancelled.status_code == 200
                and cancelled.json()["attempt"]["cancellation_requested"]
            )
            assert cancelled.json()["status"] == "CLAIMED"  # cleanup not yet acknowledged
        async with local_client(factory) as restarted:
            state = (await restarted.get(url)).json()
            assert state["attempt"]["attempt_number"] == 1
        async with factory() as session:
            assert (
                await session.scalar(select(func.count()).select_from(LocalExecutionAttemptRecord))
                == 1
            )
            assert (
                await session.scalar(
                    select(func.count()).select_from(LocalExecutionAuthorizationRecord)
                )
                == 1
            )


@pytest.mark.integration
@pytest.mark.parametrize(
    "mutation,status",
    [
        ({"mode": "REAL_CODEX"}, 403),
        ({"confirm_one_attempt": False}, 422),
        ({"acknowledge_reference_budgets": False}, 422),
        ({"max_model_cost_usd": 1}, 422),
        ({"confirmed_budget": None}, 422),
        ({"plan_digest": "sha256:" + "f" * 64}, 409),
        ({"run_slot_digest": "sha256:" + "f" * 64}, 409),
    ],
)
async def test_rejects_unauthorized_cost_and_identity_without_attempt(
    database_url: str, execution_policy: Path, mutation: dict[str, Any], status: int
) -> None:
    async with isolated_registry_database(database_url) as factory:
        async with local_client(factory) as client:
            plan = await save_plan(client)
            r = await client.post(
                PREFIX + plan["plan_id"] + "/authorize", json={**authorization(plan), **mutation}
            )
            assert r.status_code == status, r.text
        async with factory() as session:
            assert (
                await session.scalar(select(func.count()).select_from(LocalExecutionAttemptRecord))
                == 0
            )


@pytest.mark.integration
async def test_drift_blocks_authorization_and_disabled_policy_never_dispatches(
    database_url: str,
    execution_policy: Path,
    configured: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with isolated_registry_database(database_url) as factory, local_client(factory) as client:
        plan = await save_plan(client)
        (configured[1] / "workspace/answer.py").write_text("ANSWER = 1\n")
        r = await client.post(PREFIX + plan["plan_id"] + "/authorize", json=authorization(plan))
        assert r.status_code == 409 and r.json()["error"]["code"] == "PLAN_STALE"
        monkeypatch.delenv("HARNESSLAB_LOCAL_EXECUTION_POLICY")
        assert (
            await client.post(PREFIX + plan["plan_id"] + "/authorize", json=authorization(plan))
        ).status_code == 403
        assert (await client.get(PREFIX + plan["plan_id"])).json()["status"] == "NOT_AUTHORIZED"


@pytest.mark.integration
@pytest.mark.parametrize(
    "headers",
    [
        {"Authorization": "Bearer wrong"},
        {"Origin": "https://public.invalid"},
        {"Host": "public.invalid"},
        {"Sec-Fetch-Site": "cross-site"},
    ],
)
async def test_permission_isolation(
    database_url: str, execution_policy: Path, headers: dict[str, str]
) -> None:
    async with isolated_registry_database(database_url) as factory:
        async with local_client(factory) as client:
            plan = await save_plan(client)
            response = await client.post(
                PREFIX + plan["plan_id"] + "/authorize", json=authorization(plan), headers=headers
            )
            assert response.status_code == 403
        async with factory() as session:
            assert (
                await session.scalar(select(func.count()).select_from(LocalExecutionAttemptRecord))
                == 0
            )


@pytest.mark.integration
async def test_lost_claim_is_terminal_no_redispatch(
    database_url: str, execution_policy: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async with isolated_registry_database(database_url) as factory:
        async with local_client(factory) as client:
            plan = await save_plan(client)
            url = PREFIX + plan["plan_id"]
            await client.post(url + "/authorize", json=authorization(plan))
            worker = LocalWorker(factory)
            run_id = await worker.claim()
            assert run_id
            async with factory() as session, session.begin():
                lease = await session.get(ExecutionLease, run_id)
                assert lease
                lease.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)

            async def no_containers(_run: str) -> None:
                pass

            monkeypatch.setattr(worker, "_cleanup_abandoned", no_containers)
            assert await worker.recover() == 1
            assert await worker.claim() is None
            state = (await client.get(url)).json()
            assert (
                state["status"] == "INTERRUPTED" and state["result"]["acceptance"] == "NOT_VERIFIED"
            )
            assert await worker.recover() == 0
            assert (await client.post(url + "/authorize", json=authorization(plan))).json()[
                "status"
            ] == "INTERRUPTED"
        async with factory() as session:
            assert (
                await session.scalar(select(func.count()).select_from(LocalExecutionResultRecord))
                == 1
            )


@pytest.mark.integration
async def test_expired_authorization_rejected_before_backend(
    database_url: str, execution_policy: Path
) -> None:
    async with isolated_registry_database(database_url) as factory:
        policy = json.loads(execution_policy.read_text())
        policy["authorization_ttl_seconds"] = 1
        execution_policy.write_text(json.dumps(policy))
        async with local_client(factory) as client:
            plan = await save_plan(client)
            url = PREFIX + plan["plan_id"]
            await client.post(url + "/authorize", json=authorization(plan))
            worker = LocalWorker(factory)
            run_id = await worker.claim()
            assert run_id
            await asyncio.sleep(1.05)
            await worker.execute(run_id)
            result = (await client.get(url)).json()
            assert (
                result["status"] == "BLOCKED"
                and result["result"]["reason_code"] == "EXECUTION_AUTHORIZATION_STALE"
            )


@pytest.mark.integration
@pytest.mark.parametrize("drift", ["operator", "execution_policy", "budget", "image", "task"])
async def test_worker_rechecks_frozen_authorization_before_any_subject(
    database_url: str,
    execution_policy: Path,
    configured: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    drift: str,
) -> None:
    from harnesslab.local_execution import service as execution
    from harnesslab.local_execution.policy import load_execution_policy

    async with isolated_registry_database(database_url) as factory:
        async with local_client(factory) as client:
            plan = await save_plan(client)
            body = authorization(plan)
            if drift == "budget":
                body["confirmed_budget"]["wall_time_seconds"] = 1
                response = await client.post(PREFIX + plan["plan_id"] + "/authorize", json=body)
                assert response.status_code == 409
                return
            response = await client.post(PREFIX + plan["plan_id"] + "/authorize", json=body)
            assert response.status_code == 200
        worker = LocalWorker(factory)
        run_id = await worker.claim()
        assert run_id
        if drift == "operator":
            monkeypatch.setenv(
                "HARNESSLAB_LOCAL_CONFIGURATION_TOKEN",
                "rotated-local-operator-placeholder-1234567890",
            )
        elif drift == "execution_policy":
            policy = load_execution_policy().model_dump(mode="json")
            policy["scenario"] = "wrong_workspace"
            execution_policy.write_text(json.dumps(policy))
        elif drift == "task":
            (configured[1] / "workspace/answer.py").write_text("ANSWER = 2\n")
        elif drift == "image":
            monkeypatch.setattr(
                "harnesslab.local_execution.worker.local_image_identity",
                lambda _ref: "sha256:" + "f" * 64,
            )
        # Process/HTTP sentinels from configured remain active for this entire test.
        await worker.execute(run_id)
        async with factory() as session:
            state = await execution.view(session, plan["plan_id"])
            assert state["status"] == "BLOCKED" and state["result"]["episode"] is None
            assert state["result"]["model_calls"] == 0


@pytest.mark.integration
async def test_migrated_immutable_ledger_trigger_rejects_history_updates(
    database_url: str, execution_policy: Path
) -> None:
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    async with isolated_registry_database(database_url) as factory:
        async with local_client(factory) as client:
            plan = await save_plan(client)
            response = await client.post(
                PREFIX + plan["plan_id"] + "/authorize", json=authorization(plan)
            )
            run_id = response.json()["attempt"]["run_id"]
        schema = factory.kw["bind"].get_execution_options()["schema_translate_map"][None]
        # Reuse the function installed by actual Alembic migrations in this disposable DB.
        async with factory() as session, session.begin():
            for name in (
                "local_execution_authorization",
                "local_execution_attempt",
                "local_execution_result",
            ):
                await session.execute(
                    text(
                        f"CREATE TRIGGER immutable_document BEFORE UPDATE OR DELETE "
                        f'ON "{schema}".{name} FOR EACH ROW '
                        "EXECUTE FUNCTION public.local_plan_immutable()"
                    )
                )
        for name, key, value in [
            ("local_execution_attempt", "run_id", run_id),
            ("local_execution_authorization", "plan_id", plan["plan_id"]),
        ]:
            async with factory() as session:
                with pytest.raises(DBAPIError):
                    await session.execute(
                        text(
                            f'UPDATE "{schema}".{name} SET plan_id = plan_id WHERE {key} = :value'
                        ),
                        {"value": value},
                    )
                await session.rollback()
