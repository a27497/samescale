"""Real keyless Docker E2E: not a fabricated result JSON or a live model campaign."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, cast

import pytest
from httpx import AsyncClient, AsyncHTTPTransport, HTTPTransport

from harnesslab.db.models.execution_lease import ExecutionLease
from harnesslab.harness_lane.fake import PRIVATE_REASONING_SENTINEL
from harnesslab.local_execution.worker import LocalWorker
from tests.local_execution_helpers import prepare_execution_fixture
from tests.local_plan_helpers import TOKEN
from tests.test_local_execution import PREFIX, authorization
from tests.test_local_model_configuration import local_client
from tests.test_registry_lite import isolated_registry_database


@pytest.fixture
async def docker_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, Path]:
    policy, execution, package = await prepare_execution_fixture(tmp_path)
    monkeypatch.setenv("HARNESSLAB_LOCAL_TASK_POLICY", str(policy))
    monkeypatch.setenv("HARNESSLAB_LOCAL_EXECUTION_POLICY", str(execution))
    monkeypatch.setenv("HARNESSLAB_LOCAL_CONFIGURATION_TOKEN", TOKEN)
    monkeypatch.setenv("HARNESSLAB_GPT56_RELAY_BASE_URL", "https://phase2.invalid/never-called")
    monkeypatch.setenv("HARNESSLAB_GPT56_RELAY_API_KEY", "phase2-reference-only-no-provider-auth")
    monkeypatch.delenv("HARNESSLAB_PUBLIC_DEMO_MANIFEST", raising=False)

    def forbid(*args: object, **kwargs: object) -> None:
        raise AssertionError("External HTTP/Provider call forbidden")

    async def async_forbid(*args: object, **kwargs: object) -> None:
        forbid()

    monkeypatch.setattr(HTTPTransport, "handle_request", forbid)
    monkeypatch.setattr(AsyncHTTPTransport, "handle_async_request", async_forbid)
    return policy, execution, package


async def plan_for(client: AsyncClient, *, seconds: int = 20) -> dict[str, Any]:
    r = await client.post(
        "/api/local-plans/tasks/import",
        json={"root_id": "trusted", "relative_path": "micro-python-clamp/1.0.2"},
    )
    assert r.status_code == 200, r.text
    r = await client.post(
        "/api/local-plans/preflight",
        json={
            "name": "Isolated Fake engineering attempt",
            "task_reference": "micro-python-clamp@1.0.2",
            "provider_profile_id": "gpt56-relay-gpt56-responses",
            "harness_profile_id": "codex-gpt56-high",
            "budget": {
                "wall_time_seconds": seconds,
                "output_tokens_estimate": 1000,
                "cost_budget_usd": 1,
            },
        },
    )
    assert r.status_code == 200 and r.json()["status"] == "READY_TO_SAVE", r.text
    from tests.test_local_plans import confirmation

    r = await client.post("/api/local-plans/plans", json=confirmation(r.json()))
    assert r.status_code == 200, r.text
    return cast(dict[str, Any], r.json())


@pytest.mark.integration
@pytest.mark.parametrize(
    "scenario,expected,checks",
    [
        ("solve", "VERIFIED_PASS", 3),
        ("wrong_workspace", "VERIFIED_FAIL", 3),
        ("timeout", "TIMEOUT", 0),
        ("verifier_timeout", "TIMEOUT", 0),
    ],
)
async def test_actual_worker_subject_workspace_trace_and_independent_verifier(
    database_url: str,
    docker_fixture: tuple[Path, Path, Path],
    scenario: str,
    expected: str,
    checks: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from harnesslab.sandbox.docker_cli import _DockerCLI

    create_commands: list[tuple[str, ...]] = []
    original_run = _DockerCLI.run

    async def tracked_run(self: _DockerCLI, *args: str, **kwargs: Any) -> Any:
        if args[0] == "create":
            create_commands.append(args)
        return await original_run(self, *args, **kwargs)

    monkeypatch.setattr(_DockerCLI, "run", tracked_run)
    execution = docker_fixture[1]
    policy = json.loads(execution.read_text())
    policy["scenario"] = scenario
    execution.write_text(json.dumps(policy))
    async with isolated_registry_database(database_url) as factory:
        async with local_client(factory) as client:
            plan = await plan_for(client, seconds=1 if scenario == "timeout" else 20)
            url = PREFIX + plan["plan_id"]
            before = (await client.get(url)).json()
            assert before["status"] == "NOT_AUTHORIZED"
            r = await client.post(url + "/authorize", json=authorization(plan))
            assert r.status_code == 200, r.text
            workers = [LocalWorker(factory), LocalWorker(factory)]
            run_ids = await asyncio.gather(*[w.claim() for w in workers])
            assert sum(x is not None for x in run_ids) == 1
            index = next(i for i, x in enumerate(run_ids) if x is not None)
            run_id = run_ids[index]
            assert run_id
            await workers[index].execute(run_id)
            r = await client.get(url)
            assert r.status_code == 200, r.text
            state = r.json()
            assert state["status"] == expected, state
            result = state["result"]
            assert result["model_calls"] == result["model_cost_usd"] == 0
            assert result["episode"]["verifier_check_count"] == checks, result
            assert result["episode"]["source_kind"] == "synthetic"
            assert create_commands
            assert all(
                "--pull" in args and args[args.index("--pull") + 1] == "never"
                for args in create_commands
            )
            bundle = Path(policy["artifact_root"]) / run_id
            assert (bundle / "trace/normalized.json").is_file()
            assert (bundle / "workspace/calculator.py").is_file()
            trace = json.loads((bundle / "trace/normalized.json").read_text())
            assert (
                trace["events"]
                and PRIVATE_REASONING_SENTINEL
                not in (bundle / "native/codex.sanitized.jsonl").read_text()
            )
            if scenario == "solve":
                assert result["episode"]["changed_file_count"] == 1
                assert (bundle / "verifier/stdout.txt").is_file()
            if scenario == "wrong_workspace":
                assert (
                    result["acceptance"] == "RECORDED_FAIL"
                    and result["episode"]["changed_file_count"] == 0
                )
                assert "tests pass" in json.dumps(trace)  # self report was rejected
            assert await workers[index].once() is None  # never redispatch
        async with local_client(factory) as restarted:
            assert (await restarted.get(url)).json() == state
            (bundle / "workspace/calculator.py").write_text("tampered\n")
            corrupt = await restarted.get(url)
            assert (
                corrupt.status_code == 409
                and corrupt.json()["error"]["code"] == "EXECUTION_EVIDENCE_INTEGRITY_ERROR"
            )


@pytest.mark.integration
async def test_active_cancel_stops_container_without_second_dispatch(
    database_url: str, docker_fixture: tuple[Path, Path, Path]
) -> None:
    execution = docker_fixture[1]
    policy = json.loads(execution.read_text())
    policy["scenario"] = "slow"
    execution.write_text(json.dumps(policy))
    async with isolated_registry_database(database_url) as factory, local_client(factory) as client:
        plan = await plan_for(client)
        url = PREFIX + plan["plan_id"]
        await client.post(url + "/authorize", json=authorization(plan))
        worker = LocalWorker(factory)
        run_id = await worker.claim()
        assert run_id
        task = asyncio.create_task(worker.execute(run_id))
        for _ in range(40):
            async with factory() as session:
                lease = await session.get(ExecutionLease, run_id)
                if lease and lease.status == "RUNNING":
                    break
            await asyncio.sleep(0.1)
        await asyncio.sleep(0.8)
        response = await client.post(url + "/cancel", json={"action": "CANCEL"})
        assert response.json()["attempt"]["cancellation_requested"]
        await task
        result = (await client.get(url)).json()
        assert result["status"] == "CANCELLED" and result["result"]["acceptance"] == "NOT_VERIFIED"
        assert await worker.once() is None


@pytest.mark.integration
@pytest.mark.parametrize(
    "point", ["after_claim", "during_subject", "after_seal", "after_seal_tampered"]
)
async def test_actual_process_crash_preserves_or_recovers_without_execution_retry(
    database_url: str, docker_fixture: tuple[Path, Path, Path], point: str
) -> None:
    import os
    import sys
    from datetime import UTC, datetime, timedelta

    execution = docker_fixture[1]
    policy = json.loads(execution.read_text())
    if point == "during_subject":
        policy["scenario"] = "slow"
        execution.write_text(json.dumps(policy))
    if point == "after_seal_tampered":
        policy["scenario"] = "wrong_workspace"
        execution.write_text(json.dumps(policy))
    async with isolated_registry_database(database_url) as factory, local_client(factory) as client:
        plan = await plan_for(client)
        url = PREFIX + plan["plan_id"]
        response = await client.post(url + "/authorize", json=authorization(plan))
        run_id = response.json()["attempt"]["run_id"]
        schema = factory.kw["bind"].get_execution_options()["schema_translate_map"][None]
        script = """
import asyncio, os
from harnesslab.core.config import Settings
from harnesslab.db.session import create_engine, create_session_factory
from harnesslab.local_execution.worker import LocalWorker
async def run():
    engine=create_engine(Settings.without_dotenv(database_url=os.environ['DATABASE_URL'])).execution_options(schema_translate_map={None:os.environ['PHASE2_TEST_SCHEMA']})
    worker=LocalWorker(create_session_factory(engine))
    run_id=await worker.claim()
    if os.environ['PHASE2_CRASH_POINT']=='after_claim': os._exit(23)
    if os.environ['PHASE2_CRASH_POINT'].startswith('after_seal'):
        async def crash(*args): os._exit(23)
        worker._store=crash
    await worker.execute(run_id)
asyncio.run(run())
"""
        environment = {
            **os.environ,
            "DATABASE_URL": database_url,
            "PHASE2_TEST_SCHEMA": schema,
            "PHASE2_CRASH_POINT": point,
        }
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            script,
            env=environment,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
        if point == "during_subject":
            # Wait for a real subject container to start before killing its Worker.
            from harnesslab.sandbox.docker_cli import _DockerCLI

            cli = _DockerCLI()
            for _ in range(60):
                inspected = await cli.run(
                    "inspect",
                    "harnesslab-local-" + run_id,
                    "--format",
                    "{{.State.Running}}",
                    check=False,
                )
                if inspected.returncode == 0 and inspected.stdout.strip() == b"true":
                    break
                await asyncio.sleep(0.1)
            else:
                process.kill()
                await process.wait()
                pytest.fail("No actual subject started before the crash check")
            process.kill()
        await asyncio.wait_for(process.wait(), timeout=40)
        assert process.returncode != 0
        if point == "after_seal_tampered":
            from harnesslab.registry.models import canonical_digest

            sealed = Path(policy["artifact_root"]) / (run_id + ".result.json")
            forged = json.loads(sealed.read_text())
            assert forged["status"] == "VERIFIED_FAIL"
            forged["status"] = "VERIFIED_PASS"
            forged["acceptance"] = "RECORDED_PASS"
            forged["digest"] = canonical_digest({k: v for k, v in forged.items() if k != "digest"})
            sealed.write_text(json.dumps(forged))
        async with factory() as session, session.begin():
            lease = await session.get(ExecutionLease, run_id)
            assert lease
            lease.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        worker = LocalWorker(factory)
        assert await worker.recover() == 1
        result = (await client.get(url)).json()
        expected = (
            "VERIFIED_PASS"
            if point == "after_seal"
            else "FAILED_INFRA"
            if point == "after_seal_tampered"
            else "INTERRUPTED"
        )
        assert result["status"] == expected, result
        if point == "after_seal":
            assert result["result"]["episode"]["verifier_check_count"] > 0
            assert result["result"]["episode"]["changed_file_count"] == 1
        else:
            assert result["result"]["acceptance"] == "NOT_VERIFIED"
        assert await worker.once() is None and await worker.recover() == 0
