"""Exercise the live L1 entry offline, stopping at its actual transport boundary."""

from __future__ import annotations

import json
import socket
import subprocess
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest
from scripts import lecturelens_development_execution as entry

from harnesslab.custom_eval.models import canonical_digest
from harnesslab.harness_lane.docker_backend import DockerCodexBackend
from harnesslab.harness_lane.models import CodexHarnessProfile
from harnesslab.harness_lane.profile import (
    CURRENT_CODEX_IMAGE,
    configured_responses_relay_codex_profile,
)
from harnesslab.harness_lane.prompt import render_codex_harness_prompt
from harnesslab.harness_lane.runner import CodexHarnessRunner
from harnesslab.harness_lane.transport import CodexCLITransport
from harnesslab.judgelab.runner import JudgeRunner
from harnesslab.model_lane.providers import OpenAIResponsesAdapter
from harnesslab.model_lane.runner import DirectModelRunner
from harnesslab.registry.vault import CredentialVault
from harnesslab.sandbox.docker_cli import _DockerCLI
from harnesslab.sandbox.models import ImageIdentity
from harnesslab.tasks.package import TaskPackage
from harnesslab.tasks.quality import TaskIdentity


class ExecutableBoundaryReached(Exception):
    """Stop before the CLI transport can launch a model process."""


@pytest.fixture(autouse=True)
def no_external_calls(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, int]]:
    counts = dict(provider=0, model=0, judge=0, subprocess=0, network=0, result=0)

    def reject(kind: str) -> Any:
        def call(*args: Any, **kwargs: Any) -> Any:
            counts[kind] += 1
            raise AssertionError(f"Forbidden {kind} call")

        return call

    monkeypatch.setattr(OpenAIResponsesAdapter, "invoke", reject("provider"))
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", reject("provider"))
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", reject("provider"))
    monkeypatch.setattr(DockerCodexBackend, "run", reject("model"))
    monkeypatch.setattr(DirectModelRunner, "run", reject("model"))
    monkeypatch.setattr(JudgeRunner, "run", reject("judge"))
    monkeypatch.setattr(_DockerCLI, "run", reject("subprocess"))
    monkeypatch.setattr(subprocess, "Popen", reject("subprocess"))
    monkeypatch.setattr(socket.socket, "connect", reject("network"))
    monkeypatch.setattr(socket, "getaddrinfo", reject("network"))
    monkeypatch.setattr(CodexHarnessRunner, "_persist", reject("result"))
    yield counts
    assert counts == dict(provider=0, model=0, judge=0, subprocess=0, network=0, result=0)


def bind_request(case: dict[str, Any]) -> None:
    request = case["request"]
    request["request_identity"] = canonical_digest(
        {k: v for k, v in request.items() if k != "request_identity"}
    )
    case["authorization"]["request_identity"] = request["request_identity"]


def bind_plan(case: dict[str, Any]) -> None:
    plan = case["plan"]
    plan["plan_identity"] = canonical_digest(
        {k: v for k, v in plan.items() if k != "plan_identity"}
    )
    case["request"]["plan_identity"] = case["authorization"]["plan_identity"] = plan[
        "plan_identity"
    ]
    bind_request(case)


@pytest.fixture
def case(tmp_path: Path) -> dict[str, Any]:
    package = TaskPackage.load(
        Path(__file__).resolve().parents[1] / "tasks/micro-python-clamp/1.0.0"
    )
    budget = package.definition.budget.model_dump(mode="json")
    profile = configured_responses_relay_codex_profile(
        ImageIdentity(reference=CURRENT_CODEX_IMAGE, image_id=entry.IMAGE_ID),
        requested_model="gpt-6-astra",
        execution_timeout_seconds=budget["timeout_seconds"],
    )
    raw = profile.model_dump(mode="json")
    raw["codex_image"]["reference"] = entry.IMAGE_ID
    raw["built_in_behavior_profile"] += ";request_max_retries=0;stream_max_retries=0"
    raw["subject_toolchain_profile"] += ";lecturelens-frontend-lock-84eed60a;offline-deps-v1"
    profile = CodexHarnessProfile.model_validate(raw)
    prompt = render_codex_harness_prompt(
        task_instruction=package.definition.instruction,
        task_digest=package.definition.content_digest,
        workspace_input_digest=package.definition.workspace.digest,
        context_digest=None,
        network_policy=profile.tool_network_policy,
    )
    # Synthetic single-slot plan: no historical freeze, evidence, or intake dependency.
    plan: dict[str, Any] = {
        "profile": raw,
        "profile_identity": profile.fingerprint,
        "resource_budget": budget,
        "run_order": ["A/current/1"],
        "session_output_token_cap_enforced": False,
        "candidate_freeze_identity": "sha256:" + "c" * 64,
        "tasks": {
            "A": {
                **TaskIdentity.from_package(package).model_dump(mode="json"),
                "oracle_digest": package.oracle_digest,
                "variants": {
                    "current": {
                        "prompt_identity": prompt.prompt_hash,
                        "prompt_text": prompt.text,
                        "profile_identity": profile.fingerprint,
                        "setup_identity": canonical_digest(
                            {
                                "profile": profile.fingerprint,
                                "prompt": prompt.prompt_hash,
                                "resource_budget": budget,
                            }
                        ),
                    }
                },
            }
        },
    }
    plan["plan_identity"] = canonical_digest(plan)
    vault = CredentialVault(tmp_path / "vault")
    connection = {
        "model": plan["profile"]["requested_model"],
        "model_reasoning_effort": plan["profile"]["reasoning_effort"],
        "wire_api": plan["profile"]["provider_wire_api"],
        "endpoint_vault_reference": vault.put("https://provider.example.invalid/v1"),
        "credential_vault_reference": vault.put("offline-stub-not-a-credential"),
    }
    execution_id = uuid4().hex
    request = {
        "execution_id": execution_id,
        "slot": "A/current/1",
        "image_id": plan["profile"]["codex_image"]["image_id"],
        "requested_model": plan["profile"]["requested_model"],
        "reasoning_effort": plan["profile"]["reasoning_effort"],
        "codex_cli_version": plan["profile"]["codex_cli_version"],
        "candidate_freeze_identity": plan["candidate_freeze_identity"],
        "plan_identity": plan["plan_identity"],
        "profile_identity": plan["profile_identity"],
        "connection_identity": canonical_digest(connection),
        "connection_reference": vault.put(json.dumps(connection)),
        "declared_output_tokens": package.definition.budget.max_output_tokens,
        "session_output_token_cap_enforced": False,
        "token_limitation_acceptance": "REQUIRED",
        "run_order": ["A/current/1"],
        "top_level_attempts": 1,
        "automatic_retry": False,
        "automatic_resume": False,
        "request_max_retries": 0,
        "stream_max_retries": 0,
        "judge_calls": 0,
        "subject_timeout_seconds_per_attempt": package.definition.budget.timeout_seconds,
        "verifier_timeout_seconds_per_attempt": package.manifest.verifier.timeout_seconds,
        "egress_proxy_image": {
            "reference": "harnesslab-egress-proxy:1.0.0",
            "image_id": "sha256:" + "a" * 64,
        },
    }
    now = datetime.now(UTC)
    authorization = {
        "authorization_id": uuid4().hex,
        "execution_id": execution_id,
        "slot": "A/current/1",
        "issued_at": (now - timedelta(seconds=10)).isoformat(),
        "expires_at": (now + timedelta(minutes=10)).isoformat(),
        "consumed": False,
        "execution_authorized": True,
        "plan_identity": plan["plan_identity"],
        "profile_identity": plan["profile_identity"],
        "connection_identity": request["connection_identity"],
        "declared_output_tokens": request["declared_output_tokens"],
        "session_output_token_cap_enforced": False,
        "token_limitation_acceptance": entry.TOKEN_LIMITATION_ACCEPTED,
        "judge_authorized": False,
        "top_level_attempts": 1,
    }
    data = dict(
        request=request,
        plan=plan,
        authorization=authorization,
        execution_id=execution_id,
        slot="A/current/1",
        task_path=package.root,
        prompt_addendum=None,
        vault=vault,
        output=tmp_path / "output",
    )
    bind_request(data)
    return data


@pytest.fixture
def ready(monkeypatch: pytest.MonkeyPatch, case: dict[str, Any]) -> list[str]:
    reached: list[str] = []

    async def stop(self: Any, request: Any, workspace: Any) -> Any:
        assert request.execution_id == case["execution_id"]
        assert request.profile.fingerprint == case["request"]["profile_identity"]
        assert (
            request.prompt.prompt_hash
            == case["plan"]["tasks"]["A"]["variants"]["current"]["prompt_identity"]
        )
        assert workspace.workspace.exists()
        assert isinstance(self.backend, entry.DevelopmentBackend)
        assert len(list((case["vault"].root / "l1-consumed-authorizations").iterdir())) == 2
        reached.append(request.execution_id)
        raise ExecutableBoundaryReached

    monkeypatch.setattr(CodexCLITransport, "execute", stop)
    return reached


@pytest.mark.parametrize("missing", [None, {}, {"execution_authorized": False}])
async def test_missing_authorization_rejects_before_vault_or_runner(
    case: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
    missing: Any,
) -> None:
    case["authorization"] = missing
    monkeypatch.setattr(case["vault"], "read", lambda _: pytest.fail("Vault read before consent"))
    with pytest.raises(ValueError, match="authorization"):
        await entry.run_development_attempt(**case)
    assert not case["output"].exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("execution_authorized", False),
        ("token_limitation_acceptance", "implicit"),
        ("session_output_token_cap_enforced", True),
        ("declared_output_tokens", 7000),
        ("declared_output_tokens", 2000.0),
        ("consumed", True),
        ("consumed", None),
        ("execution_id", "b" * 32),
        ("slot", "A/candidate/1"),
        ("request_identity", "sha256:" + "b" * 64),
        ("plan_identity", "sha256:" + "b" * 64),
        ("profile_identity", "sha256:" + "b" * 64),
        ("connection_identity", "sha256:" + "b" * 64),
        ("issued_at", "2000-01-01T00:00:00+00:00"),
        ("issued_at", "2100-01-01T00:00:00+00:00"),
        ("expires_at", "2000-01-01T00:00:00+00:00"),
        ("expires_at", "2100-01-01T00:00:00+00:00"),
        ("issued_at", "2026-09-20T00:00:00"),
        ("expires_at", None),
        ("authorization_id", "../unsafe"),
        ("judge_authorized", True),
    ],
)
async def test_authorization_rejections(
    case: dict[str, Any],
    ready: list[str],
    field: str,
    value: Any,
) -> None:
    case["authorization"][field] = value
    with pytest.raises(ValueError):
        await entry.run_development_attempt(**case)
    assert ready == []
    assert not case["output"].exists()
    assert not (case["vault"].root / "l1-consumed-authorizations").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("declared_output_tokens", 7000),
        ("session_output_token_cap_enforced", True),
        ("token_limitation_acceptance", "ACCEPTED"),
        ("subject_timeout_seconds_per_attempt", 600),
        ("verifier_timeout_seconds_per_attempt", 600),
        ("run_order", ["A/current/1", "B/current/1"]),
        ("automatic_retry", True),
        ("automatic_resume", True),
        ("request_max_retries", 1),
        ("stream_max_retries", 1),
        ("judge_calls", 1),
        ("top_level_attempts", 4),
        ("image_id", "sha256:" + "b" * 64),
        ("requested_model", "different-model"),
        ("reasoning_effort", "medium"),
        ("codex_cli_version", "0.0.0"),
        ("candidate_freeze_identity", "sha256:" + "b" * 64),
    ],
)
async def test_resigned_request_still_must_match_effective_controls(
    case: dict[str, Any],
    field: str,
    value: Any,
) -> None:
    case["request"][field] = value
    if field == "declared_output_tokens":
        case["authorization"][field] = value
    bind_request(case)
    with pytest.raises(ValueError):
        await entry.run_development_attempt(**case)
    assert not case["output"].exists()


@pytest.mark.parametrize(
    "mutation",
    [
        "request-content",
        "plan-content",
        "profile",
        "task",
        "setup",
        "connection",
        "prompt",
        "execution",
        "slot",
    ],
)
async def test_effective_input_drift_rejects(case: dict[str, Any], mutation: str) -> None:
    if mutation == "request-content":
        case["request"]["unapproved"] = True
    elif mutation == "plan-content":
        case["plan"]["unapproved"] = True
    elif mutation == "profile":
        case["plan"]["profile"]["reasoning_effort"] = "medium"
        bind_plan(case)
    elif mutation == "task":
        case["plan"]["tasks"]["A"]["task_digest"] = "sha256:" + "b" * 64
        bind_plan(case)
    elif mutation == "setup":
        case["plan"]["tasks"]["A"]["variants"]["current"]["setup_identity"] = "sha256:" + "b" * 64
        bind_plan(case)
    elif mutation == "connection":
        connection = json.loads(case["vault"].read(case["request"]["connection_reference"]))
        connection["model"] = "different-model"
        case["request"]["connection_reference"] = case["vault"].put(json.dumps(connection))
        bind_request(case)
    elif mutation == "prompt":
        case["prompt_addendum"] = "Unapproved prompt"
    elif mutation == "execution":
        case["execution_id"] = uuid4().hex
    else:
        case["slot"] = "B/current/1"
    with pytest.raises(ValueError):
        await entry.run_development_attempt(**case)
    assert not case["output"].exists()


async def test_success_reaches_real_runner_transport_but_does_not_execute(
    case: dict[str, Any],
    ready: list[str],
) -> None:
    with pytest.raises(ExecutableBoundaryReached):
        await entry.run_development_attempt(**case)
    assert ready == [case["execution_id"]]
    assert not list(case["output"].rglob("*.json"))
    assert not list((case["output"] / "runs").iterdir())


async def test_restart_and_different_output_cannot_reuse_authorization(
    case: dict[str, Any],
    ready: list[str],
) -> None:
    with pytest.raises(ExecutableBoundaryReached):
        await entry.run_development_attempt(**case)
    case["output"] = case["output"].parent / "another-output"
    case["vault"] = CredentialVault(case["vault"].root)
    with pytest.raises(ValueError, match="already consumed"):
        await entry.run_development_attempt(**case)
    assert ready == [case["execution_id"]]
    assert not case["output"].exists()


async def test_preparation_failure_consumes_authorization_without_results(
    case: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    read = case["vault"].read
    reference = case["request"]["connection_reference"]

    def fail_credentials(ref: str) -> str:
        if ref != reference:
            raise RuntimeError("offline credential preparation failure")
        return str(read(ref))

    monkeypatch.setattr(case["vault"], "read", fail_credentials)
    with pytest.raises(RuntimeError, match="preparation failure"):
        await entry.run_development_attempt(**case)
    with pytest.raises(ValueError, match="already consumed"):
        await entry.run_development_attempt(**case)
    assert not case["output"].exists()


@pytest.mark.parametrize("reuse", ["authorization", "execution"])
async def test_identity_cannot_be_reused_with_a_new_partner(
    case: dict[str, Any],
    ready: list[str],
    reuse: str,
) -> None:
    with pytest.raises(ExecutableBoundaryReached):
        await entry.run_development_attempt(**case)
    case["output"] = case["output"].parent / "new-output"
    if reuse == "authorization":
        case["execution_id"] = uuid4().hex
        case["request"]["execution_id"] = case["authorization"]["execution_id"] = case[
            "execution_id"
        ]
        bind_request(case)
    else:
        case["authorization"]["authorization_id"] = uuid4().hex
    with pytest.raises(ValueError, match="already consumed"):
        await entry.run_development_attempt(**case)
    assert len(ready) == 1
    assert not case["output"].exists()


def test_concurrent_entry_consumes_approval_once(case: dict[str, Any], ready: list[str]) -> None:
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    barrier = Barrier(2)

    def attempt(index: int) -> str:
        local = {**case, "output": case["output"].parent / f"concurrent-{index}"}
        barrier.wait(timeout=5)
        try:
            asyncio.run(entry.run_development_attempt(**local))
        except ExecutableBoundaryReached:
            return "READY"
        except ValueError as error:
            assert "already consumed" in str(error)
            assert not local["output"].exists()
            return "REJECTED"
        pytest.fail("Unexpected execution")

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, (0, 1))) == ["READY", "REJECTED"]
    assert len(ready) == 1


async def test_runner_rechecks_actual_loaded_inputs_before_transport(
    case: dict[str, Any],
    ready: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import replace

    original = TaskPackage.load
    loads = 0

    def changed_load(path: Path) -> TaskPackage:
        nonlocal loads
        package = original(path)
        loads += 1
        if loads == 2:
            return replace(
                package,
                definition=package.definition.model_copy(
                    update={"instruction": "Changed after gate validation"},
                ),
            )
        return package

    monkeypatch.setattr(TaskPackage, "load", changed_load)
    with pytest.raises(ValueError, match="Runner inputs changed"):
        await entry.run_development_attempt(**case)
    assert loads == 2
    assert ready == []
    assert not list(case["output"].rglob("*.json"))
    assert not list((case["output"] / "runs").iterdir())


async def test_authorization_expiring_during_preparation_cannot_reach_transport(
    case: dict[str, Any],
    ready: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime.now(UTC)

    class PreparationClock(datetime):
        reads = 0

        @classmethod
        def now(cls, tz: Any = None) -> PreparationClock:
            cls.reads += 1
            value = now if cls.reads < 3 else now + timedelta(hours=1)
            return cls.fromisoformat(value.isoformat())

    monkeypatch.setattr(entry, "datetime", PreparationClock)
    with pytest.raises(ValueError, match="expired before transport"):
        await entry.run_development_attempt(**case)
    assert ready == []
    assert not list(case["output"].rglob("*.json"))


async def test_live_entry_uses_existing_budget_validator(
    case: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = []

    def reject(request: Any, authorization: Any) -> None:
        calls.append((request, authorization))
        raise ValueError("existing validator rejection")

    monkeypatch.setattr(entry, "validate_execution_budget_contract", reject)
    with pytest.raises(ValueError, match="existing validator rejection"):
        await entry.run_development_attempt(**case)
    assert calls == [(case["request"], case["authorization"])]
    assert not case["output"].exists()


def test_cli_dispatches_only_through_guarded_entry(
    case: dict[str, Any],
    ready: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import sys

    root = case["output"].parent
    arguments = ["lecturelens_development_execution"]
    for key in ("request", "plan", "authorization"):
        path = root / f"{key}.json"
        path.write_text(json.dumps(case[key]))
        arguments.extend(["--" + key, str(path)])
    for key, value in {
        "task": case["task_path"],
        "vault": case["vault"].root,
        "output": case["output"],
        "execution-id": case["execution_id"],
        "slot": case["slot"],
    }.items():
        arguments.extend(["--" + key, str(value)])
    monkeypatch.setattr(sys, "argv", arguments)
    with pytest.raises(ExecutableBoundaryReached):
        entry.main()
    assert ready == [case["execution_id"]]
    assert not list(case["output"].rglob("*.json"))
