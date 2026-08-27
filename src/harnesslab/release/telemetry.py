from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from harnesslab.release.evidence import CallEvidenceSummary, summarize_smoke_evidence


class TelemetryCallSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    call_id: str
    requested_model: str | None
    observed_model: str | None
    outcome: str | None
    duration_ms: int | None = Field(default=None, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    provider_request_count: int | None = Field(default=None, ge=0)
    harness_event_count: int | None = Field(default=None, ge=0)
    trace_coverage: str | None


class SmokeTelemetrySummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    telemetry_status: Literal["PASS", "PARTIAL"]
    complete_smoke: bool
    top_level_launch_count: int = Field(ge=0, le=8)
    total_smoke_duration_ms: int | None = Field(default=None, ge=0)
    available_input_tokens: int | None = Field(default=None, ge=0)
    available_output_tokens: int | None = Field(default=None, ge=0)
    available_total_tokens: int | None = Field(default=None, ge=0)
    available_reasoning_tokens: int | None = Field(default=None, ge=0)
    observable_provider_request_count: int | None = Field(default=None, ge=0)
    matrix_logical_run_count: Literal[630] = 630
    extrapolated_matrix_top_level_launches: Literal[630] = 630
    judge_calibration_count: Literal[63] = 63
    wall_clock_scenarios_ms: dict[str, int] | None
    cost_estimate: Literal["PRICE_INPUT_REQUIRED"] = "PRICE_INPUT_REQUIRED"
    calls: tuple[TelemetryCallSummary, ...]

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )


def _duration(call: CallEvidenceSummary) -> int | None:
    return call.facts.duration_ms if call.facts.duration_ms is not None else call.facts.latency_ms


def _sum_complete(values: tuple[int | None, ...]) -> int | None:
    available = tuple(value for value in values if value is not None)
    return sum(available) if available else None


def summarize_smoke_telemetry(artifact_root: Path) -> SmokeTelemetrySummary:
    evidence = summarize_smoke_evidence(artifact_root)
    calls = tuple(
        TelemetryCallSummary(
            call_id=call.call_id,
            requested_model=call.facts.requested_model,
            observed_model=call.facts.observed_model,
            outcome=call.facts.outcome,
            duration_ms=_duration(call),
            input_tokens=call.facts.input_tokens,
            output_tokens=call.facts.output_tokens,
            total_tokens=call.facts.total_tokens,
            reasoning_tokens=call.facts.reasoning_tokens,
            provider_request_count=call.facts.provider_request_count,
            harness_event_count=call.facts.trace_event_count,
            trace_coverage=call.facts.trace_coverage,
        )
        for call in evidence.calls
    )
    durations = tuple(call.duration_ms for call in calls)
    duration_total = _sum_complete(durations)
    observed_durations = tuple(value for value in durations if value is not None)
    scenarios = None
    if observed_durations:
        rough_per_run = sum(observed_durations) // len(observed_durations)
        scenarios = {
            f"concurrency_{workers}": (rough_per_run * 630 + workers - 1) // workers
            for workers in (1, 2, 4)
        }
    complete = evidence.status == "SUCCEEDED" and evidence.attempted_top_level_launches == 8
    return SmokeTelemetrySummary(
        telemetry_status="PASS" if complete else "PARTIAL",
        complete_smoke=complete,
        top_level_launch_count=evidence.attempted_top_level_launches,
        total_smoke_duration_ms=duration_total,
        available_input_tokens=_sum_complete(tuple(call.input_tokens for call in calls)),
        available_output_tokens=_sum_complete(tuple(call.output_tokens for call in calls)),
        available_total_tokens=_sum_complete(tuple(call.total_tokens for call in calls)),
        available_reasoning_tokens=_sum_complete(tuple(call.reasoning_tokens for call in calls)),
        observable_provider_request_count=_sum_complete(
            tuple(call.provider_request_count for call in calls)
        ),
        wall_clock_scenarios_ms=scenarios,
        calls=calls,
    )
