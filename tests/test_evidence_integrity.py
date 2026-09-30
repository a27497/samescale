from __future__ import annotations

import hashlib
import json
import shutil
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from harnesslab.api.app import create_app
from harnesslab.api.workbench_dependencies import workbench_artifact_roots, workbench_session
from harnesslab.core.config import Settings
from harnesslab.db.models.experiment import ExperimentRecord, ExperimentRunRecord
from harnesslab.db.session import create_engine, create_session_factory
from harnesslab.demo.fixtures import demo_plan
from harnesslab.demo.integrity import DemoBundle, DemoIntegrityError, load_bundle
from harnesslab.evidence.protection import FrozenEvidenceError, FrozenEvidenceGuard, snapshot_tree
from harnesslab.evidence.reader import load_verified_manifest
from harnesslab.experiment.executor import ExperimentRunExecutor
from harnesslab.experiment.queue import enqueue_plan
from tests.conftest import assert_disposable_database

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("operation", ["write", "delete", "rmtree"])
def test_frozen_evidence_mutation_fails_immediately(tmp_path: Path, operation: str) -> None:
    protected = tmp_path / "frozen"
    protected.mkdir()
    file = protected / "evidence.json"
    file.write_text('"original"')
    before = snapshot_tree(protected)
    guard = FrozenEvidenceGuard((protected,))
    guard.install()
    try:
        with pytest.raises(FrozenEvidenceError, match="mutate"):
            if operation == "write":
                file.write_text('"replacement"')
            elif operation == "delete":
                file.unlink()
            else:
                shutil.rmtree(protected)
        assert snapshot_tree(protected) == before
    finally:
        guard.active = False


@pytest.mark.parametrize("name", ["samescale_qa", "samescale_live", "public_demo", "historical"])
def test_database_cleanup_refuses_evidence_databases(name: str) -> None:
    with pytest.raises(pytest.UsageError, match="protected database"):
        assert_disposable_database(f"postgresql+psycopg://unused@127.0.0.1/{name}", "test")


def test_workbench_builders_have_no_shared_artifact_defaults() -> None:
    import inspect

    from tests.test_workbench_api import _matrix_plan, _multi_task_matrix_plan

    for builder in (_matrix_plan, _multi_task_matrix_plan):
        for parameter in ("artifact_root", "runtime_root"):
            assert (
                inspect.signature(builder).parameters[parameter].default is inspect.Parameter.empty
            )


@pytest_asyncio.fixture
async def demo_evidence(database_url: str, tmp_path: Path) -> AsyncIterator[dict[str, Any]]:
    engine = create_engine(Settings.without_dotenv(database_url=database_url))
    factory = create_session_factory(engine)
    root = tmp_path / "artifacts"
    root.mkdir()
    demo_id = "public-demo-integrity-test"
    plan_digests: dict[str, str] = {}
    try:
        for candidate in (False, True):
            id_ = demo_id + ("-candidate" if candidate else "-baseline")
            plan, bindings = demo_plan(ROOT, id_, root, tmp_path / "runtime", candidate=candidate)
            async with factory() as session, session.begin():
                await enqueue_plan(session, plan)
            await ExperimentRunExecutor(
                repository_root=ROOT,
                session_factory=factory,
                bindings=bindings,
                owner="integrity-test",
            ).run_until_idle(id_)
            plan_digests[id_] = plan.digest
        async with factory() as session:
            records = (
                await session.scalars(
                    select(ExperimentRunRecord).where(
                        ExperimentRunRecord.experiment_id.in_(plan_digests)
                    )
                )
            ).all()
            identities = []
            for record in records:
                verified = load_verified_manifest(record, (root,))
                identities.append(
                    {
                        "run_id": record.run_id,
                        "experiment_id": record.experiment_id,
                        "attempt": record.attempt,
                        "manifest": verified.path.relative_to(root).as_posix(),
                        "digest": record.evidence_digest,
                        "verifier_passed": verified.raw["verifier_passed"],
                    }
                )
        failed = next(
            r["run_id"]
            for r in identities
            if r["experiment_id"].endswith("-baseline") and not r["verifier_passed"]
        )
        bundle = DemoBundle.model_validate(
            {
                "demo_id": demo_id,
                "generated_at": datetime.now(UTC),
                "baseline_id": demo_id + "-baseline",
                "candidate_id": demo_id + "-candidate",
                "failed_run_id": failed,
                "plan_digests": plan_digests,
                "runs": identities,
                "files": snapshot_tree(root),
            }
        )
        path = tmp_path / "public-demo.json"
        path.write_text(bundle.model_dump_json())
        digest = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        app = create_app()

        async def session_override() -> AsyncIterator[Any]:
            async with factory() as session:
                yield session

        app.dependency_overrides[workbench_session] = session_override
        app.dependency_overrides[workbench_artifact_roots] = lambda: (root,)
        yield {
            "app": app,
            "bundle": bundle,
            "path": path,
            "digest": digest,
            "root": root,
            "factory": factory,
        }
    finally:
        async with factory() as session, session.begin():
            await session.execute(
                delete(ExperimentRecord).where(ExperimentRecord.id.in_(plan_digests))
            )
        await engine.dispose()


@pytest.mark.integration
async def test_demo_identity_gate_download_and_read_only_boundary(
    demo_evidence: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    env = demo_evidence
    monkeypatch.setenv("HARNESSLAB_PUBLIC_DEMO_MANIFEST", str(env["path"]))
    monkeypatch.setenv("HARNESSLAB_PUBLIC_DEMO_DIGEST", env["digest"])
    before = snapshot_tree(env["root"])
    async with AsyncClient(
        transport=ASGITransport(app=env["app"]), base_url="http://test"
    ) as client:
        response = await client.get("/api/workbench/public-demo")
        assert response.status_code == 200, response.text
        assert response.json()["provenance"] == "FIXTURE_OFFLINE"
        artifact = await client.get(
            f"/api/workbench/runs/{env['bundle'].failed_run_id}/public-artifact?download=true"
        )
        assert artifact.status_code == 200
        assert artifact.json()["passed"] is False
        assert (
            "sha256:" + hashlib.sha256(artifact.content).hexdigest()
            == artifact.headers["x-evidence-sha256"]
        )
        assert artifact.headers["content-disposition"].startswith("attachment")
        assert (await client.get("/api/workbench/runs/another/public-artifact")).status_code == 404
        assert (await client.post("/api/workbench/analyst/sessions", json={})).status_code == 403
        assert (await client.get("/")).headers["location"] == "/demo"
    assert before == snapshot_tree(env["root"])
    async with env["factory"]() as session, session.begin():
        record = await session.get(ExperimentRunRecord, env["bundle"].failed_run_id)
        assert record is not None
        record.attempt += 1
    async with AsyncClient(
        transport=ASGITransport(app=env["app"]), base_url="http://test"
    ) as client:
        mismatch = await client.get("/api/workbench/public-demo")
        assert mismatch.status_code == 409
        assert mismatch.json()["error"]["code"] == "ARTIFACT_INTEGRITY_ERROR"


@pytest.mark.integration
async def test_missing_mismatch_and_identity_never_fall_back(
    demo_evidence: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    env = demo_evidence
    path = env["path"]
    assert load_bundle(path, env["digest"]).provenance == "FIXTURE_OFFLINE"
    monkeypatch.setenv("HARNESSLAB_PUBLIC_DEMO_MANIFEST", str(path))
    monkeypatch.setenv("HARNESSLAB_PUBLIC_DEMO_DIGEST", env["digest"])
    identity = next(r for r in env["bundle"].runs if not r.verifier_passed)
    target = env["root"] / identity.manifest
    original = target.read_bytes()
    # The independent alternative must never rescue a corrupt/missing selected file.
    alternative = path.parent / "alternative.json"
    alternative.write_bytes(original)
    for payload in (
        None,
        b"{}",
        json.dumps({**json.loads(original), "run_id": "wrong-identity"}).encode(),
    ):
        if payload is None:
            target.unlink()
        else:
            target.write_bytes(payload)
        with pytest.raises(DemoIntegrityError):
            load_bundle(path, env["digest"])
        async with AsyncClient(
            transport=ASGITransport(app=env["app"]), base_url="http://test"
        ) as client:
            response = await client.get(f"/api/workbench/runs/{identity.run_id}")
            assert response.status_code == 409
            assert response.json()["error"]["code"] == "ARTIFACT_INTEGRITY_ERROR"
        target.write_bytes(original)
    assert load_bundle(path, env["digest"])


@pytest.mark.integration
async def test_public_offline_demo_has_no_side_effects_or_external_calls(
    demo_evidence: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    import socket

    import httpx
    from sqlalchemy.ext.asyncio import AsyncSession

    from harnesslab.analyst import api, real_backend
    from harnesslab.db.base import Base

    env = demo_evidence
    monkeypatch.setenv("HARNESSLAB_PUBLIC_DEMO_MANIFEST", str(env["path"]))
    monkeypatch.setenv("HARNESSLAB_PUBLIC_DEMO_DIGEST", env["digest"])

    async def database_inventory() -> str:
        async with env["factory"]() as session:
            result = {}
            for table in Base.metadata.sorted_tables:
                rows = (await session.execute(select(table))).mappings().all()
                result[table.name] = sorted(
                    json.dumps(dict(row), sort_keys=True, default=str) for row in rows
                )
            return json.dumps(result, sort_keys=True)

    protected = (ROOT / "release", ROOT / "docs/evidence", ROOT / "docs/recruiter")
    artifacts_before = snapshot_tree(env["path"].parent)
    protected_before = {str(root): snapshot_tree(root) for root in protected}
    database_before = await database_inventory()
    calls = {"database": 0, "provider": 0, "external": 0}

    def forbidden(kind: str) -> Any:
        def reject(*args: object, **kwargs: object) -> None:
            calls[kind] += 1
            pytest.fail(f"offline Demo attempted {kind} access")

        return reject

    guard = FrozenEvidenceGuard((*protected, env["path"].parent))
    guard.install()
    try:
        with monkeypatch.context() as blocked:
            blocked.setattr(api, "create_engine", forbidden("database"))
            blocked.setattr(AsyncSession, "execute", forbidden("database"))
            blocked.setattr(api, "AnalystSessions", forbidden("database"))
            blocked.setattr(real_backend, "RealAnalystBackend", forbidden("provider"))
            blocked.setattr(real_backend, "adapter_for_profile", forbidden("provider"))
            blocked.setattr(httpx.AsyncHTTPTransport, "handle_async_request", forbidden("external"))
            blocked.setattr(socket.socket, "connect", forbidden("external"))
            blocked.setattr(socket.socket, "connect_ex", forbidden("external"))
            blocked.setattr(socket, "getaddrinfo", forbidden("external"))
            async with AsyncClient(
                transport=ASGITransport(app=env["app"]), base_url="http://test"
            ) as client:
                first = await client.post("/api/workbench/analyst/examples/offline")
                second = await client.post("/api/workbench/analyst/examples/offline")
                assert first.status_code == second.status_code == 200
                assert first.json() == second.json()
                assert first.json()["metadata"] == {
                    "provider_requests": 0,
                    "persistence": "none",
                    "decisions": 2,
                    "tools": 2,
                    "completed_calls": ["query_runs", "inspect_failure"],
                }
    finally:
        guard.active = False
    assert calls == {"database": 0, "provider": 0, "external": 0}
    assert database_before == await database_inventory()
    assert artifacts_before == snapshot_tree(env["path"].parent)
    assert protected_before == {str(root): snapshot_tree(root) for root in protected}


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/api/workbench/analyst/sessions"),
        ("POST", "/api/workbench/analyst/sessions/test/resume"),
        ("PUT", "/api/workbench/analyst/sessions/test/proposal"),
        ("POST", "/api/workbench/analyst/sessions/test/approval"),
        ("DELETE", "/api/workbench/analyst/sessions/test"),
        ("PUT", "/api/workbench/analyst/examples/offline"),
        ("POST", "/api/workbench/analyst/examples/offline/extra"),
        ("POST", "/api/workbench/analyst/examples/historical"),
    ],
)
async def test_public_analyst_mutations_remain_denied(
    method: str, path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HARNESSLAB_PUBLIC_DEMO_MANIFEST", "/unused/public-demo.json")
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.request(method, path, json={})
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "PUBLIC_DEMO_READ_ONLY"


@pytest.mark.integration
@pytest.mark.parametrize("public", [False, True])
async def test_analyst_capabilities_match_server_boundary(
    public: bool, demo_evidence: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    if public:
        monkeypatch.setenv("HARNESSLAB_PUBLIC_DEMO_MANIFEST", str(demo_evidence["path"]))
        monkeypatch.setenv("HARNESSLAB_PUBLIC_DEMO_DIGEST", demo_evidence["digest"])
    else:
        monkeypatch.delenv("HARNESSLAB_PUBLIC_DEMO_MANIFEST", raising=False)
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.get("/api/workbench/analyst/capabilities")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert response.json() == {
            "public_demo_read_only": public,
            "persistent_sessions_allowed": not public,
        }
