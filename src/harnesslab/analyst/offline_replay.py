"""Digest-anchored S1 bundle replay. Reads data only; never executes captured commands."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

from harnesslab.comparability.models import canonical_digest
from harnesslab.harness_lane.models import NormalizedTrace, SanitizedNativeEvent
from harnesslab.harness_lane.trace import _normalized_trace
from harnesslab.multi_harness.trace import _trace_event
from harnesslab.tasks.package import sha256_bytes

Json = dict[str, Any]


class ReplayError(ValueError):
    """Missing, changed, unsupported or contradictory evidence: no result is released."""


def require(condition: bool, reason: str) -> None:
    if not condition:
        raise ReplayError(reason)


def _unique(pairs: list[tuple[str, Any]]) -> Json:
    result: Json = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise ReplayError("non-finite JSON value")


def decode(data: bytes) -> Json:
    obj = json.loads(data, object_pairs_hook=_unique, parse_constant=_reject_constant)
    require(isinstance(obj, dict), "expected JSON object")
    return dict(obj)


def safe_path(root: Path, relative: str) -> Path:
    path = PurePosixPath(relative)
    require(
        bool(relative)
        and not path.is_absolute()
        and path.as_posix() == relative
        and not any(p in {".", ".."} for p in path.parts),
        "unsafe evidence path",
    )
    current = root
    require(not root.is_symlink(), "linked evidence root")
    for part in path.parts:
        current = current / part
        require(not current.is_symlink(), "linked evidence path")
    return current


def read_pinned(path: Path, expected: str) -> bytes:
    require(not path.is_symlink() and path.is_file(), "missing or linked evidence file")
    data = path.read_bytes()
    require(sha256_bytes(data) == expected, "evidence digest mismatch")
    return data


def tree_digest(files: dict[str, bytes], prefix: str) -> str:
    """Same path/byte framing as tasks.package.digest_tree, on a verified byte snapshot."""
    digest = hashlib.sha256()
    entries = {p[len(prefix) :]: b for p, b in files.items() if p.startswith(prefix)}
    require(bool(entries), "missing evidence tree")
    for path, content in sorted(entries.items()):
        name = path.encode()
        digest.update(len(name).to_bytes(8, "big"))
        digest.update(name)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return "sha256:" + digest.hexdigest()


def _seal(obj: Json) -> None:
    require(
        obj.get("identity") == canonical_digest({k: v for k, v in obj.items() if k != "identity"}),
        "inconsistent sealed record",
    )


def _snapshot(root: Path, expected: str) -> tuple[Json, dict[str, bytes]]:
    bundle = decode(read_pinned(safe_path(root, "bundle.json"), expected))
    require(bundle["schema_version"] == 1, "unsupported bundle version")
    index = bundle["files"]
    require(isinstance(index, dict) and bool(index), "missing file inventory")
    require("bundle.json" not in index, "self-referential inventory")
    paths = list(root.rglob("*"))
    require(not any(p.is_symlink() for p in paths), "linked bundle member")
    actual = {p.relative_to(root).as_posix() for p in paths if p.is_file()}
    require(actual == set(index) | {"bundle.json"}, "bundle inventory mismatch")
    files = {p: read_pinned(safe_path(root, p), h) for p, h in index.items()}
    return bundle, files


def _changes(files: dict[str, bytes]) -> list[Json]:
    before = {
        p.removeprefix("baseline/"): sha256_bytes(b)
        for p, b in files.items()
        if p.startswith("baseline/")
    }
    after = {
        p.removeprefix("run/workspace/"): sha256_bytes(b)
        for p, b in files.items()
        if p.startswith("run/workspace/")
    }
    return [
        {
            "path": p,
            "status": "added" if p not in before else "deleted" if p not in after else "modified",
            "before_digest": before.get(p),
            "after_digest": after.get(p),
        }
        for p in sorted(before.keys() | after.keys())
        if before.get(p) != after.get(p)
    ]


def _verifier(files: dict[str, bytes], manifest: Json) -> Json:
    sandbox = manifest["verifier_sandbox_manifest"]
    if sandbox is None:
        require(
            not any(p.startswith("run/verifier/") for p in files), "unexpected verifier evidence"
        )
        require(
            all(
                manifest[k] is None
                for k in [
                    "verifier_artifact_digest",
                    "verifier_artifact_namespace",
                    "verifier_passed",
                    "verifier_score",
                ]
            ),
            "contradictory absent verifier",
        )
        return {"state": "NOT_RUN", "checks": None, "passed_checks": None, "task_success": None}
    require(manifest["verifier_artifact_namespace"] == "verifier", "verifier namespace drift")
    require(
        tree_digest(files, "run/verifier/") == manifest["verifier_artifact_digest"],
        "verifier tree mismatch",
    )
    require(decode(files["run/verifier/manifest.json"]) == sandbox, "verifier manifest mismatch")
    require(
        sandbox["exit_code"] == 0
        and not sandbox["timed_out"]
        and not sandbox["cancelled"]
        and sandbox["cleanup_verified"]
        and not sandbox["stdout_truncated"]
        and not sandbox["stderr_truncated"],
        "invalid verifier process",
    )
    require(sandbox["security"]["network_mode"] == "none", "verifier isolation mismatch")
    for stream in ["stdout", "stderr"]:
        require(sandbox[stream]["path"] == stream + ".txt", "verifier stream path mismatch")
        require(
            sha256_bytes(files[f"run/verifier/{stream}.txt"])
            == sandbox[stream]["digest"]
            == sandbox[f"{stream}_stream_digest"],
            "verifier stream mismatch",
        )
    for key in ["workspace_input_digest", "workspace_output_digest"]:
        require(sandbox[key] == manifest["workspace_output_digest"], "verifier workspace mismatch")
    require(
        tree_digest(files, "run/verifier/workspace/") == manifest["workspace_output_digest"],
        "verifier workspace content mismatch",
    )
    for key in ["task_id", "task_version", "task_digest"]:
        require(sandbox[key] == manifest[key], "verifier task mismatch")
    report = decode(files["run/verifier/stdout.txt"])
    checks = report["checks"]
    require(isinstance(checks, list) and bool(checks), "zero verifier checks")
    require(all(type(c["passed"]) is bool for c in checks), "invalid verifier check")
    passed = all(c["passed"] for c in checks)
    require(
        report["passed"] is passed and manifest["verifier_passed"] is passed,
        "verifier result contradiction",
    )
    require(report["score"] == manifest["verifier_score"], "verifier score mismatch")
    return {
        "state": "verified_pass" if passed else "verified_fail",
        "task_success": passed,
        "checks": len(checks),
        "passed_checks": sum(c["passed"] for c in checks),
        "report_digest": sha256_bytes(files["run/verifier/stdout.txt"]),
    }


def _tools(events: list[Json], harness: str, workspace_paths: list[str]) -> list[Json]:
    tools: list[Json] = []
    pending: dict[str, Json] = {}
    for event in events:
        native = event["native_event_type"]
        if harness == "codex":
            start = native == "item.started" and event["type"] in {
                "COMMAND_EXECUTION",
                "FILE_CHANGE",
            }
            key = event.get("item_id", "")
            end = native == "item.completed" and event["type"] in {
                "COMMAND_EXECUTION",
                "FILE_CHANGE",
            }
        else:
            start = native in {"tool.Bash", "tool.Read", "tool.Edit", "tool.Write"}
            # Sanitization discarded Claude tool IDs. Only associate an unambiguous pending tool.
            key = "unambiguous_pending"
            end = native == "user.tool_result"
        if start:
            require(bool(key) and key not in pending, "ambiguous tool sequence")
            command = event.get("command")
            mentions = [
                p
                for p in workspace_paths
                if command
                and re.search(
                    r"(?<![\w./-])(?:/workspace/)?" + re.escape(p) + r"(?![\w./-])", command
                )
            ]
            item = {
                "start_ordinal": event["ordinal"],
                "source_pointer": f"/events/{event['ordinal'] - 1}",
                "end_ordinal": None,
                "tool": event.get("item_type") if harness == "codex" else native[5:],
                "command": command,
                "status": "NO_RECORDED_RESULT",
                "exit_code": None,
                "file_events": event["file_changes"],
                "command_path_mentions": mentions,
                "path_mentions_are_access_proof": False,
                "linkage": "item_id" if harness == "codex" else "single_pending_in_recorded_order",
                "validation_command_observed": bool(
                    command
                    and re.search(
                        r"(?:python(?:3)?\s+tools/frontend_check\.py|\bpytest\b|\bvitest\s+run\b)",
                        command,
                    )
                ),
            }
            tools.append(item)
            pending[key] = item
        if end:
            require(key in pending, "orphan or ambiguous tool result")
            item = pending.pop(key)
            item.update(
                end_ordinal=event["ordinal"],
                status=event.get("status"),
                exit_code=event.get("exit_code"),
            )
    return tools


def _replay(root: Path, expected: str) -> Json:
    bundle, files = _snapshot(root, expected)
    manifest = decode(files["run/manifest.json"])
    receipt, result = decode(files["receipt.json"]), decode(files["result.json"])
    projection = result["projection"]
    for record in [
        receipt,
        result,
        projection,
        decode(files["secret-audit.json"]),
        decode(files["cleanup.json"]),
    ]:
        _seal(record)
    require(manifest["schema_version"] == 1, "unsupported run version")
    require(
        tree_digest(files, "run/") == bundle["run_digest"] == receipt["artifact_digest"],
        "run tree mismatch",
    )
    require(manifest == projection["original_evidence"], "projection manifest mismatch")
    require(
        result["scope"] == "campaign"
        and result["counted_in_campaign"] is True
        and projection["mode"] == "REAL"
        and projection["benchmark_result"] is True,
        "evidence is not a formal real campaign attempt",
    )
    require(projection["failure"] == manifest["harness_failure"], "failure taxonomy mismatch")
    require(
        manifest["run_id"] == bundle["run_id"] == receipt["execution_id"], "run identity mismatch"
    )
    require(
        manifest["plan_harness_config_identity"] == receipt["config_identity"], "config mismatch"
    )
    require(
        receipt["campaign_identity"]
        == projection["campaign_identity"]
        == bundle["campaign_identity"],
        "campaign mismatch",
    )
    require(receipt["cell_identity"] == projection["cell_identity"], "cell mismatch")
    require(manifest["task_id"] == receipt["task_id"], "receipt task mismatch")
    require(
        tree_digest(files, "baseline/") == manifest["workspace_input_digest"], "baseline mismatch"
    )
    require(
        tree_digest(files, "run/workspace/") == manifest["workspace_output_digest"],
        "output workspace mismatch",
    )
    changed = _changes(files)
    require(
        changed == manifest["changed_paths"] == projection["changed_files"],
        "changed files mismatch",
    )
    harness = manifest["harness"]
    require(harness in {"codex", "claude-code"}, "unsupported harness")
    trace_data = files["run/trace/normalized.json"]
    native_data = files[f"run/native/{harness}.sanitized.jsonl"]
    require(sha256_bytes(trace_data) == manifest["normalized_trace_digest"], "trace mismatch")
    require(
        sha256_bytes(native_data) == manifest["native_transcript_digest"], "native trace mismatch"
    )
    native = tuple(
        SanitizedNativeEvent.model_validate(decode(line)) for line in native_data.splitlines()
    )
    reconstructed = (
        _normalized_trace(native)
        if harness == "codex"
        else NormalizedTrace(events=tuple(_trace_event(e) for e in native))
    )
    trace = decode(trace_data)
    require(trace == json.loads(reconstructed.canonical_json()), "native/normalized inconsistency")
    events = trace["events"]
    require(
        [e["ordinal"] for e in events] == list(range(1, len(events) + 1)), "trace ordinal drift"
    )
    require(len(events) == manifest["trace_event_count"], "trace event count mismatch")
    if "trace_event_types" in manifest:
        require([e["type"] for e in events] == manifest["trace_event_types"], "trace type mismatch")
    terminal = [e for e in events if e["type"] in {"TURN_COMPLETED", "TURN_FAILED"}]
    require(
        (terminal[-1]["native_event_type"] if terminal else None)
        == manifest["terminal_native_event"],
        "terminal event mismatch",
    )
    if terminal and terminal[-1].get("usage") is not None:
        require(terminal[-1]["usage"] == manifest["usage"], "terminal usage mismatch")
    verifier = _verifier(files, manifest)
    if (
        manifest["timed_out"]
        or manifest["cancelled"]
        or manifest["harness_failure"]
        or manifest.get("backend_failure")
    ):
        require(verifier["state"] == "NOT_RUN", "failure/verifier contradiction")
        outcome = "harness_error"
    else:
        require(
            bool(terminal)
            and terminal[-1]["type"] == "TURN_COMPLETED"
            and manifest["process_exit_code"] == 0,
            "missing successful subject completion",
        )
        require(verifier["state"] != "NOT_RUN", "completion without verifier")
        outcome = verifier["state"]
    require(
        outcome == manifest["outcome"] == receipt["outcome"] == projection["outcome"],
        "outcome contradiction",
    )
    require(
        verifier["task_success"] is receipt["task_success"]
        and verifier["task_success"] is projection["task_success"],
        "task success contradiction",
    )
    require(
        verifier["checks"] == receipt["verifier_checks"]
        and verifier["passed_checks"] == receipt["verifier_passed_checks"],
        "verifier counts mismatch",
    )
    for key in ["usage", "duration_ms", "timed_out", "normalized_trace_digest"]:
        require(manifest[key] == projection[key], "projection field mismatch")
    require(
        manifest["duration_ms"] == receipt["subject_duration_ms"]
        and manifest["usage"] == receipt["usage"],
        "receipt duration/usage mismatch",
    )
    require(
        decode(files["secret-audit.json"])["status"] == receipt["secret_audit"] == "PASS",
        "secret audit not passed",
    )
    cleanup = decode(files["cleanup.json"])
    require((cleanup["status"] == "PASS") is receipt["cleanup_verified"], "cleanup contradiction")
    post_cleanup = None
    if "post-stop-cleanup.json" in files:
        post = decode(files["post-stop-cleanup.json"])
        _seal(post)
        require(
            post["status"] == "PASS"
            and post["files_deleted"] == 0
            and post["original_cleanup_failure_preserved"],
            "invalid cleanup supplement",
        )
        post_cleanup = post["status"]
    paths = sorted(
        p.removeprefix("run/workspace/") for p in files if p.startswith("run/workspace/")
    )
    tools = _tools(events, harness, paths)
    metadata = [
        e
        for e in events
        if e["native_event_type"] == "system" and e.get("status") == "thinking_tokens"
    ]
    last_tool = max((t["end_ordinal"] or t["start_ordinal"] for t in tools), default=0)
    budget = receipt["budget_compliance"]
    observed = manifest["usage"]["output_tokens"] if manifest["usage"] is not None else None
    declared = manifest["resource_budget"]["max_output_tokens"]
    budget_state = (
        "UNKNOWN"
        if observed is None
        else "DECLARED_BUDGET_EXCEEDED"
        if observed > declared
        else "WITHIN_DECLARED_BUDGET"
    )
    require(
        budget["status"] == budget_state
        and budget["observed_output_tokens"] == observed
        and budget["declared_output_tokens"] == declared
        and not budget["changes_task_success"],
        "budget compliance contradiction",
    )
    return {
        "schema_version": 1,
        "replay_status": "PASS",
        "bundle_digest": expected,
        "run_id": manifest["run_id"],
        "campaign_identity": bundle["campaign_identity"],
        "task": {
            k: manifest[k]
            for k in [
                "task_id",
                "task_version",
                "task_digest",
                "workspace_input_digest",
                "verifier_definition_digest",
            ]
        },
        "configuration": {
            k: manifest[k]
            for k in [
                "harness",
                "requested_model",
                "provider_route",
                "plan_harness_config_identity",
                "prompt_hash",
                "observed_model_status",
            ]
        },
        "outcome": outcome,
        "task_verification": "NOT_VERIFIED" if outcome == "harness_error" else outcome,
        "verification": verifier,
        "trace": {
            "event_count": len(events),
            "type_counts": dict(sorted(Counter(e["type"] for e in events).items())),
            "tools": tools,
            "tool_count": len(tools),
            "last_tool_ordinal": last_tool,
            "thinking_metadata_events": len(metadata),
            "trailing_thinking_metadata_events": sum(e["ordinal"] > last_tool for e in metadata),
            "thinking_metadata_is_token_usage": False,
            "per_event_duration": None,
            "timestamps_available": False,
            "coverage_label": manifest["trace_coverage"],
            "coverage_label_proves_native_completion": False,
            "native_digest": manifest["native_transcript_digest"],
            "normalized_digest": manifest["normalized_trace_digest"],
        },
        "file_access": {
            "explicit_read_events": [
                {"ordinal": t["start_ordinal"], **e}
                for t in tools
                for e in t["file_events"]
                if e["kind"] == "read"
            ],
            "explicit_edit_events": [
                {"ordinal": t["start_ordinal"], **e}
                for t in tools
                for e in t["file_events"]
                if e["kind"] != "read"
            ],
            "command_path_mentions": sorted({p for t in tools for p in t["command_path_mentions"]}),
            "shell_access_coverage": "UNKNOWN; mentions can include commands not reached",
        },
        "changed_files": changed,
        "validation": {
            "subject_commands": [t for t in tools if t["validation_command_observed"]],
            "independent_verifier": verifier,
        },
        "duration_usage": {
            "subject_ms": manifest["duration_ms"],
            "end_to_end_ms": receipt["end_to_end_observed_ms"],
            "usage": manifest["usage"],
            "cost_usd": receipt["cost_usd"],
            "provider_request_count": receipt["provider_request_count"],
            "budget_compliance": budget,
        },
        "completion_failure": {
            "native_terminal": manifest["terminal_native_event"],
            "process_exit_code": manifest["process_exit_code"],
            "timed_out": manifest["timed_out"],
            "failure_taxonomy": manifest["harness_failure"],
            "stop_reasons": receipt["stop_reasons"],
            "timeout_root_cause": "NOT_ESTABLISHED" if manifest["timed_out"] else None,
        },
        "controls": {
            "secret_audit": "PASS",
            "original_cleanup": cleanup["status"],
            "post_stop_cleanup": post_cleanup,
        },
        "integrity": {
            "files_verified": len(files),
            "native_normalized_consistent": True,
            "workspace_diff_reconstructed": True,
            "verifier_rerun": False,
        },
        "external_calls": 0,
    }


def replay_bundle(root: Path, expected_digest: str) -> Json:
    """Caller supplies a trusted digest from outside the bundle; hash files are not authority."""
    try:
        return _replay(root, expected_digest)
    except ReplayError:
        raise
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError) as exc:
        raise ReplayError("malformed or unavailable replay evidence") from exc


def compare_replays(left: Json, right: Json) -> Json:
    require(left["replay_status"] == right["replay_status"] == "PASS", "unverified replay")
    require(left["task"] == right["task"], "different task/baseline/verifier")
    require(left["campaign_identity"] == right["campaign_identity"], "different campaign")
    require(left["run_id"] != right["run_id"], "duplicate run comparison")
    return {
        "schema_version": 1,
        "kind": "OFFLINE_CROSS_RUN_TRACE_DIFF",
        "comparison_type": "AI_CODING_CONFIGURATION_COMPARISON",
        "status": "PASS",
        "left": left,
        "right": right,
        "dimensions": {
            k: {"equal": left[k] == right[k], "left": left[k], "right": right[k]}
            for k in [
                "configuration",
                "file_access",
                "changed_files",
                "validation",
                "duration_usage",
                "completion_failure",
            ]
        },
        "tool_sequence": {"left": left["trace"]["tools"], "right": right["trace"]["tools"]},
        "limits": [
            "Descriptive comparison of two recorded attempts only; "
            "no ability ranking or full configuration conclusion.",
            "Model, provider, harness and prompt-template identities differ; "
            "no Harness causal attribution.",
            "Command path mentions are not proof of file access; shell commands may short-circuit.",
            "Claude result linkage uses unambiguous recorded order; "
            "original tool IDs were not retained.",
            "No per-event timestamps; metadata counts are not tokens or proof of progress rate.",
            "Replay verifies recorded verifier state, "
            "not a new execution or reproduction of model behavior.",
            "Trusted manifest digests must be retained separately; "
            "hashes do not authenticate a replaced trust anchor.",
        ],
        "external_calls": 0,
    }


def render_diagnosis(diff: Json) -> str:
    lines = [
        "# S2 offline trace diagnosis",
        "",
        "Two recorded attempts; no ranking or Harness causal conclusion.",
        "",
    ]
    for label in ["left", "right"]:
        r = diff[label]
        lines += [
            f"## {r['configuration']['harness']} / {r['run_id']}",
            "",
            f"Outcome: {r['outcome']}; verifier: {r['verification']['state']}; "
            f"subject: {r['duration_usage']['subject_ms']} ms; "
            f"changed files: {len(r['changed_files'])}.",
            f"Native terminal: {r['completion_failure']['native_terminal']}; "
            f"failure: {r['completion_failure']['failure_taxonomy']}.",
            "",
            "| Start → result ordinal | Tool | Status / exit | "
            "Recorded paths (mentions are not proof of access) |",
            "| --- | --- | --- | --- |",
        ]
        for t in r["trace"]["tools"]:
            paths = [f"{e['kind']}: {e['path']}" for e in t["file_events"]] + t[
                "command_path_mentions"
            ]
            lines.append(
                f"| {t['start_ordinal']} → {t['end_ordinal']} | {t['tool']} | "
                f"{t['status']} / {t['exit_code']} | {', '.join(paths)} |"
            )
        lines += [
            "",
            f"Subject validation commands observed: {len(r['validation']['subject_commands'])}.",
            "Thinking metadata events after last tool: "
            f"{r['trace']['trailing_thinking_metadata_events']}; "
            "elapsed time for that interval is unknown.",
            "",
        ]
    lines += ["## Interpretation limits", ""] + [f"- {x}" for x in diff["limits"]]
    return "\n".join(lines) + "\n"
