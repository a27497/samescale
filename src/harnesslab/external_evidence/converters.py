"""Data-only converters into the existing NormalizedTrace; no Agent or session discovery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from harnesslab.analyst.offline_replay import decode, require
from harnesslab.episodes.hooks import derive_episode, normalized, read_events
from harnesslab.episodes.service import read_codex_episode
from harnesslab.episodes.verified_hooks import read_verified_hook_bundle
from harnesslab.external_evidence.models import ApprovedSource, HarnessIdentity
from harnesslab.harness_lane.models import (
    HarnessLaneEvidence,
    NormalizedTrace,
    NormalizedTraceEvent,
    TraceEventType,
)
from harnesslab.harness_lane.trace import _normalized_trace, _sanitize_event
from harnesslab.multi_harness.models import HarnessProcessCapture
from harnesslab.multi_harness.trace import collect_claude_stream
from harnesslab.registry.models import canonical_digest
from harnesslab.tasks.package import digest_tree, sha256_bytes


@dataclass(frozen=True)
class Conversion:
    trace: NormalizedTrace
    original_kind: str
    original: str
    episode_id: str | None
    coverage: str
    missing: list[str]
    changes: dict[str, Any]
    verification: dict[str, Any]
    infrastructure: dict[str, Any]
    harness: HarnessIdentity | None


def codex_artifacts(source: ApprovedSource, files: dict[str, bytes]) -> Conversion:
    # Shared intake owns acquisition, privacy and storage. Existing readers own artifact validity.
    from harnesslab.external_evidence.service import (
        input_require,
        safe_name,
        unknown_verification,
        workspace_files,
    )

    assert source.path is not None and source.digest is not None
    verification = unknown_verification()
    changes: dict[str, Any] = {"status": "BASELINE_MISSING", "paths": []}
    infrastructure: dict[str, Any] = {"status": "UNKNOWN", "root_cause": None}
    missing = [
        "actual_model",
        "provider_route",
        "request_count",
        "usage",
        "cost",
        "wall_clock_order",
    ]
    if source.format == "verified-hook-v1":
        input_require(
            sha256_bytes((source.path / "bundle.json").read_bytes()) == source.digest,
            "EVIDENCE_PIN_MISMATCH",
            "source pin mismatch",
        )
        verification = read_verified_hook_bundle(source.path, source.digest)
        require(
            verification["workspace_digest"] == source.workspace_digest,
            "verifier workspace mismatch",
        )
        # Free-form hidden check names never leave the trusted verifier reader.
        verification = {
            **verification,
            "failed_checks": [canonical_digest(name) for name in verification["failed_checks"]],
        }
        events = read_events(source.path / "hooks")
        raw = decode((source.path / "episode.json").read_bytes())
        original_kind = raw["source_kind"]
        require(
            original_kind != "synthetic" or source.source_kind == "synthetic", "fixture relabeling"
        )
        episode = derive_episode(events, original_kind)
        trace = normalized(events)
        task = decode((source.path / "task.json").read_bytes())
        baseline = source.path / "task-package" / task["id"] / task["version"] / "workspace"
        baseline_files = workspace_files(baseline)
        changes = {
            "status": "DIGEST_BOUND_BASELINE",
            "paths": sorted(
                p
                for p in files.keys() | baseline_files.keys()
                if files.get(p) != baseline_files.get(p)
            ),
        }
        original = "NOT_VERIFIED"
        episode_id = episode.identity
        coverage = "PAIRED_HOOKS_ONLY"
    elif source.format in {"native-hook-v1", "hook-v1"}:
        original_kind = source.source_kind
        input_require(
            digest_tree(source.path) == source.digest, "EVIDENCE_PIN_MISMATCH", "hook pin mismatch"
        )
        events = read_events(source.path)
        require(len({(e.source, e.session) for e in events}) == 1, "mixed hook sessions")
        try:
            episode = derive_episode(events, source.source_kind)
            trace = normalized(events)
            episode_id = episode.identity
            coverage = "PAIRED_HOOKS_ONLY"
        except ValueError:
            # Keep partial observations, without fabricating a valid original Episode.
            episode_id = None
            coverage = "INCOMPLETE_HOOKS"
            missing.append("paired_hook_lifecycle")
            trace = NormalizedTrace(
                events=tuple(
                    NormalizedTraceEvent(
                        ordinal=i,
                        type=TraceEventType.UNKNOWN,
                        native_event_type="hook." + e.event,
                        exit_code=e.exit_code,
                        status="failed" if e.failure else "observed",
                    )
                    for i, e in enumerate(sorted(events, key=lambda e: e.key), 1)
                )
            )
        original = "NOT_VERIFIED"
    elif source.format in {"codex-h-lane-v1", "h-lane-v1"}:
        original_kind = source.source_kind
        input_require(
            digest_tree(source.path) == source.digest,
            "EVIDENCE_PIN_MISMATCH",
            "H-Lane pin mismatch",
        )
        episode_record = read_codex_episode(source.path, source_kind=source.source_kind)
        require(episode_record.source_bundle_digest == source.digest, "H-Lane pin mismatch")
        require(
            episode_record.workspace_output_digest == source.workspace_digest,
            "H-Lane workspace mismatch",
        )
        trace = NormalizedTrace.model_validate(
            decode((source.path / "trace/normalized.json").read_bytes())
        )
        evidence = HarnessLaneEvidence.model_validate(
            decode((source.path / "manifest.json").read_bytes())
        )
        original = episode_record.acceptance
        require(
            original == "NOT_VERIFIED" or episode_record.verifier_check_count > 0,
            "zero collected verifier checks",
        )
        episode_id = episode_record.identity
        coverage = "RECORDED_H_LANE"
        changes = {"status": "SOURCE_REPORTED_NOT_DIFF_RECONSTRUCTED", "paths": []}
        for name in evidence.changed_paths:
            safe_name(name.path)
            changes["paths"].append(name.path)
        infrastructure = {
            "status": evidence.harness_failure.value
            if evidence.harness_failure
            else "NO_RECORDED_FAILURE",
            "timed_out": evidence.timed_out,
            "root_cause": None,
        }
        # A legacy report is kept separate; do not elevate it to the strict hook reader's L0.
        verification = unknown_verification(
            "RECORDED_RESULT_ONLY_REQUIRES_TRUSTED_INDEPENDENT_ADMISSION"
        )
        verification["task_digest"] = episode_record.task_digest
    else:
        raise ValueError("unsupported Codex artifact format")
    return Conversion(
        trace,
        original_kind,
        original,
        episode_id,
        coverage,
        missing,
        changes,
        verification,
        infrastructure,
        HarnessIdentity(
            name="codex",
            version=source.harness.version if source.harness else None,
            extensions={"converter": "codex-v1", "input_format": source.format},
        ),
    )


def stream_json(source: ApprovedSource, data: bytes) -> Conversion:
    """Interpret only supplied pinned bytes; completion is never an acceptance verdict."""
    from harnesslab.external_evidence.service import (
        input_require,
        safe_content,
        unknown_verification,
    )

    lines = data.splitlines()
    require(0 < len(lines) <= 4096, "stream event limit")
    raw_events = []
    for line in lines:
        require(len(line) <= 1_000_000, "stream line limit")
        try:
            raw = decode(line)  # Includes duplicate-key and object-envelope rejection.
        except RecursionError:
            raise ValueError("stream nesting limit") from None
        pending: list[tuple[Any, int]] = [(raw, 0)]
        nodes = 0
        while pending:
            value, depth = pending.pop()
            nodes += 1
            require(depth <= 64 and nodes <= 50_000, "stream structure limit")
            if isinstance(value, str):
                safe_content(value.encode())  # Detect escaped credential-shaped values, too.
            elif isinstance(value, dict):
                pending.extend((v, depth + 1) for pair in value.items() for v in pair)
            elif isinstance(value, list):
                pending.extend((v, depth + 1) for v in value)
        require(isinstance(raw.get("type"), str), "missing stream event type")
        raw_events.append(raw)
    codex_types = {
        "thread.started",
        "turn.started",
        "turn.completed",
        "turn.failed",
        "item.started",
        "item.updated",
        "item.completed",
        "error",
    }
    claude_types = {"system", "assistant", "user", "result", "error", "stream_event"}
    name = source.harness.name if source.harness else "codex"
    if source.format == "auto-v1":
        types = {r["type"] for r in raw_events}
        is_codex = bool(types - {"error"}) and types <= codex_types
        is_claude = bool(types - {"error"}) and types <= claude_types
        input_require(is_codex != is_claude, "EVIDENCE_INPUT_UNSUPPORTED", "ambiguous stream")
        name = "codex" if is_codex else "claude-code"
        input_require(
            source.harness is None or name == source.harness.name,
            "EVIDENCE_INPUT_UNSUPPORTED",
            "declared harness mismatch",
        )
    input_require(
        name in {"codex", "claude-code"},
        "EVIDENCE_INPUT_UNSUPPORTED",
        "no converter registered for this harness",
    )
    if name == "codex":
        events = []
        for ordinal, raw in enumerate(raw_events, 1):
            input_require(
                raw["type"] in codex_types,
                "EVIDENCE_INPUT_UNSUPPORTED",
                "unsupported saved exec protocol",
            )
            if raw["type"].startswith("item."):
                require(isinstance(raw.get("item"), dict), "missing item envelope")
                require(isinstance(raw["item"].get("type"), str), "missing item type")
            item = raw.get("item", {})
            require(isinstance(item, dict), "invalid item envelope")
            safe = {
                "type": raw["type"],
                "item": {
                    k: v
                    for k, v in item.items()
                    if k in {"type", "id", "status", "command", "exit_code", "changes"}
                },
            }
            events.append(_sanitize_event(safe, ordinal, ()))
        trace = _normalized_trace(tuple(events))
        coverage = "SUPPLIED_EXEC_JSONL_ONLY"
    else:
        import json

        for raw in raw_events:
            input_require(
                raw["type"] in claude_types,
                "EVIDENCE_INPUT_UNSUPPORTED",
                "unsupported Claude stream protocol",
            )
            if raw["type"] in {"assistant", "user"}:
                message = raw.get("message")
                require(isinstance(message, dict), "invalid Claude message")
                assert isinstance(message, dict)
                content = message.get("content")
                # Initial user prompts carry no runtime observation and are never retained.
                if raw["type"] == "user" and isinstance(content, str):
                    message["content"] = []
                    continue
                require(isinstance(content, list), "invalid Claude content")
                assert isinstance(content, list)
                for block in content:
                    require(
                        isinstance(block, dict) and isinstance(block.get("type"), str),
                        "invalid Claude content block",
                    )
                    if block["type"] == "tool_use":
                        require(
                            isinstance(block.get("name"), str)
                            and isinstance(block.get("input"), dict),
                            "invalid tool use",
                        )
                    if block["type"] == "tool_result":
                        require(
                            "is_error" not in block or isinstance(block["is_error"], bool),
                            "invalid tool result",
                        )
            if raw["type"] == "result":
                require(
                    "is_error" not in raw or isinstance(raw["is_error"], bool),
                    "invalid result envelope",
                )
        capture = HarnessProcessCapture(
            stdout_lines=tuple(json.dumps(r) for r in raw_events),
            stderr_text="",
            exit_code=None,
            duration_ms=0,
        )
        collected = collect_claude_stream(capture)
        require(
            not any(e.native_event_type == "protocol.error" for e in collected.trace.events),
            "malformed Claude stream",
        )
        # The parser's locked campaign tool-profile is unrelated to saved external intake.
        # No profile verdict is persisted and missing process facts stay unknown.
        trace = NormalizedTrace(
            events=tuple(
                e.model_copy(update={"status": "failed"}) if e.status == "error" else e
                for e in collected.trace.events
            )
        )
        coverage = "SUPPLIED_STREAM_JSON_ONLY"
    missing = [
        "actual_model",
        "provider_route",
        "request_count",
        "usage",
        "cost",
        "wall_clock_order",
        "process_exit_code",
        "independent_verifier",
    ]
    if source.task_reference is None:
        missing.append("trusted_task_contract")
    if not any(
        e.type in {TraceEventType.TURN_COMPLETED, TraceEventType.TURN_FAILED} for e in trace.events
    ):
        missing.append("native_completion")
    if any(e.type == TraceEventType.UNKNOWN for e in trace.events):
        missing.append("unmapped_events")
    if name == "claude-code":
        missing.append("tool_call_links")
    failed = any(e.type in {TraceEventType.ERROR, TraceEventType.TURN_FAILED} for e in trace.events)
    return Conversion(
        trace,
        source.source_kind,
        "NOT_VERIFIED",
        None,
        coverage,
        missing,
        {"status": "BASELINE_MISSING", "paths": []},
        unknown_verification(),
        {"status": "RECORDED_TURN_OR_STREAM_FAILURE" if failed else "UNKNOWN", "root_cause": None},
        HarnessIdentity(
            name=name,
            version=source.harness.version if source.harness else None,
            extensions={"converter": f"{name}-v1", "input_format": "stream-json-v1"},
        ),
    )
