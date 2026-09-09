from __future__ import annotations

from pathlib import Path
from typing import Any

from harnesslab.evidence.reader import EvidenceReadError, VerifiedManifest, load_normalized_trace
from harnesslab.harness_lane.models import TraceEventType

_TOOL_ITEMS = {
    TraceEventType.COMMAND_EXECUTION,
    TraceEventType.FILE_CHANGE,
    TraceEventType.MCP_TOOL_CALL,
    TraceEventType.WEB_SEARCH,
    TraceEventType.TODO_LIST,
}


def manifest_tool_calls(raw: dict[str, Any], manifest_path: Path | None = None) -> int | None:
    """Current derived invocation count; never reinterpret event totals as calls.

    Direct patch generation has no subject tools. Harness counts require digest-bound
    trace bytes. Historical Claude streams retain tool-use blocks without IDs, so count
    those starts only; Codex item lifecycle events are deduplicated by their item ID.
    This function neither updates manifests nor backfills historical database metrics.
    """
    if "provider_result" in raw and "trace_event_types" not in raw:
        return 0
    if raw.get("trace_coverage") in {"FINAL_OUTPUT_ONLY", "NOT_AVAILABLE"}:
        return None
    digest = raw.get("normalized_trace_digest")
    if manifest_path is None or not isinstance(digest, str):
        return None
    try:
        trace, _, _ = load_normalized_trace(VerifiedManifest(raw=raw, path=manifest_path))
    except EvidenceReadError:
        return None
    # Missing/truncated/protocol-error streams cannot establish a total, including zero.
    if (
        sum(
            event.type in {TraceEventType.TURN_COMPLETED, TraceEventType.TURN_FAILED}
            for event in trace.events
        )
        != 1
    ):
        return None
    if raw.get("timed_out") or raw.get("cancelled"):
        return None
    if any(event.type in {TraceEventType.UNKNOWN, TraceEventType.ERROR} for event in trace.events):
        return None
    codex_ids: set[str] = set()
    claude_ids: set[str] = set()
    claude_starts = 0
    claude_results = 0
    for event in trace.events:
        if event.native_event_type.startswith("tool."):
            if event.item_id:
                claude_ids.add(event.item_id)
            else:
                claude_starts += 1
        elif event.native_event_type == "user.tool_result":
            claude_results += 1
        elif event.type in _TOOL_ITEMS:
            if event.native_event_type not in {"item.started", "item.updated", "item.completed"}:
                return None
            if not event.item_id:
                return None
            codex_ids.add(event.item_id)
    # A results-only Claude stream is incomplete, not a zero-tool execution.
    if claude_results > claude_starts + len(claude_ids):
        return None
    return len(codex_ids) + len(claude_ids) + claude_starts
