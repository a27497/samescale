from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import AsyncIterator, Callable
from decimal import Decimal
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from harnesslab.analyst import real_backend, sessions
from harnesslab.analyst.backend import FakeAnalystBackend, ScriptedFakeAnalystBackend
from harnesslab.analyst.graph import AttributionGraph
from harnesslab.analyst.models import (
    AbstainDecision,
    InvestigationState,
    ProposedRegressionPlan,
    QueryRunsArgs,
    QueryRunsCall,
    ToolDecision,
    ToolName,
)
from harnesslab.analyst.real_backend import (
    DecisionUsage,
    RealAnalystBackend,
    decision_json_schema,
)
from harnesslab.analyst.sessions import (
    AnalystSessionError,
    AnalystSessions,
    ApprovalRequest,
    CreateInvestigation,
)
from harnesslab.budget.models import AnalystSpendLimits
from harnesslab.core.config import Settings
from harnesslab.db.models.experiment import ExperimentRecord, ExperimentRunRecord
from harnesslab.db.session import create_engine
from harnesslab.experiment.plan import build_experiment_plan
from harnesslab.experiment.queue import enqueue_plan
from harnesslab.model_lane.models import (
    ProviderIncompleteReason,
    ProviderRequest,
    ProviderResult,
    ProviderUsage,
)
from harnesslab.model_lane.providers import OpenAIResponsesAdapter
from tests.phase_g_helpers import ROOT, basic_spec


@pytest.fixture
async def service(
    database_url: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[AnalystSessions, str]]:
    resolve = real_backend.resolve_analyst_profile
    monkeypatch.setattr(
        sessions,
        "resolve_analyst_profile",
        lambda *a, **k: resolve(*a, **k).model_copy(update={"context_window_tokens": 1000}),
    )
    engine = create_engine(Settings.without_dotenv(database_url=database_url))
    experiment_id = "agent-keyless-" + uuid4().hex[:12]
    spec = basic_spec(repeat_count=1)
    spec = spec.model_copy(
        update={"experiment_id": experiment_id, "cells": (spec.cells[0],), "paired_comparisons": ()}
    )
    async with AsyncSession(engine) as session, session.begin():
        await enqueue_plan(session, build_experiment_plan(spec, ROOT))
    value = AnalystSessions(
        engine,
        repository_root=ROOT,
        artifact_roots=(tmp_path,),
        environment={
            "HARNESSLAB_GPT56_RELAY_API_KEY": "keyless-placeholder",
            "HARNESSLAB_GPT56_RELAY_BASE_URL": "https://provider.example",
        },
        real_enabled=True,
    )
    try:
        yield value, experiment_id
    finally:
        async with AsyncSession(engine) as session, session.begin():
            await session.execute(
                delete(ExperimentRecord).where(ExperimentRecord.id == experiment_id)
            )
        await engine.dispose()


class RecordingAdapter:
    def __init__(self, choose: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
        self.choose = choose
        self.requests: list[ProviderRequest] = []

    async def invoke(self, request: ProviderRequest) -> ProviderResult:
        self.requests.append(request)
        assert request.output_json_schema is not None
        data = json.loads(request.input)
        return ProviderResult(
            requested_model=request.profile.requested_model,
            provider=request.profile.provider,
            endpoint_identity=request.profile.provider_route_identity,
            protocol=request.profile.protocol,
            public_output_text=json.dumps({"decision": self.choose(data)}),
            observed_model=request.profile.requested_model,
            latency_ms=7,
            usage=ProviderUsage(input_tokens=10, output_tokens=20, total_tokens=30),
        )


def query(limit: int = 1) -> dict[str, Any]:
    return {"kind": "tools", "calls": [{"name": "query_runs", "arguments": {"limit": limit}}]}


def spend_limits(**updates: Any) -> AnalystSpendLimits:
    return AnalystSpendLimits.model_validate(
        {
            "provider_requests": 8,
            "output_tokens_per_request": 2000,
            "input_bytes_per_request": 256_000,
            "cumulative_tokens": 24_000,
            "timeout_seconds": 60,
            **updates,
        }
    )


async def real_session(service: AnalystSessions, experiment: str) -> sessions.AnalystSession:
    return await service.create(
        CreateInvestigation(
            experiment_id=experiment,
            question="Inspect the failure.",
            backend="real",
            provider_profile_id="gpt56-relay-gpt56-responses",
            spend_limits=spend_limits(),
        )
    )


async def test_real_dynamic_choices_resume_usage_and_abstention(
    service: tuple[AnalystSessions, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    api, experiment = service

    def choose(data: dict[str, Any]) -> dict[str, Any]:
        if not data["evidence"]:
            return query()
        if len(data["completed_calls"]) == 1:
            run_id = data["evidence"][0]["data_by_tool"]["query_runs"]["run_id"]
            return {
                "kind": "tools",
                "calls": [{"name": "inspect_failure", "arguments": {"run_id": run_id}}],
            }
        return {"kind": "abstain", "reason": "This run has no completed verifier evidence."}

    adapter = RecordingAdapter(choose)
    monkeypatch.setattr(real_backend, "adapter_for_profile", lambda *a, **k: adapter)
    value = await real_session(api, experiment)
    assert adapter.requests == []  # Creation is always keyless.
    value = await api.resume(value.session_id, confirm_real=True)
    assert value.state.tool_calls == 1 and value.status == "PAUSED"
    # A fresh service/process reads durable state; the backend is reconstructed from the profile.
    restored = AnalystSessions(
        api.engine,
        repository_root=ROOT,
        artifact_roots=api.artifact_roots,
        environment=api.environment,
        real_enabled=True,
    )
    value = await restored.resume(value.session_id, confirm_real=True)
    value = await restored.resume(value.session_id, confirm_real=True)
    assert value.status == "ABSTAINED"
    assert value.state.decision_iterations == 3 and value.state.tool_calls == 2
    assert [r.status for r in value.state.completed_calls] == ["COMPLETED", "COMPLETED"]
    assert len(value.usage) == len(adapter.requests) == 3
    view = value.public_view()
    assert view["totals"] == {
        "input_tokens": 30,
        "output_tokens": 60,
        "total_tokens": 90,
        "cost_usd": None,
        "latency_ms": 21,
    }
    assert view["provider"] == adapter.requests[0].profile.provider
    assert view["route"] == adapter.requests[0].profile.provider_route_identity
    assert "credential_reference" not in json.dumps(view) and "runtime" not in view
    assert (await api.resume(value.session_id)).status == "ABSTAINED"
    assert len(adapter.requests) == 3


@pytest.mark.parametrize(
    "response",
    [
        {"kind": "tools", "calls": [{"name": "shell", "arguments": {"command": "bad"}}]},
        {"kind": "tools", "calls": [{"name": "query_runs", "arguments": {"limit": "1"}}]},
        {"kind": "tools", "calls": [{"name": "query_runs", "arguments": {"sql": "SELECT 1"}}]},
        {
            "kind": "final",
            "draft": {
                "summary": "Unsupported",
                "claims": [
                    {
                        "classification": "HYPOTHESIS",
                        "statement": "Guess",
                        "evidence_refs": ["run:invented"],
                        "additional_evidence_needed": "A verifier",
                    }
                ],
            },
        },
    ],
)
async def test_invalid_decisions_and_fake_citations_fail_closed(
    service: tuple[AnalystSessions, str], monkeypatch: pytest.MonkeyPatch, response: dict[str, Any]
) -> None:
    api, experiment = service
    adapter = RecordingAdapter(lambda _: response)
    monkeypatch.setattr(real_backend, "adapter_for_profile", lambda *a, **k: adapter)
    monkeypatch.setattr(
        FakeAnalystBackend, "decide", lambda *a, **k: pytest.fail("real must not fall back to Fake")
    )
    value = await real_session(api, experiment)
    value = await api.resume(value.session_id, confirm_real=True)
    assert value.state.report is None
    assert value.state.tool_calls == 0 and value.state.decision_iterations == len(value.usage) == 1
    if response["kind"] == "final":
        assert value.status == "PAUSED" and value.state.error is None
        assert value.state.finalization_rejections == ("MISSING_EVIDENCE",)
    else:
        assert value.status == "FAILED"
    assert (await api.get(value.session_id)).state == value.state


async def test_invalid_final_draft_gets_bounded_host_feedback_and_can_repair(
    service: tuple[AnalystSessions, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    api, experiment = service

    def choose(data: dict[str, Any]) -> dict[str, Any]:
        if not data["finalization_rejections"]:
            return {
                "kind": "final",
                "draft": {
                    "summary": "Unsupported first draft",
                    "claims": [
                        {
                            "classification": "HYPOTHESIS",
                            "statement": "Guess",
                            "evidence_refs": ["run:invented"],
                            "additional_evidence_needed": "A verifier",
                        }
                    ],
                },
            }
        assert data["finalization_rejections"] == ["MISSING_EVIDENCE"]
        return {
            "kind": "final",
            "draft": {
                "summary": "No evidence-backed fact is established.",
                "claims": [],
                "limitations": ["The prior final draft cited evidence outside the catalog."],
            },
        }

    adapter = RecordingAdapter(choose)
    monkeypatch.setattr(real_backend, "adapter_for_profile", lambda *a, **k: adapter)
    value = await real_session(api, experiment)
    first = await api.resume(value.session_id, confirm_real=True)
    assert first.status == "PAUSED" and first.state.error is None
    assert first.state.finalization_rejections == ("MISSING_EVIDENCE",)
    assert len(first.usage) == 1
    assert (await api.preflight(value.session_id))["status"] == "READY"

    repaired = await api.resume(value.session_id, confirm_real=True)
    assert repaired.status == "COMPLETED" and repaired.state.report is not None
    assert repaired.state.finalization_rejections == ("MISSING_EVIDENCE",)
    assert repaired.state.report.verified_facts == ()
    assert len(repaired.usage) == len(adapter.requests) == 2
    second_payload = json.loads(adapter.requests[1].input)
    assert second_payload["finalization_rejections"] == ["MISSING_EVIDENCE"]


async def test_invalid_final_draft_fails_closed_when_decision_budget_is_exhausted(
    service: tuple[AnalystSessions, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    api, experiment = service
    adapter = RecordingAdapter(
        lambda _: {
            "kind": "final",
            "draft": {
                "summary": "Unsupported",
                "claims": [
                    {
                        "classification": "HYPOTHESIS",
                        "statement": "Guess",
                        "evidence_refs": ["run:invented"],
                        "additional_evidence_needed": "A verifier",
                    }
                ],
            },
        }
    )
    monkeypatch.setattr(real_backend, "adapter_for_profile", lambda *a, **k: adapter)
    value = await api.create(
        CreateInvestigation(
            experiment_id=experiment,
            question="Inspect the failure.",
            backend="real",
            provider_profile_id="gpt56-relay-gpt56-responses",
            decision_limit=1,
            spend_limits=spend_limits(provider_requests=1),
        )
    )
    failed = await api.resume(value.session_id, confirm_real=True)
    assert failed.status == "FAILED" and failed.state.error == "INVALID_ATTRIBUTION"
    assert failed.state.finalization_rejections == ("MISSING_EVIDENCE",)
    assert len(failed.usage) == len(adapter.requests) == 1


async def test_valid_json_out_of_scope_tool_is_rejected_by_host(
    service: tuple[AnalystSessions, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    api, experiment = service
    adapter = RecordingAdapter(
        lambda _: {
            "kind": "tools",
            "calls": [{"name": "inspect_trace", "arguments": {"run_id": "other-experiment-run"}}],
        }
    )
    monkeypatch.setattr(real_backend, "adapter_for_profile", lambda *a, **k: adapter)
    value = await real_session(api, experiment)
    value = await api.resume(value.session_id, confirm_real=True)
    assert value.state.completed_calls[0].status == "FAILED" and value.state.evidence == ()


@pytest.mark.parametrize("failure", ["exception", "timeout"])
async def test_real_failure_never_falls_back_or_refunds_usage(
    service: tuple[AnalystSessions, str], monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    api, experiment = service

    class FailureAdapter:
        async def invoke(self, request: ProviderRequest) -> ProviderResult:
            raise (
                TimeoutError() if failure == "timeout" else RuntimeError("api_key=PRIVATE_SENTINEL")
            )

    monkeypatch.setattr(real_backend, "adapter_for_profile", lambda *a, **k: FailureAdapter())
    monkeypatch.setattr(FakeAnalystBackend, "decide", lambda *a, **k: pytest.fail("Fake fallback"))
    value = await real_session(api, experiment)
    value = await api.resume(value.session_id, confirm_real=True)
    assert value.status == "FAILED" and value.state.decision_iterations == 1
    assert len(value.usage) == 1
    assert value.usage[0].failure is not None
    assert value.usage[0].failure.category == (
        "timeout" if failure == "timeout" else "provider_error"
    )
    if failure == "timeout":
        assert value.usage[0].failure.timeout_phase == "unknown"
    assert value.public_view()["totals"]["total_tokens"] is None
    assert "PRIVATE_SENTINEL" not in value.model_dump_json()
    with pytest.raises(AnalystSessionError, match="TOKEN_USAGE_UNKNOWN"):
        await api.resume(value.session_id, confirm_real=True)
    assert len((await api.get(value.session_id)).usage) == 1


@pytest.mark.parametrize(
    ("case", "category", "status", "response_status", "timeout_phase"),
    [
        ("400", "http_error", 400, None, None),
        ("401", "authentication", 401, None, None),
        ("403", "authentication", 403, None, None),
        ("429", "rate_limit", 429, None, None),
        ("500", "http_error", 500, None, None),
        ("503", "http_error", 503, None, None),
        ("failed", "provider_error", 200, "failed", None),
        ("unsafe-status", "provider_error", 200, None, None),
        ("invalid-json", "malformed_response", 200, None, None),
        ("incomplete", "incomplete_response", 200, "incomplete", None),
        ("read-timeout", "timeout", None, None, "read"),
        ("body-timeout", "timeout", 200, None, "read"),
        ("connect-timeout", "timeout", None, None, "connect"),
    ],
)
async def test_failure_metadata_is_durable_bounded_and_never_refunds_or_falls_back(
    service: tuple[AnalystSessions, str],
    monkeypatch: pytest.MonkeyPatch,
    case: str,
    category: str,
    status: int | None,
    response_status: str | None,
    timeout_phase: str | None,
) -> None:
    api, experiment = service
    calls = 0
    # Exercise raw metadata containing both arbitrary private text and the mock credential.
    private = "PRIVATE_SENTINEL keyless-placeholder"
    request_id = "req-" + private
    reserved: list[DecisionUsage] = []

    async def reply(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        assert json.loads(request.content)["text"]["format"] == {
            "type": "json_schema",
            "name": "structured_output",
            "schema": decision_json_schema(),
        }
        saved = await api.get(value.session_id)
        reserved.append(saved.usage[0])
        assert saved.usage[0].status == "RESERVED"
        if case == "read-timeout":
            raise httpx.ReadTimeout(private, request=request)
        if case == "connect-timeout":
            raise httpx.ConnectTimeout(private, request=request)
        headers = {"x-request-id": request_id, "x-private": private}
        if case == "body-timeout":

            class TimeoutBody(httpx.AsyncByteStream):
                async def __aiter__(self) -> AsyncIterator[bytes]:
                    yield private.encode()
                    raise httpx.ReadTimeout(private, request=request)

            return httpx.Response(200, stream=TimeoutBody(), headers=headers)
        if case == "incomplete":
            return httpx.Response(
                200,
                headers=headers,
                json={"status": "incomplete", "incomplete_details": {"reason": "content_filter"}},
            )
        if case == "invalid-json":
            return httpx.Response(200, content=private, headers=headers)
        return httpx.Response(
            status or 200,
            headers=headers,
            json={
                "status": private if case == "unsafe-status" else "failed",
                "error": {"message": private, "type": private},
            },
        )

    monkeypatch.setattr(FakeAnalystBackend, "decide", lambda *a, **k: pytest.fail("Fake fallback"))
    api.environment = {"DEEPSEEK_API_KEY": "keyless-placeholder"}
    value = await api.create(
        CreateInvestigation(
            experiment_id=experiment,
            question="Inspect the failure.",
            backend="real",
            provider_profile_id="deepseek-official-v4flash-responses",
            spend_limits=spend_limits(output_tokens_per_request=1200, usd="0.50"),
        )
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as client:
        monkeypatch.setattr(
            real_backend,
            "adapter_for_profile",
            lambda *a, **k: OpenAIResponsesAdapter(client=client, environment=api.environment),
        )
        failed = await api.resume(value.session_id, confirm_real=True)
        # Reconstruct service and deserialize from PostgreSQL, including the public projection.
        restored = AnalystSessions(
            api.engine,
            repository_root=ROOT,
            artifact_roots=api.artifact_roots,
            environment=api.environment,
            real_enabled=True,
        )
        saved = await restored.get(value.session_id)
        assert saved == failed
        assert saved.status == "FAILED" and saved.state.error == "BACKEND_DECISION_FAILED"
        assert saved.state.tool_calls == 0 and saved.state.decision_iterations == 1
        usage = saved.usage[0]
        assert usage.status == "FAILED" and usage.invocation_started is True
        assert usage.latency_ms is not None
        assert usage.reserved_resources == reserved[0].reserved_resources is not None
        assert usage.reserved_cost_usd == reserved[0].reserved_cost_usd
        assert usage.reserved_cost_usd is not None and usage.reserved_cost_usd > 0
        metadata = saved.public_view()["usage"][0]["failure"]
        assert metadata["category"] == category
        assert metadata["status_code"] == status
        assert metadata["response_status"] == response_status
        assert metadata["timeout_phase"] == timeout_phase
        assert metadata["request_id_sha256"] == (
            "sha256:" + hashlib.sha256(request_id.encode()).hexdigest() if status else None
        )
        if case == "read-timeout":
            assert metadata["read_timeout_stage"] == "waiting_for_response_headers"
        if case == "body-timeout":
            assert metadata["read_timeout_stage"] == "reading_response_body"
        if case == "incomplete":
            assert metadata["incomplete_reason"] == "content_filter"
        assert len(json.dumps(metadata)) < 600
        assert "PRIVATE_SENTINEL" not in saved.model_dump_json()
        assert "keyless-placeholder" not in saved.model_dump_json()
        assert usage.tokens.total_tokens is None and usage.cost_usd is None
        before = saved.usage
        preflight = await restored.preflight(value.session_id)
        assert preflight["status"] == "BLOCKED"
        assert "TOKEN_USAGE_UNKNOWN_OR_INCONSISTENT" in preflight["reasons"]
        assert "COST_USAGE_UNKNOWN" in preflight["reasons"]
        with pytest.raises(AnalystSessionError, match="TOKEN_USAGE_UNKNOWN"):
            await restored.resume(value.session_id, confirm_real=True)
        assert (await restored.get(value.session_id)).usage == before
    assert calls == 1


async def test_max_output_incomplete_result_preserves_failure_metadata_and_usage(
    service: tuple[AnalystSessions, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    api, experiment = service
    request_id = "resp-max-output-1"

    class IncompleteAdapter:
        async def invoke(self, request: ProviderRequest) -> ProviderResult:
            return ProviderResult(
                requested_model=request.profile.requested_model,
                observed_model=request.profile.requested_model,
                provider=request.profile.provider,
                endpoint_identity=request.profile.provider_route_identity,
                protocol=request.profile.protocol,
                request_id=request_id,
                public_output_text="",
                usage=ProviderUsage(
                    input_tokens=10,
                    output_tokens=2000,
                    total_tokens=2010,
                    reasoning_tokens=2000,
                ),
                stop_reason="max_output_tokens",
                response_status="incomplete",
                incomplete_reason=ProviderIncompleteReason.MAX_OUTPUT_TOKENS,
                latency_ms=9,
            )

    monkeypatch.setattr(real_backend, "adapter_for_profile", lambda *a, **k: IncompleteAdapter())
    value = await real_session(api, experiment)
    failed = await api.resume(value.session_id, confirm_real=True)

    assert failed.status == "FAILED" and failed.state.error == "BACKEND_DECISION_FAILED"
    assert failed.state.decision_iterations == 1 and failed.state.tool_calls == 0
    usage = failed.usage[0]
    assert usage.status == "FAILED" and usage.invocation_started is True
    assert usage.tokens == ProviderUsage(
        input_tokens=10, output_tokens=2000, total_tokens=2010, reasoning_tokens=2000
    )
    assert usage.failure is not None
    assert usage.failure.category == "incomplete_response"
    assert usage.failure.response_status == "incomplete"
    assert usage.failure.incomplete_reason == "max_output_tokens"
    assert usage.failure.request_id_sha256 == (
        "sha256:" + hashlib.sha256(request_id.encode()).hexdigest()
    )
    preflight = await api.preflight(value.session_id)
    assert preflight["status"] == "BLOCKED"
    assert "OUTPUT_TOKEN_CEILING_REACHED" in preflight["reasons"]


async def test_real_requires_explicit_enablement_and_confirmation(
    service: tuple[AnalystSessions, str],
) -> None:
    api, experiment = service
    value = await real_session(api, experiment)
    with pytest.raises(AnalystSessionError, match="explicit"):
        await api.resume(value.session_id)
    api.real_enabled = False
    with pytest.raises(AnalystSessionError, match="server enablement"):
        await api.resume(value.session_id, confirm_real=True)
    assert (await api.get(value.session_id)).state.decision_iterations == 0


async def test_completed_calls_are_cached_and_decision_budget_is_never_reset(
    service: tuple[AnalystSessions, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    api, experiment = service
    adapter = RecordingAdapter(lambda _: query())
    monkeypatch.setattr(real_backend, "adapter_for_profile", lambda *a, **k: adapter)
    value = await real_session(api, experiment)
    for _ in range(9):
        value = await api.resume(value.session_id, confirm_real=True)
    assert value.status == "LIMIT_REACHED"
    assert value.state.tool_calls == 1
    assert value.state.decision_iterations == len(adapter.requests) == len(value.usage) == 8
    assert len(value.state.completed_calls) == 1
    assert (await api.resume(value.session_id)).state.tool_calls == 1


async def test_twelve_distinct_tool_calls_limit_survives_resume(
    service: tuple[AnalystSessions, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    api, experiment = service

    def choose(data: dict[str, Any]) -> dict[str, Any]:
        start = (data["iteration"] - 1) * 6
        return {"kind": "tools", "calls": [query(start + i + 1)["calls"][0] for i in range(6)]}

    adapter = RecordingAdapter(choose)
    monkeypatch.setattr(real_backend, "adapter_for_profile", lambda *a, **k: adapter)
    value = await real_session(api, experiment)
    for _ in range(3):
        value = await api.resume(value.session_id, confirm_real=True)
    assert value.status == "LIMIT_REACHED" and value.state.tool_calls == 12
    assert len(value.state.completed_calls) == 12


class SimulatedCrash(BaseException):
    pass


async def test_resume_after_partial_tool_batch_does_not_repeat_completed_calls(
    service: tuple[AnalystSessions, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    api, experiment = service
    adapter = RecordingAdapter(
        lambda _: {"kind": "tools", "calls": [query(1)["calls"][0], query(2)["calls"][0]]}
    )
    monkeypatch.setattr(real_backend, "adapter_for_profile", lambda *a, **k: adapter)
    value = await real_session(api, experiment)
    original_save = api._save

    async def crash_after_first(session: AsyncSession, saved: sessions.AnalystSession) -> None:
        await original_save(session, saved)
        if (
            len(saved.state.completed_calls) == 1
            and saved.state.completed_calls[0].status == "COMPLETED"
        ):
            raise SimulatedCrash()

    monkeypatch.setattr(api, "_save", crash_after_first)
    with pytest.raises(SimulatedCrash):
        await api.resume(value.session_id, confirm_real=True)
    monkeypatch.setattr(api, "_save", original_save)
    restored = await api.get(value.session_id)
    assert restored.state.tool_calls == 1 and restored.state.decision_iterations == 1
    restored = await api.resume(value.session_id, confirm_real=True)
    assert restored.state.tool_calls == 2 and restored.state.decision_iterations == 1
    assert len(adapter.requests) == 1  # Saved decision and first completed tool were not replayed.
    assert [c.status for c in restored.state.completed_calls] == ["COMPLETED", "COMPLETED"]


async def test_interrupted_provider_reservation_is_not_refunded(
    service: tuple[AnalystSessions, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    api, experiment = service

    class CrashAdapter:
        async def invoke(self, request: ProviderRequest) -> ProviderResult:
            raise SimulatedCrash()

    monkeypatch.setattr(real_backend, "adapter_for_profile", lambda *a, **k: CrashAdapter())
    value = await real_session(api, experiment)
    with pytest.raises(SimulatedCrash):
        await api.resume(value.session_id, confirm_real=True)
    saved = await api.get(value.session_id)
    assert saved.status == "RUNNING" and len(saved.usage) == 1
    adapter = RecordingAdapter(lambda _: {"kind": "abstain", "reason": "No evidence."})
    monkeypatch.setattr(real_backend, "adapter_for_profile", lambda *a, **k: adapter)
    with pytest.raises(AnalystSessionError, match="TOKEN_USAGE_UNKNOWN"):
        await api.resume(value.session_id, confirm_real=True)
    saved = await api.get(value.session_id)
    assert saved.state.decision_iterations == 1 and len(saved.usage) == 1
    assert saved.usage[0].status == "INTERRUPTED"
    assert saved.public_view()["totals"]["total_tokens"] is None
    assert adapter.requests == []


async def test_tool_timeout_consumes_budget_and_returns_bounded_error(
    service: tuple[AnalystSessions, str],
) -> None:
    api, experiment = service
    saved = await api.create(CreateInvestigation(experiment_id=experiment, question="Timeout test"))

    class SlowTools:
        async def execute(self, call: Any) -> Any:
            await asyncio.sleep(60)

    states: list[InvestigationState] = []

    async def persist(value: InvestigationState) -> None:
        states.append(value)

    backend = ScriptedFakeAnalystBackend(
        (ToolDecision(calls=(QueryRunsCall(name=ToolName.QUERY_RUNS, arguments=QueryRunsArgs()),)),)
    )
    graph = AttributionGraph(
        backend, SlowTools(), persist=persist, single_step=True, tool_timeout_seconds=0.001
    )
    state = await graph.advance(saved.state)
    assert state.tool_calls == 1 and state.completed_calls[0].status == "TIMEOUT"
    assert any(s.inflight == "tool" and s.tool_calls == 1 for s in states)


async def test_approval_is_bound_and_content_changes_invalidate_without_execution(
    service: tuple[AnalystSessions, str],
) -> None:
    api, experiment = service
    value = await api.create(CreateInvestigation(experiment_id=experiment, question="Inspect"))
    value = await api.resume(value.session_id)
    plan = ProposedRegressionPlan(
        objective="Verify this case",
        task_ids=value.state.scope.task_ids,
        cell_ids=value.state.scope.cell_ids,
        evidence_refs=(value.state.evidence[0].ref.id,),
        acceptance_criteria=("Deterministic verification passes.",),
    )
    value = await api.propose(value.session_id, plan)
    assert value.proposal_digest is not None
    request = ApprovalRequest(
        scope_digest=value.scope_digest,
        proposal_digest=value.proposal_digest,
        reviewed_by="local-reviewer",
    )
    value = await api.approve(value.session_id, request)
    assert value.approval is not None and not value.approval.execution_authorized
    original_calls = value.state.tool_calls
    value = await api.propose(
        value.session_id, plan.model_copy(update={"objective": "Changed objective"})
    )
    assert value.approval is None
    with pytest.raises(AnalystSessionError, match="approval"):
        await api.approve(value.session_id, request)
    second = await api.create(CreateInvestigation(experiment_id=experiment, question="Inspect"))
    second = await api.resume(second.session_id)
    await api.propose(second.session_id, plan)
    with pytest.raises(AnalystSessionError, match="approval"):
        await api.approve(second.session_id, request)
    assert value.state.tool_calls == original_calls and not value.usage
    async with AsyncSession(api.engine) as db:
        rows = (
            await db.scalars(
                select(ExperimentRunRecord).where(ExperimentRunRecord.experiment_id == experiment)
            )
        ).all()
        assert all(row.status == "queued" and row.attempt == 0 for row in rows)


async def test_fake_sessions_are_deterministic_and_cannot_call_provider(
    service: tuple[AnalystSessions, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    api, experiment = service
    monkeypatch.setattr(
        real_backend, "adapter_for_profile", lambda *a, **k: pytest.fail("Fake called Provider")
    )
    reports = []
    for _ in range(2):
        value = await api.create(CreateInvestigation(experiment_id=experiment, question="Inspect"))
        while value.state.report is None:
            value = await api.resume(value.session_id)
        assert not value.usage
        reports.append(value.state.report.canonical_json())
    assert reports[0] == reports[1]


def test_provider_schema_is_closed_and_scalar_fact_values_are_supported() -> None:
    schema = decision_json_schema()

    def check(node: Any) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert set(node["required"]) == set(node["properties"])
            assert "default" not in node and "oneOf" not in node
            for child in node.values():
                check(child)
        elif isinstance(node, list):
            for child in node:
                check(child)

    check(schema)
    properties = schema["properties"]
    assert isinstance(properties, dict) and properties["decision"]


async def test_concurrent_resume_cannot_duplicate_provider_or_tool_calls(
    service: tuple[AnalystSessions, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    api, experiment = service
    entered, release = asyncio.Event(), asyncio.Event()

    class BlockingAdapter(RecordingAdapter):
        async def invoke(self, request: ProviderRequest) -> ProviderResult:
            entered.set()
            await release.wait()
            return await super().invoke(request)

    adapter = BlockingAdapter(lambda _: query())
    monkeypatch.setattr(real_backend, "adapter_for_profile", lambda *a, **k: adapter)
    value = await real_session(api, experiment)
    running = asyncio.create_task(api.resume(value.session_id, confirm_real=True))
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        reserved = await api.get(value.session_id)
        assert reserved.status == "RUNNING" and len(reserved.usage) == 1
        with pytest.raises(AnalystSessionError, match="busy"):
            await api.resume(value.session_id, confirm_real=True)
    finally:
        release.set()
        result = await running
    assert len(adapter.requests) == result.state.tool_calls == result.state.decision_iterations == 1


async def test_real_profile_drift_blocks_resume_before_spending(
    service: tuple[AnalystSessions, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    api, experiment = service
    value = await real_session(api, experiment)
    from harnesslab.registry.service import registry_catalog

    catalog = registry_catalog(ROOT, {})
    disabled = catalog.model_copy(
        update={
            "provider_model_profiles": tuple(
                p.model_copy(update={"enabled": False}) for p in catalog.provider_model_profiles
            )
        }
    )
    monkeypatch.setattr(sessions, "registry_catalog", lambda *a, **k: disabled)
    monkeypatch.setattr(
        real_backend, "adapter_for_profile", lambda *a, **k: pytest.fail("disabled profile invoked")
    )
    with pytest.raises(ValueError, match="disabled"):
        await api.resume(value.session_id, confirm_real=True)
    assert not (await api.get(value.session_id)).usage


async def test_real_provider_adapter_mocktransport_schema_and_known_cost(
    service: tuple[AnalystSessions, str],
) -> None:
    from harnesslab.budget.models import PricingAvailability, ProviderPricing
    from harnesslab.model_lane.providers import OpenAIResponsesAdapter

    api, experiment = service
    value = await real_session(api, experiment)
    assert value.profile is not None
    profile = value.profile
    pricing = ProviderPricing(
        route_identity=profile.runtime.provider_route_identity,
        availability=PricingAvailability.KNOWN,
        input_usd_per_million_tokens=Decimal("1"),
        output_usd_per_million_tokens=Decimal("2"),
        request_usd=Decimal("0.01"),
        evidence_reference="fixture:prices",
    )
    profile = profile.model_copy(update={"pricing": pricing})
    requests = []

    def reply(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        assert payload["text"]["format"]["type"] == "json_schema"
        assert payload["text"]["format"]["strict"] is True
        assert payload["model"] == profile.runtime.requested_model
        return httpx.Response(
            200,
            json={
                "id": "mock-request",
                "status": "completed",
                "model": profile.runtime.requested_model,
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {
                                        "decision": {
                                            "kind": "abstain",
                                            "reason": "No sufficient evidence.",
                                        }
                                    }
                                ),
                            }
                        ],
                    }
                ],
                "usage": {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30},
            },
        )

    assert profile.runtime.credential_reference and profile.runtime.base_url_reference
    environment = {
        profile.runtime.credential_reference: "keyless-placeholder",
        profile.runtime.base_url_reference: "https://provider.example",
    }
    async with httpx.AsyncClient(transport=httpx.MockTransport(reply)) as client:
        backend = RealAnalystBackend(
            profile,
            environment=environment,
            adapter=OpenAIResponsesAdapter(client=client, environment=environment),
            budget=spend_limits(),
            reserve=AsyncMock(),
        )
        result = await backend.decide(
            request=value.state.request,
            scope=value.state.scope,
            evidence=(),
            iteration=1,
            remaining_tool_calls=12,
        )
    assert isinstance(result, AbstainDecision) and len(requests) == 1
    assert backend.last_usage is not None
    assert backend.last_usage.cost_usd == Decimal("0.01005")


async def test_interrupted_tool_is_not_silently_replayed(
    service: tuple[AnalystSessions, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    api, experiment = service
    adapter = RecordingAdapter(lambda _: query())
    monkeypatch.setattr(real_backend, "adapter_for_profile", lambda *a, **k: adapter)
    value = await real_session(api, experiment)

    async def crash(*args: Any) -> Any:
        raise SimulatedCrash()

    monkeypatch.setattr(sessions._SessionTools, "execute", crash)
    with pytest.raises(SimulatedCrash):
        await api.resume(value.session_id, confirm_real=True)
    resumed = await api.resume(value.session_id, confirm_real=True)
    assert resumed.state.completed_calls[0].status == "INTERRUPTED"
    assert resumed.state.tool_calls == resumed.state.decision_iterations == 1
    assert len(adapter.requests) == 1


async def test_analyst_api_create_resume_get_list_propose_and_approve(
    service: tuple[AnalystSessions, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    from harnesslab.analyst import api as api_module
    from harnesslab.api.app import create_app

    api, experiment = service
    monkeypatch.setattr(api_module, "create_engine", lambda _: api.engine)
    monkeypatch.setattr(
        real_backend, "adapter_for_profile", lambda *a, **k: pytest.fail("API Fake called Provider")
    )
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        prefix = "/api/workbench/analyst/sessions"
        response = await client.post(
            prefix, json={"experiment_id": experiment, "question": "Inspect", "decision_limit": 2}
        )
        assert response.status_code == 201, response.text
        value = response.json()
        path = prefix + "/" + value["session_id"]
        assert value["request_count"] == 0 and value["decision_limit"] == 2
        response = await client.post(path + "/resume", json={})
        assert response.status_code == 200, response.text
        value = response.json()
        assert value["decision_iterations"] == 1
        assert (await client.get(path)).json() == value
        assert (
            len((await client.get(prefix, params={"experiment_id": experiment})).json()["items"])
            == 1
        )
        forbidden = await client.post(
            path + "/resume", json={"tool_limit": 999, "shell": "private"}
        )
        assert forbidden.status_code == 422 and "private" not in forbidden.text
        plan = {
            "objective": "Check boundary",
            "task_ids": value["scope"]["task_ids"],
            "cell_ids": value["scope"]["cell_ids"],
            "evidence_refs": [value["evidence"][0]["ref"]["id"]],
            "acceptance_criteria": ["Deterministic result verified."],
        }
        proposed = (await client.put(path + "/proposal", json=plan)).json()
        approval = {
            "scope_digest": proposed["scope_digest"],
            "proposal_digest": proposed["proposal_digest"],
            "reviewed_by": "tester",
        }
        approved = await client.post(path + "/approval", json=approval)
        assert approved.status_code == 200, approved.text
        assert approved.json()["approval"]["execution_authorized"] is False
        changed = await client.put(path + "/proposal", json={**plan, "objective": "Changed"})
        assert changed.json()["approval"] is None
        assert (await client.post(path + "/approval", json=approval)).status_code == 409
        assert (
            await client.post(
                prefix, json={"experiment_id": experiment, "question": "Inspect", "backend": "real"}
            )
        ).status_code == 422
        assert (
            await client.post(
                prefix, json={"experiment_id": experiment, "question": "api_key=private"}
            )
        ).status_code == 422


async def test_real_final_facts_and_model_proposal_are_host_validated(
    service: tuple[AnalystSessions, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    api, experiment = service

    def choose(data: dict[str, Any]) -> dict[str, Any]:
        if not data["evidence"]:
            return query()
        entry = data["evidence"][0]
        return {
            "kind": "final",
            "draft": {
                "summary": "A queued observation.",
                "claims": [
                    {
                        "classification": "VERIFIED_FACT",
                        "assertions": [
                            {
                                "evidence_ref": entry["ref"]["id"],
                                "tool": "query_runs",
                                "field_path": ["status"],
                                "expected_value": "queued",
                            }
                        ],
                    },
                ],
            },
            "proposed_plan": {
                "objective": "Verify the queued case later",
                "task_ids": data["scope"]["task_ids"],
                "cell_ids": data["scope"]["cell_ids"],
                "evidence_refs": [entry["ref"]["id"]],
                "acceptance_criteria": ["Collect a deterministic verifier result."],
                "repeat_count": 1,
            },
        }

    adapter = RecordingAdapter(choose)
    monkeypatch.setattr(real_backend, "adapter_for_profile", lambda *a, **k: adapter)
    value = await real_session(api, experiment)
    value = await api.resume(value.session_id, confirm_real=True)
    value = await api.resume(value.session_id, confirm_real=True)
    assert value.status == "COMPLETED" and value.state.report is not None
    assert value.state.report.verified_facts[0].statement.endswith('.status EQ "queued".')
    assert value.state.proposed_plan is not None and value.approval is None
    assert value.proposal_digest is not None


def test_gate_j_scope_recognizes_explicit_real_backend_without_execution_tools() -> None:
    from scripts.verify_gate_j import verify_scope_and_safety

    assert verify_scope_and_safety()


async def test_lower_frozen_budget_is_visible_to_real_model_and_not_reset(
    service: tuple[AnalystSessions, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, experiment = service
    adapter = RecordingAdapter(lambda _: query())
    monkeypatch.setattr(real_backend, "adapter_for_profile", lambda *a, **k: adapter)
    value = await api.create(
        CreateInvestigation(
            experiment_id=experiment,
            question="Inspect",
            backend="real",
            provider_profile_id="gpt56-relay-gpt56-responses",
            decision_limit=2,
            tool_limit=3,
            spend_limits=spend_limits(provider_requests=2),
        )
    )
    for _ in range(3):
        value = await api.resume(value.session_id, confirm_real=True)
    assert [json.loads(r.input)["remaining_decisions"] for r in adapter.requests] == [1, 0]
    assert value.status == "LIMIT_REACHED"
    assert value.public_view()["request_budget_used"] == value.public_view()["request_count"] == 2
    assert value.state.max_tool_calls == 3 and value.state.tool_calls == 1


async def test_known_credential_echo_is_rejected_without_persisting_it(
    service: tuple[AnalystSessions, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, experiment = service
    value = await real_session(api, experiment)
    assert value.profile is not None and value.profile.runtime.credential_reference
    sentinel = "keyless-credential-echo-sentinel"
    api.environment = {**api.environment, value.profile.runtime.credential_reference: sentinel}
    adapter = RecordingAdapter(lambda _: {"kind": "abstain", "reason": sentinel})
    monkeypatch.setattr(real_backend, "adapter_for_profile", lambda *a, **k: adapter)
    value = await api.resume(value.session_id, confirm_real=True)
    assert value.status == "FAILED" and len(adapter.requests) == 1
    assert sentinel not in value.model_dump_json()


async def test_interrupted_request_observation_stays_unknown_but_budget_is_spent(
    service: tuple[AnalystSessions, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, experiment = service

    class CrashAdapter:
        async def invoke(self, request: ProviderRequest) -> ProviderResult:
            raise SimulatedCrash()

    monkeypatch.setattr(real_backend, "adapter_for_profile", lambda *a, **k: CrashAdapter())
    value = await real_session(api, experiment)
    with pytest.raises(SimulatedCrash):
        await api.resume(value.session_id, confirm_real=True)
    view = (await api.get(value.session_id)).public_view()
    assert view["request_count"] is None and view["request_budget_used"] == 1
    assert view["totals"]["cost_usd"] is None and view["totals"]["total_tokens"] is None


async def create_with_limits(
    api: AnalystSessions, experiment: str, **limits: Any
) -> sessions.AnalystSession:
    return await api.create(
        CreateInvestigation(
            experiment_id=experiment,
            question="Spend guard",
            backend="real",
            provider_profile_id="gpt56-relay-gpt56-responses",
            spend_limits=spend_limits(**limits),
        )
    )


@pytest.mark.parametrize(
    ("limits", "reason"),
    [
        ({"provider_requests": 1}, "REQUEST_CEILING_REACHED"),
        ({"cumulative_tokens": 3030}, "TOKEN_CEILING_INSUFFICIENT"),
    ],
)
async def test_spend_ceiling_survives_resume_without_another_invocation(
    service: tuple[AnalystSessions, str],
    monkeypatch: pytest.MonkeyPatch,
    limits: dict[str, Any],
    reason: str,
) -> None:
    api, experiment = service
    adapter = RecordingAdapter(lambda _: query())
    monkeypatch.setattr(real_backend, "adapter_for_profile", lambda *a, **k: adapter)
    value = await create_with_limits(api, experiment, **limits)
    # 3030 admits two requests: 0+3000 and observed 30+3000; the next cannot fit.
    for _ in range(2 if "cumulative_tokens" in limits else 1):
        value = await api.resume(value.session_id, confirm_real=True)
    before = value.model_dump(mode="json")
    restored = AnalystSessions(
        api.engine,
        repository_root=ROOT,
        artifact_roots=api.artifact_roots,
        environment=api.environment,
        real_enabled=True,
    )
    for _ in range(2):
        with pytest.raises(AnalystSessionError, match=reason):
            await restored.resume(value.session_id, confirm_real=True)
    after = await restored.get(value.session_id)
    assert len(after.usage) == len(adapter.requests) == len(before["usage"])
    assert after.spend_limits == value.spend_limits and after.usage == value.usage
    assert after.state.tool_calls == value.state.tool_calls


@pytest.mark.parametrize(
    ("limits", "reason"),
    [
        ({"input_bytes_per_request": 10}, "INPUT_BYTE_CEILING"),
        ({"output_tokens_per_request": 2001}, "OUTPUT_CEILING_EXCEEDS_PROFILE"),
        ({"timeout_seconds": 181}, "TIMEOUT_CEILING_EXCEEDS_PROFILE"),
        ({"cumulative_tokens": 2999}, "TOKEN_CEILING_INSUFFICIENT"),
        ({"usd": "1"}, "USD_PRICING_UNKNOWN"),
    ],
)
async def test_preflight_limits_block_before_first_reservation(
    service: tuple[AnalystSessions, str],
    monkeypatch: pytest.MonkeyPatch,
    limits: dict[str, Any],
    reason: str,
) -> None:
    api, experiment = service
    monkeypatch.setattr(
        real_backend, "adapter_for_profile", lambda *a, **k: pytest.fail("invocation")
    )
    value = await create_with_limits(api, experiment, **limits)
    snapshot = value.model_dump_json()
    preflight = await api.preflight(value.session_id)
    assert preflight["status"] == "BLOCKED" and any(reason in r for r in preflight["reasons"])
    assert (await api.get(value.session_id)).model_dump_json() == snapshot
    with pytest.raises(AnalystSessionError, match=reason):
        await api.resume(value.session_id, confirm_real=True)
    assert (await api.get(value.session_id)).usage == ()


@pytest.mark.parametrize(
    "unknown",
    [
        ProviderUsage(),
        ProviderUsage(input_tokens=10, output_tokens=20),
        ProviderUsage(input_tokens=10, output_tokens=20, total_tokens=1),
    ],
)
async def test_unknown_or_inconsistent_usage_blocks_without_backfill(
    service: tuple[AnalystSessions, str],
    monkeypatch: pytest.MonkeyPatch,
    unknown: ProviderUsage,
) -> None:
    api, experiment = service

    class UnknownAdapter(RecordingAdapter):
        async def invoke(self, request: ProviderRequest) -> ProviderResult:
            return (await super().invoke(request)).model_copy(update={"usage": unknown})

    adapter = UnknownAdapter(lambda _: query())
    monkeypatch.setattr(real_backend, "adapter_for_profile", lambda *a, **k: adapter)
    value = await real_session(api, experiment)
    value = await api.resume(value.session_id, confirm_real=True)
    assert value.usage[0].tokens == unknown
    with pytest.raises(AnalystSessionError, match="TOKEN_USAGE_UNKNOWN_OR_INCONSISTENT"):
        await api.resume(value.session_id, confirm_real=True)
    assert len(adapter.requests) == 1 and (await api.get(value.session_id)).usage == value.usage


async def test_lower_limits_reach_adapter_only_after_durable_reservation(
    service: tuple[AnalystSessions, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, experiment = service
    value = await create_with_limits(
        api, experiment, output_tokens_per_request=100, timeout_seconds=2
    )

    class JournalAdapter(RecordingAdapter):
        async def invoke(self, request: ProviderRequest) -> ProviderResult:
            saved = await api.get(value.session_id)
            assert saved.usage[0].status == "RESERVED"
            assert saved.usage[0].reserved_resources is not None
            assert saved.usage[0].reserved_resources.output_tokens == 100
            assert saved.usage[0].reserved_resources.harness_turns == 0
            assert saved.usage[0].input_bytes == real_backend.request_input_bytes(request)
            assert request.profile.reasoning.max_output_tokens == 100
            assert request.profile.request_timeout_seconds == 2
            return await super().invoke(request)

    adapter = JournalAdapter(lambda _: query())
    monkeypatch.setattr(real_backend, "adapter_for_profile", lambda *a, **k: adapter)
    await api.resume(value.session_id, confirm_real=True)
    assert len(adapter.requests) == 1


async def test_failed_reservation_commit_cannot_invoke(
    service: tuple[AnalystSessions, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, experiment = service
    value = await real_session(api, experiment)
    original = api._save

    async def fail(session: AsyncSession, current: sessions.AnalystSession) -> None:
        if current.usage and current.usage[-1].reserved_resources is not None:
            raise SimulatedCrash()
        await original(session, current)

    monkeypatch.setattr(api, "_save", fail)
    monkeypatch.setattr(
        real_backend, "adapter_for_profile", lambda *a, **k: pytest.fail("unreserved invocation")
    )
    with pytest.raises(SimulatedCrash):
        await api.resume(value.session_id, confirm_real=True)
    saved = await api.get(value.session_id)
    assert len(saved.usage) == 1 and saved.usage[0].tokens.total_tokens is None


@pytest.mark.parametrize("route_match", [True, False])
async def test_known_price_reserves_cost_and_route_mismatch_blocks(
    service: tuple[AnalystSessions, str],
    monkeypatch: pytest.MonkeyPatch,
    route_match: bool,
) -> None:
    from harnesslab.budget.models import ProviderPricing

    api, experiment = service
    original = real_backend.resolve_analyst_profile

    def resolve(*args: Any, **kwargs: Any) -> real_backend.AnalystProfile:
        profile = original(*args, **kwargs).model_copy(update={"context_window_tokens": 1000})
        return profile.model_copy(
            update={
                "pricing": ProviderPricing(
                    route_identity=profile.runtime.provider_route_identity
                    if route_match
                    else "other-route",
                    availability="KNOWN",
                    input_usd_per_million_tokens=Decimal("1"),
                    output_usd_per_million_tokens=Decimal("2"),
                    request_usd=Decimal("0.01"),
                    evidence_reference="fixture:pricing",
                )
            }
        )

    monkeypatch.setattr(sessions, "resolve_analyst_profile", resolve)
    adapter = RecordingAdapter(lambda _: query())
    monkeypatch.setattr(real_backend, "adapter_for_profile", lambda *a, **k: adapter)
    value = await create_with_limits(api, experiment, usd="0.015")
    if route_match:
        preflight = await api.preflight(value.session_id)
        assert (
            preflight["status"] == "READY" and preflight["pricing_basis"]["availability"] == "KNOWN"
        )
        value = await api.resume(value.session_id, confirm_real=True)
        assert value.usage[0].reserved_cost_usd == Decimal("0.015")
        assert value.usage[0].cost_usd == Decimal("0.01005")
        with pytest.raises(AnalystSessionError, match="USD_CEILING_INSUFFICIENT"):
            await api.resume(value.session_id, confirm_real=True)
        assert len(adapter.requests) == 1
    else:
        with pytest.raises(AnalystSessionError, match="USD_PRICING_UNKNOWN_OR_ROUTE_MISMATCH"):
            await api.resume(value.session_id, confirm_real=True)
        assert adapter.requests == []


async def test_legacy_unbudgeted_real_session_is_readable_but_cannot_spend(
    service: tuple[AnalystSessions, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from harnesslab.db.models.analyst import AnalystSessionRecord

    api, experiment = service
    value = await real_session(api, experiment)
    async with AsyncSession(api.engine) as db, db.begin():
        row = await db.get(AnalystSessionRecord, value.session_id)
        assert row is not None
        raw = dict(row.state_json)
        raw.pop("spend_limits")
        row.state_json = raw
    monkeypatch.setattr(
        real_backend, "adapter_for_profile", lambda *a, **k: pytest.fail("old session spent")
    )
    saved = await api.get(value.session_id)
    assert saved.spend_limits is None
    assert "SPEND_LIMITS_MISSING" in (await api.preflight(value.session_id))["reasons"]
    with pytest.raises(AnalystSessionError, match="SPEND_LIMITS_MISSING"):
        await api.resume(value.session_id, confirm_real=True)
    assert (await api.get(value.session_id)).usage == ()


async def test_preflight_public_snapshot_api_and_configuration_drift(
    service: tuple[AnalystSessions, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from harnesslab.analyst.api import analyst_service
    from harnesslab.api.app import create_app

    api, experiment = service
    value = await real_session(api, experiment)
    api.real_enabled = False  # READY is preparation, never invocation authorization.
    app = create_app()
    app.dependency_overrides[analyst_service] = lambda: api
    monkeypatch.setattr(
        real_backend, "adapter_for_profile", lambda *a, **k: pytest.fail("preflight invoked")
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(f"/api/workbench/analyst/sessions/{value.session_id}/preflight")
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "READY" and result["reasons"] == []
    assert result["credential_reference_status"] == result["base_url_reference_status"] == "SET"
    assert result["server_real_enabled"] is False and result["execution_authorized"] is False
    assert result["scope_digest"] == value.scope_digest and result["decision_ceiling"] == 8
    assert value.spend_limits is not None
    assert result["spend_limits"] == value.spend_limits.model_dump(mode="json")
    assert (
        "keyless-placeholder" not in response.text
        and "https://provider.example" not in response.text
    )
    assert (await api.get(value.session_id)).model_dump_json() == value.model_dump_json()
    api.environment = {}
    blocked = await api.preflight(value.session_id)
    assert blocked["status"] == "BLOCKED"
    assert {
        "CREDENTIAL_REFERENCE_MISSING",
        "BASE_URL_REFERENCE_MISSING",
        "PROFILE_DRIFT_OR_UNAVAILABLE",
    } <= set(blocked["reasons"])


async def test_unknown_registry_context_is_not_estimated_from_bytes(
    service: tuple[AnalystSessions, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, experiment = service
    monkeypatch.setattr(sessions, "resolve_analyst_profile", real_backend.resolve_analyst_profile)
    value = await real_session(api, experiment)
    assert "INPUT_TOKEN_BOUND_UNKNOWN" in (await api.preflight(value.session_id))["reasons"]
    with pytest.raises(AnalystSessionError, match="INPUT_TOKEN_BOUND_UNKNOWN"):
        await api.resume(value.session_id, confirm_real=True)


def test_registry_spend_metadata_preserves_defaults_and_pins_live_price_basis(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from harnesslab.registry import seeds

    environment = {
        "HARNESSLAB_GPT56_RELAY_API_KEY": "mock-key",
        "HARNESSLAB_GPT56_RELAY_BASE_URL": "https://provider.example",
    }
    baseline = seeds.build_registry_catalog(ROOT, environment)
    monkeypatch.setattr(seeds, "_tasks", lambda *a: baseline.tasks)
    profile_id = "gpt56-relay-gpt56-responses"
    before = real_backend.resolve_analyst_profile(baseline, profile_id, ROOT)
    assert before.context_window_tokens is None and before.pricing is None
    metadata = {
        "model_context_windows": {"gpt-5.6-sol": 1000},
        "profile_pricing_references": {profile_id: "prices.json"},
    }
    (tmp_path / "metadata.json").write_text(json.dumps(metadata))
    price = {
        "route_identity": before.runtime.provider_route_identity,
        "availability": "KNOWN",
        "input_usd_per_million_tokens": "1",
        "output_usd_per_million_tokens": "2",
        "request_usd": "0",
        "evidence_reference": "fixture:price-source",
    }
    (tmp_path / "prices.json").write_text(json.dumps(price))
    environment["HARNESSLAB_REGISTRY_SPEND_METADATA"] = "metadata.json"
    catalog = seeds.build_registry_catalog(tmp_path, environment)
    profile = real_backend.resolve_analyst_profile(catalog, profile_id, tmp_path)
    assert profile.context_window_tokens == 1000 and profile.pricing is not None
    assert profile.profile_digest != before.profile_digest
    assert profile.pricing.evidence_reference == "fixture:price-source"
    # Same reference, changed bytes must also invalidate the frozen full profile digest.
    (tmp_path / "prices.json").write_text(json.dumps({**price, "request_usd": "0.01"}))
    assert (
        real_backend.resolve_analyst_profile(catalog, profile_id, tmp_path).digest != profile.digest
    )
    (tmp_path / "metadata.json").write_text(
        json.dumps({**metadata, "model_context_windows": {"unknown": 10}})
    )
    with pytest.raises(ValueError, match="unknown identities"):
        seeds.build_registry_catalog(tmp_path, environment)


async def test_provider_cannot_bypass_journal_and_timeout_cap(
    service: tuple[AnalystSessions, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, experiment = service
    value = await create_with_limits(api, experiment, timeout_seconds=0.01)
    assert value.profile is not None
    adapter = RecordingAdapter(lambda _: query())
    backend = RealAnalystBackend(
        value.profile, environment=api.environment, adapter=adapter, budget=value.spend_limits
    )
    with pytest.raises(ValueError, match="SPEND_PREFLIGHT_BLOCKED"):
        await backend.decide(
            request=value.state.request,
            scope=value.state.scope,
            evidence=(),
            iteration=1,
            remaining_tool_calls=12,
        )
    assert adapter.requests == []  # A directly constructed real backend needs a journal callback.

    class SlowAdapter:
        async def invoke(self, request: ProviderRequest) -> ProviderResult:
            await asyncio.sleep(1)
            pytest.fail("timeout did not cancel the mock provider")

    monkeypatch.setattr(real_backend, "adapter_for_profile", lambda *a, **k: SlowAdapter())
    value = await api.resume(value.session_id, confirm_real=True)
    assert value.status == "FAILED" and len(value.usage) == 1
    with pytest.raises(AnalystSessionError, match="TOKEN_USAGE_UNKNOWN"):
        await api.resume(value.session_id, confirm_real=True)


async def test_input_byte_limit_counts_schema_instructions_and_utf8(
    service: tuple[AnalystSessions, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, experiment = service
    value = await real_session(api, experiment)
    assert value.profile is not None
    backend = RealAnalystBackend(
        value.profile, environment=api.environment, budget=value.spend_limits
    )
    request = backend.prepare(
        request=value.state.request,
        scope=value.state.scope,
        evidence=(),
        iteration=1,
        remaining_tool_calls=12,
    )
    size = real_backend.request_input_bytes(request)
    assert size > len(request.input.encode())
    unicode_request = request.model_copy(update={"instructions": request.instructions + "证据"})
    assert real_backend.request_input_bytes(unicode_request) == size + 6
    assert "INPUT_BYTE_CEILING_EXCEEDED" in real_backend.spend_reasons(
        value.profile, spend_limits(input_bytes_per_request=size - 1), (), request
    )
    assert (
        real_backend.spend_reasons(
            value.profile, spend_limits(input_bytes_per_request=size), (), request
        )
        == ()
    )


async def test_context_and_pricing_drift_block_an_existing_budgeted_session(
    service: tuple[AnalystSessions, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api, experiment = service
    value = await real_session(api, experiment)
    assert value.profile is not None
    monkeypatch.setattr(
        sessions,
        "resolve_analyst_profile",
        lambda *a, **k: value.profile.model_copy(update={"context_window_tokens": 999}),
    )
    assert "PROFILE_DRIFT_OR_UNAVAILABLE" in (await api.preflight(value.session_id))["reasons"]
    with pytest.raises(AnalystSessionError, match="profile changed"):
        await api.resume(value.session_id, confirm_real=True)
    assert (await api.get(value.session_id)).usage == ()


@pytest.mark.parametrize(
    ("update", "reason"),
    [
        (
            {"tokens": ProviderUsage(input_tokens=10, output_tokens=2000, total_tokens=2010)},
            "OUTPUT_TOKEN_CEILING_REACHED",
        ),
        ({"input_bytes": 256_000}, "INPUT_BYTE_CEILING_REACHED"),
        ({"latency_ms": 60_000}, "TIMEOUT_CEILING_REACHED"),
        ({"cost_usd": None}, "COST_USAGE_UNKNOWN"),
    ],
)
async def test_observed_ceilings_and_unknown_cost_are_not_refunded(
    service: tuple[AnalystSessions, str],
    update: dict[str, Any],
    reason: str,
) -> None:
    from harnesslab.budget.models import ProviderPricing

    api, experiment = service
    value = await real_session(api, experiment)
    assert value.profile is not None
    profile = value.profile.model_copy(
        update={
            "pricing": ProviderPricing(
                route_identity=value.profile.runtime.provider_route_identity,
                availability="KNOWN",
                input_usd_per_million_tokens=Decimal("1"),
                output_usd_per_million_tokens=Decimal("2"),
                request_usd=Decimal("0"),
            )
        }
    )
    backend = RealAnalystBackend(profile, environment=api.environment, budget=spend_limits(usd="1"))
    request = backend.prepare(
        request=value.state.request,
        scope=value.state.scope,
        evidence=(),
        iteration=2,
        remaining_tool_calls=12,
    )
    usage = real_backend.DecisionUsage(
        iteration=1,
        status="FAILED",
        invocation_started=True,
        tokens=ProviderUsage(input_tokens=10, output_tokens=20, total_tokens=30),
        cost_usd=Decimal("0.01"),
    )
    usage = usage.model_copy(update=update)
    assert reason in real_backend.spend_reasons(profile, backend.budget, (usage,), request)
    assert (
        usage.model_dump(mode="json")[next(iter(update))] is not None
        or reason == "COST_USAGE_UNKNOWN"
    )
