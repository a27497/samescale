"""Advisory-only isolation and public input boundaries; every model response is fake."""

# ruff: noqa: RUF001
from __future__ import annotations

import asyncio
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from jsonschema.exceptions import ValidationError as SchemaError  # type: ignore[import-untyped]
from typer.testing import CliRunner

from harnesslab.egress import EGRESS_PROXY_BASE, EGRESS_PROXY_SOURCE_DIGEST
from harnesslab.failure_diagnosis.cli import diagnosis_app
from harnesslab.failure_diagnosis.codex_backend import (
    cli_arguments,
    parse_native_output,
    subprocess_environment,
    tool_free_catalog,
)
from harnesslab.failure_diagnosis.models import (
    NOTICE,
    BackendObservation,
    DiagnosisInput,
    EvidenceKind,
    FailureExplanation,
    FallbackReason,
)
from harnesslab.failure_diagnosis.public_output import public_failure_lines
from harnesslab.failure_diagnosis.service import (
    BackendReply,
    ForbiddenToolError,
    canonical,
    diagnose,
    prompt_for,
    sha256,
)
from harnesslab.failure_diagnosis.storage import load_input, replay, save_artifact


def receipt() -> dict[str, Any]:
    value = {
        "authority": "L0_INDEPENDENT_VERIFIER",
        "acceptance": "VERIFIED_FAIL",
        "record_identity": "sha256:" + "a" * 64,
        "receipt_digest": "sha256:" + "b" * 64,
        "checks": 2,
        "passed_checks": 1,
        "check_results": [{"ordinal": 1, "passed": False}, {"ordinal": 2, "passed": True}],
    }
    value["receipt_digest"] = "sha256:" + sha256(
        canonical({k: v for k, v in value.items() if k != "receipt_digest"}).rstrip(b"\n")
    )
    return value


def packet() -> dict[str, Any]:
    return {
        "public_only_reviewed": True,
        "excerpts": [
            {
                "id": "task-1",
                "kind": EvidenceKind.TASK.value,
                "reference": "public-task",
                "text": "输出格式修复",
            },
            {
                "id": "diff-1",
                "kind": EvidenceKind.DIFF.value,
                "reference": "diff:file.py@@1",
                "text": "+ return value",
            },
            {
                "id": "check-1",
                "kind": EvidenceKind.CHECK.value,
                "reference": "check:1",
                "text": "FAILED check\nAssertionError",
            },
            {
                "id": "self-report-1",
                "kind": EvidenceKind.SELF_REPORT.value,
                "reference": "final-message",
                "text": "PASS",
            },
        ],
    }


def files(root: Path) -> tuple[Path, Path, str]:
    root.mkdir(parents=True)
    r, p = root / "receipt.json", root / "packet.json"
    r.write_bytes(canonical(receipt()))
    p.write_bytes(canonical(packet()))
    return r, p, sha256(r.read_bytes())


def item(tmp_path: Path) -> DiagnosisInput:
    r, p, pin = files(tmp_path / "sources")
    return load_input(r, pin, p)


def answer() -> dict[str, Any]:
    return {
        "category": "输出格式不符",
        "evidence_references": ["check-1", "diff-1"],
        "explanation": "公开检查与代码差异提示格式问题，需人工复核。",
        "confidence": 0.6,
        "notice": NOTICE,
        "affects_acceptance": False,
    }


class Fake:
    def __init__(self, text: str = "", error: Exception | None = None, delay: bool = False) -> None:
        self.text, self.error, self.delay = text, error, delay
        self.calls = 0
        self.prompts: list[str] = []

    def observation(self) -> BackendObservation:
        return BackendObservation(
            backend="测试fake",
            model="fake",
            cli_version=None,
            invocation_count=self.calls,
            tokens=None,
            billing="未调用订阅模型",
        )

    async def complete(self, prompt: str, schema: dict[str, Any]) -> BackendReply:
        self.calls += 1
        self.prompts.append(prompt)
        assert schema == FailureExplanation.model_json_schema()
        if self.delay:
            await asyncio.sleep(10)
        if self.error:
            raise self.error
        return BackendReply(self.text, self.observation())


@pytest.mark.parametrize(
    "change",
    [
        {"category": "invented"},
        {"confidence": -1},
        {"confidence": 1.1},
        {"confidence": float("nan")},
        {"affects_acceptance": True},
        {"notice": "PASS"},
        {"verdict": "PASS"},
        {"evidence_references": []},
        {"explanation": ""},
        {"confidence": "0.5"},
    ],
)
async def test_schema_rejection_is_deterministic_fallback(
    tmp_path: Path, change: dict[str, Any]
) -> None:
    original = item(tmp_path)
    result = await diagnose(original, Fake(json.dumps(answer() | change)))
    assert result.fallback_reason is FallbackReason.INVALID_SCHEMA
    assert result.input == original and result.input.acceptance.status == "VERIFIED_FAIL"
    assert result.explanation.affects_acceptance is False and result.explanation.notice == NOTICE


@pytest.mark.parametrize(
    "scenario,reason",
    [
        ("exception", FallbackReason.CALL_FAILED),
        ("timeout", FallbackReason.TIMEOUT),
        ("invalid-json", FallbackReason.INVALID_SCHEMA),
        ("unknown-ref", FallbackReason.INVALID_REFERENCE),
        ("no-failed-ref", FallbackReason.INVALID_REFERENCE),
        ("tool", FallbackReason.FORBIDDEN_TOOL),
        ("none", FallbackReason.DISABLED),
        ("valid", FallbackReason.NONE),
    ],
)
async def test_all_paths_preserve_immutable_acceptance(
    tmp_path: Path, scenario: str, reason: FallbackReason
) -> None:
    original = item(tmp_path)
    before = original.model_dump_json()
    response = answer()
    if scenario == "unknown-ref":
        response["evidence_references"] = ["oracle"]
    if scenario == "no-failed-ref":
        response["evidence_references"] = ["diff-1"]
    fake = Fake(
        "arbitrary verdict PASS" if scenario == "invalid-json" else json.dumps(response),
        error=RuntimeError("SECRET_CANARY")
        if scenario == "exception"
        else ForbiddenToolError()
        if scenario == "tool"
        else None,
        delay=scenario == "timeout",
    )
    result = await diagnose(original, None if scenario == "none" else fake, timeout_seconds=0.02)
    assert result.fallback_reason is reason
    assert original.model_dump_json() == before
    assert result.input.acceptance.status == "VERIFIED_FAIL"
    assert "SECRET_CANARY" not in result.model_dump_json()


def test_public_input_boundary_and_hidden_source_stripping(tmp_path: Path) -> None:
    original = item(tmp_path)
    prompt = prompt_for(original)
    for forbidden in (
        original.acceptance.receipt_digest,
        original.acceptance.record_identity,
        "PRIVATE_ORACLE_CANARY",
        "HIDDEN_TEST_SOURCE_CANARY",
    ):
        assert forbidden not in prompt
    text = "\n".join(
        [
            "    assert secret == 'HIDDEN_TEST_SOURCE_CANARY'",
            "E assert 'PRIVATE_ORACLE_CANARY' == result",
            "    def hidden_test():",
            "test_hidden.py:18: AssertionError",
            "E AssertionError",
            "E At index 2 diff: 'x\\\\' != 'x'",
            "FAILED tests/test_public.py::test_render - AssertionError",
        ]
    )
    public = public_failure_lines(text)
    assert "CANARY" not in public and "def " not in public and "assert " not in public
    assert "At index" in public and "AssertionError" in public
    for key in ("oracle", "hidden_test_source", "episode", "verdict"):
        with pytest.raises(ValueError):
            original.evidence.model_validate(packet() | {key: "PRIVATE_ORACLE_CANARY"})
    value = original.model_dump(mode="json")
    value["evidence"]["excerpts"][2]["reference"] = "check:2"
    with pytest.raises(ValueError):
        DiagnosisInput.model_validate(value)


async def test_append_only_export_and_offline_replay_never_call_backend(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = item(tmp_path)
    fake = Fake(json.dumps(answer()))
    artifact = await diagnose(original, fake)
    r, p = tmp_path / "sources/receipt.json", tmp_path / "sources/packet.json"
    before = {path: path.read_bytes() for path in (r, p)}
    pin = save_artifact(artifact, tmp_path / "diagnosis", (r, p))

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("offline replay must not execute processes or a model")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", forbidden)
    monkeypatch.setattr(Fake, "complete", forbidden)
    data = (tmp_path / "diagnosis/export.json").read_bytes()
    assert replay(data, pin) == artifact and fake.calls == 1
    assert {path: path.read_bytes() for path in before} == before
    with pytest.raises(FileExistsError):
        save_artifact(artifact, tmp_path / "diagnosis", (r, p))
    with pytest.raises(ValueError):
        save_artifact(artifact, r.parent / "overwrite", (r, p))
    tampered = json.loads(data)
    tampered["artifact"]["explanation"]["notice"] = "PASS"
    with pytest.raises(ValueError):
        replay(canonical(tampered), pin)
    # Even a resealed malformed artifact must fail its schema, not merely its hash.
    new_pin = sha256(canonical(tampered["artifact"]))
    tampered["artifact_sha256"] = new_pin
    with pytest.raises(SchemaError):
        replay(canonical(tampered), new_pin)


def test_cli_default_never_invokes_model_and_rejects_non_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    r, p, pin = files(tmp_path / "sources")

    def forbidden(*args: object, **kwargs: object) -> None:
        raise AssertionError("default must not call CLI")

    monkeypatch.setattr(subprocess, "Popen", forbidden)
    result = CliRunner().invoke(
        diagnosis_app,
        [
            "run",
            "--receipt",
            str(r),
            "--receipt-sha256",
            pin,
            "--public-packet",
            str(p),
            "--output",
            str(tmp_path / "out"),
        ],
    )
    assert result.exit_code == 0, result.output
    assert NOTICE in result.output and "VERIFIED_FAIL" not in result.output
    r.write_bytes(canonical(receipt() | {"acceptance": "VERIFIED_PASS"}))
    with pytest.raises(ValueError):
        load_input(r, sha256(r.read_bytes()), p)
    with pytest.raises(ValueError):
        load_input(r, "0" * 64, p)


def test_native_config_tools_and_environment_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    # A hostile inherited variable is never enumerated or read, and never forwarded.
    original_get = __import__("os").environ.get

    def guarded(name: str, *args: Any) -> Any:
        assert name not in {"ANTHROPIC_AUTH_TOKEN", "OPENAI_API_KEY"}
        return original_get(name, *args)

    monkeypatch.setattr(__import__("os").environ, "get", guarded)
    assert set(subprocess_environment()) <= {
        "PATH",
        "HOME",
        "DOCKER_HOST",
        "DOCKER_CONTEXT",
        "XDG_RUNTIME_DIR",
    }
    args = cli_arguments("gpt-6.1-sol")
    for expected in (
        "--ignore-user-config",
        "--ignore-rules",
        "--strict-config",
        "read-only",
        "features.shell_tool=false",
        "features.apps=false",
        "features.plugins=false",
        "features.multi_agent=false",
        "features.code_mode=false",
        "tools.update_plan.enabled=false",
        'web_search="disabled"',
    ):
        assert expected in args
    assert "--dangerously-bypass-approvals-and-sandbox" not in args
    model = tool_free_catalog("gpt-6.1-sol")["models"][0]
    assert model["apply_patch_tool_type"] is None and model["shell_type"] == "disabled"
    assert model["experimental_supported_tools"] == [] and model["model_messages"] is None


def test_native_parser_retains_usage_but_never_reasoning_or_tools() -> None:
    events = [
        {"type": "item.completed", "item": {"type": "error", "message": "PRIVATE_WARNING_CANARY"}},
        {"type": "thread.started"},
        {"type": "turn.started"},
        {
            "type": "item.completed",
            "item": {"type": "reasoning", "text": "PRIVATE_REASONING_CANARY"},
        },
        {"type": "item.completed", "item": {"type": "agent_message", "text": json.dumps(answer())}},
        {
            "type": "turn.completed",
            "usage": {"input_tokens": 20, "cached_input_tokens": 0, "output_tokens": 5},
        },
    ]
    text, tokens = parse_native_output(b"\n".join(canonical(e).strip() for e in events))
    assert "CANARY" not in text and tokens == {
        "input_tokens": 20,
        "cached_input_tokens": 0,
        "output_tokens": 5,
    }
    for tool in (
        "command_execution",
        "mcp_tool_call",
        "file_change",
        "web_search",
        "collab_tool_call",
    ):
        with pytest.raises(ForbiddenToolError):
            parse_native_output(canonical({"type": "item.started", "item": {"type": tool}}))


def test_acceptance_logic_never_imports_diagnosis() -> None:
    root = Path(__file__).resolve().parents[1] / "src/harnesslab"
    for module in (
        "external_evidence/verification.py",
        "external_evidence/service.py",
        "local_execution/sandbox.py",
        "sandbox/runner.py",
    ):
        assert "failure_diagnosis" not in (root / module).read_text()


@pytest.mark.parametrize("stall", [False, True])
async def test_external_backend_readonly_mounts_no_secret_env_and_timeout_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stall: bool
) -> None:
    from types import SimpleNamespace

    from harnesslab.failure_diagnosis import codex_backend as module

    original = item(tmp_path)
    vendor = tmp_path / "vendor"
    (vendor / "bin").mkdir(parents=True)
    (vendor / "bin/codex").write_bytes(b"FAKE_CLI")
    monkeypatch.setattr(module, "CLI_SHA256", sha256(b"FAKE_CLI"))
    credential = tmp_path / "credential-reference.json"
    credential.write_text("CREDENTIAL_CANARY_DO_NOT_READ")
    commands: list[tuple[str, ...]] = []
    prompts: list[bytes] = []
    killed: list[bool] = []
    cleanups: list[bool] = []

    class Docker:
        def __init__(self, **kwargs: Any) -> None:
            assert set(kwargs["environment"]) <= {
                "PATH",
                "HOME",
                "DOCKER_HOST",
                "DOCKER_CONTEXT",
                "XDG_RUNTIME_DIR",
            }

        async def run(self, *args: str, **kwargs: Any) -> Any:
            commands.append(args)
            if args[0] != "image":
                return SimpleNamespace(stdout=b"")
            image = [
                {
                    "Config": {
                        "Labels": {
                            "com.harnesslab.egress.version": "1.0.0",
                            "com.harnesslab.egress.base": EGRESS_PROXY_BASE.split("@")[1],
                            "com.harnesslab.egress.source": EGRESS_PROXY_SOURCE_DIGEST,
                        }
                    },
                    "Id": "sha256:" + "f" * 64,
                    "RepoDigests": [],
                }
            ]
            return SimpleNamespace(stdout=canonical(image))

    class Boundary:
        subject_network_mode = "private-internal-network"

        def subject_proxy_environment(self) -> dict[str, str]:
            return {"HTTPS_PROXY": "http://private-proxy:8080", "NO_PROXY": ""}

        async def provision(self, cli: Any) -> None:
            pass

        async def cleanup(self, cli: Any) -> None:
            cleanups.append(True)

    class Input:
        def write(self, value: bytes) -> None:
            prompts.append(value)

        async def drain(self) -> None:
            pass

        def close(self) -> None:
            pass

    class Output:
        done = False

        async def read(self, count: int) -> bytes:
            if stall:
                await asyncio.sleep(10)
            if self.done:
                return b""
            self.done = True
            return canonical(
                {
                    "type": "item.completed",
                    "item": {"type": "agent_message", "text": json.dumps(answer())},
                }
            ) + canonical(
                {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 5}}
            )

    class Process:
        returncode: int | None = None
        stdin = Input()
        stdout = Output()

        async def communicate(self) -> tuple[bytes, bytes]:
            self.returncode = 0
            return b"codex-cli 0.162.1\n", b""

        async def wait(self) -> int:
            self.returncode = 0
            return 0

        def kill(self) -> None:
            killed.append(True)

    async def spawn(*args: str, **kwargs: Any) -> Any:
        commands.append(args)
        assert "ANTHROPIC_AUTH_TOKEN" not in kwargs["env"] and "OPENAI_API_KEY" not in kwargs["env"]
        return Process()

    monkeypatch.setattr(module, "_DockerCLI", Docker)
    monkeypatch.setattr(module, "boundary_for_provider_url", lambda *a, **kw: Boundary())
    monkeypatch.setattr(asyncio, "create_subprocess_exec", spawn)
    result = await diagnose(
        original,
        module.CodexSubscriptionBackend(vendor, credential),
        timeout_seconds=0.03 if stall else 2,
    )
    assert result.fallback_reason is (FallbackReason.TIMEOUT if stall else FallbackReason.NONE)
    assert result.backend.invocation_count == 1
    assert bool(killed) is stall and cleanups == [True]
    container = next(args for args in commands if args[:2] == ("docker", "run"))
    assert "--read-only" in container and "--cap-drop=ALL" in container
    assert container[container.index("--network") + 1] == "private-internal-network"
    mounts = [container[n + 1] for n, part in enumerate(container) if part == "--volume"]
    assert len(mounts) == 3 and all(m.endswith(":ro") for m in mounts)
    assert not any("sources" in m or "oracle" in m or "hidden" in m for m in mounts)
    assert prompts == [prompt_for(original).encode()]
    assert any(args[:2] == ("rm", "--force") for args in commands)


@pytest.mark.parametrize(
    "text,category,mode",
    [
        ("TimeoutError", "超时", "规则降级"),
        ("ImportError", "构建或依赖问题", "规则降级"),
        ("AssertionError", "逻辑或算法问题", "规则降级"),
        ("只有失败标记，没有公开的原因信息", "原因未知", "诊断不可用"),
    ],
)
async def test_coarse_rules_and_unavailable_are_explicit(
    tmp_path: Path, text: str, category: str, mode: str
) -> None:
    original = item(tmp_path)
    value = original.model_dump(mode="json")
    value["evidence"]["excerpts"][2]["text"] = text
    result = await diagnose(DiagnosisInput.model_validate(value))
    assert result.explanation.category.value == category and result.mode == mode
    assert result.explanation.confidence == 0 and result.backend.invocation_count == 0
