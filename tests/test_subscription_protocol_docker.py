"""No-provider acceptance: frozen executable, protocol double, existing queue and verifier."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, cast

import pytest

from harnesslab.local_execution.worker import LocalWorker
from harnesslab.local_plans.service import local_image_identity
from tests.test_local_execution import PREFIX, authorization
from tests.test_local_execution_docker import docker_fixture as docker_fixture
from tests.test_local_execution_docker import plan_for
from tests.test_local_model_configuration import local_client
from tests.test_registry_lite import isolated_registry_database


def protocol_policy(
    execution: Path, *, scenario: str = "solve", requests: int = 2, seconds: int = 20
) -> dict[str, Any]:
    policy = json.loads(execution.read_text())
    policy.update(
        {
            "protocol_stub": True,
            "protocol_scenario": scenario,
            "protocol_limits": {"wall_time_seconds": seconds, "max_requests": requests},
            "subject_image_identity": local_image_identity("harnesslab-phase-e-codex:0.149.0"),
        }
    )
    execution.write_text(json.dumps(policy))
    return cast(dict[str, Any], policy)


@pytest.mark.integration
@pytest.mark.parametrize(
    "scenario,requests,expected",
    [
        ("solve", 2, "VERIFIED_PASS"),
        ("solve", 1, "FAILED_INFRA"),
        ("auth_expired", 2, "FAILED_INFRA"),
        ("quota_exhausted", 2, "FAILED_INFRA"),
        ("upstream_failure", 2, "FAILED_INFRA"),
        ("hang", 2, "TIMEOUT"),
    ],
)
async def test_offline_protocol_worker_and_isolated_verifier(
    database_url: str,
    docker_fixture: tuple[Path, Path, Path],
    scenario: str,
    requests: int,
    expected: str,
) -> None:
    policy = protocol_policy(
        docker_fixture[1],
        scenario=scenario,
        requests=requests,
        seconds=3 if scenario == "hang" else 20,
    )
    async with isolated_registry_database(database_url) as factory, local_client(factory) as client:
        plan = await plan_for(client)
        url = PREFIX + plan["plan_id"]
        body = {**authorization(plan), "subscription_limits": policy["protocol_limits"]}
        auth = await client.post(url + "/authorize", json=body)
        assert auth.status_code == 200, auth.text
        assert (await client.post(url + "/authorize", json=body)).json() == auth.json()
        run_id = auth.json()["attempt"]["run_id"]
        worker = LocalWorker(factory)
        assert await worker.once() == run_id
        observed = await client.get(url)
        assert observed.status_code == 200, observed.text
        result = observed.json()["result"]
        receipt_path = Path(policy["artifact_root"]) / (run_id + ".protocol.json")
        assert receipt_path.is_file(), result
        receipt = json.loads(receipt_path.read_text())
        assert observed.json()["status"] == expected, (result, receipt)
        assert receipt["requests_received"] == (2 if scenario == "solve" else 1)
        assert receipt["requests_consumed"] <= requests
        assert receipt["turns_consumed"] <= 1
        assert receipt["automatic_retries"] == receipt["real_model_requests"] == 0
        assert receipt["token_usage"] is None
        assert result["model_calls"] == result["model_cost_usd"] == 0
        if expected == "VERIFIED_PASS":
            assert result["episode"]["source_kind"] == "synthetic"
            assert result["episode"]["verifier_check_count"] == 3
            assert result["episode"]["changed_file_count"] == 1
            assert receipt["requests_consumed"] == 2
        for path in Path(policy["artifact_root"]).rglob("*"):
            if path.is_file():
                assert b"offline-controller-canary-" not in path.read_bytes()
        assert await worker.once() is None


@pytest.mark.integration
async def test_offline_protocol_active_cancel_no_dispatch_retry(
    database_url: str,
    docker_fixture: tuple[Path, Path, Path],
) -> None:
    from harnesslab.sandbox.docker_cli import _DockerCLI

    policy = protocol_policy(docker_fixture[1], scenario="hang", seconds=20)
    async with isolated_registry_database(database_url) as factory, local_client(factory) as client:
        plan = await plan_for(client)
        url = PREFIX + plan["plan_id"]
        auth = await client.post(
            url + "/authorize",
            json={**authorization(plan), "subscription_limits": policy["protocol_limits"]},
        )
        run_id = auth.json()["attempt"]["run_id"]
        worker = LocalWorker(factory)
        assert await worker.claim() == run_id
        task = asyncio.create_task(worker.execute(run_id))
        cli = _DockerCLI()
        for _ in range(60):
            running = await cli.run(
                "inspect",
                "harnesslab-local-" + run_id,
                "--format",
                "{{.State.Running}}",
                check=False,
            )
            if running.returncode == 0 and running.stdout.strip() == b"true":
                break
            await asyncio.sleep(0.1)
        else:
            task.cancel()
            await task
            pytest.fail("No Subject started before cancellation")
        assert (await client.post(url + "/cancel", json={"action": "CANCEL"})).json()["attempt"][
            "cancellation_requested"
        ]
        await task
        state = (await client.get(url)).json()
        assert state["status"] == "CANCELLED", state
        assert state["result"]["acceptance"] == "NOT_VERIFIED"
        assert await worker.once() is None


@pytest.mark.integration
@pytest.mark.parametrize("point", ["during_subject", "after_seal"])
async def test_offline_protocol_process_crash_recovers_counts_without_redispatch(
    database_url: str,
    docker_fixture: tuple[Path, Path, Path],
    point: str,
) -> None:
    import os
    import sys
    from datetime import UTC, datetime, timedelta

    from harnesslab.db.models.execution_lease import ExecutionLease

    policy = protocol_policy(
        docker_fixture[1], scenario="hang" if point == "during_subject" else "solve"
    )
    async with isolated_registry_database(database_url) as factory, local_client(factory) as client:
        plan = await plan_for(client)
        url = PREFIX + plan["plan_id"]
        auth = await client.post(
            url + "/authorize",
            json={**authorization(plan), "subscription_limits": policy["protocol_limits"]},
        )
        run_id = auth.json()["attempt"]["run_id"]
        schema = factory.kw["bind"].get_execution_options()["schema_translate_map"][None]
        script = """
import asyncio, os
from harnesslab.core.config import Settings
from harnesslab.db.session import create_engine, create_session_factory
from harnesslab.local_execution.worker import LocalWorker
async def run():
    engine=create_engine(Settings.without_dotenv(database_url=os.environ['DATABASE_URL'])).execution_options(schema_translate_map={None:os.environ['PROTOCOL_TEST_SCHEMA']})
    worker=LocalWorker(create_session_factory(engine))
    run_id=await worker.claim()
    if os.environ['PROTOCOL_CRASH_POINT']=='after_seal':
        async def crash(*args): os._exit(23)
        worker._store=crash
    await worker.execute(run_id)
asyncio.run(run())
"""
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            script,
            env={**os.environ, "PROTOCOL_TEST_SCHEMA": schema, "PROTOCOL_CRASH_POINT": point},
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        if point == "during_subject":
            for _ in range(80):
                journal = (
                    Path(policy["runtime_root"])
                    / (run_id + "-controller")
                    / "receipts/controller.json"
                )
                if journal.exists() and json.loads(journal.read_text())["requests_consumed"] == 1:
                    break
                await asyncio.sleep(0.1)
            else:
                process.kill()
                await process.wait()
                pytest.fail("No actual protocol request reached the isolated controller")
            process.kill()
        await asyncio.wait_for(process.wait(), timeout=40)
        assert process.returncode != 0
        async with factory() as session, session.begin():
            lease = await session.get(ExecutionLease, run_id)
            assert lease
            lease.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        worker = LocalWorker(factory)
        assert await worker.recover() == 1
        state = (await client.get(url)).json()
        assert state["status"] == (
            "INTERRUPTED" if point == "during_subject" else "VERIFIED_PASS"
        ), state
        assert state["result"]["offline_protocol"]["receipt"]["requests_consumed"] == (
            1 if point == "during_subject" else 2
        )
        assert await worker.once() is None
        receipt = Path(policy["artifact_root"]) / (run_id + ".protocol.json")
        receipt.write_text(
            receipt.read_text()
            .replace('"requests_consumed": 1', '"requests_consumed": 0')
            .replace('"requests_consumed": 2', '"requests_consumed": 1')
        )
        tampered = await client.get(url)
        assert tampered.status_code == 409, tampered.text
