"""Passive local hooks: content-free receipts, CUSTOM Episodes and pinned offline replay.

No transcript reads, environment capture, commands, sockets or subject execution.
Only the local operator may configure the spool. Hashes attest integrity, not origin.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from harnesslab.analyst.offline_replay import decode, read_pinned, require
from harnesslab.comparability.models import canonical_digest
from harnesslab.contracts.common import Sha256Digest
from harnesslab.episodes.service import SourceKind
from harnesslab.harness_lane.models import NormalizedTrace, NormalizedTraceEvent, TraceEventType
from harnesslab.tasks.package import sha256_bytes

MAX_INPUT = 1_048_576
MAX_EVENTS = 4096
EVENTS = {"SessionStart", "PreToolUse", "PostToolUse", "PostToolUseFailure", "Stop"}
TOOLS = {"Bash", "apply_patch", "Edit", "Write", "Read"}


class HookEvent(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)

    schema_version: Literal[1] = 1
    source: Literal["codex", "claude"]
    session: Sha256Digest
    event: Literal["SessionStart", "PreToolUse", "PostToolUse", "PostToolUseFailure", "Stop"]
    call: Sha256Digest | None = None
    tool: Literal["Bash", "apply_patch", "Edit", "Write", "Read", "OTHER"] | None = None
    exit_code: int | None = Field(default=None, ge=-255, le=255)
    failure: bool = False

    @property
    def key(self) -> str:
        # A conflicting redelivery cannot silently create a new event.
        phase = "result" if self.event.startswith("PostToolUse") else self.event
        return canonical_digest([self.source, self.session, phase, self.call])[7:]


def _identity(value: Any) -> str:
    require(isinstance(value, str) and 0 < len(value) <= 512, "missing hook identity")
    return canonical_digest(value)


def _exit(response: Any) -> int | None:
    if isinstance(response, dict):
        value = response.get("exit_code", response.get("exitCode"))
        if value is not None:
            require(type(value) is int and -255 <= value <= 255, "invalid exit status")
            return int(value)
    # Codex 0.153.4 sends command stdout here, not the process-status envelope.
    # Even text that resembles a runtime header is not evidence of an exit code.
    return None


def redact_hook(raw: bytes, source: str) -> HookEvent:
    """Project to enums, hashes and numbers BEFORE any filesystem write."""
    require(len(raw) <= MAX_INPUT, "hook input too large")
    obj = decode(raw)
    event = obj.get("hook_event_name")
    require(event in EVENTS, "unsupported hook event")
    require(source in {"codex", "claude"}, "unsupported hook producer")
    require(source == "claude" or event != "PostToolUseFailure", "unsupported Codex event")
    tool_event = event in {"PreToolUse", "PostToolUse", "PostToolUseFailure"}
    tool = obj.get("tool_name") if tool_event else None
    require(not tool_event or (isinstance(tool, str) and bool(tool)), "missing tool")
    code = _exit(obj.get("tool_response")) if event == "PostToolUse" else None
    return HookEvent.model_validate(
        {
            "source": source,
            "session": _identity(obj.get("session_id")),
            "event": event,
            "call": _identity(obj.get("tool_use_id")) if tool_event else None,
            "tool": (tool if tool in TOOLS else "OTHER") if tool_event else None,
            "exit_code": code,
            "failure": event == "PostToolUseFailure" or (code is not None and code != 0),
        }
    )


def _directory(path: Path) -> None:
    require(not any(p.is_symlink() for p in (path, *path.parents)), "linked store")
    repository = Path(__file__).resolve().parents[3]
    require(
        not any(path.resolve().is_relative_to(repository / p) for p in ("tasks", "release")),
        "Official namespace is protected",
    )
    path.mkdir(parents=True, exist_ok=True, mode=0o700)


def _write_once(path: Path, data: bytes) -> None:
    require(not path.is_symlink(), "linked destination")
    try:
        with path.open("xb") as stream:
            os.chmod(path, 0o600)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except FileExistsError:
        require(path.is_file() and path.read_bytes() == data, "conflicting receipt")


def encode(obj: Any) -> bytes:
    return (json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def receive_hook(raw: bytes, source: str, spool: Path) -> HookEvent:
    # The lock serializes native hook processes; partial writes are rejected on read.
    _directory(spool)
    lock = spool / ".lock"
    require(not lock.is_symlink(), "linked lock")
    with lock.open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        try:
            event = redact_hook(raw, source)
            require(len(list(spool.glob("*.json"))) < MAX_EVENTS, "spool limit")
            _write_once(spool / (event.key + ".json"), encode(event.model_dump(mode="json")))
            return event
        except (ValueError, OSError, TypeError):
            # Content-free poison marker prevents incomplete acquisition being called complete.
            _write_once(spool / "REJECTED", b"FAIL_CLOSED\n")
            raise


def read_events(spool: Path) -> list[HookEvent]:
    require(spool.is_dir(), "missing spool")
    require(not any(p.is_symlink() for p in (spool, *spool.parents)), "linked spool")
    paths = list(spool.iterdir())
    require(0 < len(paths) <= MAX_EVENTS + 1, "invalid spool size")
    require(
        all(p.name == ".lock" or re.fullmatch(r"[a-f0-9]{64}\.json", p.name) for p in paths),
        "incomplete or rejected capture",
    )
    events = []
    for path in paths:
        require(path.is_file() and not path.is_symlink(), "unsafe receipt")
        if path.name == ".lock":
            continue
        require(path.stat().st_size <= 4096, "oversized receipt")
        event = HookEvent.model_validate(decode(path.read_bytes()))
        require(path.stem == event.key, "receipt identity drift")
        events.append(event)
    return events


def normalized(events: list[HookEvent]) -> NormalizedTrace:
    require(bool(events), "missing events")
    require(len({(e.source, e.session) for e in events}) == 1, "mixed sessions")
    require(len({e.key for e in events}) == len(events), "duplicate receipts")
    starts = [e for e in events if e.event == "SessionStart"]
    stops = [e for e in events if e.event == "Stop"]
    require(len(starts) == len(stops) == 1, "missing lifecycle evidence")
    before = {e.call: e for e in events if e.event == "PreToolUse"}
    after = {e.call: e for e in events if e.event.startswith("PostToolUse")}
    require(bool(before) and before.keys() == after.keys(), "missing paired tool evidence")
    require(None not in before, "missing tool identity")
    ordered = [*starts]
    for call in sorted(c for c in before if c is not None):
        pre, post = before[call], after[call]
        require(pre.tool == post.tool and call is not None, "tool identity mismatch")
        ordered.extend([pre, post])
    ordered.extend(stops)
    result = []
    for i, event in enumerate(ordered, 1):
        lifecycle = event.event in {"SessionStart", "Stop"}
        require(lifecycle == (event.call is None and event.tool is None), "invalid event shape")
        require(event.exit_code is None or event.event == "PostToolUse", "invalid exit evidence")
        require(
            event.failure
            == (
                event.event == "PostToolUseFailure"
                or (event.exit_code is not None and event.exit_code != 0)
            ),
            "contradictory failure",
        )
        kind = (
            TraceEventType.THREAD_STARTED
            if event.event == "SessionStart"
            else TraceEventType.TURN_COMPLETED
            if event.event == "Stop"
            else TraceEventType.COMMAND_EXECUTION
            if event.tool == "Bash"
            else TraceEventType.FILE_CHANGE
            if event.tool in {"Edit", "Write", "apply_patch"}
            else TraceEventType.UNKNOWN
        )
        result.append(
            NormalizedTraceEvent(
                ordinal=i,
                type=kind,
                native_event_type="hook." + event.event,
                item_id=event.call,
                thread_id=event.session,
                item_type=event.tool,
                exit_code=event.exit_code,
                status="failed" if event.failure else "observed",
            )
        )
    return NormalizedTrace(events=tuple(result))


class HookEpisode(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    namespace: Literal["CUSTOM"] = "CUSTOM"
    source_format: Literal["native-hook-v1"] = "native-hook-v1"
    source_kind: SourceKind
    source_authenticity: Literal["NOT_ATTESTED"] = "NOT_ATTESTED"
    source: Literal["codex", "claude"]
    session: Sha256Digest
    source_bundle_digest: Sha256Digest
    trace_digest: Sha256Digest
    event_count: int
    failed_tools: int
    execution_state: Literal["TURN_ENDED"] = "TURN_ENDED"
    evidence_state: Literal["PAIRED_HOOKS_ONLY"] = "PAIRED_HOOKS_ONLY"
    acceptance: Literal["NOT_VERIFIED"] = "NOT_VERIFIED"
    ordering: Literal["CAUSAL_PAIRS_NOT_WALL_CLOCK"] = "CAUSAL_PAIRS_NOT_WALL_CLOCK"
    execution_authorized: Literal[False] = False
    comparison_eligible: Literal[False] = False

    @property
    def identity(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))


def derive_episode(events: list[HookEvent], source_kind: SourceKind) -> HookEpisode:
    trace = normalized(events)
    receipts = [e.model_dump(mode="json") for e in sorted(events, key=lambda e: e.key)]
    return HookEpisode(
        source_kind=source_kind,
        source=events[0].source,
        session=events[0].session,
        source_bundle_digest=canonical_digest(receipts),
        trace_digest=sha256_bytes(trace.canonical_json().encode()),
        event_count=len(events),
        failed_tools=sum(e.failure for e in events),
    )


def import_hook_episode(spool: Path, store: Path, *, source_kind: SourceKind) -> HookEpisode:
    require(
        not spool.resolve().is_relative_to(store.resolve())
        and not store.resolve().is_relative_to(spool.resolve()),
        "overlapping store",
    )
    events = read_events(spool)
    episode = derive_episode(events, source_kind)
    require(episode == derive_episode(read_events(spool), source_kind), "capture changed")
    _directory(store)
    _write_once(store / (episode.identity[7:] + ".json"), encode(episode.model_dump(mode="json")))
    return episode


def attribution(events: list[HookEvent], source_kind: SourceKind) -> dict[str, Any]:
    episode = derive_episode(events, source_kind)
    failures = sorted((e for e in events if e.failure), key=lambda e: e.key)
    require(bool(failures), "no observed Bad Case")
    return {
        "schema_version": 1,
        "namespace": "CUSTOM",
        "episode_identity": episode.identity,
        "trace_digest": episode.trace_digest,
        "scope": "OBSERVED_TOOL_FAILURE",
        "category": "tool_execution_failure",
        "authority": "L0_HOOK_PROCESS_STATUS",
        "failed_calls": [
            {"call": e.call, "exit_code": e.exit_code, "event": e.event} for e in failures
        ],
        "root_cause": None,
        "task_acceptance": "NOT_VERIFIED",
        "comparison_eligible": False,
        "limitation": "A tool failure does not establish final task failure or model causality.",
    }


def freeze_hook_case(
    spool: Path, store: Path, destination: Path, *, source_kind: SourceKind
) -> str:
    episode = import_hook_episode(spool, store, source_kind=source_kind)
    events = read_events(spool)
    require(episode == derive_episode(events, source_kind), "capture changed before freeze")
    case = {
        "schema_version": 1,
        "kind": "hook-regression-v1",
        "episode": episode.model_dump(mode="json"),
        "receipts": [e.model_dump(mode="json") for e in sorted(events, key=lambda e: e.key)],
        "normalized_trace": json.loads(normalized(events).canonical_json()),
        "bad_case": attribution(events, source_kind),
    }
    _directory(destination.parent)
    _write_once(destination, encode(case))
    return sha256_bytes(encode(case))


def replay_hook_case(path: Path, expected: str) -> dict[str, Any]:
    require(path.stat().st_size <= MAX_INPUT * 4, "oversized regression case")
    case = decode(read_pinned(path, expected))
    if case.get("kind") == "verified-hook-regression-v1":
        from harnesslab.episodes.verified_hooks import replay_verified_hook_case

        return replay_verified_hook_case(path, expected, case)
    require(
        set(case)
        == {"schema_version", "kind", "episode", "receipts", "normalized_trace", "bad_case"},
        "invalid regression schema",
    )
    require(
        case["schema_version"] == 1 and case["kind"] == "hook-regression-v1",
        "unsupported regression",
    )
    episode = HookEpisode.model_validate(case["episode"])
    events = [HookEvent.model_validate(e) for e in case["receipts"]]
    require(episode == derive_episode(events, episode.source_kind), "episode replay drift")
    require(
        case["normalized_trace"] == json.loads(normalized(events).canonical_json()),
        "trace replay drift",
    )
    require(
        case["bad_case"] == attribution(events, episode.source_kind), "attribution replay drift"
    )
    return {
        "status": "PASS",
        "case_digest": expected,
        "episode_identity": episode.identity,
        "bad_case": case["bad_case"],
        "subject_executed": False,
        "external_calls": 0,
        "verifier_executed": False,
        "acceptance": "NOT_VERIFIED",
    }
