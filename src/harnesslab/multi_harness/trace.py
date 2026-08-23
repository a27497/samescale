from __future__ import annotations

import hashlib
import json
from typing import Any

from harnesslab.harness_lane.models import (
    CodexTokenUsage,
    HarnessFailureCategory,
    NativeFileChange,
    NormalizedTrace,
    NormalizedTraceEvent,
    ObservedModelStatus,
    SanitizedNativeEvent,
    TraceEventType,
)
from harnesslab.multi_harness.models import HarnessProcessCapture, MultiHarnessCollection
from harnesslab.sandbox.artifacts import redact_exact

MAX_LINES = 10_000
MAX_LINE_BYTES = 1_000_000
MAX_TEXT = 131_072


class _DuplicateKey(ValueError):
    pass


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKey(key)
        result[key] = value
    return result


def _text(value: object, secrets: tuple[str, ...], limit: int = MAX_TEXT) -> str | None:
    if not isinstance(value, str):
        return None
    encoded = redact_exact(value, secrets).encode("utf-8")[:limit]
    while True:
        try:
            return encoded.decode("utf-8")
        except UnicodeDecodeError:
            encoded = encoded[:-1]


def _usage(value: object) -> CodexTokenUsage | None:
    if not isinstance(value, dict):
        return None

    def number(name: str) -> int | None:
        item = value.get(name)
        return item if isinstance(item, int) and not isinstance(item, bool) and item >= 0 else None

    return CodexTokenUsage(
        input_tokens=number("input_tokens"),
        cached_input_tokens=number("cache_read_input_tokens"),
        cache_write_input_tokens=number("cache_creation_input_tokens"),
        output_tokens=number("output_tokens"),
    )


def _digest(sanitized_jsonl: str, trace: NormalizedTrace) -> tuple[str, str]:
    native = "sha256:" + hashlib.sha256(sanitized_jsonl.encode()).hexdigest()
    trace_digest = "sha256:" + hashlib.sha256(trace.canonical_json().encode()).hexdigest()
    return native, trace_digest


def _failure_from_capture(capture: HarnessProcessCapture) -> HarnessFailureCategory | None:
    if capture.cancelled:
        return HarnessFailureCategory.CANCELLED
    if capture.timed_out:
        return HarnessFailureCategory.TIMEOUT
    if capture.exit_code not in {0, None}:
        return HarnessFailureCategory.PROCESS_ERROR
    return None


def _protocol_failure(capture: HarnessProcessCapture) -> MultiHarnessCollection:
    event = SanitizedNativeEvent(ordinal=1, event_type="protocol.error", error_code="malformed")
    sanitized = event.canonical_json() + "\n"
    trace = NormalizedTrace(
        events=(
            NormalizedTraceEvent(
                ordinal=1,
                type=TraceEventType.ERROR,
                native_event_type=event.event_type,
                status=event.error_code,
            ),
        )
    )
    native_digest, trace_digest = _digest(sanitized, trace)
    return MultiHarnessCollection(
        (event,),
        sanitized,
        native_digest,
        trace,
        trace_digest,
        None,
        None,
        ObservedModelStatus.NOT_EXPOSED,
        None,
        0,
        _failure_from_capture(capture) or HarnessFailureCategory.PROTOCOL_ERROR,
    )


def _trace_event(event: SanitizedNativeEvent) -> NormalizedTraceEvent:
    mapping = {
        "system.init": TraceEventType.THREAD_STARTED,
        "assistant.text": TraceEventType.AGENT_MESSAGE,
        "assistant.thinking": TraceEventType.REASONING_PRESENT,
        "tool.Bash": TraceEventType.COMMAND_EXECUTION,
        "tool.Read": TraceEventType.COMMAND_EXECUTION,
        "tool.Edit": TraceEventType.FILE_CHANGE,
        "tool.Write": TraceEventType.FILE_CHANGE,
        "user.tool_result": TraceEventType.COMMAND_EXECUTION,
        "system.api_retry": TraceEventType.API_RETRY,
        "result.success": TraceEventType.TURN_COMPLETED,
        "result.error": TraceEventType.TURN_FAILED,
        "deepseek.final": TraceEventType.AGENT_MESSAGE,
    }
    return NormalizedTraceEvent(
        ordinal=event.ordinal,
        type=mapping.get(event.event_type, TraceEventType.UNKNOWN),
        native_event_type=event.event_type,
        item_type=event.item_type,
        status=event.status,
        text=event.text,
        command=event.command,
        public_output=event.public_output,
        exit_code=event.exit_code,
        file_changes=event.file_changes,
        usage=event.usage,
    )


def collect_claude_stream(
    capture: HarnessProcessCapture, *, secret_values: tuple[str, ...] = ()
) -> MultiHarnessCollection:
    if len(capture.stdout_lines) > MAX_LINES:
        return _protocol_failure(capture)
    events: list[SanitizedNativeEvent] = []
    observed_model: str | None = None
    terminal: str | None = None
    usage: CodexTokenUsage | None = None
    retries = 0
    profile_violation = False
    structured_failure: HarnessFailureCategory | None = None
    try:
        for line in capture.stdout_lines:
            if len(line.encode()) > MAX_LINE_BYTES:
                raise ValueError("line too large")
            raw = json.loads(line, object_pairs_hook=_unique_object)
            if not isinstance(raw, dict) or not isinstance(raw.get("type"), str):
                raise ValueError("event is not an object with a type")
            root_type = raw["type"]
            if root_type == "system" and raw.get("subtype") == "init":
                tools = raw.get("tools")
                if not isinstance(tools, list) or set(tools) != {"Read", "Edit", "Write", "Bash"}:
                    profile_violation = True
                mcp = raw.get("mcp_servers", [])
                plugins = raw.get("plugins", [])
                if mcp not in ([], {}) or plugins not in ([], {}):
                    profile_violation = True
                model = _text(raw.get("model"), secret_values, 300)
                observed_model = model or observed_model
                events.append(
                    SanitizedNativeEvent(
                        ordinal=len(events) + 1,
                        event_type="system.init",
                        observed_model=model,
                    )
                )
            elif root_type == "assistant":
                message = raw.get("message")
                content = message.get("content") if isinstance(message, dict) else None
                if not isinstance(content, list):
                    raise ValueError("assistant content is missing")
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    block_type = block.get("type")
                    common: dict[str, Any] = {
                        "ordinal": len(events) + 1,
                        "item_type": str(block_type) if block_type is not None else None,
                    }
                    if block_type == "thinking":
                        events.append(
                            SanitizedNativeEvent(
                                **common,
                                event_type="assistant.thinking",
                                reasoning_present=True,
                            )
                        )
                    elif block_type == "text":
                        events.append(
                            SanitizedNativeEvent(
                                **common,
                                event_type="assistant.text",
                                text=_text(block.get("text"), secret_values),
                            )
                        )
                    elif block_type == "tool_use":
                        name = block.get("name")
                        if name not in {"Read", "Edit", "Write", "Bash"}:
                            profile_violation = True
                        tool_name = str(name)
                        tool_input = block.get("input")
                        tool_input = tool_input if isinstance(tool_input, dict) else {}
                        path = _text(
                            tool_input.get("file_path", tool_input.get("path")), secret_values, 1000
                        )
                        changes = (
                            (NativeFileChange(path=path, kind=tool_name.lower()),) if path else ()
                        )
                        events.append(
                            SanitizedNativeEvent(
                                **common,
                                event_type=f"tool.{tool_name}",
                                command=_text(tool_input.get("command"), secret_values, 16_384),
                                file_changes=changes,
                            )
                        )
                    else:
                        events.append(
                            SanitizedNativeEvent(**common, event_type=f"assistant.{block_type}")
                        )
            elif root_type == "user":
                message = raw.get("message")
                content = message.get("content") if isinstance(message, dict) else None
                if not isinstance(content, list):
                    raise ValueError("user content is missing")
                for block in content:
                    if not isinstance(block, dict) or block.get("type") != "tool_result":
                        continue
                    value = block.get("content")
                    if isinstance(value, list):
                        value = "\n".join(
                            str(item.get("text", "")) for item in value if isinstance(item, dict)
                        )
                    events.append(
                        SanitizedNativeEvent(
                            ordinal=len(events) + 1,
                            event_type="user.tool_result",
                            public_output=_text(value, secret_values, 65_536),
                            status="error" if block.get("is_error") is True else "completed",
                        )
                    )
            elif root_type == "system" and raw.get("subtype") == "api_retry":
                retries += 1
                events.append(
                    SanitizedNativeEvent(
                        ordinal=len(events) + 1,
                        event_type="system.api_retry",
                        status=_text(raw.get("attempt"), secret_values, 200),
                        error_code=_text(raw.get("error"), secret_values, 200),
                    )
                )
            elif root_type == "result":
                failed = raw.get("is_error") is True or raw.get("subtype") not in {"success", None}
                terminal = "result.error" if failed else "result.success"
                usage = _usage(raw.get("usage"))
                events.append(
                    SanitizedNativeEvent(
                        ordinal=len(events) + 1,
                        event_type=terminal,
                        status=_text(raw.get("subtype"), secret_values, 200),
                        text=_text(raw.get("result"), secret_values),
                        usage=usage,
                        error_code=_text(raw.get("error"), secret_values, 200),
                    )
                )
            elif root_type == "error":
                error = raw.get("error")
                error = error if isinstance(error, dict) else {}
                code = _text(error.get("type", error.get("code")), secret_values, 200)
                categories = {
                    "authentication_error": HarnessFailureCategory.AUTHENTICATION,
                    "invalid_api_key": HarnessFailureCategory.AUTHENTICATION,
                    "configuration_error": HarnessFailureCategory.CONFIGURATION,
                    "timeout_error": HarnessFailureCategory.TIMEOUT,
                    "cancelled": HarnessFailureCategory.CANCELLED,
                }
                structured_failure = categories.get(
                    code or "", HarnessFailureCategory.MODEL_TURN_FAILED
                )
                terminal = "result.error"
                events.append(
                    SanitizedNativeEvent(
                        ordinal=len(events) + 1,
                        event_type="result.error",
                        error_code=code,
                    )
                )
            else:
                events.append(
                    SanitizedNativeEvent(
                        ordinal=len(events) + 1,
                        event_type=str(root_type),
                        status=_text(raw.get("subtype"), secret_values, 200),
                    )
                )
    except (ValueError, TypeError, UnicodeError, json.JSONDecodeError, _DuplicateKey):
        return _protocol_failure(capture)
    trace = NormalizedTrace(events=tuple(_trace_event(event) for event in events))
    sanitized = "".join(event.canonical_json() + "\n" for event in events)
    native_digest, trace_digest = _digest(sanitized, trace)
    failure = _failure_from_capture(capture)
    if failure is None and profile_violation:
        failure = HarnessFailureCategory.PROFILE_VIOLATION
    if failure is None and structured_failure is not None:
        failure = structured_failure
    if failure is None and terminal == "result.error":
        failure = HarnessFailureCategory.MODEL_TURN_FAILED
    if failure is None and terminal is None:
        failure = HarnessFailureCategory.PROTOCOL_ERROR
    return MultiHarnessCollection(
        tuple(events),
        sanitized,
        native_digest,
        trace,
        trace_digest,
        terminal,
        observed_model,
        ObservedModelStatus.EXPOSED if observed_model else ObservedModelStatus.NOT_EXPOSED,
        usage,
        retries,
        failure,
    )


def collect_deepseek_final(
    capture: HarnessProcessCapture, *, secret_values: tuple[str, ...] = ()
) -> MultiHarnessCollection:
    output = _text("\n".join(capture.stdout_lines), secret_values)
    if output is None or (not output.strip() and _failure_from_capture(capture) is None):
        return _protocol_failure(capture)
    event = SanitizedNativeEvent(ordinal=1, event_type="deepseek.final", text=output)
    trace = NormalizedTrace(events=(_trace_event(event),))
    sanitized = event.canonical_json() + "\n"
    native_digest, trace_digest = _digest(sanitized, trace)
    return MultiHarnessCollection(
        (event,),
        sanitized,
        native_digest,
        trace,
        trace_digest,
        "process.completed" if capture.exit_code == 0 else "process.failed",
        None,
        ObservedModelStatus.NOT_EXPOSED,
        None,
        0,
        _failure_from_capture(capture),
    )
