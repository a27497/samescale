from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from harnesslab.analyst.offline_replay import ReplayError
from harnesslab.episodes.hooks import (
    MAX_INPUT,
    attribution,
    encode,
    freeze_hook_case,
    import_hook_episode,
    normalized,
    read_events,
    receive_hook,
    redact_hook,
    replay_hook_case,
)
from harnesslab.episodes.service import inspect_episode
from harnesslab.tasks.package import sha256_bytes


def payload(event: str, **overrides: object) -> bytes:
    obj = {"hook_event_name": event, "session_id": "test-session"}
    if "ToolUse" in event:
        obj.update(tool_name="Bash", tool_use_id="call-1")
    return encode(obj | overrides)


def capture(path: Path, source: str = "codex", reverse: bool = False) -> None:
    events = [
        payload("SessionStart"),
        payload("PreToolUse"),
        payload("PostToolUse", tool_response={"exit_code": 1}),
        payload("Stop"),
    ]
    for raw in reversed(events) if reverse else events:
        receive_hook(raw, source, path)


def test_duplicate_out_of_order_and_restart_import(tmp_path: Path) -> None:
    spool, store = tmp_path / "spool", tmp_path / "store"
    capture(spool, reverse=True)
    first = import_hook_episode(spool, store, source_kind="synthetic")
    capture(spool)  # independent callbacks redelivered in a different order
    second = import_hook_episode(spool, store, source_kind="synthetic")
    assert first == second and len(list(store.iterdir())) == 1
    assert inspect_episode(next(store.iterdir())) == first
    # New Python process, no in-memory session state.
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "from harnesslab.cli import app; app()",
            "episode",
            "import-hooks",
            str(spool),
            "--store",
            str(store),
            "--source-kind",
            "synthetic",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert first.identity in result.stdout


@pytest.mark.parametrize("source", ["codex", "claude"])
def test_redaction_precedes_any_persistence(tmp_path: Path, source: str) -> None:
    secret = "private-sentinel-raw-prompt-key-reasoning"
    receive_hook(
        payload(
            "PostToolUse",
            tool_response={"exit_code": 1, "stdout": secret},
            prompt=secret,
            reasoning=secret,
            api_key=secret,
            env={"PRIVATE": secret},
            transcript_path=secret,
            tool_input={"command": secret},
            session_id=secret,
            tool_use_id=secret,
            tool_name=secret,
        ),
        source,
        tmp_path,
    )
    data = b"".join(p.read_bytes() for p in tmp_path.iterdir())
    assert secret.encode() not in data
    assert b"prompt" not in data and b"reasoning" not in data and b"stdout" not in data
    assert read_events(tmp_path)[0].tool == "OTHER"


@pytest.mark.parametrize("missing", ["SessionStart", "PreToolUse", "PostToolUse", "Stop"])
def test_missing_evidence_never_freezes(tmp_path: Path, missing: str) -> None:
    spool = tmp_path / "spool"
    capture(spool)
    event = next(e for e in read_events(spool) if e.event == missing)
    (spool / (event.key + ".json")).unlink()
    with pytest.raises(ReplayError):
        freeze_hook_case(spool, tmp_path / "store", tmp_path / "case.json", source_kind="synthetic")
    assert not (tmp_path / "case.json").exists()


@pytest.mark.parametrize(
    "raw",
    [
        b'{"hook_event_name":"Stop","hook_event_name":"Stop"}',
        b'{"x":NaN}',
        b"[]",
        b"{}",
        b"x" * (MAX_INPUT + 1),
    ],
)
def test_malformed_capture_poisoned_fail_closed(tmp_path: Path, raw: bytes) -> None:
    capture(tmp_path)
    with pytest.raises(ValueError):
        receive_hook(raw, "codex", tmp_path)
    with pytest.raises(ReplayError):
        read_events(tmp_path)
    assert (tmp_path / "REJECTED").read_text() == "FAIL_CLOSED\n"


def test_conflicting_redelivery_preserves_original(tmp_path: Path) -> None:
    capture(tmp_path)
    original = {p.name: p.read_bytes() for p in tmp_path.glob("*.json")}
    with pytest.raises(ReplayError):
        receive_hook(payload("PostToolUse", tool_response={"exit_code": 0}), "codex", tmp_path)
    assert original == {p.name: p.read_bytes() for p in tmp_path.glob("*.json")}
    with pytest.raises(ReplayError):
        read_events(tmp_path)


def test_claude_failure_has_no_invented_exit_status(tmp_path: Path) -> None:
    for event in ["SessionStart", "PreToolUse", "PostToolUseFailure", "Stop"]:
        receive_hook(payload(event, error="do not persist"), "claude", tmp_path)
    bad = attribution(read_events(tmp_path), "synthetic")
    assert bad["failed_calls"][0]["exit_code"] is None
    assert bad["root_cause"] is None


def test_no_inference_from_agent_self_report_or_stdout(tmp_path: Path) -> None:
    for event in ["SessionStart", "PreToolUse", "PostToolUse", "Stop"]:
        receive_hook(
            payload(
                event,
                tool_response={"stdout": "Exit code: 1"},
                last_assistant_message="All tests failed",
            ),
            "codex",
            tmp_path,
        )
    episode = import_hook_episode(tmp_path, tmp_path.parent / "episodes", source_kind="synthetic")
    assert episode.failed_tools == 0 and episode.acceptance == "NOT_VERIFIED"
    with pytest.raises(ReplayError, match="no observed"):
        attribution(read_events(tmp_path), "synthetic")


@pytest.mark.parametrize("code", [0, 1, 7, -1])
def test_codex_stdout_never_establishes_process_status(code: int) -> None:
    raw = payload(
        "PostToolUse",
        tool_response=f"Wall time: 0.2 seconds\nProcess exited with code {code}\nOutput:\nsecret",
    )
    assert redact_hook(raw, "codex").exit_code is None
    assert redact_hook(raw, "codex").failure is False


def test_frozen_case_deterministic_and_offline(tmp_path: Path) -> None:
    spool, case = tmp_path / "spool", tmp_path / "case.json"
    capture(spool)
    digest = freeze_hook_case(spool, tmp_path / "store", case, source_kind="synthetic")
    result = replay_hook_case(case, digest)
    assert result["bad_case"]["category"] == "tool_execution_failure"
    assert result["acceptance"] == "NOT_VERIFIED"
    for name in ("a.json", "b.json"):
        completed = subprocess.run(
            [
                sys.executable,
                "scripts/replay_hook.py",
                "--case",
                str(case),
                "--sha256",
                digest,
                "--output",
                str(tmp_path / name),
            ],
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stderr
    assert (tmp_path / "a.json").read_bytes() == (tmp_path / "b.json").read_bytes()


@pytest.mark.parametrize("field", ["receipts", "normalized_trace", "bad_case", "episode"])
def test_reanchored_semantic_drift_fails_closed(tmp_path: Path, field: str) -> None:
    spool, case = tmp_path / "spool", tmp_path / "case.json"
    capture(spool)
    digest = freeze_hook_case(spool, tmp_path / "store", case, source_kind="synthetic")
    obj = json.loads(case.read_bytes())
    if field == "receipts":
        obj[field].pop()
    elif field == "normalized_trace":
        obj[field]["events"][1]["type"] = "TURN_FAILED"
    elif field == "bad_case":
        obj[field]["root_cause"] = "model_incompetence"
    else:
        obj[field]["failed_tools"] = 0
    case.write_bytes(encode(obj))
    with pytest.raises(ReplayError):
        replay_hook_case(case, digest)
    with pytest.raises(ReplayError):
        replay_hook_case(case, sha256_bytes(case.read_bytes()))


def test_mixed_sessions_rejected(tmp_path: Path) -> None:
    capture(tmp_path)
    receive_hook(payload("Stop", session_id="another-session"), "codex", tmp_path)
    with pytest.raises(ReplayError, match="mixed"):
        normalized(read_events(tmp_path))


def test_link_and_partial_receipt_fail_closed(tmp_path: Path) -> None:
    spool = tmp_path / "spool"
    capture(spool)
    target = next(spool.glob("*.json"))
    original = target.read_bytes()
    target.write_bytes(b"{")
    with pytest.raises(ValueError):
        read_events(spool)
    target.write_bytes(original)
    link = tmp_path / "linked"
    link.symlink_to(spool, target_is_directory=True)
    with pytest.raises(ReplayError):
        read_events(link)


def test_receiver_has_no_execution_surface() -> None:
    import ast

    import harnesslab.episodes.hooks as hooks

    tree = ast.parse(Path(hooks.__file__).read_text())
    imports = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    imports |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    assert not imports & {"subprocess", "socket", "httpx", "requests"}


def test_real_hook_capture_retains_unknown_status_and_blocks_freeze(tmp_path: Path) -> None:
    source = Path(__file__).resolve().parents[1] / "docs/evidence/real-hook-trace-20260922"
    events = read_events(source / "codex-hooks")
    trace = normalized(events)
    assert sha256_bytes(trace.canonical_json().encode()) == (
        "sha256:2c0d9239546e1ea3fd00edbd10edd7cf37e3153d0e80ceff88fea92f3dc8a63f"
    )
    episode = import_hook_episode(
        source / "codex-hooks", tmp_path / "store", source_kind="unverified"
    )
    assert episode.identity == (
        "sha256:1342cd0f5695ef9a1d765ee7018f0d775d01730d0859d28228aab4814ab1d525"
    )
    assert episode.event_count == 10 and episode.failed_tools == 0
    assert episode.acceptance == "NOT_VERIFIED"
    with pytest.raises(ReplayError, match="no observed Bad Case"):
        freeze_hook_case(
            source / "codex-hooks",
            tmp_path / "store",
            tmp_path / "case.json",
            source_kind="unverified",
        )
    assert not (tmp_path / "case.json").exists()
