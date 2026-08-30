from __future__ import annotations

from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from harnesslab.api.app import create_app


def _bundle(root: Path) -> Path:
    root.mkdir()
    (root / "index.html").write_text("<main>bundled-workbench</main>", encoding="utf-8")
    assets = root / "assets"
    assets.mkdir()
    (assets / "app.js").write_text("window.bundled = true", encoding="utf-8")
    return root


async def test_bundled_workbench_serves_root_assets_and_refresh_routes(tmp_path: Path) -> None:
    application = create_app(workbench_dist=_bundle(tmp_path / "dist"))
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        root = await client.get("/")
        asset = await client.get("/assets/app.js")
        refresh = await client.get("/experiments/example")

    assert root.status_code == 200
    assert "bundled-workbench" in root.text
    assert asset.status_code == 200
    assert asset.text == "window.bundled = true"
    assert refresh.status_code == 200
    assert "bundled-workbench" in refresh.text


async def test_api_routes_remain_authoritative_with_bundle(tmp_path: Path) -> None:
    application = create_app(workbench_dist=_bundle(tmp_path / "dist"))
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.get("/api/not-a-real-route")
        missing_asset = await client.get("/assets/not-built.js")

    assert response.status_code == 404
    assert "bundled-workbench" not in response.text
    assert missing_asset.status_code == 404
    assert "bundled-workbench" not in missing_asset.text


def test_explicit_bundle_must_contain_index(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match=r"containing index\.html"):
        create_app(workbench_dist=tmp_path)


def test_configured_bundle_is_required(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HARNESSLAB_WORKBENCH_DIST", str(tmp_path / "missing"))

    with pytest.raises(RuntimeError, match="HARNESSLAB_WORKBENCH_DIST"):
        create_app()
