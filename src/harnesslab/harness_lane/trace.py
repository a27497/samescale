from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any

from harnesslab.harness_lane.models import (
    CodexCollection,
    CodexProcessCapture,
    CodexTokenUsage,
    HarnessFailureCategory,
    NativeFileChange,
    NormalizedTrace,
    NormalizedTraceEvent,
    ObservedModelStatus,
    SanitizedNativeEvent,
    TraceEventType,
)
from harnesslab.sandbox.artifacts import redact_exact

MAX_NATIVE_LINES = 10_000
MAX_NATIVE_LINE_BYTES = 1_000_000
MAX_NATIVE_TOTAL_BYTES = 4_000_000
MAX_PUBLIC_TEXT = 131_072
MAX_COMMAND_TEXT = 16_384
MAX_COMMAND_OUTPUT = 65_536
_BWRAP_NAMESPACE_DENIAL = "bwrap: No permissions to create a new namespace"


class _CommandExecutionOutcome(StrEnum):
    SUCCESSFUL = "successful_command"
    SUBJECT_NONZERO_EXIT = "subject_command_nonzero_exit"
    INFRA_FAILURE = "command_execution_infra_failure"


class _DuplicateKey(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(key)
        result[key] = value
    return result


def _safe_text(value: object, *, limit: int, secrets: tuple[str, ...]) -> str | None:
    if not isinstance(value, str):
        return None
    redacted = redact_exact(value, secrets)
    encoded = redacted.encode("utf-8", errors="strict")
    if len(encoded) > limit:
        encoded = encoded[:limit]
        while True:
            try:
                redacted = encoded.decode("utf-8")
                break
            except UnicodeDecodeError:
                encoded = encoded[:-1]
    return redacted


def _nonnegative(value: object) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def _usage(value: object) -> CodexTokenUsage | None:
    if not isinstance(value, dict):
        return None
    return CodexTokenUsage(
        input_tokens=_nonnegative(value.get("input_tokens")),
        cached_input_tokens=_nonnegative(value.get("cached_input_tokens")),
        cache_write_input_tokens=_nonnegative(value.get("cache_write_input_tokens")),
        output_tokens=_nonnegative(value.get("output_tokens")),
        reasoning_output_tokens=_nonnegative(value.get("reasoning_output_tokens")),
    )


def _native_changes(value: object, secrets: tuple[str, ...]) -> tuple[NativeFileChange, ...]:
    if not isinstance(value, list):
        return ()
    changes: list[NativeFileChange] = []
    for raw in value[:1000]:
        if not isinstance(raw, dict):
            continue
        path = _safe_text(raw.get("path"), limit=1000, secrets=secrets)
        if not path:
            continue
        changes.append(
            NativeFileChange(
                path=path,
                kind=_safe_text(raw.get("kind"), limit=100, secrets=secrets),
            )
        )
    return tuple(changes)


def _error_fields(raw: dict[str, Any], secrets: tuple[str, ...]) -> tuple[str | None, str | None]:
    error = raw.get("error")
    if isinstance(error, dict):
        return (
            _safe_text(error.get("message"), limit=MAX_PUBLIC_TEXT, secrets=secrets),
            _safe_text(error.get("code"), limit=200, secrets=secrets),
        )
    return _safe_text(error, limit=MAX_PUBLIC_TEXT, secrets=secrets), None


def _sanitize_event(
    raw: dict[str, Any], ordinal: int, secrets: tuple[str, ...]
) -> SanitizedNativeEvent:
    event_type = _safe_text(raw.get("type"), limit=200, secrets=secrets)
    if not event_type:
        raise ValueError("native event type is missing")
    thread_id = _safe_text(raw.get("thread_id"), limit=300, secrets=secrets)
    observed_model = _safe_text(
        raw.get("observed_model", raw.get("model")), limit=300, secrets=secrets
    )
    if event_type in {"turn.completed", "turn.failed", "error"}:
        text: str | None = None
        error_code: str | None = None
        if event_type in {"turn.failed", "error"}:
            text, error_code = _error_fields(raw, secrets)
            if text is None:
                text = _safe_text(raw.get("message"), limit=MAX_PUBLIC_TEXT, secrets=secrets)
        return SanitizedNativeEvent(
            ordinal=ordinal,
            event_type=event_type,
            thread_id=thread_id,
            observed_model=observed_model,
            text=text,
            usage=_usage(raw.get("usage")),
            error_code=error_code,
        )
    if event_type not in {"item.started", "item.updated", "item.completed"}:
        return SanitizedNativeEvent(
            ordinal=ordinal,
            event_type=event_type,
            status=_safe_text(raw.get("status"), limit=200, secrets=secrets),
            thread_id=thread_id,
            observed_model=observed_model,
        )
    item = raw.get("item")
    if not isinstance(item, dict):
        raise ValueError("item event lacks an item object")
    item_type = _safe_text(item.get("type"), limit=200, secrets=secrets)
    if not item_type:
        raise ValueError("native item type is missing")
    common: dict[str, object] = {
        "ordinal": ordinal,
        "event_type": event_type,
        "item_type": item_type,
        "item_id": _safe_text(item.get("id"), limit=300, secrets=secrets),
        "status": _safe_text(item.get("status"), limit=200, secrets=secrets),
        "thread_id": thread_id,
        "observed_model": observed_model,
    }
    if item_type == "reasoning":
        return SanitizedNativeEvent(**common, reasoning_present=True)
    if item_type == "agent_message":
        return SanitizedNativeEvent(
            **common,
            text=_safe_text(item.get("text"), limit=MAX_PUBLIC_TEXT, secrets=secrets),
        )
    if item_type == "command_execution":
        public_output = item.get("aggregated_output", item.get("output"))
        return SanitizedNativeEvent(
            **common,
            command=_safe_text(item.get("command"), limit=MAX_COMMAND_TEXT, secrets=secrets),
            public_output=_safe_text(public_output, limit=MAX_COMMAND_OUTPUT, secrets=secrets),
            exit_code=item.get("exit_code") if isinstance(item.get("exit_code"), int) else None,
        )
    if item_type == "file_change":
        return SanitizedNativeEvent(
            **common,
            file_changes=_native_changes(item.get("changes"), secrets),
        )
    if item_type == "error":
        return SanitizedNativeEvent(
            **common,
            text=_safe_text(item.get("message"), limit=MAX_PUBLIC_TEXT, secrets=secrets),
            error_code=_safe_text(item.get("code"), limit=200, secrets=secrets),
        )
    return SanitizedNativeEvent(**common)


def _trace_type(event: SanitizedNativeEvent) -> TraceEventType:
    if event.event_type == "thread.started":
        return TraceEventType.THREAD_STARTED
    if event.event_type == "turn.started":
        return TraceEventType.TURN_STARTED
    if event.event_type == "turn.completed":
        return TraceEventType.TURN_COMPLETED
    if event.event_type == "turn.failed":
        return TraceEventType.TURN_FAILED
    if event.event_type == "error":
        return TraceEventType.ERROR
    item_types = {
        "agent_message": TraceEventType.AGENT_MESSAGE,
        "reasoning": TraceEventType.REASONING_PRESENT,
        "command_execution": TraceEventType.COMMAND_EXECUTION,
        "file_change": TraceEventType.FILE_CHANGE,
        "mcp_tool_call": TraceEventType.MCP_TOOL_CALL,
        "web_search": TraceEventType.WEB_SEARCH,
        "todo_list": TraceEventType.TODO_LIST,
        "error": TraceEventType.ITEM_ERROR,
    }
    return item_types.get(event.item_type or "", TraceEventType.UNKNOWN)


def _normalized_trace(events: tuple[SanitizedNativeEvent, ...]) -> NormalizedTrace:
    return NormalizedTrace(
        events=tuple(
            NormalizedTraceEvent(
                ordinal=event.ordinal,
                type=_trace_type(event),
                native_event_type=event.event_type,
                item_type=event.item_type,
                item_id=event.item_id,
                status=event.status,
                text=event.text,
                command=event.command,
                public_output=event.public_output,
                exit_code=event.exit_code,
                file_changes=event.file_changes,
                usage=event.usage,
            )
            for event in events
        )
    )


def _completed_command_outcome(
    event: NormalizedTraceEvent,
) -> _CommandExecutionOutcome | None:
    """Classify completed commands without treating ordinary shell exits as infrastructure."""

    if (
        event.type is not TraceEventType.COMMAND_EXECUTION
        or event.native_event_type != "item.completed"
    ):
        return None
    if _BWRAP_NAMESPACE_DENIAL in (event.public_output or ""):
        return _CommandExecutionOutcome.INFRA_FAILURE
    if event.exit_code is not None and event.exit_code != 0:
        return _CommandExecutionOutcome.SUBJECT_NONZERO_EXIT
    if event.status in {"failed", "error"}:
        return _CommandExecutionOutcome.INFRA_FAILURE
    if event.status == "completed" and event.exit_code == 0:
        return _CommandExecutionOutcome.SUCCESSFUL
    return None


def _clean_execution_budget_exhaustion(
    capture: CodexProcessCapture,
    trace: NormalizedTrace,
    *,
    malformed: bool,
    profile_violation: bool,
    terminal: SanitizedNativeEvent | None,
) -> bool:
    """Recognize a budget-limited subject only from strict positive trace evidence."""

    if (
        not capture.timed_out
        or capture.cancelled
        or malformed
        or profile_violation
        or terminal is not None
    ):
        return False
    trace_types = {event.type for event in trace.events}
    if not {
        TraceEventType.THREAD_STARTED,
        TraceEventType.TURN_STARTED,
    }.issubset(trace_types):
        return False
    disqualifying = {
        TraceEventType.ITEM_ERROR,
        TraceEventType.TURN_FAILED,
        TraceEventType.ERROR,
        TraceEventType.UNKNOWN,
        TraceEventType.MCP_TOOL_CALL,
        TraceEventType.WEB_SEARCH,
        TraceEventType.API_RETRY,
    }
    if trace_types & disqualifying:
        return False
    command_outcomes = tuple(
        outcome
        for event in trace.events
        if (outcome := _completed_command_outcome(event)) is not None
    )
    if _CommandExecutionOutcome.INFRA_FAILURE in command_outcomes:
        return False
    return _CommandExecutionOutcome.SUCCESSFUL in command_outcomes


def collect_codex_jsonl(
    capture: CodexProcessCapture, *, secret_values: tuple[str, ...] = ()
) -> CodexCollection:
    events: list[SanitizedNativeEvent] = []
    malformed = False
    total_bytes = 0
    if len(capture.lines) > MAX_NATIVE_LINES:
        malformed = True
    for ordinal, line in enumerate(capture.lines[:MAX_NATIVE_LINES], start=1):
        try:
            encoded = line.encode("utf-8", errors="strict")
        except UnicodeEncodeError:
            encoded = b""
            malformed = True
        total_bytes += len(encoded)
        if len(encoded) > MAX_NATIVE_LINE_BYTES or total_bytes > MAX_NATIVE_TOTAL_BYTES:
            malformed = True
            events.append(SanitizedNativeEvent(ordinal=ordinal, event_type="malformed"))
            continue
        try:
            raw = json.loads(line, object_pairs_hook=_unique_object)
            if not isinstance(raw, dict):
                raise ValueError("native line must be an object")
            event = _sanitize_event(raw, ordinal, secret_values)
        except (ValueError, TypeError, UnicodeError, _DuplicateKey, json.JSONDecodeError):
            malformed = True
            event = SanitizedNativeEvent(ordinal=ordinal, event_type="malformed")
        events.append(event)
    sanitized = tuple(events)
    sanitized_jsonl = "".join(event.canonical_json() + "\n" for event in sanitized)
    native_digest = "sha256:" + hashlib.sha256(sanitized_jsonl.encode("utf-8")).hexdigest()
    trace = _normalized_trace(sanitized)
    trace_json = trace.canonical_json()
    trace_digest = "sha256:" + hashlib.sha256(trace_json.encode("utf-8")).hexdigest()
    terminals = [
        event
        for event in sanitized
        if event.event_type in {"turn.completed", "turn.failed", "error"}
    ]
    terminal = terminals[-1] if terminals else None
    profile_violation = any(
        event.item_type in {"mcp_tool_call", "web_search"} for event in sanitized
    )
    authentication_codes = {
        "authentication_error",
        "invalid_api_key",
        "unauthorized",
    }
    if capture.cancelled:
        failure = HarnessFailureCategory.CANCELLED
    elif profile_violation:
        failure = HarnessFailureCategory.PROFILE_VIOLATION
    elif malformed or len(terminals) > 1:
        failure = HarnessFailureCategory.PROTOCOL_ERROR
    elif capture.timed_out:
        failure = (
            HarnessFailureCategory.EXECUTION_BUDGET_EXHAUSTED
            if _clean_execution_budget_exhaustion(
                capture,
                trace,
                malformed=malformed,
                profile_violation=profile_violation,
                terminal=terminal,
            )
            else HarnessFailureCategory.TIMEOUT
        )
    elif terminal is None:
        failure = (
            HarnessFailureCategory.PROCESS_ERROR
            if capture.exit_code not in {None, 0}
            else HarnessFailureCategory.PROTOCOL_ERROR
        )
    elif terminal.event_type in {"turn.failed", "error"}:
        failure = (
            HarnessFailureCategory.AUTHENTICATION
            if terminal.error_code in authentication_codes
            else HarnessFailureCategory.MODEL_TURN_FAILED
        )
    else:
        failure = None
    observed_model = next(
        (event.observed_model for event in sanitized if event.observed_model is not None), None
    )
    usage = next(
        (
            event.usage
            for event in reversed(sanitized)
            if event.event_type == "turn.completed" and event.usage is not None
        ),
        None,
    )
    return CodexCollection(
        sanitized_events=sanitized,
        sanitized_jsonl=sanitized_jsonl,
        native_digest=native_digest,
        trace=trace,
        trace_digest=trace_digest,
        thread_id=next((event.thread_id for event in sanitized if event.thread_id), None),
        terminal_event=terminal.event_type if terminal is not None else None,
        observed_model=observed_model,
        observed_model_status=(
            ObservedModelStatus.EXPOSED
            if observed_model is not None
            else ObservedModelStatus.NOT_EXPOSED
        ),
        usage=usage,
        failure_category=failure,
    )
