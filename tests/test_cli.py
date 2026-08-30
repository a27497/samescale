from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from harnesslab import __version__
from harnesslab.cli import app
from harnesslab.productization.lifecycle import CheckState, LifecycleCheck

runner = CliRunner()


def test_help_lists_integrated_control_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    for command in (
        "preflight",
        "budget",
        "custom-eval",
        "up",
        "down",
        "status",
        "doctor",
        "serve",
        "model",
        "harness",
    ):
        assert command in result.stdout


def test_version_uses_package_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert result.stdout.strip() == __version__


def test_serve_uses_psycopg_compatible_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_run(application: str, **options: object) -> None:
        captured["application"] = application
        captured.update(options)

    monkeypatch.setattr("harnesslab.cli.uvicorn.run", fake_run)
    result = runner.invoke(app, ["serve", "--port", "8123"])

    assert result.exit_code == 0
    assert captured["application"] == "harnesslab.api.app:app"
    assert captured["port"] == 8123
    assert captured["loop"] == "harnesslab.core.runtime:selector_loop_factory"


def test_doctor_reports_product_not_running_with_distinct_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class NotRunningLifecycle:
        def doctor(self) -> tuple[LifecycleCheck, ...]:
            return (
                LifecycleCheck("docker", CheckState.PASS, "server ready"),
                LifecycleCheck("compose", CheckState.PASS, "configuration valid"),
                LifecycleCheck("postgresql", CheckState.NOT_RUNNING, "run `harnesslab up`"),
                LifecycleCheck("api-health", CheckState.NOT_RUNNING, "services not ready"),
                LifecycleCheck("workbench", CheckState.NOT_RUNNING, "services not ready"),
            )

    monkeypatch.setattr(
        "harnesslab.productization.cli._lifecycle",
        lambda _compose_file, _project_name: NotRunningLifecycle(),
    )
    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 2
    assert "NOT_RUNNING" in result.stdout
    assert "postgresql" in result.stdout
    assert "SECRETS=MASKED" in result.stdout


def test_doctor_reports_pass_for_ready_product(monkeypatch: pytest.MonkeyPatch) -> None:
    class ReadyLifecycle:
        def doctor(self) -> tuple[LifecycleCheck, ...]:
            return (
                LifecycleCheck("docker", CheckState.PASS, "server ready"),
                LifecycleCheck("compose", CheckState.PASS, "configuration valid"),
                LifecycleCheck("postgresql", CheckState.PASS, "running health=healthy"),
                LifecycleCheck("migration", CheckState.PASS, "complete"),
                LifecycleCheck("api-container", CheckState.PASS, "running health=healthy"),
                LifecycleCheck("api-health", CheckState.PASS, "http://127.0.0.1:8000/api/health"),
                LifecycleCheck("workbench", CheckState.PASS, "http://127.0.0.1:8000/"),
                LifecycleCheck("provider-calls", CheckState.PASS, "disabled for lifecycle"),
                LifecycleCheck("judge-calls", CheckState.PASS, "disabled for lifecycle"),
            )

    monkeypatch.setattr(
        "harnesslab.productization.cli._lifecycle",
        lambda _compose_file, _project_name: ReadyLifecycle(),
    )
    result = runner.invoke(app, ["doctor"])

    assert result.exit_code == 0
    assert "api-health" in result.stdout
    assert "workbench" in result.stdout
    assert "provider-calls" in result.stdout
    assert "judge-calls" in result.stdout


def test_model_profile_validate_does_not_read_credential() -> None:
    profile = Path(__file__).resolve().parents[1] / "profiles" / "openai-responses.example.yaml"

    result = runner.invoke(app, ["model", "profile", "validate", str(profile)], env={})

    assert result.exit_code == 0
    assert "PASS provider=openai" in result.stdout
    assert "credential_reference=OPENAI_API_KEY" in result.stdout


def test_invalid_model_profile_does_not_echo_rejected_credential(tmp_path: Path) -> None:
    literal_secret = "literal-private-credential-value-must-not-be-echoed"
    profile = tmp_path / "invalid-profile.yaml"
    profile.write_text(
        f"""requested_model: fake-model
provider: fake-provider
base_url: https://provider.invalid/v1
route: /responses
protocol: responses
reasoning:
  max_output_tokens: 1000
credential_reference: {literal_secret}
""",
        encoding="utf-8",
    )

    result = runner.invoke(app, ["model", "profile", "validate", str(profile)])

    assert result.exit_code == 1
    assert "field validation error" in result.stdout
    assert literal_secret not in result.stdout


def test_model_run_missing_credential_is_not_configured(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    profile = tmp_path / "profile.yaml"
    profile.write_text(
        """requested_model: fake-model
provider: fake-provider
base_url: https://provider.invalid/v1
route: /responses
protocol: responses
reasoning:
  max_output_tokens: 1000
credential_reference: GATE_D_CLI_MISSING_KEY
""",
        encoding="utf-8",
    )
    monkeypatch.delenv("GATE_D_CLI_MISSING_KEY", raising=False)
    task = Path(__file__).resolve().parents[1] / "tasks" / "micro-python-clamp" / "1.0.0"

    result = runner.invoke(
        app,
        [
            "model",
            "run",
            str(task),
            "--profile",
            str(profile),
            "--artifact-root",
            str(tmp_path / "artifacts"),
            "--allow-custom-endpoint",
        ],
        env={"GATE_D_CLI_MISSING_KEY": ""},
    )

    assert result.exit_code == 2
    assert "outcome=provider_error" in result.stdout
    assert (tmp_path / "artifacts").is_dir()


@pytest.mark.integration
def test_harness_codex_doctor_reports_pinned_runtime() -> None:
    result = runner.invoke(app, ["harness", "codex", "doctor"])

    assert result.exit_code == 0
    assert "PASS version=codex-cli 0.149.0" in result.stdout
    assert "harnesslab-phase-e-codex:0.149.0" in result.stdout
    assert "REAL_CODEX_SMOKE=NOT_VERIFIED" in result.stdout
