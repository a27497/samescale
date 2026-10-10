"""Saved historical Real evidence and separately labelled adversarial fixtures; zero Agent calls."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient, AsyncHTTPTransport, HTTPTransport

from harnesslab.api.app import create_app
from harnesslab.api.workbench_errors import WorkbenchAPIError
from harnesslab.episodes.hooks import encode, receive_hook
from harnesslab.external_evidence import service
from harnesslab.external_evidence.models import ApprovedSource, EvidencePolicy
from harnesslab.external_evidence.verification import verify_workspace
from harnesslab.tasks.package import digest_tree, sha256_bytes
from tests.local_plan_helpers import HEADERS, TOKEN
from tests.test_verified_hook_synthetic import _bundle

ROOT = Path(__file__).resolve().parents[1]
REAL_BUNDLE = ROOT / "docs/evidence/real-codex-native-hook-20261007/frozen/attempt-1"
REAL_PIN = "sha256:17243ac021add7d99478366ce0d843dae1a9d95a218e53f716a7ef538b86aa23"
REAL_WORKSPACE = "sha256:760feb0c05137db5266f8aa0b9c9684478228cf66755c3c6bfe6a09f5889ffc8"
PREFIX = "/api/external-evidence"


def historical_source() -> ApprovedSource:
    return ApprovedSource(
        source_id="approved-historical-real",
        format="verified-hook-v1",
        source_kind="historical",
        path=REAL_BUNDLE,
        digest=REAL_PIN,
        workspace=REAL_BUNDLE / "final-workspace",
        workspace_digest=REAL_WORKSPACE,
    )


def policy_file(tmp_path: Path, sources: list[ApprovedSource]) -> Path:
    path = tmp_path / "evidence-policy.json"
    policy = EvidencePolicy(store=tmp_path / "records", sources=tuple(sources))
    path.write_bytes(encode(policy.model_dump(mode="json")))
    path.chmod(0o600)
    return path


@pytest.fixture
def configured(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = policy_file(tmp_path, [historical_source()])
    monkeypatch.setenv("HARNESSLAB_EXTERNAL_EVIDENCE_POLICY", str(path))
    monkeypatch.setenv("HARNESSLAB_LOCAL_CONFIGURATION_TOKEN", TOKEN)
    monkeypatch.delenv("HARNESSLAB_PUBLIC_DEMO_MANIFEST", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("Evidence API/import/replay attempted network or process execution")

    async def async_forbidden(*args: object, **kwargs: object) -> None:
        forbidden()

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(HTTPTransport, "handle_request", forbidden)
    monkeypatch.setattr(AsyncHTTPTransport, "handle_async_request", async_forbidden)
    return path


async def import_real(client: AsyncClient) -> dict[str, Any]:
    response = await client.post(
        PREFIX + "/records",
        json={"source_id": "approved-historical-real", "consent": "IMPORT_APPROVED_SAVED_EVIDENCE"},
    )
    assert response.status_code == 200, response.text
    return dict(response.json())


async def test_real_saved_native_evidence_private_api_restart_export_and_replay(
    configured: Path,
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://localhost", headers=HEADERS
    ) as client:
        sources = (await client.get(PREFIX + "/sources")).json()
        assert "path" not in json.dumps(sources) and "/home/" not in json.dumps(sources)
        item = await import_real(client)
        record = item["record"]
        assert record["source"]["source_kind"] == "historical"
        assert record["original_source_kind"] == "unverified"
        assert (
            record["episode_identity"]
            == "sha256:63c82a966208a128187c14ab06bbca6236b6c48e094c30140ef59408fa5fee53"
        )
        assert record["original_acceptance"] == "NOT_VERIFIED"
        assert item["diagnosis"]["workspace_acceptance"] == "VERIFIED_PASS"
        assert item["diagnosis"]["independent_verification"]["checks"] == 5
        assert record["source_authenticity"] == "NOT_ATTESTED"
        assert len(record["trace"]) == 12 and all(e["exit_code"] is None for e in record["trace"])
        assert record["file_changes"] == {"status": "DIGEST_BOUND_BASELINE", "paths": ["events.py"]}
        assert "usage" in record["completeness"]["missing_fields"]
        assert await import_real(client) == item
        export = await client.get(PREFIX + f"/records/{item['identity']}/export")
        assert export.status_code == 200 and export.headers["cache-control"] == "no-store"
        data = export.content
        digest = export.headers["x-evidence-sha256"]
        a = service.replay_export(data, digest)
        b = service.replay_export(data, digest)
        assert encode(a) == encode(b)
        assert a["subject_executed"] is False and a["verifier_executed"] is False
        assert a["external_calls"] == 0 and a["diagnosis"] == item["diagnosis"]
        for forbidden in (
            b"verifier-source",
            b"verifier/verify.py",
            b"/home/",
            b"Bearer",
            TOKEN.encode(),
            b"private_reasoning",
        ):
            assert forbidden not in data
    # Independent app instance and deleted/removed source do not require re-running anything.
    policy = service.load_policy()
    configured.write_bytes(
        encode(policy.model_copy(update={"sources": ()}).model_dump(mode="json"))
    )
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://localhost", headers=HEADERS
    ) as client:
        assert (await client.get(PREFIX + f"/records/{item['identity']}")).json() == item


@pytest.mark.parametrize("kind", ["no_token", "wrong_origin", "missing_origin", "public_demo"])
async def test_permission_denial_precedes_source_db_or_file_reads(
    configured: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    headers = dict(HEADERS)
    if kind == "no_token":
        headers.pop("Authorization")
    if kind == "wrong_origin":
        headers["Origin"] = "https://evil.invalid"
    if kind == "missing_origin":
        headers.pop("Origin")
    if kind == "public_demo":
        monkeypatch.setenv("HARNESSLAB_PUBLIC_DEMO_MANIFEST", "/unread/demo.json")

    def forbidden() -> EvidencePolicy:
        raise AssertionError("permission denial must precede storage")

    monkeypatch.setattr(service, "load_policy", forbidden)
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://localhost", headers=headers
    ) as client:
        response = await client.post(
            PREFIX + "/records",
            json={
                "source_id": "approved-historical-real",
                "consent": "IMPORT_APPROVED_SAVED_EVIDENCE",
            },
        )
        assert response.status_code == 403
        if kind != "missing_origin":
            assert (await client.get(PREFIX + "/sources")).status_code == 403


@pytest.mark.parametrize(
    "payload",
    [
        {"source_id": "../../auth.json", "consent": "IMPORT_APPROVED_SAVED_EVIDENCE"},
        {"source_id": "unknown", "consent": "IMPORT_APPROVED_SAVED_EVIDENCE"},
        {"source_id": "approved-historical-real", "consent": "RUN_AGENT"},
        {
            "source_id": "approved-historical-real",
            "consent": "IMPORT_APPROVED_SAVED_EVIDENCE",
            "path": "/home/dev/.codex",
        },
    ],
)
async def test_no_arbitrary_paths_commands_or_implicit_consent(
    configured: Path, payload: dict[str, Any]
) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://localhost", headers=HEADERS
    ) as client:
        assert (await client.post(PREFIX + "/records", json=payload)).status_code in {409, 422}
    assert not service.load_policy().store.exists()


@pytest.mark.parametrize(
    "damage",
    [
        "pin",
        "workspace",
        "symlink",
        "hardlink",
        "credential",
        "hidden_verifier",
        "binary",
        "oversize",
    ],
)
def test_adversarial_source_never_persists_partial_record(tmp_path: Path, damage: str) -> None:
    _, bundle, digest = _bundle(tmp_path)
    workspace = bundle / "final-workspace"
    source = ApprovedSource(
        source_id="synthetic",
        format="verified-hook-v1",
        source_kind="synthetic",
        path=bundle,
        digest=digest,
        workspace=workspace,
        workspace_digest=digest_tree(workspace),
    )
    if damage == "pin":
        source = source.model_copy(update={"digest": "sha256:" + "0" * 64})
    if damage == "workspace":
        (workspace / "calculator.py").write_text("tampered\n")
    if damage == "symlink":
        (workspace / "escape.txt").symlink_to(tmp_path / "never-read-auth.json")
    if damage == "hardlink":
        os.link(workspace / "calculator.py", workspace / "linked.py")
    if damage == "credential":
        (workspace / "leak.py").write_text("access_token = 'SYNTHETIC_SECRET_CANARY_1234'\n")
    if damage == "hidden_verifier":
        (workspace / "verifier").mkdir()
        (workspace / "verifier/secret.txt").write_text("hidden")
    if damage == "binary":
        (workspace / "binary.bin").write_bytes(b"\x00\xff")
    if damage == "oversize":
        (workspace / "large.txt").write_bytes(b"x" * 4_000_001)
    policy = EvidencePolicy(store=tmp_path / "records", sources=(source,))
    with pytest.raises((OSError, ValueError, WorkbenchAPIError)):
        service.ingest(policy, source.source_id)
    assert not policy.store.exists()


def test_fixture_relabeling_is_rejected(tmp_path: Path) -> None:
    _, bundle, digest = _bundle(tmp_path)
    source = ApprovedSource(
        source_id="cannot-be-real",
        format="verified-hook-v1",
        source_kind="historical",
        path=bundle,
        digest=digest,
        workspace=bundle / "final-workspace",
        workspace_digest=digest_tree(bundle / "final-workspace"),
    )
    with pytest.raises(ValueError, match="fixture relabeling"):
        service.project(source)


def native_source(root: Path, *, partial: bool = False) -> ApprovedSource:
    spool = root / "hooks"
    for event in (
        ("SessionStart", "PreToolUse")
        if partial
        else ("SessionStart", "PreToolUse", "PostToolUse", "Stop")
    ):
        raw: dict[str, Any] = {
            "session_id": "fixture-only",
            "hook_event_name": event,
            "private_reasoning": "PRIVATE_REASONING_CANARY",
        }
        if "ToolUse" in event:
            raw.update(tool_name="Bash", tool_use_id="fixture-call")
        if event == "PostToolUse":
            raw["tool_response"] = {"exit_code": 1}
        receive_hook(encode(raw), "codex", spool)
    workspace = root / "final-workspace"
    workspace.mkdir(parents=True)
    (workspace / "answer.py").write_text("ANSWER = 42\n")
    return ApprovedSource(
        source_id="synthetic-native",
        format="native-hook-v1",
        source_kind="synthetic",
        path=spool,
        digest=digest_tree(spool),
        workspace=workspace,
        workspace_digest=digest_tree(workspace),
    )


@pytest.mark.parametrize("partial", [True, False])
def test_missing_task_and_partial_evidence_stay_unverified(tmp_path: Path, partial: bool) -> None:
    source = native_source(tmp_path, partial=partial)
    policy = EvidencePolicy(store=tmp_path / "records", sources=(source,))
    item = service.ingest(policy, source.source_id)
    assert item["diagnosis"]["workspace_acceptance"] == "NOT_VERIFIED"
    assert (
        item["record"]["episode_identity"] is None
        if partial
        else item["record"]["episode_identity"] is not None
    )
    assert item["diagnosis"]["observed_failed_tools"] == ([] if partial else [3])
    assert b"PRIVATE_REASONING_CANARY" not in service.export_record(policy, item["identity"])


@pytest.mark.parametrize("damage", ["workspace", "record", "receipt", "export", "wrong_pin"])
def test_tampering_refuses_read_or_replay(tmp_path: Path, damage: str) -> None:
    policy = EvidencePolicy(store=tmp_path / "records", sources=(historical_source(),))
    item = service.ingest(policy, "approved-historical-real")
    root = policy.store / item["identity"]
    packet = service.export_record(policy, item["identity"])
    if damage == "workspace":
        (root / "workspace/events.py").write_text("tampered")
    if damage == "record":
        (root / "record.json").write_text("{}")
    if damage == "receipt":
        (root / "verification.json").write_text('{"acceptance":"VERIFIED_PASS"}')
    if damage in {"workspace", "record", "receipt"}:
        with pytest.raises((ValueError, OSError)):
            service.export_record(policy, item["identity"])
    elif damage == "export":
        raw = json.loads(packet)
        raw["diagnosis"]["workspace_acceptance"] = "VERIFIED_FAIL"
        mutated = encode(raw)
        with pytest.raises(ValueError, match="diagnosis drift"):
            service.replay_export(mutated, sha256_bytes(mutated))
    else:
        with pytest.raises(ValueError, match="export pin mismatch"):
            service.replay_export(packet, "sha256:" + "0" * 64)


async def test_concurrent_import_is_idempotent(configured: Path) -> None:
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://localhost", headers=HEADERS
    ) as client:
        a, b = await asyncio.gather(import_real(client), import_real(client))
        assert a == b
        assert len((await client.get(PREFIX + "/records")).json()["items"]) == 1


def test_policy_rejects_credential_roots_without_reading_them(
    configured: Path, tmp_path: Path
) -> None:
    raw = json.loads(configured.read_bytes())
    raw["sources"][0]["path"] = str(tmp_path / ".codex")
    configured.write_bytes(encode(raw))
    with pytest.raises(WorkbenchAPIError, match="separate owned evidence policy"):
        service.load_policy()


async def test_no_trusted_task_refuses_verifier_before_process_launch(configured: Path) -> None:
    policy = service.load_policy()
    item = service.ingest(policy, "approved-historical-real")
    with pytest.raises(ValueError, match="trusted task mapping"):
        await verify_workspace(policy, item["identity"])


@pytest.mark.parametrize("terminal", ["turn.completed", "turn.failed", None])
def test_supplied_saved_exec_jsonl_drops_private_content_without_raw_persistence(
    tmp_path: Path, terminal: str | None
) -> None:
    source = native_source(tmp_path / "saved-stream")
    stream = tmp_path / "provided-jsonl"
    stream.mkdir()
    events = [
        {"type": "thread.started", "thread_id": "provided-identity"},
        {
            "type": "item.completed",
            "item": {"type": "reasoning", "text": "PRIVATE_REASONING_CANARY"},
        },
        {
            "type": "item.completed",
            "item": {"type": "agent_message", "text": "DONE; PRIVATE_PROMPT_CANARY"},
        },
        {
            "type": "item.completed",
            "item": {
                "type": "command_execution",
                "id": "cmd-1",
                "command": "echo SECRET_COMMAND_CANARY",
                "aggregated_output": "PRIVATE_OUTPUT_CANARY",
                "exit_code": 1,
                "status": "completed",
            },
        },
    ]
    if terminal:
        events.append(
            {"type": terminal, "usage": {"input_tokens": 123}, "error": "PRIVATE_ERROR_CANARY"}
        )
    (stream / "events.jsonl").write_bytes(b"".join(encode(e) for e in events))
    source = source.model_copy(
        update={"format": "codex-jsonl-v1", "path": stream, "digest": digest_tree(stream)}
    )
    policy = EvidencePolicy(store=tmp_path / "records", sources=(source,))
    item = service.ingest(policy, source.source_id)
    assert item["record"]["episode_identity"] is None
    assert item["diagnosis"]["workspace_acceptance"] == "NOT_VERIFIED"
    assert item["diagnosis"]["agent_self_reports"] == [3]
    assert item["diagnosis"]["observed_failed_tools"] == [4]
    assert ("native_completion" in item["record"]["completeness"]["missing_fields"]) is (
        terminal is None
    )
    if terminal == "turn.failed":
        assert item["diagnosis"]["infrastructure"]["status"] == "RECORDED_TURN_OR_STREAM_FAILURE"
    for path in policy.store.rglob("*"):
        if path.is_file():
            assert b"CANARY" not in path.read_bytes()
    assert b"CANARY" not in service.export_record(policy, item["identity"])


def test_private_rollout_format_and_zero_check_reanchoring_are_rejected(tmp_path: Path) -> None:
    source = native_source(tmp_path)
    stream = tmp_path / "provided-jsonl"
    stream.mkdir()
    (stream / "events.jsonl").write_bytes(
        encode({"type": "response_item", "payload": "private-rollout"})
    )
    source = source.model_copy(
        update={"format": "codex-jsonl-v1", "path": stream, "digest": digest_tree(stream)}
    )
    with pytest.raises(ValueError, match="unsupported saved exec protocol"):
        service.project(source)
    with pytest.raises(ValueError, match="zero or contradictory"):
        service.validate_verification(
            {"acceptance": "VERIFIED_PASS", "checks": 0, "passed_checks": 0}
        )
