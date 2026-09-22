from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from harnesslab.api.app import create_app
from harnesslab.api.routes.health import database_check_dependency
from harnesslab.core.config import get_settings


@pytest.fixture(autouse=True)
def clear_settings_cache() -> Iterator[None]:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.mark.integration
async def test_health_reports_healthy_database(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DATABASE_URL", database_url)
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


async def test_health_reports_unavailable_database_without_secret_leak() -> None:
    application = create_app()

    async def unavailable() -> None:
        raise RuntimeError("password=must-not-leak")

    application.dependency_overrides[database_check_dependency] = lambda: unavailable
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.get("/api/health")

    assert response.status_code == 503
    assert response.json() == {"status": "unhealthy", "database": "unavailable"}
    assert "must-not-leak" not in response.text


@pytest.mark.parametrize("configured", [None, "invalid-secret-sentinel"])
async def test_missing_or_invalid_configuration_is_actionable(
    configured: str | None, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    if configured is not None:
        monkeypatch.setenv("DATABASE_URL", configured)
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        health = await client.get("/api/health")
        assert health.status_code == 503
        assert health.json() == {"status": "unhealthy", "database": "unavailable"}
        for path in (
            "/api/workbench/experiments",
            "/api/workbench/analyst/sessions?experiment_id=test",
        ):
            response = await client.get(path)
            assert response.status_code == 503
            assert response.json()["error"]["code"] == "WORKSPACE_NOT_CONFIGURED"
            assert "samescale up" in response.text
            assert "invalid-secret-sentinel" not in response.text
