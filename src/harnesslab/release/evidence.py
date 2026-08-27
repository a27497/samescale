from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from harnesslab.release.smoke import EXPECTED_CALL_IDS, SmokeExecutionReceipt
from harnesslab.sandbox.artifacts import sha256_file
from harnesslab.tasks.package import TaskPackageError, digest_tree


class EvidenceSummaryError(ValueError):
    """Smoke evidence is missing, unsafe, mutable, or internally inconsistent."""


class SafeCallFacts(BaseModel):
    """Allowlisted evidence facts; provider content and process diagnostics are excluded."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    call_id: str
    requested_model: str | None = None
    observed_model: str | None = None
    observed_model_status: str | None = None
    outcome: str | None = None
    provider_failure: str | None = None
    timeout_phase: str | None = None
    read_timeout_stage: str | None = None
    transport_trace: dict[str, Any] | None = None
    harness_failure: str | None = None
    process_exit_code: int | None = None
    timed_out: bool | None = None
    duration_ms: int | None = Field(default=None, ge=0)
    latency_ms: int | None = Field(default=None, ge=0)
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    reasoning_tokens: int | None = Field(default=None, ge=0)
    trace_coverage: str | None = None
    trace_event_count: int | None = Field(default=None, ge=0)
    workspace_mutated: bool | None = None
    verifier_status: str | None = None
    verifier_score: float | None = Field(default=None, ge=0, le=1)
    provider_request_count: int | None = Field(default=None, ge=0)


class CallEvidenceSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    call_id: str
    evidence_digest_domain: Literal["ARTIFACT_TREE_DIGEST", "RAW_FILE_SHA256"]
    evidence_digest: str
    receipt_digest_verified: bool
    egress_attestation_digest_count: int = Field(ge=0)
    facts: SafeCallFacts


class SmokeEvidenceSummary(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    evidence_class: Literal["CORE_REAL_SMOKE"] = "CORE_REAL_SMOKE"
    receipt_digest_domain: Literal["RAW_FILE_SHA256"] = "RAW_FILE_SHA256"
    receipt_digest: str
    plan_id: str
    smoke_plan_digest: str
    release_plan_digest: str
    status: str
    attempted_top_level_launches: int = Field(ge=0, le=8)
    attempted_call_ids: tuple[str, ...]
    failing_call_id: str | None
    failure_category: str | None
    calls: tuple[CallEvidenceSummary, ...]

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    def candidate_history_summary(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "smoke_plan_digest": self.smoke_plan_digest,
            "release_plan_digest": self.release_plan_digest,
            "receipt_digest": self.receipt_digest,
            "receipt_digest_domain": self.receipt_digest_domain,
            "status": self.status,
            "attempted_top_level_launches": self.attempted_top_level_launches,
            "failing_call_id": self.failing_call_id,
            "failure_category": self.failure_category,
            "calls": [
                {
                    **call.facts.model_dump(mode="json", exclude_none=True),
                    "evidence_digest": call.evidence_digest,
                    "evidence_digest_domain": call.evidence_digest_domain,
                }
                for call in self.calls
            ],
            "retry_count": 0,
            "fallback_count": 0,
        }


def _sha256_bytes(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def _load_object(path: Path) -> dict[str, Any]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise EvidenceSummaryError(f"invalid safe evidence artifact: {path.name}") from exc
    if not isinstance(raw, dict):
        raise EvidenceSummaryError("safe evidence artifact must contain an object")
    return raw


def _safe_int(value: object) -> int | None:
    return value if isinstance(value, int) and value >= 0 else None


def _safe_float(value: object) -> float | None:
    if isinstance(value, (int, float)) and 0 <= float(value) <= 1:
        return float(value)
    return None


def _safe_text(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _safe_transport_trace(value: object) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    allowed_top = {"schema_version", "source", "source_version", "phases"}
    if not set(value) <= allowed_top or not isinstance(value.get("phases"), list):
        return None
    phases: list[dict[str, Any]] = []
    for phase in value["phases"][:8]:
        if not isinstance(phase, dict) or not set(phase) <= {
            "phase",
            "started_ms",
            "completed_ms",
        }:
            return None
        normalized = {
            "phase": _safe_text(phase.get("phase")),
            "started_ms": _safe_int(phase.get("started_ms")),
            "completed_ms": _safe_int(phase.get("completed_ms")),
        }
        if normalized["phase"] is None or normalized["started_ms"] is None:
            return None
        phases.append({key: item for key, item in normalized.items() if item is not None})
    return {
        key: item
        for key, item in {
            "schema_version": _safe_int(value.get("schema_version")),
            "source": _safe_text(value.get("source")),
            "source_version": _safe_text(value.get("source_version")),
            "phases": phases,
        }.items()
        if item is not None
    }


def _artifact_facts(call_id: str, artifact: Path) -> SafeCallFacts:
    if artifact.is_dir():
        manifest = artifact / "manifest.json"
        if not manifest.is_file():
            candidates = tuple(sorted(artifact.glob("*.json")))
            if len(candidates) != 1:
                raise EvidenceSummaryError(f"call artifact has no unique safe manifest: {call_id}")
            manifest = candidates[0]
    elif artifact.is_file():
        manifest = artifact
    else:
        raise EvidenceSummaryError(f"call artifact is unavailable: {call_id}")
    raw = _load_object(manifest)
    provider_error = raw.get("provider_error")
    if not isinstance(provider_error, dict):
        provider_error = {}
    provider_result = raw.get("provider_result")
    if not isinstance(provider_result, dict):
        provider_result = {}
    usage = raw.get("usage")
    if not isinstance(usage, dict):
        usage = provider_result.get("usage")
    if not isinstance(usage, dict):
        usage = raw.get("provider_usage")
    if not isinstance(usage, dict):
        usage = {}
    changed_paths = raw.get("changed_paths")
    workspace_mutated = None
    if isinstance(changed_paths, list):
        workspace_mutated = bool(changed_paths)
    elif raw.get("workspace_input_digest") is not None:
        output = raw.get("workspace_output_digest")
        workspace_mutated = output is not None and output != raw.get("workspace_input_digest")
    verifier_passed = raw.get("verifier_passed")
    verifier_status = (
        "PASS" if verifier_passed is True else "FAIL" if verifier_passed is False else "NOT_RUN"
    )
    latency = provider_error.get("latency_ms", provider_result.get("latency_ms"))
    attempt_count = provider_error.get(
        "attempt_count",
        raw.get("generation_settings", {}).get("attempt_count")
        if isinstance(raw.get("generation_settings"), dict)
        else None,
    )
    return SafeCallFacts(
        call_id=call_id,
        requested_model=_safe_text(raw.get("requested_model", raw.get("requested_judge_model"))),
        observed_model=_safe_text(raw.get("observed_model", raw.get("observed_judge_model"))),
        observed_model_status=_safe_text(raw.get("observed_model_status")),
        outcome=_safe_text(raw.get("outcome")),
        provider_failure=_safe_text(raw.get("provider_failure")),
        timeout_phase=_safe_text(provider_error.get("timeout_phase")),
        read_timeout_stage=_safe_text(provider_error.get("read_timeout_stage")),
        transport_trace=_safe_transport_trace(provider_error.get("transport_trace")),
        harness_failure=_safe_text(raw.get("harness_failure")),
        process_exit_code=(
            raw.get("process_exit_code") if isinstance(raw.get("process_exit_code"), int) else None
        ),
        timed_out=(raw.get("timed_out") if isinstance(raw.get("timed_out"), bool) else None),
        duration_ms=_safe_int(raw.get("duration_ms")),
        latency_ms=_safe_int(latency),
        input_tokens=_safe_int(usage.get("input_tokens")),
        output_tokens=_safe_int(usage.get("output_tokens")),
        total_tokens=_safe_int(usage.get("total_tokens")),
        reasoning_tokens=_safe_int(usage.get("reasoning_tokens")),
        trace_coverage=_safe_text(raw.get("trace_coverage")),
        trace_event_count=_safe_int(raw.get("trace_event_count")),
        workspace_mutated=workspace_mutated,
        verifier_status=verifier_status,
        verifier_score=_safe_float(raw.get("verifier_score")),
        provider_request_count=_safe_int(attempt_count),
    )


def summarize_call_artifact(call_id: str, artifact: Path) -> SafeCallFacts:
    """Read only the allowlisted safe fields from one immutable call artifact."""

    return _artifact_facts(call_id, artifact.resolve())


def _resolve_artifact(root: Path, call_id: str, reference: str) -> Path:
    supplied = Path(reference)
    if supplied.exists():
        candidate = supplied.resolve()
        if candidate != root and root in candidate.parents:
            return candidate
    # Exact receipts remain hash-stable when a complete evidence root is archived or relocated.
    # Only the frozen call-id suffix is remapped; arbitrary absolute paths are never followed.
    if supplied.name != call_id:
        raise EvidenceSummaryError("unavailable call artifact reference has an unsafe suffix")
    relocated = (root / call_id / call_id).resolve()
    if relocated == root or root not in relocated.parents or not relocated.exists():
        raise EvidenceSummaryError(f"relocated call artifact is unavailable: {call_id}")
    return relocated


def summarize_smoke_evidence(artifact_root: Path) -> SmokeEvidenceSummary:
    root = artifact_root.resolve()
    receipt_path = root / "smoke-execution.json"
    try:
        receipt_bytes = receipt_path.read_bytes()
        receipt = SmokeExecutionReceipt.model_validate_json(receipt_bytes)
    except (OSError, ValidationError) as exc:
        raise EvidenceSummaryError("invalid SmokeExecutionReceipt") from exc
    attempted_ids = EXPECTED_CALL_IDS[: receipt.attempted_top_level_launches]
    if receipt.status.value == "SUCCEEDED" and (
        receipt.attempted_top_level_launches != 8
        or len(receipt.results) != 8
        or receipt.failing_call_id is not None
        or receipt.failure_category is not None
    ):
        raise EvidenceSummaryError("successful receipt is not a complete frozen smoke")
    if receipt.status.value == "ABORTED" and (
        not attempted_ids or receipt.failing_call_id is None or receipt.failure_category is None
    ):
        raise EvidenceSummaryError("aborted receipt lacks a typed failing frozen call")
    if receipt.failing_call_id is not None and (
        not attempted_ids or receipt.failing_call_id != attempted_ids[-1]
    ):
        raise EvidenceSummaryError("receipt failing call disagrees with frozen launch order")
    result_ids = tuple(result.call_id for result in receipt.results)
    if result_ids != attempted_ids[: len(result_ids)]:
        raise EvidenceSummaryError("receipt results disagree with frozen launch order")
    calls: list[CallEvidenceSummary] = []
    for result in receipt.results:
        file_references = tuple(
            reference
            for reference in result.evidence_references
            if not reference.startswith(("egress-proxy:", "egress-network:"))
        )
        if len(file_references) != 1 or not result.evidence_digests:
            raise EvidenceSummaryError("call result does not have one authoritative artifact")
        artifact = _resolve_artifact(root, result.call_id, file_references[0])
        if artifact.is_dir():
            domain: Literal["ARTIFACT_TREE_DIGEST", "RAW_FILE_SHA256"] = "ARTIFACT_TREE_DIGEST"
            try:
                digest = digest_tree(artifact)
            except (OSError, TaskPackageError) as exc:
                raise EvidenceSummaryError("call artifact tree is unreadable") from exc
        else:
            domain = "RAW_FILE_SHA256"
            digest = sha256_file(artifact)
        calls.append(
            CallEvidenceSummary(
                call_id=result.call_id,
                evidence_digest_domain=domain,
                evidence_digest=digest,
                receipt_digest_verified=digest == result.evidence_digests[0],
                egress_attestation_digest_count=max(0, len(result.evidence_digests) - 1),
                facts=_artifact_facts(result.call_id, artifact),
            )
        )
    if any(not call.receipt_digest_verified for call in calls):
        raise EvidenceSummaryError("receipt artifact digest does not match authoritative evidence")
    return SmokeEvidenceSummary(
        receipt_digest=_sha256_bytes(receipt_bytes),
        plan_id=receipt.plan_id,
        smoke_plan_digest=receipt.smoke_plan_digest,
        release_plan_digest=receipt.release_plan_digest,
        status=receipt.status.value,
        attempted_top_level_launches=receipt.attempted_top_level_launches,
        attempted_call_ids=attempted_ids,
        failing_call_id=receipt.failing_call_id,
        failure_category=(receipt.failure_category.value if receipt.failure_category else None),
        calls=tuple(calls),
    )


def verify_history_against_summary(history: dict[str, Any], summary: SmokeEvidenceSummary) -> None:
    """Authoritative ingestion check for facts whose digest domains were historically copied."""

    expected = summary.candidate_history_summary()
    for field in (
        "plan_id",
        "smoke_plan_digest",
        "release_plan_digest",
        "receipt_digest",
        "status",
        "attempted_top_level_launches",
        "failing_call_id",
        "failure_category",
    ):
        if history.get(field) != expected.get(field):
            raise EvidenceSummaryError(f"history disagrees with evidence summary: {field}")
    history_calls = history.get("calls")
    if not isinstance(history_calls, list) or len(history_calls) != len(summary.calls):
        raise EvidenceSummaryError("history call set disagrees with evidence summary")
    for history_call, summarized in zip(history_calls, summary.calls, strict=True):
        if not isinstance(history_call, dict) or (
            history_call.get("call_id") != summarized.call_id
            or history_call.get("evidence_digest") != summarized.evidence_digest
        ):
            raise EvidenceSummaryError("history call evidence digest/domain disagrees")
