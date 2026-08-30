from __future__ import annotations

import asyncio
import hashlib
import ipaddress
import json
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from harnesslab.cli import app
from harnesslab.egress import (
    EGRESS_PROXY_BASE,
    EGRESS_PROXY_IMAGE,
    EGRESS_PROXY_SOURCE_DIGEST,
    INTERNAL_NETWORK_GATEWAY_MODE_OPTION,
    EgressNetworkIsolationUnavailable,
    EgressPolicy,
    EgressProxyRuntime,
    EgressSecurityError,
    ProviderScopedDockerBoundary,
    preflight_egress_network_isolation,
)
from harnesslab.harness_lane.adapter import HarnessAdapterError
from harnesslab.harness_lane.docker_backend import (
    CodexBackendExecutionError,
    DockerCodexBackend,
)
from harnesslab.harness_lane.models import (
    CodexBackendFailureEvidence,
    CodexBackendFailurePhase,
    CodexProcessCapture,
    HarnessFailureCategory,
    HarnessLaneOutcome,
    ObservedModelStatus,
)
from harnesslab.harness_lane.profile import (
    CODEX_IMAGE,
    canonical_codex_profile,
    configured_gpt56_relay_codex_profile,
)
from harnesslab.harness_lane.trace import collect_codex_jsonl
from harnesslab.model_lane.models import DirectModelOutcome
from harnesslab.multi_harness.docker_backend import DockerMultiHarnessBackend
from harnesslab.multi_harness.models import HarnessProcessCapture, TraceCoverage
from harnesslab.multi_harness.profile import (
    CLAUDE_IMAGE,
    DEEPSEEK_IMAGE,
    canonical_deepseek_profile,
    configured_deepseek_v4flash_profile,
    configured_qwen_opencode_go_claude_profile,
)
from harnesslab.multi_harness.runtime import _validate_deepseek_effective_config
from harnesslab.multi_harness.trace import collect_deepseek_final
from harnesslab.release.contracts import (
    load_contiguous_v2_histories,
    load_release_evidence,
    validate_dynamic_v2_history,
)
from harnesslab.release.models import EvidenceState, ReleaseHistorySummary
from harnesslab.release.smoke import (
    EXPECTED_ADAPTERS,
    EXPECTED_CALL_IDS,
    EXPECTED_RUNNERS,
    REQUIRED_CONFIGURATION_REFERENCES,
    ProductionSmokeInvoker,
    ResolvedSmokeBinding,
    RuntimeIdentities,
    SmokeCallFailure,
    SmokeCallResult,
    SmokeContinuationPolicy,
    SmokeControlPlane,
    SmokeControlPlaneError,
    SmokeExecutionStatus,
    SmokeFailureCategory,
    _validate_harness_observed_model,
    execute_real_smoke,
)
from harnesslab.sandbox.docker_cli import _DockerCLI
from harnesslab.sandbox.models import ImageIdentity
from harnesslab.sandbox.preflight import _docker_runtime_preflight

ROOT = Path(__file__).resolve().parents[1]
RUNNER = CliRunner()
SAFE_ENVIRONMENT = {
    "HARNESSLAB_GPT56_RELAY_BASE_URL": "https://relay.example.test/v1",
    "HARNESSLAB_GPT56_RELAY_API_KEY": "fake-relay-key",
    "HARNESSLAB_OPENCODE_GO_API_KEY": "fake-opencode-go-key",
    "DEEPSEEK_API_KEY": "fake-deepseek-key",
}


def _image(reference: str, marker: str) -> ImageIdentity:
    return ImageIdentity(reference=reference, image_id="sha256:" + marker * 64)


def _runtime() -> RuntimeIdentities:
    return RuntimeIdentities(
        codex_image=_image(CODEX_IMAGE, "1"),
        claude_image=_image(CLAUDE_IMAGE, "2"),
        deepseek_image=_image(DEEPSEEK_IMAGE, "3"),
        egress_proxy_image=_image(EGRESS_PROXY_IMAGE, "4"),
        deepseek_config_digest="sha256:" + "5" * 64,
    )


def _post_r10_subject_command_timeout_lines() -> tuple[str, ...]:
    return (
        json.dumps({"type": "thread.started", "thread_id": "post-r10-thread"}),
        json.dumps({"type": "turn.started"}),
        json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "id": "message-1",
                    "type": "agent_message",
                    "text": "Inspecting the workspace.",
                },
            }
        ),
        json.dumps(
            {
                "type": "item.started",
                "item": {
                    "id": "command-1",
                    "type": "command_execution",
                    "command": "sed -n '1,200p' events.py",
                    "status": "in_progress",
                },
            }
        ),
        json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "id": "command-1",
                    "type": "command_execution",
                    "command": "sed -n '1,200p' events.py",
                    "aggregated_output": "source inspected",
                    "status": "completed",
                    "exit_code": 0,
                },
            }
        ),
        json.dumps(
            {
                "type": "item.started",
                "item": {
                    "id": "command-2",
                    "type": "command_execution",
                    "command": "git status --short",
                    "status": "in_progress",
                },
            }
        ),
        json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "id": "command-2",
                    "type": "command_execution",
                    "command": "git status --short",
                    "aggregated_output": "fatal: not a git repository",
                    "status": "failed",
                    "exit_code": 128,
                },
            }
        ),
        json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "id": "change-1",
                    "type": "file_change",
                    "status": "completed",
                    "changes": [{"path": "events.py", "kind": "update"}],
                },
            }
        ),
    )


def _bwrap_timeout_lines() -> tuple[str, ...]:
    return (
        json.dumps({"type": "thread.started", "thread_id": "bwrap-thread"}),
        json.dumps({"type": "turn.started"}),
        json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "id": "command-1",
                    "type": "command_execution",
                    "command": "python -m pytest",
                    "aggregated_output": "bwrap: No permissions to create a new namespace",
                    "status": "failed",
                    "exit_code": 1,
                },
            }
        ),
    )


def _error_timeout_lines() -> tuple[str, ...]:
    return (
        *_post_r10_subject_command_timeout_lines()[:5],
        json.dumps({"type": "error", "error": {"message": "provider proxy returned 403"}}),
    )


class RecordingInvoker:
    def __init__(self, failing_call_id: str | None = None) -> None:
        self.failing_call_id = failing_call_id
        self.calls: list[ResolvedSmokeBinding] = []

    async def invoke(self, binding: ResolvedSmokeBinding) -> SmokeCallResult:
        self.calls.append(binding)
        call_id = binding.frozen.call.call_id
        if call_id == self.failing_call_id:
            raise SmokeCallFailure(SmokeFailureCategory.ROUTE_MISMATCH, "fake failure")
        return SmokeCallResult(
            call_id=call_id,
            evidence_references=(f"fake://{call_id}",),
            evidence_digests=("sha256:" + "6" * 64,),
        )


def _mutated_repository(tmp_path: Path) -> Path:
    root = tmp_path / "repository"
    shutil.copytree(ROOT / "release", root / "release")
    task = next(
        item
        for item in json.loads((ROOT / "release/core-corpus.json").read_text())["tasks"]
        if item["task_id"] == "core-python-deduplicate"
    )
    source = ROOT / task["package_path"]
    shutil.copytree(source, root / task["package_path"])
    return root


def test_smoke_production_control_plane_exact_eight_call_binding() -> None:
    control = SmokeControlPlane.load(ROOT)
    assert tuple(binding.call.call_id for binding in control.bindings) == EXPECTED_CALL_IDS
    assert tuple(binding.runner_identity for binding in control.bindings) == EXPECTED_RUNNERS
    assert tuple(binding.adapter_identity for binding in control.bindings) == EXPECTED_ADAPTERS
    assert control.smoke_plan.max_top_level_launch_count == 8
    assert control.smoke_plan.max_output_token_ceiling == 14_256
    assert control.smoke_plan.release_plan_digest == control.release_plan.digest


def test_top_level_release_history_covers_repository_attempts_through_r16() -> None:
    histories, expected_references = load_contiguous_v2_histories(ROOT / "release/history", ROOT)
    expected_attempts = tuple(range(1, len(histories) + 1))
    manifest = load_release_evidence(ROOT / "release/release-evidence.json")
    summary = manifest.release_history

    assert len(histories) == 13
    assert (
        tuple(int(item["attempt_id"].rsplit("-", 1)[1]) for item in histories) == expected_attempts
    )
    assert summary.attempt_references == expected_references
    assert summary.latest_attempt_id == histories[-1]["attempt_id"]
    assert summary.latest_attempt_status == histories[-1]["status"] == "ABORTED"
    assert summary.latest_failing_call_id == histories[-1]["failing_call_id"]
    assert histories[-1]["calls_5_to_8"] == "NOT_RUN"
    assert summary.latest_not_run_call_ids == EXPECTED_CALL_IDS[4:]
    assert len(summary.keyless_repairs) == 1
    repair = summary.keyless_repairs[0]
    assert repair.repair_id == "R12"
    assert repair.after_attempt_id == "core-real-smoke-v2-attempt-9"
    assert repair.state == "KEYLESS_VERIFIED"
    assert repair.real_calls == 0
    assert summary.complete_smoke is EvidenceState.NOT_VERIFIED
    assert summary.matrix_evidence is EvidenceState.NOT_RUN
    assert summary.release_verification is EvidenceState.NOT_VERIFIED
    assert manifest.remote_ci.state is EvidenceState.NOT_VERIFIED
    assert not manifest.core_release_ready
    assert all(
        item["smoke_plan_digest"]
        == "sha256:8e0b6482dac4ccb0312d881eff3ab68f741d2b22b085557b1f9315e99fd1a18a"
        and item["release_plan_digest"]
        == "sha256:9ed4e586a663b5f1aba161718bbca584a6dc306bcb895fe1bc05d7b94aa3b4eb"
        for item in histories
    )

    release_docs = (ROOT / "docs/RELEASE_EVIDENCE.md").read_text(encoding="utf-8")
    authorization_docs = (ROOT / "docs/REAL_EVIDENCE_AUTHORIZATION.md").read_text(encoding="utf-8")
    resume_docs = (ROOT / "docs/RESUME_SCOPE.md").read_text(encoding="utf-8")
    assert "attempt-1.json` through `history/core-real-v2-attempt-13.json`" in release_docs
    assert "Attempt 13 executed Calls 1-4" in authorization_docs
    assert "post-R12 real Claude verification remains `NOT_RUN` / `NOT_REACHED`" in release_docs
    assert "Calls 2-8 were `NOT_RUN`" in authorization_docs
    assert "attempts 1-13" in resume_docs
    assert "post-R12 real Claude verification remains `NOT_RUN` / `NOT_REACHED`" in resume_docs


def test_release_history_summary_accepts_a_future_contiguous_attempt() -> None:
    raw = json.loads((ROOT / "release/release-evidence.json").read_text(encoding="utf-8"))[
        "release_history"
    ]
    raw["attempt_references"].append("release/history/core-real-v2-attempt-14.json")
    raw["latest_attempt_id"] = "core-real-smoke-v2-attempt-14"
    raw["latest_attempt_status"] = "SUCCEEDED"
    raw["latest_failing_call_id"] = None
    raw["latest_not_run_call_ids"] = []

    summary = ReleaseHistorySummary.model_validate(raw)

    assert summary.latest_attempt_id.endswith("attempt-14")
    assert summary.latest_attempt_status == "SUCCEEDED"
    assert summary.keyless_repairs[0].after_attempt_id == "core-real-smoke-v2-attempt-9"


def test_release_history_summary_rejects_a_removed_attempt_reference() -> None:
    raw = json.loads((ROOT / "release/release-evidence.json").read_text(encoding="utf-8"))[
        "release_history"
    ]
    raw["attempt_references"].pop()

    with pytest.raises(ValidationError, match="latest attempt id"):
        ReleaseHistorySummary.model_validate(raw)


def test_release_history_summary_rejects_a_gap() -> None:
    raw = json.loads((ROOT / "release/release-evidence.json").read_text(encoding="utf-8"))[
        "release_history"
    ]
    del raw["attempt_references"][4]

    with pytest.raises(ValidationError, match="contiguous"):
        ReleaseHistorySummary.model_validate(raw)


def test_release_history_summary_rejects_latest_attempt_id_mismatch() -> None:
    raw = json.loads((ROOT / "release/release-evidence.json").read_text(encoding="utf-8"))[
        "release_history"
    ]
    raw["latest_attempt_id"] = "core-real-smoke-v2-attempt-9"

    with pytest.raises(ValidationError, match="latest attempt id"):
        ReleaseHistorySummary.model_validate(raw)


def test_gate_k_dynamic_history_rejects_latest_failing_call_mismatch() -> None:
    histories, references = load_contiguous_v2_histories(ROOT / "release/history", ROOT)
    manifest = load_release_evidence(ROOT / "release/release-evidence.json")
    summary = manifest.release_history.model_copy(
        update={"latest_failing_call_id": EXPECTED_CALL_IDS[1]}
    )

    with pytest.raises(ValueError, match="latest-attempt summary"):
        validate_dynamic_v2_history(
            histories,
            references,
            summary,
            smoke_plan_digest=(
                "sha256:8e0b6482dac4ccb0312d881eff3ab68f741d2b22b085557b1f9315e99fd1a18a"
            ),
            release_plan_digest=(
                "sha256:9ed4e586a663b5f1aba161718bbca584a6dc306bcb895fe1bc05d7b94aa3b4eb"
            ),
            smoke_call_ids=EXPECTED_CALL_IDS,
        )


def test_post_r4_smoke_history_is_safe_immutable_and_truthful() -> None:
    path = ROOT / "release/history/core-real-v2-attempt-2.json"
    history = json.loads(path.read_text(encoding="utf-8"))
    serialized = json.dumps(history, sort_keys=True)

    assert history["source_commit"] == "07e48c2b3eb330c3ff56a8473bb98025f86490b3"
    assert history["receipt_digest"] == (
        "sha256:e25ddea75fa5ca2ade3167bc063d9b771da1af5381f5a13403af118e136976d2"
    )
    assert history["attempted_top_level_launches"] == 4
    assert [call["outcome"] for call in history["calls"]] == [
        "verified_fail",
        "verified_pass",
        "verified_pass",
        "INFRASTRUCTURE",
    ]
    assert [call.get("verifier_score") for call in history["calls"][:3]] == [0.8, 1.0, 1.0]
    assert history["calls_5_to_8"] == "NOT_RUN"
    assert history["retry_count"] == history["fallback_count"] == 0
    assert "/home/dev/harnesslab-evidence" not in serialized
    assert "response_body" not in serialized
    assert "reasoning_content" not in serialized


def test_post_r5_smoke_history_is_safe_immutable_and_truthful() -> None:
    path = ROOT / "release/history/core-real-v2-attempt-3.json"
    history = json.loads(path.read_text(encoding="utf-8"))
    serialized = json.dumps(history, sort_keys=True)

    assert history["source_commit"] == "519ee8034af845f636aac8d836536dd4c4601bd0"
    assert history["receipt_digest"] == (
        "sha256:bb0f747005b90caa1983168f84d9dcc468be7e1ea7e575f488ce66e41e30faae"
    )
    assert history["attempted_top_level_launches"] == 1
    assert history["calls"][0]["outcome"] == "provider_error"
    assert history["calls"][0]["provider_failure"] == "timeout"
    assert history["calls"][0]["timeout_phase"] == "read"
    assert history["calls_2_to_8"] == "NOT_RUN"
    assert history["retry_count"] == history["fallback_count"] == 0
    assert history["raw_evidence_hygiene"] == "REJECTED_CONFIG_VALUE_DISCLOSURE"
    audits = history["prior_v2_raw_evidence_audit"]
    assert [item["base_url_present"] for item in audits] == ["YES", "YES", "YES"]
    assert [item["api_key_present"] for item in audits] == ["NO", "NO", "NO"]
    assert "/home/dev/harnesslab-evidence" not in serialized
    assert SAFE_ENVIRONMENT["HARNESSLAB_GPT56_RELAY_BASE_URL"] not in serialized
    assert all(value not in serialized for name, value in SAFE_ENVIRONMENT.items() if "KEY" in name)
    assert "response_body" not in serialized
    assert "reasoning_content" not in serialized


def test_post_r6_smoke_history_is_safe_immutable_and_truthful() -> None:
    path = ROOT / "release/history/core-real-v2-attempt-4.json"
    history = json.loads(path.read_text(encoding="utf-8"))
    serialized = json.dumps(history, sort_keys=True)

    assert history["source_commit"] == "06027d08735886a2add1c492081154a4374ea3e2"
    assert history["receipt_digest"] == (
        "sha256:c3eb90ce738805311f8ed35209c86b387749865739b797047f2b0ac5207b0856"
    )
    assert history["attempted_top_level_launches"] == 4
    assert [call["outcome"] for call in history["calls"]] == [
        "verified_fail",
        "verified_pass",
        "verified_pass",
        "harness_error",
    ]
    codex = history["calls"][3]
    assert codex["harness_failure"] == "timeout"
    assert codex["duration_ms"] == 90592
    assert codex["observed_model"] is None
    assert codex["verifier"] == "NOT_RUN"
    assert codex["safe_diagnostics"] == [
        "PROXY_CONNECT_DENIED_403",
        "WEBSOCKET_TO_HTTPS_FALLBACK",
    ]
    assert history["calls_5_to_8"] == "NOT_RUN"
    assert history["retry_count"] == history["fallback_count"] == 0
    assert history["runtime_value_hygiene"] == {
        "base_url_present": "NO",
        "api_key_present": "NO",
    }
    assert "GENERATED_PROFILE_SUPPRESSED_BY_IGNORE_USER_CONFIG" in serialized
    assert "/home/dev/harnesslab-evidence" not in serialized
    assert SAFE_ENVIRONMENT["HARNESSLAB_GPT56_RELAY_BASE_URL"] not in serialized
    assert all(value not in serialized for name, value in SAFE_ENVIRONMENT.items() if "KEY" in name)
    assert "response_body" not in serialized
    assert "reasoning_content" not in serialized


def test_post_r7_smoke_history_is_safe_immutable_and_truthful() -> None:
    path = ROOT / "release/history/core-real-v2-attempt-5.json"
    history = json.loads(path.read_text(encoding="utf-8"))
    serialized = json.dumps(history, sort_keys=True)

    assert history["source_commit"] == "029c0d84036dc697786fad02910c4212298ed28c"
    assert history["receipt_digest"] == (
        "sha256:9a8e4892d2fd070f004038068bc30aa2b327f366414455cf494be4a65fb6941a"
    )
    assert history["attempted_top_level_launches"] == 4
    assert [call["outcome"] for call in history["calls"]] == [
        "verified_fail",
        "subject_output_error",
        "verified_pass",
        "harness_error",
    ]
    assert history["calls"][0]["verifier_score"] == 0.8
    assert history["calls"][1]["stop_reason"] == "max_tokens"
    assert history["calls"][2]["verifier_score"] == 1.0
    codex = history["calls"][3]
    assert codex["harness_failure"] == "timeout"
    assert codex["duration_ms"] == 90563
    assert codex["trace_coverage"] == "FULL_STREAM"
    assert codex["trace_event_count"] == 15
    assert codex["verifier"] == "NOT_RUN"
    assert history["calls_5_to_8"] == "NOT_RUN"
    assert history["retry_count"] == history["fallback_count"] == 0
    assert history["safe_route_diagnostics"] == {
        "builtin_provider_proxy_403_present": "NO",
        "websocket_fallback_present": "NO",
    }
    assert history["safe_command_diagnostics"] == {
        "command_execution_attempts": 5,
        "command_execution_failures": 5,
        "root_cause": "CODEX_INNER_BWRAP_USER_NAMESPACE_DENIED",
    }
    assert history["runtime_value_hygiene"] == {
        "relay_base_url_present": "NO",
        "api_key_present": "NO",
    }
    assert "/home/dev/harnesslab-evidence" not in serialized
    assert all(value not in serialized for name, value in SAFE_ENVIRONMENT.items() if "KEY" in name)
    assert "response_body" not in serialized
    assert "reasoning_content" not in serialized


def test_post_r9_attempt_6_history_is_safe_immutable_and_truthful() -> None:
    path = ROOT / "release/history/core-real-v2-attempt-6.json"
    history = json.loads(path.read_text(encoding="utf-8"))
    serialized = json.dumps(history, sort_keys=True)

    assert history["source_commit"] == "14d18f9ac00cff18395c951a52c65f3469c199ad"
    assert history["receipt_digest"] == (
        "sha256:ba773df2c0b75d256ce5477e1ec4950286103031ebdd114bb33d730c45a28175"
    )
    assert history["attempted_top_level_launches"] == 1
    call = history["calls"][0]
    assert call["provider_failure"] == "timeout"
    assert call["timeout_phase"] == "read"
    assert call["latency_ms"] == 90386
    assert history["calls_2_to_8"] == "NOT_RUN"
    assert history["retry_count"] == history["fallback_count"] == 0
    assert history["runtime_value_hygiene"] == {
        "relay_base_url_present": "NO",
        "relay_api_key_present": "NO",
        "all_runtime_value_match_file_count": 0,
    }
    assert "/home/dev/harnesslab-evidence" not in serialized
    assert all(value not in serialized for name, value in SAFE_ENVIRONMENT.items() if "KEY" in name)
    assert "response_body" not in serialized
    assert "reasoning_content" not in serialized


def test_post_r9_attempt_7_history_is_safe_immutable_and_truthful() -> None:
    path = ROOT / "release/history/core-real-v2-attempt-7.json"
    history = json.loads(path.read_text(encoding="utf-8"))
    serialized = json.dumps(history, sort_keys=True)

    assert history["source_commit"] == "14d18f9ac00cff18395c951a52c65f3469c199ad"
    assert history["receipt_digest"] == (
        "sha256:fc77340afe9b71988c005af6bdbe519944287927767ff43f4a100743b8db02ed"
    )
    assert history["attempted_top_level_launches"] == 4
    assert [call["outcome"] for call in history["calls"]] == [
        "verified_pass",
        "verified_pass",
        "verified_pass",
        "harness_error",
    ]
    assert [call["verifier_score"] for call in history["calls"][:3]] == [1.0, 1.0, 1.0]
    codex = history["calls"][3]
    assert codex["original_persisted_harness_failure"] == "timeout"
    assert codex["original_persisted_process_exit_code"] == 0
    assert codex["duration_ms"] == 90580
    assert codex["terminal_native_event"] is None
    assert codex["verifier"] == "NOT_RUN"
    assert history["r10_classification_review"] == ("CLEAN_EXECUTION_BUDGET_EXHAUSTION_CANDIDATE")
    assert history["safe_r9_diagnostics"] == {
        "bwrap_namespace_error_present": "NO",
        "provider_proxy_403_present": "NO",
        "websocket_fallback_present": "NO",
        "successful_command_count": 1,
        "failed_command_count": 0,
    }
    assert history["security_profile"] == {
        "status": "PASS",
        "effective_filesystem_policy": "workspace-write",
        "filesystem_enforcement": "outer-docker",
        "codex_inner_filesystem_policy": "unrestricted",
        "tool_network_policy": "deny",
        "codex_inner_network_policy": "deny",
        "codex_inner_network_enforcement": "seccomp",
    }
    assert history["calls_5_to_8"] == "NOT_RUN"
    assert history["retry_count"] == history["fallback_count"] == 0
    assert "/home/dev/harnesslab-evidence" not in serialized
    assert all(value not in serialized for name, value in SAFE_ENVIRONMENT.items() if "KEY" in name)
    assert "response_body" not in serialized
    assert "reasoning_content" not in serialized


def test_post_r10_attempt_8_history_is_safe_immutable_and_truthful() -> None:
    path = ROOT / "release/history/core-real-v2-attempt-8.json"
    history = json.loads(path.read_text(encoding="utf-8"))
    serialized = json.dumps(history, sort_keys=True)

    assert history["source_commit"] == "2eb2be74c131e330be48467495b8c559776be146"
    assert history["receipt_digest"] == (
        "sha256:45eae792acbb7f8bc92d3097804dbc5c13ad85f181910f24092543d5d8c9749e"
    )
    assert history["attempted_top_level_launches"] == 4
    assert [call["outcome"] for call in history["calls"]] == [
        "subject_output_error",
        "verified_fail",
        "verified_fail",
        "harness_error",
    ]
    assert [call["statistical_outcome"] for call in history["calls"][:3]] == [
        "capability_fail",
        "capability_fail",
        "capability_fail",
    ]
    assert [call["verifier_score"] for call in history["calls"][:3]] == [None, 0.8, 0.8]
    codex = history["calls"][3]
    assert codex["original_persisted_harness_failure"] == "timeout"
    assert codex["original_persisted_process_exit_code"] is None
    assert codex["duration_ms"] == 90530
    assert codex["timed_out"] is True
    review = history["r11_classification_review"]
    assert review == {
        "result": "EXECUTION_BUDGET_EXHAUSTED_CANDIDATE",
        "successful_command_count": 1,
        "subject_nonzero_command_count": 1,
        "command_execution_infra_failure_count": 0,
        "file_change_completed": True,
        "failed_command_reason": "SUBJECT_COMMAND_NONZERO_EXIT",
        "safe_reason_detail": "GIT_WORKSPACE_PROBE_NOT_REPOSITORY",
    }
    assert history["security_profile"]["status"] == "PASS"
    assert history["runtime_value_hygiene"]["status"] == "PASS"
    assert history["runtime_value_hygiene"]["all_runtime_value_match_file_count"] == 0
    assert history["calls_5_to_8"] == "NOT_RUN"
    assert history["retry_count"] == history["fallback_count"] == 0
    assert "/home/dev/harnesslab-evidence" not in serialized
    assert "git status --short" not in serialized
    assert all(value not in serialized for name, value in SAFE_ENVIRONMENT.items() if "KEY" in name)
    assert "response_body" not in serialized
    assert "reasoning_content" not in serialized


def test_post_r11_attempt_9_history_is_safe_immutable_and_truthful() -> None:
    path = ROOT / "release/history/core-real-v2-attempt-9.json"
    history = json.loads(path.read_text(encoding="utf-8"))
    serialized = json.dumps(history, sort_keys=True)

    assert history["source_commit"] == "9f7ac3836da83d6009e2caa5eade07683ed68c7f"
    assert history["receipt_digest"] == (
        "sha256:750cb6a6d396bc49c43d07b9912bb5a84f016849d6e799faac435a750a0516bb"
    )
    assert history["attempted_top_level_launches"] == 6
    assert [call["outcome"] for call in history["calls"]] == [
        "verified_fail",
        "subject_output_error",
        "subject_output_error",
        "harness_error",
        "harness_error",
        "harness_error",
    ]
    assert [call["statistical_outcome"] for call in history["calls"][:5]] == ["capability_fail"] * 5
    claude = history["calls"][5]
    assert claude["harness"] == "claude-code"
    assert claude["cli_version"] == "2.1.241"
    assert claude["harness_failure"] == "process_error"
    assert claude["process_exit_code"] == 1
    assert claude["duration_ms"] == 1658
    assert claude["trace_event_count"] == 0
    assert claude["observed_model"] is None
    assert claude["verifier"] == "NOT_RUN"
    assert history["calls_7_to_8"] == "NOT_RUN"
    assert history["retry_count"] == history["fallback_count"] == 0
    assert history["runtime_value_hygiene"]["status"] == "PASS"
    assert history["runtime_value_hygiene"]["all_runtime_value_match_file_count"] == 0
    assert "/home/dev/harnesslab-evidence" not in serialized
    assert all(value not in serialized for name, value in SAFE_ENVIRONMENT.items() if "KEY" in name)
    assert "response_body" not in serialized
    assert "reasoning_content" not in serialized


def test_post_r12_attempt_10_history_is_safe_immutable_and_truthful() -> None:
    path = ROOT / "release/history/core-real-v2-attempt-10.json"
    history = json.loads(path.read_text(encoding="utf-8"))
    serialized = json.dumps(history, sort_keys=True)

    assert history["source_commit"] == "faf3b506c88421717c80a6848acbb08451e4314a"
    assert history["receipt_digest"] == (
        "sha256:be06f9eff5303db4f808b61dcf7da98d8a76a574a469f4bec474a8de95bff1df"
    )
    assert history["status"] == "ABORTED"
    assert history["attempted_top_level_launches"] == 1
    assert history["failing_call_id"] == EXPECTED_CALL_IDS[0]
    assert history["failure_category"] == "PROVIDER_FAILURE"
    call = history["calls"][0]
    assert call == {
        "call_id": EXPECTED_CALL_IDS[0],
        "requested_model": "gpt-5.6-sol",
        "observed_model": None,
        "latency_ms": 90277,
        "attempt_count": 1,
        "provider_failure": "timeout",
        "timeout_phase": "read",
        "outcome": "provider_error",
        "verifier": "NOT_RUN",
        "evidence_digest": (
            "sha256:97a9aa721a2c0d16eb80cf8a03be05ea944b86d18a3c48be58876f7b79dc6057"
        ),
    }
    assert "capability" not in call
    assert history["calls_2_to_8"] == "NOT_RUN"
    assert history["retry_count"] == history["fallback_count"] == 0
    assert history["runtime_value_hygiene"] == {
        "status": "PASS",
        "relay_base_url_present": "NO",
        "relay_api_key_present": "NO",
        "opencode_go_api_key_present": "NO",
        "deepseek_api_key_present": "NO",
        "all_runtime_value_match_file_count": 0,
        "recognized_credential_pattern_match_file_count": 0,
        "scan_error_count": 0,
    }
    assert "operational provider failure" in history["interpretation"]
    assert "not model capability evidence" in history["interpretation"]
    assert "did not reach Codex, Claude, DeepSeek Harness, or Judge" in history["interpretation"]
    assert "/home/dev/harnesslab-operator-evidence" not in serialized
    assert all(value not in serialized for value in SAFE_ENVIRONMENT.values())
    assert "response_body" not in serialized
    assert "reasoning_content" not in serialized


def test_post_r14_attempt_11_history_is_safe_immutable_and_truthful() -> None:
    path = ROOT / "release/history/core-real-v2-attempt-11.json"
    history = json.loads(path.read_text(encoding="utf-8"))
    serialized = json.dumps(history, sort_keys=True)

    assert history["source_commit"] == "a8800c1c5143743f23903cdc84f2fe2390d55604"
    assert history["receipt_digest"] == (
        "sha256:72cc8eb4d076fe2d25fa8aabdbc23b4a69b865aaa492f30a6849be6f72d4c0b0"
    )
    assert history["status"] == "ABORTED"
    assert history["attempted_top_level_launches"] == 1
    assert history["failing_call_id"] == EXPECTED_CALL_IDS[0]
    assert history["failure_category"] == "PROVIDER_FAILURE"
    call = history["calls"][0]
    assert call == {
        "call_id": EXPECTED_CALL_IDS[0],
        "requested_model": "gpt-5.6-sol",
        "observed_model": None,
        "latency_ms": 90405,
        "attempt_count": 1,
        "provider_failure": "timeout",
        "timeout_phase": "read",
        "outcome": "provider_error",
        "verifier": "NOT_RUN",
        "evidence_digest": (
            "sha256:5ea824fbcae24ee3b4ad6ccedd3c5f51167c7628dc7278509ef6aecf44a88259"
        ),
    }
    assert "read_timeout_stage" not in call
    assert history["calls_2_to_8"] == "NOT_RUN"
    assert history["retry_count"] == history["fallback_count"] == 0
    assert history["runtime_value_hygiene"] == {
        "status": "PASS",
        "relay_base_url_present": "NO",
        "relay_api_key_present": "NO",
        "opencode_go_api_key_present": "NO",
        "deepseek_api_key_present": "NO",
        "all_runtime_value_match_file_count": 0,
        "recognized_credential_pattern_match_file_count": 0,
        "scan_error_count": 0,
    }
    assert "operational provider failure evidence" in history["interpretation"]
    assert "not model capability evidence" in history["interpretation"]
    assert "Attempt 11 never reached Calls 2-8" in history["interpretation"]
    assert "NOT_DETERMINED" in serialized
    assert "/home/dev/harnesslab-operator-evidence" not in serialized
    assert all(value not in serialized for value in SAFE_ENVIRONMENT.values())
    assert "response_body" not in serialized
    assert "reasoning_content" not in serialized


def test_post_r15_attempt_12_history_is_safe_immutable_and_truthful() -> None:
    path = ROOT / "release/history/core-real-v2-attempt-12.json"
    history = json.loads(path.read_text(encoding="utf-8"))
    serialized = json.dumps(history, sort_keys=True)

    assert history["source_commit"] == "8d87c641e847c1b3bd0d53a96ef2655ed102d2d4"
    assert history["receipt_digest"] == (
        "sha256:056d49742d72366cdc630651563846aa15f3eee00d961bbbc3c98c9e9bc5f0a3"
    )
    assert history["status"] == "ABORTED"
    assert history["attempted_top_level_launches"] == 1
    assert history["failing_call_id"] == EXPECTED_CALL_IDS[0]
    assert history["failure_category"] == "PROVIDER_FAILURE"
    assert history["calls"] == [
        {
            "call_id": EXPECTED_CALL_IDS[0],
            "requested_model": "gpt-5.6-sol",
            "observed_model": None,
            "latency_ms": 90358,
            "attempt_count": 1,
            "provider_failure": "timeout",
            "timeout_phase": "read",
            "read_timeout_stage": "waiting_for_response_headers",
            "outcome": "provider_error",
            "verifier": "NOT_RUN",
            "evidence_digest": (
                "sha256:18a15e9166a2848b4cab24cd04f710268d581c2c973718c2f31de4babe19c687"
            ),
        }
    ]
    assert history["calls_2_to_8"] == "NOT_RUN"
    assert history["retry_count"] == history["fallback_count"] == 0
    assert history["runtime_value_hygiene"]["status"] == "PASS"
    assert history["runtime_value_hygiene"]["all_runtime_value_match_file_count"] == 0
    assert history["runtime_value_hygiene"]["recognized_credential_pattern_match_file_count"] == 0
    assert history["runtime_value_hygiene"]["scan_error_count"] == 0
    assert "No HTTP response headers became available" in history["interpretation"]
    assert "NOT_DETERMINED" in serialized
    assert "CONNECT_TCP" in serialized
    assert "predates direct-provider transport-phase tracing" in serialized
    assert "/home/dev/harnesslab-operator-evidence" not in serialized
    assert all(value not in serialized for value in SAFE_ENVIRONMENT.values())
    assert "response_body" not in serialized
    assert "reasoning_content" not in serialized


def test_smoke_dry_run_preflight_performs_zero_provider_invocations() -> None:
    control = SmokeControlPlane.load(ROOT)
    receipt = control.preflight()
    assert receipt.status is SmokeExecutionStatus.SUCCEEDED
    assert receipt.attempted_top_level_launches == 0
    assert receipt.results == ()
    cli = RUNNER.invoke(app, ["release", "smoke", "preflight", "--repository-root", str(ROOT)])
    assert cli.exit_code == 0
    assert "SMOKE_CALL_BINDINGS=8" in cli.stdout
    assert "REAL_EVALUATION_CALL_COUNT=0" in cli.stdout
    disabled = RUNNER.invoke(app, ["release", "smoke", "execute", "--repository-root", str(ROOT)])
    assert disabled.exit_code == 2
    assert "real smoke requires --allow-real-smoke" in disabled.stdout
    workflow = (ROOT / ".github/workflows/full-ci.yml").read_text()
    assert "--allow-real-smoke" not in workflow
    assert "release smoke execute" not in workflow


def test_v2_credential_preflight_prints_presence_only() -> None:
    environment = {name: f"secret-value-for-{name}" for name in REQUIRED_CONFIGURATION_REFERENCES}
    result = RUNNER.invoke(app, ["release", "smoke", "credential-preflight"], env=environment)
    assert result.exit_code == 0
    assert result.stdout.splitlines() == [
        f"{name}=SET" for name in REQUIRED_CONFIGURATION_REFERENCES
    ]
    assert all(value not in result.stdout for value in environment.values())

    environment.pop("HARNESSLAB_OPENCODE_GO_API_KEY")
    missing = RUNNER.invoke(app, ["release", "smoke", "credential-preflight"], env=environment)
    assert missing.exit_code == 2
    assert "HARNESSLAB_OPENCODE_GO_API_KEY=MISSING" in missing.stdout


@pytest.mark.asyncio
async def test_smoke_same_path_fake_execution_consumes_exact_plan_without_network() -> None:
    control = SmokeControlPlane.load(ROOT)
    bindings = control.resolve_real_bindings(SAFE_ENVIRONMENT, _runtime())
    invoker = RecordingInvoker()
    receipt = await control.execute(bindings, invoker, allow_real_smoke=True)
    assert receipt.status is SmokeExecutionStatus.SUCCEEDED
    assert receipt.attempted_top_level_launches == 8
    assert len(receipt.results) == 8
    assert tuple(item.frozen.call.call_id for item in invoker.calls) == EXPECTED_CALL_IDS
    assert tuple(item.frozen.call.max_output_tokens for item in invoker.calls) == (
        2000,
        2000,
        2000,
        2000,
        2000,
        2000,
        2000,
        256,
    )
    assert sum(int(item.frozen.call.top_level_launches) for item in invoker.calls) == 8
    assert {ref for item in invoker.calls for ref in item.frozen.call.credential_references} == set(
        REQUIRED_CONFIGURATION_REFERENCES
    )


@pytest.mark.asyncio
async def test_smoke_direct_subject_output_error_is_capability_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    control = SmokeControlPlane.load(ROOT)
    binding = control.resolve_real_bindings(SAFE_ENVIRONMENT, _runtime())[1]
    artifact = tmp_path / "subject-output-artifact"
    artifact.mkdir()
    (artifact / "manifest.json").write_text("{}\n", encoding="utf-8")

    class SubjectOutputRunner:
        def __init__(self, **_: object) -> None:
            pass

        async def run(self, *_: object, **__: object) -> SimpleNamespace:
            return SimpleNamespace(
                artifact_directory=artifact,
                evidence=SimpleNamespace(
                    provider_failure=None,
                    outcome=DirectModelOutcome.SUBJECT_OUTPUT_ERROR,
                    observed_model="qwen3.8-max",
                ),
            )

    monkeypatch.setattr("harnesslab.release.smoke.DirectModelRunner", SubjectOutputRunner)
    invoker = ProductionSmokeInvoker(ROOT, SAFE_ENVIRONMENT, tmp_path / "smoke")
    result = await invoker.invoke(binding)

    assert result.call_id == EXPECTED_CALL_IDS[1]
    assert len(result.evidence_references) == 1
    assert len(result.evidence_digests) == 1


@pytest.mark.asyncio
async def test_production_smoke_persists_codex_precapture_infrastructure_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    control = SmokeControlPlane.load(ROOT)
    binding = control.resolve_real_bindings(SAFE_ENVIRONMENT, _runtime())[3]
    secret = SAFE_ENVIRONMENT["HARNESSLAB_GPT56_RELAY_API_KEY"]
    runtime_url = SAFE_ENVIRONMENT["HARNESSLAB_GPT56_RELAY_BASE_URL"]

    class PreCaptureFailureBackend:
        def __init__(self, *, credentials: dict[str, str], **_: object) -> None:
            self.credentials = credentials
            self.egress_attestation = None

        @property
        def artifact_secret_values(self) -> tuple[str, ...]:
            return tuple(self.credentials.values())

        async def run(self, _: object) -> CodexProcessCapture:
            stderr_digest = (
                "sha256:"
                + hashlib.sha256(f"Codex failed; credential={secret}".encode()).hexdigest()
            )
            raise CodexBackendExecutionError(
                CodexBackendFailureEvidence(
                    phase=CodexBackendFailurePhase.CONTAINER_START,
                    duration_ms=3,
                    stderr_category="PRESENT",
                    stderr_digest=stderr_digest,
                )
            )

    monkeypatch.setattr("harnesslab.release.smoke.DockerCodexBackend", PreCaptureFailureBackend)
    invoker = ProductionSmokeInvoker(ROOT, SAFE_ENVIRONMENT, tmp_path / "smoke")
    with pytest.raises(SmokeCallFailure) as raised:
        await invoker.invoke(binding)

    assert raised.value.category is SmokeFailureCategory.INFRASTRUCTURE
    evidence_result = raised.value.evidence_result
    assert evidence_result is not None
    assert evidence_result.call_id == EXPECTED_CALL_IDS[3]
    artifact = Path(evidence_result.evidence_references[0])
    artifact_text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for path in artifact.rglob("*")
        if path.is_file()
    )
    assert (artifact / "manifest.json").is_file()
    assert secret not in artifact_text
    assert runtime_url not in artifact_text
    assert secret not in str(raised.value)
    assert runtime_url not in str(raised.value)
    assert secret not in evidence_result.model_dump_json()
    assert runtime_url not in evidence_result.model_dump_json()


@pytest.mark.asyncio
async def test_smoke_missing_config_stops_before_first_call() -> None:
    control = SmokeControlPlane.load(ROOT)
    invoker = RecordingInvoker()
    environment = dict(SAFE_ENVIRONMENT)
    environment.pop("HARNESSLAB_OPENCODE_GO_API_KEY")
    with pytest.raises(SmokeControlPlaneError, match="HARNESSLAB_OPENCODE_GO_API_KEY"):
        control.resolve_real_bindings(environment, _runtime())
    assert invoker.calls == []


@pytest.mark.asyncio
async def test_smoke_abort_on_first_failure_never_invokes_calls_four_through_eight() -> None:
    control = SmokeControlPlane.load(ROOT)
    bindings = control.resolve_real_bindings(SAFE_ENVIRONMENT, _runtime())
    invoker = RecordingInvoker(EXPECTED_CALL_IDS[2])
    receipt = await control.execute(bindings, invoker, allow_real_smoke=True)
    assert receipt.status is SmokeExecutionStatus.ABORTED
    assert receipt.attempted_top_level_launches == 3
    assert receipt.failing_call_id == EXPECTED_CALL_IDS[2]
    assert receipt.failure_category is SmokeFailureCategory.ROUTE_MISMATCH
    assert tuple(item.frozen.call.call_id for item in invoker.calls) == EXPECTED_CALL_IDS[:3]
    assert len(receipt.results) == 2


@pytest.mark.asyncio
async def test_smoke_typed_codex_infrastructure_failure_stops_without_retry_or_fallback() -> None:
    control = SmokeControlPlane.load(ROOT)
    bindings = control.resolve_real_bindings(SAFE_ENVIRONMENT, _runtime())

    class TypedFailureInvoker(RecordingInvoker):
        async def invoke(self, binding: ResolvedSmokeBinding) -> SmokeCallResult:
            self.calls.append(binding)
            call_id = binding.frozen.call.call_id
            result = SmokeCallResult(
                call_id=call_id,
                evidence_references=(f"fake://{call_id}",),
                evidence_digests=("sha256:" + "7" * 64,),
            )
            if call_id == EXPECTED_CALL_IDS[3]:
                raise SmokeCallFailure(
                    SmokeFailureCategory.INFRASTRUCTURE,
                    "typed Codex infrastructure failure",
                    result,
                )
            return result

    invoker = TypedFailureInvoker()
    receipt = await control.execute(bindings, invoker, allow_real_smoke=True)

    assert receipt.status is SmokeExecutionStatus.ABORTED
    assert receipt.attempted_top_level_launches == 4
    assert receipt.failing_call_id == EXPECTED_CALL_IDS[3]
    assert receipt.failure_category is SmokeFailureCategory.INFRASTRUCTURE
    assert tuple(item.call_id for item in receipt.results) == EXPECTED_CALL_IDS[:4]
    assert tuple(item.frozen.call.call_id for item in invoker.calls) == EXPECTED_CALL_IDS[:4]


@pytest.mark.asyncio
async def test_smoke_post_r10_subject_command_failure_continues_to_call_five(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    control = SmokeControlPlane.load(ROOT)
    bindings = control.resolve_real_bindings(SAFE_ENVIRONMENT, _runtime())
    artifact = tmp_path / "codex-budget-artifact"
    artifact.mkdir()
    (artifact / "manifest.json").write_text("{}\n", encoding="utf-8")

    class FakeBackend:
        def __init__(self, **_: object) -> None:
            self.egress_attestation = None

    class BudgetRunner:
        def __init__(self, **_: object) -> None:
            pass

        async def run(self, *_: object, **__: object) -> SimpleNamespace:
            collection = collect_codex_jsonl(
                CodexProcessCapture(
                    _post_r10_subject_command_timeout_lines(),
                    None,
                    90_530,
                    timed_out=True,
                )
            )
            assert collection.failure_category is HarnessFailureCategory.EXECUTION_BUDGET_EXHAUSTED
            return SimpleNamespace(
                artifact_directory=artifact,
                evidence=SimpleNamespace(
                    harness_failure=collection.failure_category,
                    outcome=HarnessLaneOutcome.HARNESS_ERROR,
                    observed_model=None,
                ),
            )

    monkeypatch.setattr("harnesslab.release.smoke.DockerCodexBackend", FakeBackend)
    monkeypatch.setattr("harnesslab.release.smoke.CodexHarnessRunner", BudgetRunner)
    production = ProductionSmokeInvoker(ROOT, SAFE_ENVIRONMENT, tmp_path / "smoke")

    class SequenceInvoker(RecordingInvoker):
        async def invoke(self, binding: ResolvedSmokeBinding) -> SmokeCallResult:
            self.calls.append(binding)
            if binding.frozen.call.call_id == EXPECTED_CALL_IDS[3]:
                return await production.invoke(binding)
            return SmokeCallResult(
                call_id=binding.frozen.call.call_id,
                evidence_references=(f"fake://{binding.frozen.call.call_id}",),
                evidence_digests=("sha256:" + "8" * 64,),
            )

    invoker = SequenceInvoker()
    receipt = await control.execute(bindings, invoker, allow_real_smoke=True)

    assert receipt.status is SmokeExecutionStatus.SUCCEEDED
    assert receipt.attempted_top_level_launches == 8
    assert tuple(item.call_id for item in receipt.results) == EXPECTED_CALL_IDS
    assert tuple(item.frozen.call.call_id for item in invoker.calls) == EXPECTED_CALL_IDS
    assert sum(item.frozen.call.call_id == EXPECTED_CALL_IDS[3] for item in invoker.calls) == 1
    assert EXPECTED_CALL_IDS[4] in tuple(item.frozen.call.call_id for item in invoker.calls)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "trace_lines",
    (
        (
            json.dumps({"type": "thread.started", "thread_id": "ambiguous-thread"}),
            json.dumps({"type": "turn.started"}),
        ),
        _bwrap_timeout_lines(),
        _error_timeout_lines(),
    ),
    ids=("ambiguous", "bwrap", "error"),
)
async def test_smoke_infra_timeout_trace_stops_at_call_four(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    trace_lines: tuple[str, ...],
) -> None:
    control = SmokeControlPlane.load(ROOT)
    bindings = control.resolve_real_bindings(SAFE_ENVIRONMENT, _runtime())
    artifact = tmp_path / "codex-timeout-artifact"
    artifact.mkdir()
    (artifact / "manifest.json").write_text("{}\n", encoding="utf-8")

    class FakeBackend:
        def __init__(self, **_: object) -> None:
            self.egress_attestation = None

    class TimeoutRunner:
        def __init__(self, **_: object) -> None:
            pass

        async def run(self, *_: object, **__: object) -> SimpleNamespace:
            collection = collect_codex_jsonl(
                CodexProcessCapture(trace_lines, None, 90_001, timed_out=True)
            )
            assert collection.failure_category is HarnessFailureCategory.TIMEOUT
            return SimpleNamespace(
                artifact_directory=artifact,
                evidence=SimpleNamespace(
                    harness_failure=collection.failure_category,
                    outcome=HarnessLaneOutcome.HARNESS_ERROR,
                    observed_model=None,
                ),
            )

    monkeypatch.setattr("harnesslab.release.smoke.DockerCodexBackend", FakeBackend)
    monkeypatch.setattr("harnesslab.release.smoke.CodexHarnessRunner", TimeoutRunner)
    production = ProductionSmokeInvoker(ROOT, SAFE_ENVIRONMENT, tmp_path / "smoke")

    class SequenceInvoker(RecordingInvoker):
        async def invoke(self, binding: ResolvedSmokeBinding) -> SmokeCallResult:
            self.calls.append(binding)
            if binding.frozen.call.call_id == EXPECTED_CALL_IDS[3]:
                return await production.invoke(binding)
            return SmokeCallResult(call_id=binding.frozen.call.call_id)

    invoker = SequenceInvoker()
    receipt = await control.execute(bindings, invoker, allow_real_smoke=True)

    assert receipt.status is SmokeExecutionStatus.ABORTED
    assert receipt.attempted_top_level_launches == 4
    assert receipt.failing_call_id == EXPECTED_CALL_IDS[3]
    assert receipt.failure_category is SmokeFailureCategory.HARNESS_FAILURE
    assert tuple(item.frozen.call.call_id for item in invoker.calls) == EXPECTED_CALL_IDS[:4]


@pytest.mark.asyncio
async def test_smoke_budget_exhaustion_rejects_exposed_wrong_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    control = SmokeControlPlane.load(ROOT)
    binding = control.resolve_real_bindings(SAFE_ENVIRONMENT, _runtime())[3]
    artifact = tmp_path / "codex-wrong-model-artifact"
    artifact.mkdir()
    (artifact / "manifest.json").write_text("{}\n", encoding="utf-8")

    class FakeBackend:
        def __init__(self, **_: object) -> None:
            self.egress_attestation = None

    class WrongModelRunner:
        def __init__(self, **_: object) -> None:
            pass

        async def run(self, *_: object, **__: object) -> SimpleNamespace:
            return SimpleNamespace(
                artifact_directory=artifact,
                evidence=SimpleNamespace(
                    harness_failure=HarnessFailureCategory.EXECUTION_BUDGET_EXHAUSTED,
                    outcome=HarnessLaneOutcome.HARNESS_ERROR,
                    observed_model="wrong-model",
                ),
            )

    monkeypatch.setattr("harnesslab.release.smoke.DockerCodexBackend", FakeBackend)
    monkeypatch.setattr("harnesslab.release.smoke.CodexHarnessRunner", WrongModelRunner)
    invoker = ProductionSmokeInvoker(ROOT, SAFE_ENVIRONMENT, tmp_path / "smoke")

    with pytest.raises(SmokeCallFailure) as raised:
        await invoker.invoke(binding)

    assert raised.value.category is SmokeFailureCategory.OBSERVED_MODEL_CONFLICT


@pytest.mark.asyncio
async def test_smoke_multi_harness_model_turn_failure_is_capability_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    control = SmokeControlPlane.load(ROOT)
    binding = control.resolve_real_bindings(SAFE_ENVIRONMENT, _runtime())[5]
    artifact = tmp_path / "claude-turn-failure-artifact"
    artifact.mkdir()
    (artifact / "manifest.json").write_text("{}\n", encoding="utf-8")

    class FakeBackend:
        def __init__(self, **_: object) -> None:
            self.egress_attestation = None

    class TurnFailureRunner:
        def __init__(self, **_: object) -> None:
            pass

        async def run(self, *_: object, **__: object) -> SimpleNamespace:
            return SimpleNamespace(
                artifact_directory=artifact,
                evidence=SimpleNamespace(
                    harness_failure=HarnessFailureCategory.MODEL_TURN_FAILED,
                    outcome=HarnessLaneOutcome.HARNESS_ERROR,
                    observed_model=None,
                ),
            )

    monkeypatch.setattr("harnesslab.release.smoke.DockerMultiHarnessBackend", FakeBackend)
    monkeypatch.setattr("harnesslab.release.smoke.MultiHarnessRunner", TurnFailureRunner)
    invoker = ProductionSmokeInvoker(ROOT, SAFE_ENVIRONMENT, tmp_path / "smoke")

    result = await invoker.invoke(binding)

    assert result.call_id == EXPECTED_CALL_IDS[5]


@pytest.mark.asyncio
async def test_smoke_one_judge_call_only() -> None:
    control = SmokeControlPlane.load(ROOT)
    bindings = control.resolve_real_bindings(SAFE_ENVIRONMENT, _runtime())
    assert sum(binding.frozen.call.lane == "J" for binding in bindings) == 1
    assert bindings[-1].frozen.call.judge_case_reference == (
        "judge_suites/core-calibration/1.0.0#label-l0-pass"
    )
    invoker = RecordingInvoker()
    receipt = await control.execute(bindings, invoker, allow_real_smoke=True)
    judge_calls = [item for item in invoker.calls if item.frozen.call.lane == "J"]
    assert receipt.status is SmokeExecutionStatus.SUCCEEDED
    assert len(judge_calls) == 1


def _r1_test_policy() -> SmokeContinuationPolicy:
    return SmokeContinuationPolicy(
        policy_id="kb2r-r1-v4-suffix-continuation",
        base_branch_head="cd7de16eb4549d4a108ec9908b57905b50cd0562",
        repair_commit_identity="cd7de16eb4549d4a108ec9908b57905b50cd0562",
        release_plan_reference="release/core-real-evidence-plan-v4.json",
        release_plan_digest="sha256:" + "1" * 64,
        smoke_plan_reference="release/core-real-smoke-plan-v4.json",
        smoke_plan_digest="sha256:" + "2" * 64,
        original_receipt_reference=("artifacts/core-real-matrix-v4-canary/smoke-execution.json"),
        original_receipt_digest="sha256:" + "3" * 64,
        original_calls=tuple(
            SmokeCallResult(
                call_id=call_id,
                evidence_references=(f"fixture://{call_id}",),
                evidence_digests=("sha256:" + "4" * 64,),
            )
            for call_id in EXPECTED_CALL_IDS[:4]
        ),
        old_control_plane_classification="OBSERVED_MODEL_CONFLICT",
        raw_safe_fact=("observed_model_status=NOT_EXPOSED;observed_model=null;verifier=PASS"),
        repaired_classification_rule=(
            "NOT_EXPOSED_PLUS_NULL_IS_OBSERVED_MODEL_MISSING_LIMITATION_NOT_CONFLICT"
        ),
        codex_observed_model_capability="NOT_GUARANTEED_BY_PINNED_SCHEMA",
        allowed_suffix_call_ids=EXPECTED_CALL_IDS[4:],
        protected_file_sha256={},
    )


@pytest.mark.asyncio
async def test_r1_continuation_can_only_launch_calls_5_to_8_with_combined_ceiling(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    control = SmokeControlPlane.load(ROOT, plan_version="v4")
    bindings = control.resolve_real_bindings(SAFE_ENVIRONMENT, _runtime())
    invoker = RecordingInvoker()
    monkeypatch.setattr(control, "validate_continuation_policy", lambda _: control.preflight())
    receipt = await control.execute_continuation(
        bindings,
        invoker,
        _r1_test_policy(),
        allow_real_smoke=True,
        receipt_path=tmp_path / "r1-smoke-execution.json",
    )

    assert tuple(item.frozen.call.call_id for item in invoker.calls) == EXPECTED_CALL_IDS[4:]
    assert receipt.reran_calls_1_to_4 is False
    assert (receipt.new_subject_launches, receipt.total_subject_launches) == (3, 7)
    assert (receipt.new_judge_launches, receipt.total_judge_launches) == (1, 1)
    assert receipt.recovery_attempts == 0


@pytest.mark.asyncio
async def test_r1_continuation_failure_stops_before_judge_and_cannot_retry(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    control = SmokeControlPlane.load(ROOT, plan_version="v4")
    bindings = control.resolve_real_bindings(SAFE_ENVIRONMENT, _runtime())
    invoker = RecordingInvoker(failing_call_id=EXPECTED_CALL_IDS[5])
    monkeypatch.setattr(control, "validate_continuation_policy", lambda _: control.preflight())
    receipt_path = tmp_path / "r1-smoke-execution.json"
    receipt = await control.execute_continuation(
        bindings,
        invoker,
        _r1_test_policy(),
        allow_real_smoke=True,
        receipt_path=receipt_path,
    )
    assert tuple(item.frozen.call.call_id for item in invoker.calls) == EXPECTED_CALL_IDS[4:6]
    assert receipt.new_subject_launches == 2
    assert receipt.new_judge_launches == 0
    with pytest.raises(SmokeControlPlaneError, match="retries are forbidden"):
        await control.execute_continuation(
            bindings,
            RecordingInvoker(),
            _r1_test_policy(),
            allow_real_smoke=True,
            receipt_path=receipt_path,
        )


@pytest.mark.parametrize(
    ("mutation", "value"),
    (
        ("ninth-call", None),
        ("task-id", "other-task"),
        ("task-digest", "sha256:" + "9" * 64),
        ("model", "other-model"),
        ("route", "other|responses|env:OTHER/responses"),
        ("output-ceiling", 14_257),
        ("judge-launches", 2),
    ),
)
def test_smoke_plan_mutation_or_ninth_call_is_rejected_before_execution(
    tmp_path: Path, mutation: str, value: object
) -> None:
    root = _mutated_repository(tmp_path)
    path = root / "release/core-real-smoke-plan.json"
    raw = json.loads(path.read_text())
    if mutation == "ninth-call":
        extra = dict(raw["calls"][-1])
        extra["call_id"] = "smoke-9-forbidden"
        raw["calls"].append(extra)
    elif mutation == "task-id":
        raw["calls"][0]["task_id"] = value
    elif mutation == "task-digest":
        raw["calls"][0]["task_digest"] = value
    elif mutation == "model":
        raw["calls"][0]["requested_model"] = value
    elif mutation == "route":
        raw["calls"][0]["provider_route"] = value
    elif mutation == "output-ceiling":
        raw["max_output_token_ceiling"] = value
    else:
        raw["calls"][-1]["top_level_launches"] = value
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(SmokeControlPlaneError):
        SmokeControlPlane.load(root)


def test_smoke_ninth_call_is_rejected_before_execution(tmp_path: Path) -> None:
    root = _mutated_repository(tmp_path)
    path = root / "release/core-real-smoke-plan.json"
    raw = json.loads(path.read_text())
    extra = dict(raw["calls"][-1])
    extra["call_id"] = "smoke-9-forbidden"
    raw["calls"].append(extra)
    path.write_text(json.dumps(raw), encoding="utf-8")
    with pytest.raises(SmokeControlPlaneError):
        SmokeControlPlane.load(root)


def test_smoke_provider_fallbacks_are_rejected_in_production_assertions() -> None:
    control = SmokeControlPlane.load(ROOT)
    profiles = {profile.profile_id: profile for profile in control.release_plan.selected_profiles}
    with pytest.raises(SmokeControlPlaneError, match="Codex relay fallback"):
        control._assert_codex_route(
            canonical_codex_profile(_runtime().codex_image),
            profiles["harness-codex-gpt56-medium"],
            SAFE_ENVIRONMENT,
        )
    claude = configured_qwen_opencode_go_claude_profile(_runtime().claude_image).model_copy(
        update={"provider_fixed_base_url": "https://api.anthropic.com"}
    )
    with pytest.raises(SmokeControlPlaneError, match="Claude OpenCode Go route"):
        control._assert_claude_route(
            claude,
            profiles["harness-claude-qwen38-opencode-go"],
            SAFE_ENVIRONMENT,
        )
    with pytest.raises(SmokeControlPlaneError, match="DeepSeek official-route"):
        control._assert_deepseek_route(
            canonical_deepseek_profile(
                _runtime().deepseek_image, _runtime().deepseek_config_digest
            ),
            profiles["harness-deepseek-v4flash"],
            SAFE_ENVIRONMENT,
        )


def test_dsh_e1_not_exposed_is_accepted_without_observed_model_fabrication() -> None:
    profile = configured_deepseek_v4flash_profile(
        _runtime().deepseek_image, _runtime().deepseek_config_digest
    )
    collection = collect_deepseek_final(HarnessProcessCapture(("completed output",), "", 0, 1))
    _validate_harness_observed_model(
        profile,
        trace_coverage=profile.trace_coverage,
        observed_model_status=collection.observed_model_status,
        observed_model=collection.observed_model,
    )
    assert profile.requested_model == "deepseek-v4-flash"
    assert collection.observed_model_status is ObservedModelStatus.NOT_EXPOSED
    assert collection.observed_model is None
    assert collection.sanitized_events[0].observed_model is None
    assert profile.requested_model not in collection.sanitized_jsonl


def test_claude_smoke_requires_exact_exposed_observed_model() -> None:
    profile = configured_qwen_opencode_go_claude_profile(_runtime().claude_image)
    _validate_harness_observed_model(
        profile,
        trace_coverage=TraceCoverage.FULL_STREAM,
        observed_model_status=ObservedModelStatus.EXPOSED,
        observed_model="qwen3.8-max",
    )
    for status, observed_model in (
        (ObservedModelStatus.NOT_EXPOSED, None),
        (ObservedModelStatus.EXPOSED, "wrong-model"),
    ):
        with pytest.raises(SmokeCallFailure) as raised:
            _validate_harness_observed_model(
                profile,
                trace_coverage=TraceCoverage.FULL_STREAM,
                observed_model_status=status,
                observed_model=observed_model,
            )
        assert raised.value.category is SmokeFailureCategory.OBSERVED_MODEL_CONFLICT


def test_codex_smoke_not_exposed_is_limitation_but_exposed_mismatch_blocks() -> None:
    profile = configured_gpt56_relay_codex_profile(
        _runtime().codex_image,
        provider_base_url_reference="HARNESSLAB_GPT56_RELAY_BASE_URL",
        reasoning_effort="medium",
    )
    assessment = _validate_harness_observed_model(
        profile,
        trace_coverage=TraceCoverage.FULL_STREAM,
        observed_model_status=ObservedModelStatus.NOT_EXPOSED,
        observed_model=None,
    )
    assert assessment.value == "OBSERVED_MODEL_MISSING"
    with pytest.raises(SmokeCallFailure) as raised:
        _validate_harness_observed_model(
            profile,
            trace_coverage=TraceCoverage.FULL_STREAM,
            observed_model_status=ObservedModelStatus.EXPOSED,
            observed_model="wrong-model",
        )
    assert raised.value.category is SmokeFailureCategory.OBSERVED_MODEL_CONFLICT


def test_dsh_incoherent_observed_model_state_is_rejected() -> None:
    profile = configured_deepseek_v4flash_profile(
        _runtime().deepseek_image, _runtime().deepseek_config_digest
    )
    for coverage, status, observed_model in (
        (TraceCoverage.FINAL_OUTPUT_ONLY, ObservedModelStatus.EXPOSED, "deepseek-v4-flash"),
        (TraceCoverage.FINAL_OUTPUT_ONLY, ObservedModelStatus.NOT_EXPOSED, "deepseek-v4-flash"),
        (TraceCoverage.FULL_STREAM, ObservedModelStatus.NOT_EXPOSED, None),
    ):
        with pytest.raises(SmokeCallFailure) as raised:
            _validate_harness_observed_model(
                profile,
                trace_coverage=coverage,
                observed_model_status=status,
                observed_model=observed_model,
            )
        assert raised.value.category is SmokeFailureCategory.OBSERVED_MODEL_CONFLICT


def test_deepseek_runtime_config_drift_remains_rejected() -> None:
    _validate_deepseek_effective_config("provider: deepseek-official\nmodel: deepseek-v4-flash\n")
    for drifted in (
        "provider: other-provider\nmodel: deepseek-v4-flash\n",
        "provider: deepseek-official\nmodel: other-model\n",
    ):
        with pytest.raises(RuntimeError, match="effective provider/model identity drifted"):
            _validate_deepseek_effective_config(drifted)


def test_release_cli_normalizes_egress_isolation_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def unavailable(*_: object, **__: object) -> object:
        raise EgressNetworkIsolationUnavailable("EGRESS_NETWORK_ISOLATION_UNAVAILABLE")

    monkeypatch.setattr("harnesslab.cli.execute_real_smoke", unavailable)
    result = RUNNER.invoke(
        app,
        [
            "release",
            "smoke",
            "execute",
            "--allow-real-smoke",
            "--repository-root",
            str(ROOT),
        ],
    )
    assert result.exit_code == 2
    assert "FAIL smoke execution: EGRESS_NETWORK_ISOLATION_UNAVAILABLE" in result.stdout
    assert "Traceback" not in result.stdout


def test_immutable_egress_proxy_image_identity_is_required() -> None:
    assert "@sha256:" in EGRESS_PROXY_BASE
    assert EGRESS_PROXY_SOURCE_DIGEST.startswith("sha256:")
    dockerfile = (ROOT / "docker/egress/Dockerfile").read_text()
    assert dockerfile.splitlines()[0] == f"FROM {EGRESS_PROXY_BASE}"
    assert EGRESS_PROXY_SOURCE_DIGEST in dockerfile
    proxy_bytes = (ROOT / "docker/egress/proxy.py").read_bytes()
    proxy_digest = "sha256:" + hashlib.sha256(proxy_bytes).hexdigest()
    assert proxy_digest == EGRESS_PROXY_SOURCE_DIGEST
    with pytest.raises(EgressSecurityError, match="inspected non-zero"):
        ProviderScopedDockerBoundary(
            EgressPolicy(allowed_hostname="provider.example.test"),
            "review-internal",
            "review-proxy",
            ImageIdentity(reference=EGRESS_PROXY_IMAGE, image_id="sha256:" + "0" * 64),
        )


def test_internal_network_create_argv_requires_isolated_gateway_mode() -> None:
    boundary = ProviderScopedDockerBoundary(
        EgressPolicy(allowed_hostname="provider.example.test"),
        "review-internal",
        "review-proxy",
        _runtime().egress_proxy_image,
    )
    assert boundary.create_internal_network_argv() == (
        "network",
        "create",
        "--driver",
        "bridge",
        "--internal",
        "--ipv6=false",
        "-o",
        "com.docker.network.bridge.gateway_mode_ipv4=isolated",
        "review-internal",
    )


@pytest.mark.asyncio
async def test_real_smoke_network_isolation_preflight_fails_before_first_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime_resolution_attempted = False

    async def unavailable() -> object:
        raise EgressNetworkIsolationUnavailable("EGRESS_NETWORK_ISOLATION_UNAVAILABLE")

    async def forbidden_runtime_resolution() -> RuntimeIdentities:
        nonlocal runtime_resolution_attempted
        runtime_resolution_attempted = True
        return _runtime()

    monkeypatch.setattr("harnesslab.release.smoke.preflight_egress_network_isolation", unavailable)
    monkeypatch.setattr(
        "harnesslab.release.smoke.resolve_runtime_identities", forbidden_runtime_resolution
    )
    with pytest.raises(
        EgressNetworkIsolationUnavailable, match="EGRESS_NETWORK_ISOLATION_UNAVAILABLE"
    ):
        await execute_real_smoke(
            ROOT,
            allow_real_smoke=True,
            environment=SAFE_ENVIRONMENT,
        )
    assert not runtime_resolution_attempted


@pytest.mark.asyncio
async def test_actual_docker_network_isolation_preflight_attests_and_cleans_up() -> None:
    attestation = await preflight_egress_network_isolation()
    assert attestation.driver == "bridge"
    assert attestation.internal is True
    assert attestation.enable_ipv6 is False
    assert attestation.gateway_mode_ipv4 == "isolated"
    _, environment = await _docker_runtime_preflight()
    cli = _DockerCLI(output_limit=1_000_000, environment=environment)
    absent = await cli.run("network", "inspect", attestation.network, check=False)
    assert absent.returncode != 0


@pytest.mark.asyncio
async def test_network_attestation_rejects_internal_bridge_without_isolated_gateway_mode() -> None:
    _, environment = await _docker_runtime_preflight()
    cli = _DockerCLI(output_limit=1_000_000, environment=environment)
    network = f"hl-review-mutation-{uuid4().hex[:12]}"
    boundary = ProviderScopedDockerBoundary(
        EgressPolicy(allowed_hostname="provider.example.test"),
        network,
        "hl-review-mutation-unused-proxy",
        _runtime().egress_proxy_image,
    )
    try:
        await cli.run(
            "network",
            "create",
            "--driver",
            "bridge",
            "--internal",
            "--ipv6=false",
            network,
        )
        inspected = await cli.run("network", "inspect", network)
        options = json.loads(inspected.stdout)[0]["Options"] or {}
        assert options.get(INTERNAL_NETWORK_GATEWAY_MODE_OPTION) != "isolated"
        with pytest.raises(
            EgressNetworkIsolationUnavailable, match="EGRESS_NETWORK_ISOLATION_UNAVAILABLE"
        ):
            await boundary.attest_internal_network(cli)
    finally:
        await cli.run("network", "rm", network, check=False)
    absent = await cli.run("network", "inspect", network, check=False)
    assert absent.returncode != 0


@pytest.mark.asyncio
async def test_egress_cleanup_attempts_every_resource_after_partial_failure() -> None:
    class FailingCLI:
        def __init__(self) -> None:
            self.calls: list[tuple[str, ...]] = []

        async def run(self, *arguments: str, **_: object) -> object:
            self.calls.append(arguments)
            if arguments[0] == "kill":
                raise RuntimeError("synthetic subject cleanup failure")
            return SimpleNamespace(
                returncode=1 if arguments[:2] == ("network", "inspect") else 0,
                stdout=b"",
            )

    cli = FailingCLI()
    boundary = ProviderScopedDockerBoundary(
        EgressPolicy(allowed_hostname="provider.example.test"),
        "review-internal",
        "review-proxy",
        _runtime().egress_proxy_image,
    )
    with pytest.raises(EgressSecurityError, match="cleanup was not verified"):
        await boundary.cleanup(cli)
    assert ("rm", "--force", "review-proxy") in cli.calls
    assert ("network", "rm", "review-internal") in cli.calls
    assert ("network", "inspect", "review-internal") in cli.calls


@pytest.mark.asyncio
async def test_codex_and_multiharness_cleanup_continue_after_subject_failure() -> None:
    class PartialFailureCLI:
        def __init__(self, subject: str) -> None:
            self.subject = subject
            self.calls: list[tuple[str, ...]] = []

        async def run(self, *arguments: str, **_: object) -> object:
            self.calls.append(arguments)
            if arguments == ("kill", self.subject):
                raise RuntimeError("synthetic subject cleanup failure")
            return SimpleNamespace(
                returncode=1 if arguments[:2] == ("network", "inspect") else 0,
                stdout=b"",
            )

    for backend_type, prefix in (
        (DockerCodexBackend, "codex"),
        (DockerMultiHarnessBackend, "multi"),
    ):
        boundary = ProviderScopedDockerBoundary(
            EgressPolicy(allowed_hostname="provider.example.test"),
            f"{prefix}-internal",
            f"{prefix}-proxy",
            _runtime().egress_proxy_image,
        )
        backend = backend_type(egress_boundary=boundary)
        cli = PartialFailureCLI(f"{prefix}-subject")
        with pytest.raises(HarnessAdapterError, match="cleanup was not verified"):
            await backend._cleanup_execution(
                cast(_DockerCLI, cli), f"{prefix}-subject", create_attempted=True
            )
        assert ("rm", "--force", f"{prefix}-proxy") in cli.calls
        assert ("network", "rm", f"{prefix}-internal") in cli.calls


@pytest.mark.asyncio
async def test_actual_local_docker_egress_topology_denies_bypass_and_cleans_up() -> None:
    identity = await EgressProxyRuntime().ensure_image()
    _, environment = await _docker_runtime_preflight()
    cli = _DockerCLI(output_limit=1_000_000, environment=environment)
    suffix = uuid4().hex[:12]
    network = f"hl-review-{suffix}-internal"
    proxy = f"hl-review-{suffix}-proxy"
    subject = f"hl-review-{suffix}-subject"
    verifier = f"hl-review-{suffix}-verifier"
    boundary = ProviderScopedDockerBoundary(
        EgressPolicy(allowed_hostname="provider.example.test"),
        network,
        proxy,
        identity,
    )
    sentinel_connection = asyncio.Event()

    async def record_sentinel_connection(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        sentinel_connection.set()
        writer.close()
        await writer.wait_closed()

    sentinel = await asyncio.start_server(record_sentinel_connection, "0.0.0.0", 0)
    sentinel_port = int(sentinel.sockets[0].getsockname()[1])
    provisioned = False
    try:
        attestation = await boundary.provision(cli)
        provisioned = True
        assert attestation.image.image_id == identity.image_id
        assert attestation.networks == tuple(sorted((network, "bridge")))
        assert attestation.internal_network_is_internal
        assert attestation.internal_network_security.driver == "bridge"
        assert attestation.internal_network_security.internal is True
        assert attestation.internal_network_security.enable_ipv6 is False
        assert attestation.internal_network_security.gateway_mode_ipv4 == "isolated"
        assert not attestation.privileged
        assert attestation.read_only_rootfs
        assert attestation.user == "10001:10001"
        assert "ALL" in attestation.cap_drop
        assert "no-new-privileges=true" in attestation.security_options
        assert not attestation.published_ports
        assert not attestation.docker_socket_mounted
        network_inspect = await cli.run("network", "inspect", network)
        ipam_config = json.loads(network_inspect.stdout)[0]["IPAM"]["Config"][0]
        assert "Gateway" not in ipam_config
        subnet = ipaddress.ip_network(ipam_config["Subnet"])
        ordinary_gateway = str(subnet.network_address + 1)

        subject_code = f"""
import socket, sys, time
deadline = time.monotonic() + 5
while True:
    try:
        sock = socket.create_connection(({proxy!r}, 8080), timeout=1)
        break
    except OSError:
        if time.monotonic() >= deadline:
            raise
sock.sendall(b'CONNECT undeclared.invalid:443 HTTP/1.1\\r\\nHost: undeclared.invalid\\r\\n\\r\\n')
reply = sock.recv(128)
sock.close()
if not reply.startswith(b'HTTP/1.1 403'):
    sys.exit(10)
try:
    socket.create_connection(('1.1.1.1', 443), timeout=1)
except OSError:
    pass
else:
    sys.exit(11)
try:
    socket.create_connection(({ordinary_gateway!r}, {sentinel_port}), timeout=1)
except OSError:
    sys.exit(0)
sys.exit(12)
"""
        await cli.run(
            "create",
            "--name",
            subject,
            "--network",
            network,
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges=true",
            "--entrypoint",
            "python",
            EGRESS_PROXY_IMAGE,
            "-c",
            subject_code,
        )
        subject_networks = await cli.run(
            "inspect", subject, "--format", "{{json .NetworkSettings.Networks}}"
        )
        assert tuple(json.loads(subject_networks.stdout).keys()) == (network,)
        subject_result = await cli.run("start", "--attach", subject, check=False, timeout=15)
        assert subject_result.returncode == 0
        assert not sentinel_connection.is_set()

        verifier_code = """
import socket, sys
try:
    socket.create_connection(('1.1.1.1', 443), timeout=1)
except OSError:
    sys.exit(0)
sys.exit(12)
"""
        await cli.run(
            "create",
            "--name",
            verifier,
            "--network",
            "none",
            "--entrypoint",
            "python",
            EGRESS_PROXY_IMAGE,
            "-c",
            verifier_code,
        )
        verifier_network = await cli.run(
            "inspect", verifier, "--format", "{{json .HostConfig.NetworkMode}}"
        )
        assert json.loads(verifier_network.stdout) == "none"
        verifier_result = await cli.run("start", "--attach", verifier, check=False, timeout=10)
        assert verifier_result.returncode == 0
    finally:
        sentinel.close()
        await sentinel.wait_closed()
        for container in (subject, verifier):
            await cli.run("kill", container, check=False)
            await cli.run("rm", "--force", container, check=False)
        if provisioned:
            await boundary.cleanup(cli)
    for container in (subject, verifier, proxy):
        absent = await cli.run(
            "ps", "--all", "--quiet", "--filter", f"name=^/{container}$", check=False
        )
        assert not absent.stdout.strip()
    absent_network = await cli.run("network", "inspect", network, check=False)
    assert absent_network.returncode != 0
