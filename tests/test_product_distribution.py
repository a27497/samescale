from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import cast

import yaml

ROOT = Path(__file__).resolve().parents[1]
COMPOSE_PATH = ROOT / "docker-compose.yml"
DOCKERFILE_PATH = ROOT / "docker/product/Dockerfile"
HEALTHCHECK_PATH = ROOT / "docker/product/healthcheck.py"
DIGEST_PATTERN = re.compile(r"@sha256:[0-9a-f]{64}$")


def _mapping(value: object) -> dict[str, object]:
    assert isinstance(value, dict)
    return cast(dict[str, object], value)


def _sequence(value: object) -> list[object]:
    assert isinstance(value, list)
    return cast(list[object], value)


def _compose_services() -> dict[str, object]:
    raw: object = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    return _mapping(_mapping(raw)["services"])


def test_product_images_and_build_dependencies_are_reproducibly_pinned() -> None:
    dockerfile = DOCKERFILE_PATH.read_text(encoding="utf-8")
    from_images = [line.split()[1] for line in dockerfile.splitlines() if line.startswith("FROM ")]

    assert from_images
    assert all(DIGEST_PATTERN.search(image) for image in from_images)
    assert any(image.startswith("node:24.18.1-bookworm-slim@") for image in from_images)
    assert any(image.startswith("ghcr.io/astral-sh/uv:0.12.5@") for image in from_images)
    assert any(image.startswith("python:3.12.14-slim-bookworm@") for image in from_images)
    assert "npm ci --no-audit --no-fund" in dockerfile
    assert "uv sync --locked --no-dev" in dockerfile

    postgres = _mapping(_compose_services()["postgres"])
    postgres_image = postgres["image"]
    assert isinstance(postgres_image, str)
    assert postgres_image.startswith("postgres:18.6@")
    assert DIGEST_PATTERN.search(postgres_image)


def test_wheel_embeds_the_complete_trusted_product_build_context() -> None:
    packaging = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    included = packaging["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]

    assert included["docker-compose.yml"].endswith("distribution/docker-compose.yml")
    assert included["docker/product"].endswith("distribution/docker/product")
    assert included["frontend/src"].endswith("distribution/frontend/src")
    assert included["frontend/package-lock.json"].endswith(
        "distribution/frontend/package-lock.json"
    )
    assert included["src"].endswith("distribution/src")
    assert included["tasks"].endswith("distribution/tasks")
    assert included["uv.lock"].endswith("distribution/uv.lock")


def test_compose_requires_database_health_then_migration_before_api() -> None:
    services = _compose_services()
    migrate = _mapping(services["migrate"])
    api = _mapping(services["api"])

    assert _sequence(migrate["command"]) == ["alembic", "upgrade", "head"]
    migrate_dependencies = _mapping(migrate["depends_on"])
    assert _mapping(migrate_dependencies["postgres"])["condition"] == "service_healthy"
    api_dependencies = _mapping(api["depends_on"])
    assert _mapping(api_dependencies["migrate"])["condition"] == ("service_completed_successfully")


def test_product_ports_and_runtime_privileges_are_bounded() -> None:
    services = _compose_services()
    postgres = _mapping(services["postgres"])
    api = _mapping(services["api"])
    dockerfile = DOCKERFILE_PATH.read_text(encoding="utf-8")

    assert all(str(port).startswith("127.0.0.1:") for port in _sequence(postgres["ports"]))
    assert all(str(port).startswith("127.0.0.1:") for port in _sequence(api["ports"]))
    assert api["read_only"] is True
    assert _sequence(api["cap_drop"]) == ["ALL"]
    assert "no-new-privileges:true" in _sequence(api["security_opt"])
    assert "USER 10001:10001" in dockerfile


def test_bundled_workbench_is_part_of_readiness_and_no_call_credentials_are_wired() -> None:
    services = _compose_services()
    api = _mapping(services["api"])
    environment = _mapping(api["environment"])
    dockerfile = DOCKERFILE_PATH.read_text(encoding="utf-8")
    healthcheck = HEALTHCHECK_PATH.read_text(encoding="utf-8")

    assert environment["HARNESSLAB_WORKBENCH_DIST"] == "/opt/harnesslab/frontend/dist"
    assert environment["HARNESSLAB_CUSTOM_EVAL_STORE"] == "/opt/harnesslab/custom-eval"
    assert "harnesslab-custom-eval:/opt/harnesslab/custom-eval" in _sequence(api["volumes"])
    assert "/opt/harnesslab/custom-eval" in dockerfile
    assert "COPY --from=workbench-build" in dockerfile
    assert '"http://127.0.0.1:8000/api/health"' in healthcheck
    assert '"http://127.0.0.1:8000/"' in healthcheck
    assert 'response.headers.get_content_type() == "text/html"' in healthcheck

    wired_names = {str(name).upper() for name in environment}
    forbidden_markers = ("API_KEY", "TOKEN", "CREDENTIAL", "PROVIDER", "JUDGE")
    assert not any(marker in name for name in wired_names for marker in forbidden_markers)
