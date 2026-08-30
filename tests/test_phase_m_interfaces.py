from __future__ import annotations

import json
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from typer.testing import CliRunner

from harnesslab.api.app import create_app
from harnesslab.cli import app
from harnesslab.preflight import PreflightSpecification, assess_preflight
from tests.test_phase_m_preflight import _budget, _observations, _specification

runner = CliRunner()


def test_cli_lists_preflight_and_budget_interfaces() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "preflight" in result.stdout
    assert "budget" in result.stdout


def test_budget_cli_emits_deterministic_keyless_estimate(tmp_path: Path) -> None:
    manifest = tmp_path / "budget.json"
    manifest.write_text(_budget().model_dump_json(), encoding="utf-8")

    result = runner.invoke(app, ["budget", "estimate", str(manifest)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["expected_subject_calls"] == 1
    assert payload["expected_judge_calls"] == 0
    assert payload["budget_ceiling_status"] == "WITHIN_CEILING"


def test_preflight_cli_emits_exact_status_and_never_calls_provider(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    specification = _specification()
    expected = assess_preflight(specification, _observations())
    manifest = tmp_path / "preflight.json"
    manifest.write_text(specification.model_dump_json(), encoding="utf-8")

    async def fake_run(
        received: PreflightSpecification,
        repository_root: Path,
    ) -> object:
        assert received == specification
        assert repository_root == Path(".")
        return expected

    monkeypatch.setattr("harnesslab.preflight.cli.run_preflight", fake_run)
    result = runner.invoke(app, ["preflight", "run", str(manifest)])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["status"] == "READY"
    assert payload["provider_calls"] == 0
    assert payload["judge_calls"] == 0


def test_invalid_cli_manifest_does_not_echo_rejected_content(tmp_path: Path) -> None:
    secret = "literal-secret-must-not-be-echoed"
    manifest = tmp_path / "invalid.json"
    manifest.write_text(json.dumps({"unexpected": secret}), encoding="utf-8")

    result = runner.invoke(app, ["preflight", "run", str(manifest)])

    assert result.exit_code == 2
    assert "field validation error" in result.stdout
    assert secret not in result.stdout


def test_preflight_cli_injects_private_assignment_file_without_echoing_values(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    specification = _specification()
    expected = assess_preflight(specification, _observations())
    manifest = tmp_path / "preflight.json"
    manifest.write_text(specification.model_dump_json(), encoding="utf-8")
    secret = "literal-private-value"
    secret_file = tmp_path / "operator.env"
    secret_file.write_text(f"PHASE_M_PROVIDER_KEY={secret}\n", encoding="utf-8")
    secret_file.chmod(0o600)

    async def fake_run(
        received: PreflightSpecification,
        repository_root: Path,
        environment: dict[str, str],
    ) -> object:
        assert received == specification
        assert repository_root == Path(".")
        assert environment["PHASE_M_PROVIDER_KEY"] == secret
        return expected

    monkeypatch.setattr("harnesslab.preflight.cli.run_preflight", fake_run)
    result = runner.invoke(
        app,
        ["preflight", "run", str(manifest), "--secret-env-file", str(secret_file)],
    )

    assert result.exit_code == 0
    assert secret not in result.stdout
    assert json.loads(result.stdout)["status"] == "READY"


def test_preflight_cli_rejects_public_or_unexpected_secret_env_source(
    tmp_path: Path,
) -> None:
    manifest = tmp_path / "preflight.json"
    manifest.write_text(_specification().model_dump_json(), encoding="utf-8")
    secret_file = tmp_path / "operator.env"
    secret_file.write_text("UNEXPECTED_REFERENCE=private\n", encoding="utf-8")
    secret_file.chmod(0o644)

    result = runner.invoke(
        app,
        ["preflight", "run", str(manifest), "--secret-env-file", str(secret_file)],
    )

    assert result.exit_code == 2
    assert "private mode" in result.stdout
    assert "private" not in result.stdout.replace("private mode", "")


async def test_preflight_assessment_api_is_pure_and_keyless() -> None:
    specification = _specification()
    payload = specification.model_dump(mode="json")
    payload["observations"] = _observations().model_dump(mode="json")

    async with AsyncClient(
        transport=ASGITransport(app=create_app()),
        base_url="http://test",
    ) as client:
        response = await client.post("/api/preflight/assess", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "READY"
    assert body["provider_calls"] == 0
    assert body["judge_calls"] == 0


async def test_budget_api_preserves_unknown_cost_as_unknown() -> None:
    request = _budget()

    async with AsyncClient(
        transport=ASGITransport(app=create_app()),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/preflight/budget",
            json=request.model_dump(mode="json"),
        )

    assert response.status_code == 200
    assert response.json()["budget_ceiling_status"] == "WITHIN_CEILING"
