from __future__ import annotations

import asyncio
import json
import os
import subprocess
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient, AsyncHTTPTransport, HTTPTransport
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from harnesslab.api.app import create_app
from harnesslab.api.workbench_dependencies import workbench_session
from harnesslab.api.workbench_errors import WorkbenchAPIError
from harnesslab.custom_eval.models import canonical_digest
from harnesslab.db.models.experiment import ExperimentRecord, ExperimentRunRecord
from harnesslab.db.models.local_plan import LocalPlanPreflightRecord, LocalTaskPlanRecord
from harnesslab.local_plans import service
from harnesslab.local_plans.models import PlanRequest, PreflightReceipt, SavedPlan
from harnesslab.local_plans.tasks import LocalImport, import_task, inspect_task, load_policy
from tests.local_plan_helpers import HEADERS, TOKEN, prepare_policy, request
from tests.test_local_model_configuration import local_client
from tests.test_registry_lite import isolated_registry_database

PREFIX = "/api/local-plans"


@pytest.fixture
def configured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    policy, package = prepare_policy(tmp_path)
    monkeypatch.setenv("HARNESSLAB_LOCAL_TASK_POLICY", str(policy))
    monkeypatch.setenv("HARNESSLAB_LOCAL_CONFIGURATION_TOKEN", TOKEN)
    monkeypatch.setenv("HARNESSLAB_GPT56_RELAY_BASE_URL", "https://phase1.invalid/fixture")
    monkeypatch.setenv("HARNESSLAB_GPT56_RELAY_API_KEY", "phase1-test-reference-only")
    monkeypatch.delenv("HARNESSLAB_PUBLIC_DEMO_MANIFEST", raising=False)
    monkeypatch.setattr(service, "local_image_identity", lambda _ref: "sha256:" + "a" * 64)

    def forbidden_execution(*args: object, **kwargs: object) -> None:
        raise AssertionError("Phase-1 attempted a process or external HTTP call")

    async def forbidden_http(*args: object, **kwargs: object) -> None:
        forbidden_execution()

    monkeypatch.setattr(subprocess, "run", forbidden_execution)
    monkeypatch.setattr(subprocess, "Popen", forbidden_execution)
    monkeypatch.setattr(HTTPTransport, "handle_request", forbidden_execution)
    monkeypatch.setattr(AsyncHTTPTransport, "handle_async_request", forbidden_http)
    return policy, package


async def ingest(client: AsyncClient) -> dict[str, object]:
    r = await client.post(
        PREFIX + "/tasks/import",
        json={"root_id": "trusted", "relative_path": "phase1-fixture/1.0.0"},
    )
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


async def checked(client: AsyncClient) -> dict[str, object]:
    r = await client.post(PREFIX + "/preflight", json=request())
    assert r.status_code == 200 and r.json()["status"] == "READY_TO_SAVE", r.text
    return r.json()  # type: ignore[no-any-return]


def confirmation(receipt: dict[str, object], key: str | None = None) -> dict[str, object]:
    return {
        "receipt_id": receipt["receipt_id"],
        "receipt_digest": receipt["receipt_digest"],
        "idempotency_key": key or str(uuid4()),
        "confirm_plan_only": True,
    }


@pytest.mark.integration
async def test_complete_private_journey_idempotence_restart_and_zero_execution(
    database_url: str, configured: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Phase-1 attempted execution")

    monkeypatch.setattr("harnesslab.tasks.verifier.execute_verifier", forbidden)
    monkeypatch.setattr("harnesslab.tasks.validation.execute_verifier", forbidden)
    async with isolated_registry_database(database_url) as factory:
        async with local_client(factory) as client:
            sources = await client.get(PREFIX + "/sources")
            assert sources.status_code == 200 and str(configured[0].parent) not in sources.text
            task = await ingest(client)
            assert (
                task["eligible_for_planning"]
                and task["behavioral_validation"] == "TRUSTED_PRIOR_RESULT"
            )
            assert "verifier_calls" not in task and task["verifier_executed"] is False
            assert (await client.get(PREFIX + "/configurations")).json()["items"]
            receipt = await checked(client)
            assert (
                PreflightReceipt.model_validate(receipt).receipt_digest == receipt["receipt_digest"]
            )
            payload = confirmation(receipt)
            responses = await asyncio.gather(
                client.post(PREFIX + "/plans", json=payload),
                client.post(PREFIX + "/plans", json=payload),
            )
            assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
            saved = responses[0].json()
            assert SavedPlan.model_validate(saved).plan_digest == saved["plan_digest"]
            assert (
                saved
                == responses[1].json()
                == (await client.post(PREFIX + "/plans", json=payload)).json()
            )
            assert (
                saved["execution_authorized"] is False
                and saved["runs_created"] == saved["episodes_created"] == 0
            )
            custom = saved["preflight"]["material"]["custom_plan"]
            assert len(custom["targets"]) == len(custom["tasks"]) == len(custom["run_slots"]) == 1
            assert "cells" not in custom and custom["repeat_count"] == 1
            assert str(configured[0].parent) not in json.dumps(saved) and TOKEN not in json.dumps(
                saved
            )
            assert saved["preflight"]["material"]["budget_semantics"]["cost_budget_usd"].startswith(
                "REFERENCE_ONLY"
            )
            execute = await client.post(PREFIX + "/plans/" + saved["plan_id"] + "/execute", json={})
            assert (
                execute.status_code == 403
                and execute.json()["error"]["code"] == "PHASE1_EXECUTION_DISABLED"
            )
            other = await checked(client)
            conflict = await client.post(
                PREFIX + "/plans", json=confirmation(other, str(payload["idempotency_key"]))
            )
            assert (
                conflict.status_code == 409
                and conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
            )
        # Fresh FastAPI application/session: PostgreSQL, not an in-process cache.
        async with local_client(factory) as restarted:
            listed = (await restarted.get(PREFIX + "/plans")).json()
            assert listed["total"] == 1
            reread = (await restarted.get(PREFIX + "/plans/" + saved["plan_id"])).json()
            assert (
                reread["plan"] == saved and reread["current_status"] == "UNCHANGED_RECHECK_REQUIRED"
            )
            (configured[1] / "workspace" / "answer.py").write_text("ANSWER = 1\n")
            drifted = (await restarted.get(PREFIX + "/plans/" + saved["plan_id"])).json()
            assert drifted["plan"] == saved and drifted["current_status"] == "STALE"
        async with factory() as session:
            assert await session.scalar(select(func.count()).select_from(LocalTaskPlanRecord)) == 1
            for model in (ExperimentRecord, ExperimentRunRecord):
                assert await session.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.integration
@pytest.mark.parametrize(
    "change",
    [
        "workspace",
        "verifier",
        "provider",
        "credential",
        "image",
        "code",
        "admission",
        "policy",
        "harness-revision",
    ],
)
async def test_drift_invalidates_preflight_without_saving(
    database_url: str, configured: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, change: str
) -> None:
    async with isolated_registry_database(database_url) as factory, local_client(factory) as client:
        await ingest(client)
        if change == "harness-revision":
            body = {
                "name": "Codex custom selection",
                "template_profile_id": "codex-gpt56-high",
                "provider_profile_ids": ["gpt56-relay-gpt56-responses"],
                "expected_revision": 0,
                "enabled": True,
            }
            assert (
                await client.put("/api/local-configuration/harnesses/phase1", json=body)
            ).status_code == 200
            body_request = request()
            body_request["harness_profile_id"] = "local-harness-phase1-v1"
            response = await client.post(PREFIX + "/preflight", json=body_request)
            assert response.json()["status"] == "READY_TO_SAVE", response.text
            receipt = response.json()
            assert (
                await client.put(
                    "/api/local-configuration/harnesses/phase1",
                    json={**body, "expected_revision": 1, "enabled": False},
                )
            ).status_code == 200
        else:
            receipt = await checked(client)
        policy, package = configured
        if change in {"workspace", "verifier"}:
            (package / change / ("answer.py" if change == "workspace" else "verify.py")).write_text(
                "changed\n"
            )
        elif change == "provider":
            monkeypatch.setenv("HARNESSLAB_GPT56_RELAY_BASE_URL", "https://changed.invalid/fixture")
        elif change == "credential":
            monkeypatch.delenv("HARNESSLAB_GPT56_RELAY_API_KEY")
        elif change == "image":
            monkeypatch.setattr(service, "local_image_identity", lambda _r: "sha256:" + "b" * 64)
        elif change == "code":
            monkeypatch.setattr(service, "application_code_identity", lambda: "sha256:" + "c" * 64)
        elif change == "admission":
            (policy.parent / "validation.json").write_text("{}")
        elif change == "policy":
            d = json.loads(policy.read_text())
            d["admissions"] = []
            policy.write_text(json.dumps(d))
        saved = await client.post(PREFIX + "/plans", json=confirmation(receipt))
        assert saved.status_code == 409 and saved.json()["error"]["code"] == "PREFLIGHT_STALE", (
            saved.text
        )
        async with factory() as session:
            assert await session.scalar(select(func.count()).select_from(LocalTaskPlanRecord)) == 0


@pytest.mark.parametrize(
    "path",
    [
        "../phase1-fixture/1.0.0",
        "/etc",
        "phase1-fixture/../1.0.0",
        "phase1-fixture//1.0.0",
        "./phase1-fixture/1.0.0",
        "https://outside.invalid/task",
        "phase1-fixture\\1.0.0",
    ],
)
def test_paths_outside_contract_are_rejected(configured: tuple[Path, Path], path: str) -> None:
    with pytest.raises(WorkbenchAPIError, match=r"approved|canonical|outside"):
        import_task(load_policy(), LocalImport(root_id="trusted", relative_path=path))


@pytest.mark.parametrize(
    "kind",
    ["source-link", "file-link", "fifo", "hardlink", "credentials", "broken-manifest", "oversize"],
)
def test_illegal_task_files_never_execute(configured: tuple[Path, Path], kind: str) -> None:
    policy, package = configured
    if kind == "source-link":
        (package.parent / "link").symlink_to(package, target_is_directory=True)
        relative = "phase1-fixture/link"
    else:
        relative = "phase1-fixture/1.0.0"
        target = package / "workspace" / "unsafe"
        if kind == "file-link":
            target.symlink_to(policy)
        elif kind == "fifo":
            import os

            os.mkfifo(target)
        elif kind == "hardlink":
            import os

            os.link(policy, target)
        elif kind == "credentials":
            (package / ".env").write_text("test sentinel")
        elif kind == "broken-manifest":
            (package / "task.yaml").write_text("schema_version: 1\nid: ../invalid\n")
        elif kind == "oversize":
            with target.open("wb") as f:
                f.truncate(8_000_001)
    with pytest.raises((ValueError, WorkbenchAPIError)):
        import_task(load_policy(), LocalImport(root_id="trusted", relative_path=relative))


@pytest.mark.integration
@pytest.mark.parametrize(
    "case",
    [
        "budget-missing",
        "image-missing",
        "image-not-approved",
        "task-missing",
        "unqualified",
        "budget-exceeds-task",
        "wrong-harness",
    ],
)
async def test_blocked_preflight_creates_no_plan_or_valid_receipt(
    database_url: str, configured: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, case: str
) -> None:
    async with isolated_registry_database(database_url) as factory, local_client(factory) as client:
        task = await ingest(client)
        body = request()
        if case == "budget-missing":
            body["budget"] = None
        elif case == "image-missing":
            monkeypatch.setattr(service, "local_image_identity", lambda _r: None)
        elif case == "image-not-approved":
            p = configured[0]
            d = json.loads(p.read_text())
            d["runtime_images"] = {}
            p.write_text(json.dumps(d))
        elif case == "task-missing":
            body["task_reference"] = "missing@1.0.0"
        elif case == "unqualified":
            p = configured[0]
            d = json.loads(p.read_text())
            d["admissions"] = []
            p.write_text(json.dumps(d))
            inspected = (await client.get(PREFIX + "/tasks/" + str(task["reference"]))).json()
            assert (
                inspected["structural_validation"] == "PASS"
                and inspected["behavioral_validation"] == "NOT_VERIFIED"
                and not inspected["eligible_for_planning"]
            )
        elif case == "budget-exceeds-task":
            body["budget"] = {
                "wall_time_seconds": 91,
                "output_tokens_estimate": 1000,
                "cost_budget_usd": 1,
            }
        elif case == "wrong-harness":
            body["harness_profile_id"] = "direct-gpt56"
        response = await client.post(PREFIX + "/preflight", json=body)
        assert response.status_code == 200 and response.json()["status"] == "BLOCKED", response.text
        assert (
            await client.post(PREFIX + "/plans", json=confirmation(response.json()))
        ).status_code == 409
        async with factory() as session:
            for model in (
                LocalTaskPlanRecord,
                LocalPlanPreflightRecord,
                ExperimentRecord,
                ExperimentRunRecord,
            ):
                assert await session.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.parametrize(
    "extra",
    [
        {"budget": {"wall_time_seconds": 90, "output_tokens_estimate": 1000}},
        {
            "budget": {
                "wall_time_seconds": "90",
                "output_tokens_estimate": 1000,
                "cost_budget_usd": 1,
            }
        },
        {"command": "execute"},
        {
            "budget": {
                "wall_time_seconds": 90,
                "output_tokens_estimate": 1000,
                "cost_budget_usd": float("inf"),
            }
        },
    ],
)
def test_plan_schema_is_bounded(extra: dict[str, object]) -> None:
    with pytest.raises(ValueError):
        PlanRequest.model_validate({**request(), **extra})


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/sources"),
        ("GET", "/tasks"),
        ("GET", "/configurations"),
        ("GET", "/plans"),
        ("GET", "/plans/missing"),
        ("POST", "/tasks/import"),
        ("POST", "/preflight"),
        ("POST", "/plans"),
        ("POST", "/plans/missing/execute"),
    ],
)
@pytest.mark.parametrize("boundary", ["no-token", "cross-origin", "public-demo", "remote-host"])
async def test_permission_denial_precedes_database_and_filesystem(
    configured: tuple[Path, Path],
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
    boundary: str,
) -> None:
    app = create_app()

    async def forbidden_session() -> AsyncIterator[AsyncSession]:
        raise AssertionError("unauthorized request touched DB")
        yield

    app.dependency_overrides[workbench_session] = forbidden_session

    def forbidden_policy():  # type: ignore[no-untyped-def]
        raise AssertionError("unauthorized request touched files")

    monkeypatch.setattr("harnesslab.local_plans.api.load_policy", forbidden_policy)
    headers = dict(HEADERS)
    if boundary == "no-token":
        headers.pop("Authorization")
    elif boundary == "cross-origin":
        headers["Origin"] = "https://outside.invalid"
    elif boundary == "public-demo":
        app.state.local_configuration_allowed = False
    elif boundary == "remote-host":
        headers.update({"Host": "outside.invalid", "Origin": "http://outside.invalid"})
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://localhost") as client:
        response = await client.request(
            method, PREFIX + path, headers=headers, json={} if method == "POST" else None
        )
        assert response.status_code == 403 and TOKEN not in response.text


@pytest.mark.integration
async def test_confirmation_expiry_and_corruption_fail_closed(
    database_url: str, configured: tuple[Path, Path]
) -> None:
    async with isolated_registry_database(database_url) as factory, local_client(factory) as client:
        await ingest(client)
        receipt = await checked(client)
        for value in (False, 1, "true", None):
            response = await client.post(
                PREFIX + "/plans", json={**confirmation(receipt), "confirm_plan_only": value}
            )
            assert response.status_code == 422
        assert (
            await client.post(
                PREFIX + "/plans",
                json={**confirmation(receipt), "receipt_digest": "sha256:" + "0" * 64},
            )
        ).status_code == 409
        async with factory() as session:
            row = await session.get(LocalPlanPreflightRecord, str(receipt["receipt_id"]))
            assert row is not None
            d = dict(row.document)
            d["expires_at"] = (
                (datetime.now(UTC) - timedelta(minutes=1)).isoformat().replace("+00:00", "Z")
            )
            d["receipt_digest"] = canonical_digest(
                {k: v for k, v in d.items() if k != "receipt_digest"}
            )
            row.document = d
            row.digest = str(d["receipt_digest"])
            await session.commit()
        expired = await client.post(PREFIX + "/plans", json=confirmation(d))
        assert expired.status_code == 409 and expired.json()["error"]["code"] == "PREFLIGHT_EXPIRED"
        good = await checked(client)
        saved = (await client.post(PREFIX + "/plans", json=confirmation(good))).json()
        async with factory() as session:
            plan = await session.get(LocalTaskPlanRecord, saved["plan_id"])
            assert plan is not None
            doc = dict(plan.document)
            doc["execution_authorized"] = True
            plan.document = doc
            await session.commit()
        assert (await client.get(PREFIX + "/plans/" + saved["plan_id"])).status_code == 409


@pytest.mark.integration
async def test_migrated_tables_reject_updates_and_deletes(database_url: str) -> None:
    from harnesslab.core.config import Settings
    from harnesslab.db.session import create_engine

    engine = create_engine(Settings.without_dotenv(database_url=database_url))
    try:
        async with engine.begin() as connection:
            triggers = await connection.scalar(
                text(
                    "SELECT count(*) FROM pg_trigger "
                    "WHERE tgname='immutable_document' AND NOT tgisinternal"
                )
            )
            assert triggers is not None and triggers >= 2
        for table in ("local_plan_preflight", "local_task_plan"):
            for operation in ("UPDATE", "DELETE"):
                await assert_immutable_row(engine, table, operation)
    finally:
        await engine.dispose()


async def assert_immutable_row(engine: AsyncEngine, table: str, operation: str) -> None:
    # A synthetic row in a rolled-back transaction exercises the physical DB gate.
    async with engine.connect() as connection:
        transaction = await connection.begin()
        preflight_id, plan_id = str(uuid4()), str(uuid4())
        await connection.execute(
            text("INSERT INTO local_plan_preflight(id,digest,document) VALUES (:id,:digest,'{}')"),
            {"id": preflight_id, "digest": "sha256:" + uuid4().hex * 2},
        )
        await connection.execute(
            text(
                "INSERT INTO local_task_plan(id,preflight_id,idempotency_key,digest,document) "
                "VALUES (:id,:preflight_id,:key,:digest,'{}')"
            ),
            {
                "id": plan_id,
                "preflight_id": preflight_id,
                "key": str(uuid4()),
                "digest": "sha256:" + uuid4().hex * 2,
            },
        )
        with pytest.raises(DBAPIError, match="immutable"):
            statement = (
                f"UPDATE {table} SET digest=digest WHERE id=:record_id"
                if operation == "UPDATE"
                else f"DELETE FROM {table} WHERE id=:record_id"
            )
            await connection.execute(
                text(statement),
                {"record_id": plan_id if table == "local_task_plan" else preflight_id},
            )
        await transaction.rollback()


def test_managed_special_file_is_rejected_before_legacy_snapshot_reads(
    configured: tuple[Path, Path],
) -> None:
    policy = load_policy()
    imported = import_task(
        policy, LocalImport(root_id="trusted", relative_path="phase1-fixture/1.0.0")
    )
    os.mkfifo(policy.managed_store / "index" / "blocking.json")
    with pytest.raises(WorkbenchAPIError, match="ordinary files"):
        inspect_task(policy, imported.reference)


def test_shared_writable_policy_cannot_enable_task_ingestion(
    configured: tuple[Path, Path],
) -> None:
    configured[0].chmod(0o666)
    with pytest.raises(WorkbenchAPIError, match="not shared-writable"):
        load_policy()
