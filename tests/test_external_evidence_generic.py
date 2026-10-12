"""Tool-neutral synthetic input contract; no sessions, providers or Agent execution."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient, AsyncHTTPTransport, HTTPTransport
from pydantic import ValidationError

from harnesslab.api.app import create_app
from harnesslab.episodes.hooks import encode
from harnesslab.external_evidence import service
from harnesslab.external_evidence.models import ApprovedSource, EvidencePolicy, ExternalRecord
from harnesslab.registry.models import canonical_digest
from harnesslab.tasks.package import digest_tree, sha256_bytes
from tests.local_plan_helpers import HEADERS, TOKEN
from tests.test_episodes import source as h_lane_source  # noqa: F401
from tests.test_external_evidence import native_source, policy_file
from tests.test_verified_hook_synthetic import _bundle

CLAUDE = [
    {"type": "system", "subtype": "init", "tools": ["Read", "Edit", "Write", "Bash", "Other"]},
    {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "thinking", "thinking": "PRIVATE_THINKING_CANARY"},
                {"type": "text", "text": "CLAIM_CANARY: all requirements done"},
                {
                    "type": "tool_use",
                    "id": "call-1",
                    "name": "Bash",
                    "input": {"command": "pytest"},
                },
                {
                    "type": "tool_use",
                    "id": "call-2",
                    "name": "Edit",
                    "input": {"file_path": "answer.py"},
                },
            ]
        },
    },
    {
        "type": "user",
        "message": {
            "content": [
                {
                    "type": "tool_result",
                    "tool_use_id": "call-1",
                    "is_error": True,
                    "content": "RAW_TOOL_OUTPUT_CANARY",
                },
            ]
        },
    },
    {"type": "result", "subtype": "success", "is_error": False, "result": "RESULT_CANARY"},
]
CODEX = [
    {"type": "thread.started", "thread_id": "PRIVATE_ID_CANARY"},
    {"type": "item.completed", "item": {"type": "agent_message", "text": "CLAIM_CANARY"}},
    {"type": "turn.completed", "usage": {"input_tokens": 100}},
]


def generic_source(root: Path, harness: str = "code-only", *, auto: bool = False) -> ApprovedSource:
    workspace = root / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "answer.py").write_text("ANSWER = 42\n")
    values: dict[str, Any] = dict(
        source_id="synthetic-" + harness,
        source_kind="synthetic",
        workspace=workspace,
        workspace_digest=digest_tree(workspace),
        task_reference="custom:task/1.0.0",
        task_digest="sha256:" + "a" * 64,
    )
    if harness == "code-only":
        return ApprovedSource(format="code-only-v1", **values)
    log = root / "supplied-stream"
    log.mkdir()
    (log / "events.jsonl").write_bytes(
        b"".join(encode(r) for r in (CLAUDE if harness == "claude-code" else CODEX))
    )
    return ApprovedSource(
        format="auto-v1" if auto else "stream-json-v1",
        path=log,
        digest=digest_tree(log),
        harness=None if auto else {"name": harness, "version": "synthetic-fixture"},
        **values,
    )


@pytest.fixture(autouse=True)
def no_external_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("data-only intake attempted process or external I/O")

    async def async_forbidden(*args: object, **kwargs: object) -> None:
        forbidden()

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(HTTPTransport, "handle_request", forbidden)
    monkeypatch.setattr(AsyncHTTPTransport, "handle_async_request", async_forbidden)


@pytest.mark.parametrize(
    "harness,coverage",
    [
        ("codex", "SUPPLIED_EXEC_JSONL_ONLY"),
        ("claude-code", "SUPPLIED_STREAM_JSON_ONLY"),
        ("code-only", "NO_RUN_RECORD"),
    ],
)
async def test_shared_private_intake_and_replay(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, harness: str, coverage: str
) -> None:
    source = generic_source(tmp_path, harness)
    monkeypatch.setenv("HARNESSLAB_EXTERNAL_EVIDENCE_POLICY", str(policy_file(tmp_path, [source])))
    monkeypatch.setenv("HARNESSLAB_LOCAL_CONFIGURATION_TOKEN", TOKEN)
    monkeypatch.delenv("HARNESSLAB_PUBLIC_DEMO_MANIFEST", raising=False)
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://localhost", headers=HEADERS
    ) as client:
        assert (await client.get("/api/external-evidence/configuration-check")).json()[
            "status"
        ] == "CONFIGURED"
        assert (
            await client.post(
                "/api/external-evidence/records", json={"source_id": source.source_id}
            )
        ).status_code == 422
        response = await client.post(
            "/api/external-evidence/records",
            json={"source_id": source.source_id, "consent": "IMPORT_APPROVED_SAVED_EVIDENCE"},
        )
        assert response.status_code == 200, response.text
        item = response.json()
        assert item["record"]["kind"] == "external-run-evidence-v1"
        assert item["record"]["completeness"]["coverage"] == coverage
        assert item["record"]["completeness"]["status"] == "PARTIAL"
        assert item["record"]["source_authenticity"] == "NOT_ATTESTED"
        assert item["diagnosis"]["workspace_acceptance"] == "NOT_VERIFIED"
        assert item["diagnosis"]["independent_verification"]["checks"] == 0
        assert item["record"]["original_acceptance"] == "NOT_VERIFIED"
        if harness == "code-only":
            assert item["record"]["harness"] is None and item["record"]["trace"] == []
        else:
            assert item["record"]["harness"]["name"] == harness
            assert item["record"]["harness"]["version"] == "synthetic-fixture"
        if harness == "claude-code":
            assert item["diagnosis"]["observed_failed_tools"] == [6]
            assert item["diagnosis"]["agent_self_reports"] == [3]
        exported = await client.get(
            "/api/external-evidence/records/" + item["identity"] + "/export"
        )
        assert exported.status_code == 200
        assert "CANARY" not in exported.text
        replay = service.replay_export(exported.content, exported.headers["x-evidence-sha256"])
        assert replay["diagnosis"]["workspace_acceptance"] == "NOT_VERIFIED"
        assert replay["subject_executed"] is False
        # All tools retain the same operator/public boundary.
        assert (
            await client.get(
                "/api/external-evidence/sources", headers={"Authorization": "Bearer wrong"}
            )
        ).status_code == 403
    assert not any(
        "CANARY" in p.read_text() for p in (tmp_path / "records").rglob("*") if p.is_file()
    )


@pytest.mark.parametrize("harness", ["codex", "claude-code"])
def test_auto_detection_and_incomplete_capture(tmp_path: Path, harness: str) -> None:
    source = generic_source(tmp_path, harness, auto=True)
    assert source.path is not None
    (source.path / "events.jsonl").write_bytes(encode((CODEX if harness == "codex" else CLAUDE)[0]))
    source = source.model_copy(update={"digest": digest_tree(source.path)})
    record, _ = service.project(source)
    assert record.harness is not None and record.harness.name == harness
    assert record.harness.version is None
    assert "native_completion" in record.completeness["missing_fields"]
    assert record.recorded_verification["checks"] == 0


@pytest.mark.parametrize(
    "damage",
    [
        "broken",
        "duplicate",
        "envelope",
        "mixed",
        "ambiguous",
        "sensitive",
        "path",
        "pin",
        "workspace",
        "tool",
        "boolean",
    ],
)
def test_invalid_streams_never_persist(tmp_path: Path, damage: str) -> None:
    source = generic_source(tmp_path, "claude-code", auto=True)
    assert source.path is not None
    samples = {
        "broken": b'{"type":',
        "duplicate": b'{"type":"result","type":"assistant"}',
        "envelope": encode({"type": "assistant", "message": {"content": [42]}}),
        "mixed": encode(CODEX[0]) + encode(CLAUDE[0]),
        "ambiguous": encode({"type": "error"}),
        "sensitive": encode(
            {"type": "result", "result": 'api_key = "SYNTHETIC_CREDENTIAL_CANARY"'}
        ),
        "path": encode(
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Edit",
                            "input": {"file_path": ".claude/auth.json"},
                        }
                    ]
                },
            }
        ),
        "tool": encode(
            {
                "type": "assistant",
                "message": {"content": [{"type": "tool_use", "name": "Bash", "input": []}]},
            }
        ),
        "boolean": encode({"type": "result", "is_error": "false"}),
    }
    if damage in samples:
        (source.path / "events.jsonl").write_bytes(samples[damage])
        source = source.model_copy(update={"digest": digest_tree(source.path)})
    elif damage == "pin":
        source = source.model_copy(update={"digest": "sha256:" + "b" * 64})
    else:
        (source.workspace / "answer.py").write_text("tampered")
    policy = EvidencePolicy(store=tmp_path / "records", sources=(source,))
    with pytest.raises(ValueError):
        service.ingest(policy, source.source_id)
    assert not policy.store.exists()


def test_code_only_conditions_and_stream_pins_required(tmp_path: Path) -> None:
    source = generic_source(tmp_path)
    for changes in (
        {"task_digest": None},
        {"task_reference": ""},
        {"path": tmp_path},
        {"harness": {"name": "codex"}},
    ):
        with pytest.raises(ValidationError):
            ApprovedSource.model_validate({**source.model_dump(), **changes})
    for name in ["codex", "claude-code"]:
        source = generic_source(tmp_path / name, name)
        with pytest.raises(ValidationError):
            ApprovedSource.model_validate({**source.model_dump(), "digest": None})


def test_pre_migration_record_keeps_original_identity_and_export(tmp_path: Path) -> None:
    # Produced with the unmodified branch at 6affea4; never regenerated by the new model.
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/external-evidence-legacy.json").read_text()
    )
    raw, pin = fixture["record"], fixture["identity"]
    assert canonical_digest(raw) == pin
    record = ExternalRecord.model_validate(raw)
    assert record.identity == pin and record.harness is None
    policy = EvidencePolicy(
        store=tmp_path / "records", sources=(native_source(tmp_path / "source"),)
    )
    root = policy.store / pin[7:]
    (root / "workspace").mkdir(parents=True)
    (root / "record.json").write_bytes(encode(raw))
    (root / "workspace/answer.py").write_text("ANSWER = 42\n")
    policy.store.chmod(0o700)
    assert service.read_record(policy, pin[7:]).identity == pin
    exported = service.export_record(policy, pin[7:])
    assert (
        service.replay_export(exported, sha256_bytes(exported))["diagnosis"]["workspace_acceptance"]
        == "NOT_VERIFIED"
    )
    with pytest.raises(ValidationError):
        ExternalRecord.model_validate({**raw, "harness": {"name": "claude-code"}})


def test_h_lane_converter_and_generic_alias(h_lane_source: Path, tmp_path: Path) -> None:  # noqa: F811
    source = ApprovedSource(
        source_id="synthetic-h-lane",
        format="codex-h-lane-v1",
        source_kind="synthetic",
        path=h_lane_source,
        digest=digest_tree(h_lane_source),
        workspace=h_lane_source / "workspace",
        workspace_digest=digest_tree(h_lane_source / "workspace"),
    )
    legacy, _ = service.project(source)
    generic = ApprovedSource.model_validate(
        {
            **source.model_dump(),
            "format": "h-lane-v1",
            "task_reference": "custom:task/1",
            "task_digest": "sha256:" + "a" * 64,
        }
    )
    modern, _ = service.project(generic)
    assert legacy.trace == modern.trace
    assert legacy.episode_identity == modern.episode_identity
    assert modern.completeness["coverage"] == "RECORDED_H_LANE"
    assert modern.original_acceptance == "NOT_VERIFIED"
    assert modern.recorded_verification["checks"] == 0


def test_verified_hook_converter_keeps_independent_result_separate(tmp_path: Path) -> None:
    _, bundle, digest = _bundle(tmp_path)
    source = ApprovedSource(
        source_id="synthetic-bound-hooks",
        format="verified-hook-v1",
        source_kind="synthetic",
        path=bundle,
        digest=digest,
        workspace=bundle / "final-workspace",
        workspace_digest=digest_tree(bundle / "final-workspace"),
    )
    policy = EvidencePolicy(store=tmp_path / "records", sources=(source,))
    item = service.ingest(policy, source.source_id)
    assert item["record"]["original_acceptance"] == "NOT_VERIFIED"
    assert item["record"]["harness"]["name"] == "codex"
    assert item["record"]["completeness"]["coverage"] == "PAIRED_HOOKS_ONLY"
    assert item["diagnosis"]["workspace_acceptance"] == "VERIFIED_FAIL"
    assert item["diagnosis"]["independent_verification"]["checks"] > 0


def test_generic_hook_alias_keeps_original_episode(tmp_path: Path) -> None:
    source = native_source(tmp_path)
    legacy, _ = service.project(source)
    generic = ApprovedSource.model_validate(
        {
            **source.model_dump(),
            "format": "hook-v1",
            "task_reference": "custom:task/1",
            "task_digest": "sha256:" + "a" * 64,
        }
    )
    modern, _ = service.project(generic)
    assert legacy.trace == modern.trace and legacy.episode_identity == modern.episode_identity
    assert modern.completeness["coverage"] == "PAIRED_HOOKS_ONLY"


@pytest.mark.parametrize("harness", ["codex", "claude-code", "code-only"])
async def test_tampered_inputs_share_safe_api_rejection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, harness: str
) -> None:
    source = generic_source(tmp_path, harness)
    monkeypatch.setenv("HARNESSLAB_EXTERNAL_EVIDENCE_POLICY", str(policy_file(tmp_path, [source])))
    monkeypatch.setenv("HARNESSLAB_LOCAL_CONFIGURATION_TOKEN", TOKEN)
    monkeypatch.delenv("HARNESSLAB_PUBLIC_DEMO_MANIFEST", raising=False)
    (source.workspace / "answer.py").write_text("changed after approval")
    async with AsyncClient(
        transport=ASGITransport(app=create_app()), base_url="http://localhost", headers=HEADERS
    ) as client:
        response = await client.post(
            "/api/external-evidence/records",
            json={"source_id": source.source_id, "consent": "IMPORT_APPROVED_SAVED_EVIDENCE"},
        )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EVIDENCE_PIN_MISMATCH"
    assert str(tmp_path) not in response.text
    assert not (tmp_path / "records").exists()


@pytest.mark.parametrize(
    "payload",
    [
        {"type": "item.completed"},
        {"type": "item.completed", "item": {}},
    ],
)
def test_codex_malformed_items_are_rejected(tmp_path: Path, payload: dict[str, Any]) -> None:
    source = generic_source(tmp_path, "codex")
    assert source.path is not None
    (source.path / "events.jsonl").write_bytes(encode(payload))
    source = source.model_copy(update={"digest": digest_tree(source.path)})
    with pytest.raises(ValueError):
        service.ingest(
            EvidencePolicy(store=tmp_path / "records", sources=(source,)), source.source_id
        )
    assert not (tmp_path / "records").exists()
