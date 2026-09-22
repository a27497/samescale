from __future__ import annotations

import hashlib
import json
import socket
from pathlib import Path

import httpx
import pytest
from typer.testing import CliRunner

from harnesslab.cli import app
from harnesslab.productization.assets import AssetError, validate_bundle
from harnesslab.productization.demo import create_demo_app


def bundle(root: Path) -> Path:
    root.mkdir()
    (root / "index.html").write_text('<div id="app"></div><script src="/app.js"></script>')
    (root / "app.js").write_text('document.querySelector("#app").textContent="SameScale"')
    files = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}
    (root / "samescale-build.json").write_text(json.dumps({"files": files}))
    return root


@pytest.mark.asyncio
async def test_demo_is_keyless_without_database_and_rejects_persistent_actions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("DATABASE_URL=invalid\nHARNESSLAB_ANALYST_REAL_ENABLED=1\n")
    monkeypatch.setenv("HARNESSLAB_ANALYST_REAL_ENABLED", "1")
    monkeypatch.setenv("HARNESSLAB_GPT56_RELAY_API_KEY", "test-sentinel-never-use")

    def forbidden_connect(*args: object, **kwargs: object) -> None:
        pytest.fail("The standalone demo must not contact a database or provider")

    monkeypatch.setattr(socket.socket, "connect", forbidden_connect)
    application = create_demo_app(bundle(tmp_path / "dist"))
    async with (
        application.router.lifespan_context(application),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=application), base_url="http://test"
        ) as client,
    ):
        assert (await client.get("/api/demo/health")).json()["mode"] == "demo"
        assert (await client.get("/api/product")).json() == {
            "mode": "demo",
            "persistence": "none",
            "health_path": "/api/demo/health",
        }
        result = await client.post("/api/workbench/analyst/examples/offline")
        assert result.status_code == 200
        assert result.json()["kind"] == "offline_fake"
        assert result.json()["metadata"]["provider_requests"] == 0
        assert (await client.get("/api/workbench/analyst/examples/historical")).json()[
            "kind"
        ] == "historical_real"
        assert (await client.get("/api/workbench/analyst/examples/comparison")).json()[
            "kind"
        ] == "historical_comparison"
        for resource in ("models", "providers", "harnesses", "capabilities", "settings"):
            response = await client.get(f"/api/registry/{resource}")
            assert response.status_code == 200
            assert "test-sentinel-never-use" not in response.text
        settings = (await client.get("/api/registry/settings")).json()
        credential = next(
            item
            for item in settings["credentials"]
            if item["credential_ref"] == "HARNESSLAB_GPT56_RELAY_API_KEY"
        )
        assert credential["status"] == "SET"
        for path in [
            "/api/workbench/analyst/sessions",
            "/api/workbench/analyst/sessions/id/resume",
            "/api/experiments/snapshot",
            "/api/experiments/preflight",
        ]:
            response = await client.post(path, json={})
            assert response.status_code == 503
            assert response.json()["code"] == "FULL_WORKSPACE_REQUIRED"
        # Database health must not falsely pass just because the demo is healthy.
        assert (await client.get("/api/health")).status_code == 503
        assert (await client.get("/analyst/sessions")).status_code == 200
        assert (await client.get("/missing.js")).status_code == 404


@pytest.mark.asyncio
async def test_demo_readiness_detects_deleted_or_modified_assets(tmp_path: Path) -> None:
    dist = bundle(tmp_path / "dist")
    application = create_demo_app(dist)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=application), base_url="http://test"
    ) as client:
        (dist / "app.js").write_text("corrupted")
        assert (await client.get("/api/demo/health")).status_code == 503
        with pytest.raises(AssetError):
            validate_bundle(dist)
        (dist / "app.js").unlink()
        assert (await client.get("/api/demo/health")).status_code == 503


def test_demo_port_collision_reports_actionable_error_without_starting_server() -> None:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        result = CliRunner().invoke(app, ["demo", "--port", str(port)])
        assert result.exit_code == 2
        assert "--port" in result.stdout
        assert "Ready:" not in result.stdout
        # The original socket is still owned and usable.
        listener.listen()


def test_demo_diagnostics_do_not_require_docker(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[int, bool]] = []

    def check(port: int, *, inspect_assets: bool = False) -> None:
        calls.append((port, inspect_assets))

    monkeypatch.setattr("harnesslab.cli.check_demo", check)
    monkeypatch.setattr("harnesslab.productization.cli.check_demo", check)
    runner = CliRunner()
    assert runner.invoke(app, ["doctor", "--demo", "--port", "8765"]).exit_code == 0
    assert runner.invoke(app, ["status", "--demo", "--port", "8765"]).exit_code == 0
    assert calls == [(8765, True), (8765, False)]


def test_build_failure_is_operational_and_does_not_start_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from harnesslab.productization.assets import AssetBuildError

    def fail(**kwargs: object) -> Path:
        raise AssetBuildError("UI build failed; correct prerequisites and retry.")

    monkeypatch.setattr("harnesslab.productization.demo.demo_bundle", fail)
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    result = CliRunner().invoke(app, ["demo", "--port", str(port)])
    assert result.exit_code == 1
    assert "retry" in result.stdout and "Ready:" not in result.stdout
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", port))
