"""P1 usability boundaries: saved history plus explicit fixtures, no execution or database."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from typer.testing import CliRunner

from harnesslab.api.app import create_app
from harnesslab.external_evidence import service, verification
from harnesslab.external_evidence.cli import external_evidence_app
from tests.local_plan_helpers import HEADERS, TOKEN
from tests.test_external_evidence import historical_source, native_source, policy_file

PREFIX = "/api/external-evidence"


@pytest.fixture
def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = policy_file(
        tmp_path, [historical_source(), native_source(tmp_path / "fixture", partial=True)]
    )
    monkeypatch.setenv("HARNESSLAB_EXTERNAL_EVIDENCE_POLICY", str(path))
    monkeypatch.setenv("HARNESSLAB_LOCAL_CONFIGURATION_TOKEN", TOKEN)
    monkeypatch.delenv("HARNESSLAB_PUBLIC_DEMO_MANIFEST", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    return path


@pytest.mark.parametrize("damage", ["workspace", "record", "receipt", "sensitive", "missing"])
async def test_mixed_records_keep_healthy_reads_and_refuse_corrupt_details(
    setup: Path, damage: str
) -> None:
    policy = service.load_policy()
    real = service.ingest(policy, "approved-historical-real")
    synthetic = service.ingest(policy, "synthetic-native")
    frozen = (policy.store / real["identity"] / "record.json").read_bytes()
    root = policy.store / synthetic["identity"]
    if damage == "workspace":
        (root / "workspace/answer.py").write_text("changed")
    elif damage == "record":
        (root / "record.json").write_text("{}")
    elif damage == "receipt":
        (root / "verification.json").write_text("[]")
    elif damage == "sensitive":
        (root / "workspace/answer.py").write_text("access_token = 'SYNTHETIC_PRIVATE_CANARY_1234'")
    else:
        (root / "record.json").unlink()
    # A new app instance reads persistent state; the malformed sibling never becomes a pass.
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://localhost", headers=HEADERS
    ) as client:
        response = await client.get(PREFIX + "/records")
        assert response.status_code == 200
        items = response.json()["items"]
        assert len(items) == 2
        good = next(i for i in items if i["identity"] == real["identity"])
        bad = next(i for i in items if i["identity"] == synthetic["identity"])
        assert good["status"] == "AVAILABLE" and good["acceptance"] == "VERIFIED_PASS"
        assert bad["status"] == "CORRUPT" and bad["error_code"] == "EVIDENCE_RECORD_CORRUPT"
        assert not {"source_id", "source_kind", "acceptance"} & bad.keys()
        assert "CANARY" not in response.text and "/home/" not in response.text
        for suffix in ["", "/export"]:
            assert (
                await client.get(PREFIX + f"/records/{synthetic['identity']}" + suffix)
            ).status_code == 409
            assert (
                await client.get(PREFIX + f"/records/{real['identity']}" + suffix)
            ).status_code == 200
        result = (await client.get(PREFIX + f"/records/{real['identity']}")).json()
        assert result["diagnosis"]["original_episode_acceptance"] == "NOT_VERIFIED"
        assert result["diagnosis"]["independent_verification"]["checks"] == 5
    assert (policy.store / real["identity"] / "record.json").read_bytes() == frozen


async def test_all_records_corrupt_are_reported_not_an_empty_list(setup: Path) -> None:
    policy = service.load_policy()
    ids = [
        service.ingest(policy, name)["identity"]
        for name in ["approved-historical-real", "synthetic-native"]
    ]
    for identity in ids:
        (policy.store / identity / "record.json").write_text("[]")
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://localhost", headers=HEADERS
    ) as client:
        response = await client.get(PREFIX + "/records")
        assert response.status_code == 200
        assert len(response.json()["items"]) == 2
        assert all(i["status"] == "CORRUPT" for i in response.json()["items"])


async def test_corrupt_workspace_refuses_verifier_admission_before_launch(
    setup: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = service.load_policy()
    item = service.ingest(policy, "synthetic-native")
    root = policy.store / item["identity"]
    (root / "workspace/answer.py").write_text("changed")

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("corrupt record launched a Verifier")

    monkeypatch.setattr(verification, "PinnedVerifierSandbox", forbidden)
    with pytest.raises(ValueError, match="workspace drift"):
        await verification.verify_workspace(policy, item["identity"])
    assert not (root / "verification-attempt.json").exists()


@pytest.mark.parametrize(
    "damage",
    [
        "policy_rights",
        "policy_schema",
        "store_rights",
        "node_rights",
        "symlink",
        "hardlink",
        "entry_name",
    ],
)
async def test_global_policy_and_storage_errors_are_not_row_warnings(
    setup: Path, damage: str, tmp_path: Path
) -> None:
    policy = service.load_policy()
    service.ingest(policy, "approved-historical-real")
    expected = "EVIDENCE_STORAGE_UNSAFE"
    if damage == "policy_rights":
        setup.chmod(0o644)
        expected = "EVIDENCE_POLICY_PERMISSION"
    elif damage == "policy_schema":
        setup.write_text('{"untrusted":"PRIVATE_CANARY_DO_NOT_REFLECT"}')
        expected = "EVIDENCE_POLICY_INVALID"
    elif damage == "store_rights":
        policy.store.chmod(0o755)
    elif damage == "node_rights":
        next(policy.store.glob("*/record.json")).chmod(0o000)
    elif damage == "symlink":
        target = tmp_path / "not-read.txt"
        target.write_text("PRIVATE_CANARY_DO_NOT_REFLECT")
        (policy.store / "escape").symlink_to(target)
    elif damage == "hardlink":
        original = next(policy.store.glob("*/record.json"))
        os.link(original, policy.store / "linked")
    else:
        (policy.store / "PRIVATE_CANARY_DO_NOT_REFLECT").mkdir()
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://localhost", headers=HEADERS
    ) as client:
        response = await client.get(PREFIX + "/records")
        assert response.status_code == 403
        assert response.json()["error"]["code"] == expected
        assert "items" not in response.json() and "PRIVATE_CANARY" not in response.text


def test_read_only_check_does_not_read_sources_import_execute_or_write(
    setup: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    policy = service.load_policy()

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("read-only check crossed its contract")

    for name in ["project", "ingest", "workspace_files", "read_record"]:
        monkeypatch.setattr(service, name, forbidden)
    monkeypatch.setattr(tempfile, "TemporaryDirectory", forbidden)
    result = CliRunner().invoke(external_evidence_app, ["check"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["status"] == "CONFIGURED"
    assert data["source_contents_checked"] is data["pins_verified"] is False
    assert data["subject_executed"] is data["verifier_executed"] is False
    assert TOKEN not in result.stdout and "/home/" not in result.stdout
    assert not policy.store.exists()


def test_check_distinguishes_unset_empty_and_bad_policy(
    setup: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("HARNESSLAB_EXTERNAL_EVIDENCE_POLICY")
    assert service.configuration_check()["issues"] == ["EXTERNAL_EVIDENCE_DISABLED"]
    monkeypatch.setenv("HARNESSLAB_EXTERNAL_EVIDENCE_POLICY", str(setup))
    raw = json.loads(setup.read_text())
    raw["sources"] = []
    setup.write_text(json.dumps(raw))
    assert service.configuration_check()["status"] == "NO_APPROVED_SOURCES"
    setup.chmod(0o644)
    assert service.configuration_check()["issues"] == ["EVIDENCE_POLICY_PERMISSION"]
    assert CliRunner().invoke(external_evidence_app, ["check"]).exit_code == 2


def test_check_forbids_credential_policy_path_before_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Synthetic path only, no developer authentication file is accessed.
    path = tmp_path / ".codex" / "auth.json"
    monkeypatch.setenv("HARNESSLAB_EXTERNAL_EVIDENCE_POLICY", str(path))

    def forbidden(*args: object) -> None:
        raise AssertionError("credential-shaped policy path was read")

    monkeypatch.setattr(service, "read_owned_json", forbidden)
    assert service.configuration_check()["issues"] == ["EVIDENCE_POLICY_INVALID"]


@pytest.mark.parametrize("case", ["pin", "sensitive"])
async def test_import_reason_codes_are_safe_and_no_record_is_created(
    setup: Path, case: str
) -> None:
    raw = json.loads(setup.read_text())
    source = raw["sources"][1]
    if case == "pin":
        source["workspace_digest"] = "sha256:" + "0" * 64
        expected = "EVIDENCE_PIN_MISMATCH"
    else:
        (Path(source["workspace"]) / "answer.py").write_text(
            "access_token = 'SYNTHETIC_CANARY_FOR_TEST_1234'"
        )
        expected = "EVIDENCE_SENSITIVE_INPUT"
    setup.write_text(json.dumps(raw))
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://localhost", headers=HEADERS
    ) as client:
        response = await client.post(
            PREFIX + "/records",
            json={"source_id": "synthetic-native", "consent": "IMPORT_APPROVED_SAVED_EVIDENCE"},
        )
        assert response.status_code == 409 and response.json()["error"]["code"] == expected
        assert "CANARY" not in response.text
    assert not Path(raw["store"]).exists()


async def test_configuration_api_denies_permissions_before_policy_read(
    setup: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def forbidden() -> dict[str, object]:
        raise AssertionError("unauthorized configuration read")

    monkeypatch.setattr(service, "configuration_check", forbidden)
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://localhost"
    ) as client:
        assert (await client.get(PREFIX + "/configuration-check")).status_code == 403
