from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from harnesslab.contracts.common import Protocol
from harnesslab.contracts.provider import ThinkingMode, ThinkingTransport
from harnesslab.judgelab.models import JudgeMode, digest
from harnesslab.judgelab.plan import load_calibration_spec
from harnesslab.judgelab.prompt import build_provider_request
from harnesslab.model_lane.providers import AnthropicMessagesAdapter
from harnesslab.release.judge import (
    REAL_JUDGE_CALIBRATION_ID,
    REAL_JUDGE_CALLS,
    REAL_JUDGE_CELL_ID,
    REAL_JUDGE_PLAN_DIGEST,
    REAL_JUDGE_PREDECESSOR_PLAN_DIGEST,
    REAL_JUDGE_SAFE_PARALLELISM,
    build_real_judge_plan,
)

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "release"
SUITE_ROOT = ROOT / "judge_suites/core-calibration/1.0.0"


def test_r1_scientific_closeout_freezes_only_supplied_immutable_facts() -> None:
    closeout = json.loads((RELEASE / "kb3-v6-canary-r1-closeout.json").read_text())
    assert closeout["canary_plan_digest"] == (
        "sha256:e276417d78203008b4c6412c7bc62256cc4367af5adf56427b4d86df2aadab3a"
    )
    assert closeout["execution_closeout_digest"] == (
        "sha256:e863e4106032eac7181d2c4ce241d4017c3dd6d39540b232009c9c3d8edc8aa9"
    )
    assert [item["status"] for item in closeout["calls"]] == [
        "VERIFIED_PASS",
        "VERIFIED_PASS",
        "JUDGE_OUTPUT_ERROR",
    ]
    assert [item["call_evidence_digest"] for item in closeout["calls"]] == [
        "sha256:2c45fc430dfd5dee95e497e14d7598cae9d297fcbadd8f2bf3e8f07e58f639f6",
        "sha256:3841840169951605f6a45d3bbfc97406e4be636f1418c1fcc208612f2210dd7a",
        "sha256:4912d472e48e2febc3a089caba2beddb05b400442707bddc3194edda0a3cc614",
    ]
    judge = closeout["calls"][2]
    assert judge["observed_model"] == "glm-5.2"
    assert judge["judge_output_failure_kind"] == "STRICT_SCHEMA_VALIDATION"
    assert judge["provider_failure"] is None
    assert closeout["scientific_classification"] == {
        "subject_real_canary_paths_pass": True,
        "glm_judge_qualified": False,
        "successful_subject_calls_must_not_be_rerun": True,
        "r1_evidence_reusable_as_j1_judge_evidence": False,
    }
    assert closeout["bounds_observed"] == {
        "retries": 0,
        "semantic_retries": 0,
        "substitutions": 0,
        "matrix_calls": 0,
    }


def test_v6_j1_plan_is_exact_keyless_and_frozen() -> None:
    plan, suite, definitions = build_real_judge_plan(ROOT)
    cell = plan.judge_cells[0]
    profile = cell.model_profile
    base_spec = load_calibration_spec(SUITE_ROOT / "calibration.yaml")
    frozen = json.loads((RELEASE / "core-real-judge-v6-j1-plan.json").read_text())

    assert plan.calibration_id == REAL_JUDGE_CALIBRATION_ID == "core-real-judge-v6-j1"
    assert cell.id == REAL_JUDGE_CELL_ID == "judge-glm52-alibaba-bailian-messages"
    assert plan.plan_digest == REAL_JUDGE_PLAN_DIGEST == frozen["plan_digest"]
    assert (
        frozen["predecessor_plan_digest"]
        == REAL_JUDGE_PREDECESSOR_PLAN_DIGEST
        == ("sha256:0cf4222bc7a9fc896029a406eb81605c83c63ecacd681567a487189d1d6ecd06")
    )
    assert frozen["predecessor_plan_state"] == "SUPERSEDED_MUST_NOT_BE_AUTHORIZED"
    assert len(plan.judge_cells) == 1
    assert len(plan.slots) == REAL_JUDGE_CALLS == 63
    assert plan.repeat_count == 3
    assert profile.requested_model == "glm-5.2"
    assert profile.provider == "alibaba-bailian"
    assert profile.protocol is Protocol.MESSAGES
    assert profile.base_url_reference == "HARNESSLAB_ALIBABA_BAILIAN_ANTHROPIC_BASE_URL"
    assert profile.route == "/v1/messages"
    assert profile.credential_reference == "HARNESSLAB_ALIBABA_BAILIAN_API_KEY"
    assert profile.reasoning.max_output_tokens == 256
    assert profile.reasoning.effort is None
    assert profile.reasoning.temperature is None
    assert profile.thinking_mode is ThinkingMode.DISABLED
    assert profile.thinking_transport is ThinkingTransport.ANTHROPIC_MESSAGES_THINKING_OBJECT
    assert (
        cell.profile_identity
        == frozen["judge_cell"]["profile_identity"]
        == ("sha256:1b8233c8b413f9c1fc2f84c051cf2baf0a5467a5c8c44c2a1889787fbcaae020")
    )
    assert frozen["treatment"]["j1_thinking_mode"] == "EXPLICITLY_DISABLED"
    assert frozen["judge_cell"]["thinking_mode"] == "EXPLICITLY_DISABLED"
    assert cell.runner_contract == "provider-adapter-v1"
    assert suite.suite_digest == frozen["calibration"]["suite_digest"]
    assert definitions[cell.id].definition_digest == frozen["calibration"]["definition_digest"]
    assert plan.qualification_policy == base_spec.qualification_policy
    assert digest(plan.qualification_policy) == frozen["calibration"]["qualification_policy_digest"]
    assert frozen["calibration"]["qualification_policy_status"] == "UNCHANGED"
    assert frozen["calibration"]["safe_parallelism"] == REAL_JUDGE_SAFE_PARALLELISM == 1


def test_every_j1_slot_has_mode_specific_strict_schema_without_evidence_reuse() -> None:
    plan, suite, definitions = build_real_judge_plan(ROOT)
    cell = plan.judge_cells[0]
    cases = {case.case_id: case for case in suite.public.cases}
    definition = definitions[cell.id]
    for slot in plan.slots:
        request = build_provider_request(
            definition=definition,
            case=cases[slot.case_id],
            slot=slot,
            profile=cell.model_profile,
        )
        assert request.output_json_schema is not None
        schema = cast(dict[str, Any], request.output_json_schema.value)
        assert schema["type"] == "object"
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])

    frozen = json.loads((RELEASE / "core-real-judge-v6-j1-plan.json").read_text())
    authority = frozen["evidence_and_authorization"]
    assert authority["r1_subject_evidence_reused_as_judge_evidence"] is False
    assert authority["spend_authorized"] is False
    assert authority["judge_execution_authorized"] is False
    assert authority["matrix_execution_authorized"] is False
    assert authority["real_provider_calls"] == authority["real_judge_calls"] == 0


def test_j1_label_score_and_pairwise_payloads_disable_thinking_and_keep_schema() -> None:
    plan, suite, definitions = build_real_judge_plan(ROOT)
    cell = plan.judge_cells[0]
    cases = {case.case_id: case for case in suite.public.cases}
    definition = definitions[cell.id]
    adapter = AnthropicMessagesAdapter()
    seen_modes = set()
    for slot in plan.slots:
        if slot.case_mode in seen_modes:
            continue
        seen_modes.add(slot.case_mode)
        request = build_provider_request(
            definition=definition,
            case=cases[slot.case_id],
            slot=slot,
            profile=cell.model_profile,
        )
        assert request.output_json_schema is not None
        payload = adapter._payload(request)
        assert payload["thinking"] == {"type": "disabled"}
        assert payload["output_config"] == {
            "format": {
                "type": "json_schema",
                "schema": request.output_json_schema.value,
            }
        }
        assert "effort" not in payload["output_config"]
        assert "temperature" not in payload
    assert seen_modes == set(JudgeMode)


def test_j1_budget_and_formal_matrix_bindings_are_unchanged() -> None:
    frozen = json.loads((RELEASE / "core-real-judge-v6-j1-plan.json").read_text())
    matrix = json.loads((RELEASE / "core-real-matrix-v6-control.json").read_text())
    budget = frozen["planning_budget"]
    worst_case = (
        Decimal(budget["input_tokens_per_call_ceiling"])
        * Decimal(budget["call_count"])
        * Decimal(budget["input_cny_per_million_tokens"])
        + Decimal(budget["output_tokens_per_call_ceiling"])
        * Decimal(budget["call_count"])
        * Decimal(budget["output_cny_per_million_tokens"])
    ) / Decimal(1_000_000)
    assert worst_case == Decimal("4.580352")
    assert budget["worst_case_cny"] == "4.580352"
    assert budget["classification"] == "PLANNING_WORST_CASE_NOT_ACTUAL_BILL"
    assert (
        frozen["formal_matrix"]["plan_digest"]
        == matrix["plan_digest"]
        == ("sha256:c18afc7b003a379f3456b23649e6d161da55e4fb5a34b4702dffbff35fb3604a")
    )
    assert (
        frozen["formal_matrix"]["schedule_digest"]
        == matrix["schedule_digest"]
        == "sha256:f3ac0384cddafd4b4dd7b811f66a0e117cdc7e68b758cd111d5e6a4d6726dd2a"
    )
    assert frozen["formal_matrix"]["profile_c"] == "UNCHANGED"
    assert frozen["formal_matrix"]["subject_cells"] == "UNCHANGED"
    assert frozen["formal_matrix"]["j1_bound_into_matrix"] is False
    assert frozen["formal_matrix"]["authorization_state"] == "NOT_AUTHORIZED"
