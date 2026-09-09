from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from harnesslab.experiment.report import _manifest_metrics
from harnesslab.harness_lane.models import CodexProcessCapture
from harnesslab.harness_lane.trace import collect_codex_jsonl
from harnesslab.multi_harness.models import HarnessProcessCapture
from harnesslab.multi_harness.trace import collect_claude_stream, collect_deepseek_final


def _write_trace(tmp_path: Path, collection: Any, **extra: Any) -> dict[str, Any]:
    trace_dir = tmp_path / "trace"
    trace_dir.mkdir(exist_ok=True)
    (trace_dir / "normalized.json").write_text(collection.trace.canonical_json())
    return {
        "normalized_trace_digest": collection.trace_digest,
        "trace_event_count": len(collection.trace.events),
        "trace_event_types": [event.type.value for event in collection.trace.events],
        **extra,
    }


def test_codex_lifecycle_events_count_one_call(tmp_path: Path) -> None:
    lines = [
        json.dumps(
            {
                "type": f"item.{stage}",
                "item": {"type": "command_execution", "id": "cmd-1", "status": "completed"},
            }
        )
        for stage in ("started", "updated", "completed")
    ]
    lines.append(json.dumps({"type": "turn.completed"}))
    collection = collect_codex_jsonl(CodexProcessCapture(tuple(lines), 0, 10))
    raw = _write_trace(tmp_path, collection)
    assert _manifest_metrics(raw, tmp_path / "manifest.json")["tool_calls"] == 1


def test_claude_tool_result_is_not_another_call(tmp_path: Path) -> None:
    lines = [
        {
            "type": "assistant",
            "message": {
                "content": [{"type": "tool_use", "id": "call-1", "name": "Bash", "input": {}}]
            },
        },
        {
            "type": "user",
            "message": {
                "content": [{"type": "tool_result", "tool_use_id": "call-1", "content": "ok"}]
            },
        },
        {"type": "result", "subtype": "success"},
    ]
    collection = collect_claude_stream(
        HarnessProcessCapture(
            stdout_lines=tuple(json.dumps(line) for line in lines),
            stderr_text="",
            exit_code=0,
            duration_ms=10,
        )
    )
    raw = _write_trace(tmp_path, collection, trace_coverage="FULL_STREAM")
    assert _manifest_metrics(raw, tmp_path / "manifest.json")["tool_calls"] == 1


def test_final_output_only_tool_count_is_unknown(tmp_path: Path) -> None:
    collection = collect_deepseek_final(
        HarnessProcessCapture(
            stdout_lines=("done",),
            stderr_text="",
            exit_code=0,
            duration_ms=10,
        )
    )
    raw = _write_trace(tmp_path, collection, trace_coverage="FINAL_OUTPUT_ONLY")
    assert _manifest_metrics(raw, tmp_path / "manifest.json")["tool_calls"] is None


@pytest.mark.parametrize("event_types", [[], ["COMMAND_EXECUTION", "COMMAND_EXECUTION"]])
def test_legacy_event_summary_without_trace_is_unknown(event_types: list[str]) -> None:
    assert _manifest_metrics({"trace_event_types": event_types})["tool_calls"] is None


@pytest.mark.parametrize("damage", ["missing", "digest", "malformed", "no_terminal", "no_id"])
def test_unverifiable_or_incomplete_trace_never_becomes_zero(tmp_path: Path, damage: str) -> None:
    lines = [
        {"type": "item.completed", "item": {"type": "command_execution", "id": "cmd-1"}},
        {"type": "turn.completed"},
    ]
    if damage == "no_terminal":
        lines.pop()
    if damage == "no_id":
        lines[0] = {"type": "item.completed", "item": {"type": "command_execution"}}
    collection = collect_codex_jsonl(
        CodexProcessCapture(
            tuple(json.dumps(line) for line in lines),
            0,
            10,
        )
    )
    raw = _write_trace(tmp_path, collection)
    path = tmp_path / "trace" / "normalized.json"
    if damage == "missing":
        path.unlink()
    elif damage == "digest":
        path.write_text(path.read_text() + " ")
    elif damage == "malformed":
        from harnesslab.sandbox.artifacts import sha256_file

        path.write_text("{}")
        raw["normalized_trace_digest"] = sha256_file(path)
    assert _manifest_metrics(raw, tmp_path / "manifest.json")["tool_calls"] is None


def test_observed_zero_and_distinct_calls_are_preserved(tmp_path: Path) -> None:
    collection = collect_codex_jsonl(CodexProcessCapture(('{"type":"turn.completed"}',), 0, 10))
    raw = _write_trace(tmp_path, collection)
    assert _manifest_metrics(raw, tmp_path / "manifest.json")["tool_calls"] == 0
    lines = [
        json.dumps(
            {
                "type": f"item.{stage}",
                "item": {"type": "command_execution", "id": item_id, "command": "same command"},
            }
        )
        for item_id in ("one", "two")
        for stage in ("started", "completed")
    ]
    lines.append('{"type":"turn.completed"}')
    collection = collect_codex_jsonl(CodexProcessCapture(tuple(lines), 0, 10))
    raw = _write_trace(tmp_path, collection)
    assert _manifest_metrics(raw, tmp_path / "manifest.json")["tool_calls"] == 2
    assert _manifest_metrics({"provider_result": None})["tool_calls"] == 0


def test_executor_and_report_share_count_without_changing_source_bytes(tmp_path: Path) -> None:
    from harnesslab.experiment.executor import _metrics
    from harnesslab.harness_lane.models import HarnessLaneEvidence

    collection = collect_codex_jsonl(
        CodexProcessCapture(
            (
                '{"type":"item.started","item":{"type":"command_execution","id":"one"}}',
                '{"type":"item.completed","item":{"type":"command_execution","id":"one"}}',
                '{"type":"turn.completed"}',
            ),
            0,
            10,
        )
    )
    raw = _write_trace(tmp_path, collection, duration_ms=10)
    # Only metrics fields are needed here; collector and immutable trace bytes are real.
    evidence = HarnessLaneEvidence.model_construct(
        **{**raw, "trace_event_types": tuple(event.type for event in collection.trace.events)}
    )
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(raw))
    before = {file: file.read_bytes() for file in (path, tmp_path / "trace" / "normalized.json")}
    assert _metrics(evidence, path).tool_calls == _manifest_metrics(raw, path)["tool_calls"] == 1
    assert before == {file: file.read_bytes() for file in before}


@pytest.mark.integration
@pytest.mark.parametrize("coverage, expected", [("FULL_STREAM", 1), ("FINAL_OUTPUT_ONLY", None)])
async def test_diagnosis_derives_calls_without_legacy_row_or_event_count_fallback(
    database_url: str, tmp_path: Path, coverage: str, expected: int | None
) -> None:
    from datetime import UTC, datetime, timedelta
    from uuid import uuid4

    from sqlalchemy import delete

    from harnesslab.core.config import Settings
    from harnesslab.db.models.experiment import ExperimentRecord, ExperimentRunRecord
    from harnesslab.db.session import create_engine, create_session_factory
    from harnesslab.diagnosis.service import diagnose_experiment
    from harnesslab.experiment.executor import attempt_execution_id
    from harnesslab.experiment.plan import build_experiment_plan
    from harnesslab.experiment.queue import claim_next_run, enqueue_plan
    from harnesslab.sandbox.artifacts import sha256_file
    from tests.phase_g_helpers import ROOT, basic_spec

    engine = create_engine(Settings.without_dotenv(database_url=database_url))
    factory = create_session_factory(engine)
    experiment_id = f"phase-l2-metrics-{uuid4().hex[:12]}"
    plan = build_experiment_plan(
        basic_spec(repeat_count=1).model_copy(update={"experiment_id": experiment_id}), ROOT
    )
    collection = collect_codex_jsonl(
        CodexProcessCapture(
            (
                '{"type":"item.started","item":{"type":"command_execution","id":"one"}}',
                '{"type":"item.completed","item":{"type":"command_execution","id":"one"}}',
                '{"type":"turn.completed"}',
            ),
            0,
            10,
        )
    )
    try:
        async with factory() as session, session.begin():
            await enqueue_plan(session, plan)
            claim = await claim_next_run(
                session, experiment_id, "test", now=datetime.now(UTC), ttl=timedelta(seconds=30)
            )
            assert claim is not None
            raw = _write_trace(
                tmp_path, collection, trace_coverage=coverage, run_id=attempt_execution_id(claim)
            )
            path = tmp_path / "manifest.json"
            path.write_text(json.dumps(raw))
            row = await session.get(ExperimentRunRecord, claim.run_id)
            assert row is not None
            row.artifact_manifest_path = str(path)
            row.evidence_digest = sha256_file(path)
            row.normalized_outcome = "capability_fail"
            row.source_outcome = "verified_fail"
            row.tool_calls = (
                99  # A historical event-total cache is not authoritative call evidence.
            )
        async with factory() as session:
            report = await diagnose_experiment(
                session, experiment_id, (tmp_path,), repository_root=ROOT
            )
            assert report.cells[0].task_families[0].clusters[0].runs[0].tool_calls.count == expected
            assert report.cells[0].task_families[0].clusters[0].runs[0].tool_calls.status == (
                "REPORTED" if expected is not None else "NOT_REPORTED"
            )
            row = await session.get(ExperimentRunRecord, claim.run_id)
            assert row is not None and row.tool_calls == 99
    finally:
        async with factory() as session, session.begin():
            await session.execute(
                delete(ExperimentRecord).where(ExperimentRecord.id == experiment_id)
            )
        await engine.dispose()


def test_protocol_failed_trace_cannot_establish_zero_tool_calls(tmp_path: Path) -> None:
    collection = collect_codex_jsonl(
        CodexProcessCapture(
            (
                '{"type":"turn.completed"}',
                '{"type":"turn.completed"}',
            ),
            0,
            10,
        )
    )
    assert collection.failure_category is not None
    raw = _write_trace(tmp_path, collection, harness_failure=collection.failure_category.value)
    assert _manifest_metrics(raw, tmp_path / "manifest.json")["tool_calls"] is None
