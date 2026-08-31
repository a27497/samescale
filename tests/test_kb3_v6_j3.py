from __future__ import annotations

import hashlib
import json
from pathlib import Path

from harnesslab.contracts.common import Protocol
from harnesslab.judgelab.models import JudgeMode, digest
from harnesslab.judgelab.output import parse_judge_output
from harnesslab.judgelab.prompt import build_provider_request
from harnesslab.model_lane.providers import OpenAICompatibleChatAdapter
from harnesslab.release.judge_j3 import (
    J3_APPLICATION_RETRY_COUNT,
    J3_BASE_URL,
    J3_CALLS,
    J3_MODEL,
    J3_PLAN_DIGEST,
    J3_REASONING_EFFORT,
    J3_REPEAT_COUNT,
    J3_ROUTE_CANARY_DIGEST,
    J3_SAFE_PARALLELISM,
    J3_SCIENTIFIC_ROUTE_IDENTITY,
    build_j3_plan,
    build_j3_route_canary_identity,
    configured_j3_profile,
    j3_route_canary_digest,
)

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "release"
J2_RESULT = RELEASE / "core-real-judge-v6-j2-result.json"
J2_CANARY = RELEASE / "core-real-judge-v6-j2-route-canary.json"
J3_PLAN = RELEASE / "core-real-judge-v6-j3-plan.json"
J3_CANARY = RELEASE / "core-real-judge-v6-j3-route-canary.json"


def test_j2_is_frozen_as_route_unavailable_not_judge_failure() -> None:
    result = json.loads(J2_RESULT.read_text())
    assert result["state"] == result["final_route_state"] == ("ROUTE_UNAVAILABLE_PRE_INFERENCE")
    historical = result["historical_route_canary"]
    assert historical == {
        "route_canary_digest": (
            "sha256:2577d4458734ce07a3e45b60274b045390d69b77967344cd2dd866eb0010af9c"
        ),
        "requested_model": "anthropic/claude-opus-5",
        "route": "VERCEL_AI_GATEWAY_PINNED_ANTHROPIC",
        "application_provider_calls": 1,
        "application_retry_count": 0,
        "http_status": 403,
        "failure_stage": "PRE_INFERENCE",
        "observed_model": "NOT_REPORTED",
        "usable_model_output": False,
        "qualification_evidence": False,
        "historical_attempt_authorized": True,
        "retest_authorized": False,
    }
    assert result["qualification"] == {
        "status": "NOT_EVALUATED_ROUTE_UNAVAILABLE",
        "judge_failure_classification": False,
        "j2_qualification_calls": 0,
        "matrix_calls": 0,
    }
    assert result["operator_side_diagnosis"] == {
        "credential_check_endpoint": "/v1/credits",
        "credential_authentication": "SUCCEEDED",
        "credit_balance": 0,
        "interpretation": "ROUTE_FAILURE_IS_NOT_CLAUDE_CAPABILITY_EVIDENCE",
    }
    assert set(result["freeze_activity"].values()) == {0}
    assert hashlib.sha256(J2_CANARY.read_bytes()).hexdigest() == (
        "a1cc3231faef3183ef193b166ced3c8ac9c592773e1fc1fab9b5f35565124083"
    )


def test_j3_profile_and_qualification_plan_are_exact_and_keyless() -> None:
    profile = configured_j3_profile()
    plan, suite, _definitions = build_j3_plan(ROOT)
    frozen = json.loads(J3_PLAN.read_text())

    assert profile.requested_model == J3_MODEL == "grok-4.6"
    assert profile.provider == "aiwanwu-relay"
    assert profile.base_url == J3_BASE_URL == "https://aiwanwu.cc/v1"
    assert profile.route == "/chat/completions"
    assert profile.protocol is Protocol.CHAT_COMPLETIONS
    assert profile.credential_reference == "HARNESSLAB_AIWANWU_API_KEY"
    assert profile.reasoning.effort == J3_REASONING_EFFORT == "high"
    assert profile.reasoning.max_output_tokens == 256
    assert profile.reasoning.temperature is None
    assert plan.plan_digest == J3_PLAN_DIGEST == frozen["plan_digest"]
    assert plan.judge_cells[0].profile_identity == frozen["judge_cell"]["profile_identity"]
    assert len(plan.slots) == J3_CALLS == 63
    assert plan.repeat_count == J3_REPEAT_COUNT == 3
    assert (
        suite.suite_digest
        == frozen["calibration"]["suite_digest"]
        == ("sha256:c2708196237eab94dac473581e3a06de2f7d0e2c50e8b55190b253e547fc43fb")
    )
    assert (
        digest(plan.qualification_policy)
        == frozen["calibration"]["qualification_policy_digest"]
        == "sha256:82b84e9f0e3330e9d2f3f9068e054d9041158ae3bd7bba38a0044530e8fe6170"
    )
    assert frozen["calibration"]["safe_parallelism"] == J3_SAFE_PARALLELISM == 1
    assert frozen["calibration"]["application_retry_count"] == (J3_APPLICATION_RETRY_COUNT) == 0
    assert frozen["state"] == "PREREGISTERED_NOT_AUTHORIZED_NOT_RUN"
    assert (
        frozen["judge_cell"]["scientific_route_identity"]
        == (J3_SCIENTIFIC_ROUTE_IDENTITY)
        == "GROK_4_6_VIA_AIWANWU_RELAY"
    )


def test_j3_payloads_bind_high_reasoning_and_existing_strict_mode_schemas() -> None:
    plan, suite, definitions = build_j3_plan(ROOT)
    cell = plan.judge_cells[0]
    cases = {case.case_id: case for case in suite.public.cases}
    adapter = OpenAICompatibleChatAdapter()
    seen_modes = set()

    for slot in plan.slots:
        if slot.case_mode in seen_modes:
            continue
        seen_modes.add(slot.case_mode)
        case = cases[slot.case_id]
        request = build_provider_request(
            definition=definitions[cell.id],
            case=case,
            slot=slot,
            profile=cell.model_profile,
        )
        payload = adapter._payload(request)
        assert payload["model"] == "grok-4.6"
        assert payload["reasoning_effort"] == "high"
        assert payload["max_tokens"] == 256
        assert payload["response_format"] == {
            "type": "json_schema",
            "json_schema": {
                "name": "judge_output",
                "strict": True,
                "schema": request.output_json_schema.value,
            },
        }
        schema = payload["response_format"]["json_schema"]["schema"]
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])
        assert schema["properties"]["schema_version"] == {"type": "integer", "const": 1}
        assert schema["properties"]["reason"]["maxLength"] == (
            definitions[cell.id].maximum_public_justification_length
        )
        for forbidden in (
            "temperature",
            "top_p",
            "frequency_penalty",
            "presence_penalty",
            "stop",
        ):
            assert forbidden not in payload

        if slot.case_mode is JudgeMode.LABEL:
            output = json.dumps(
                {"schema_version": 1, "label": case.allowed_labels[0], "reason": "ok"},
                separators=(",", ":"),
            )
        elif slot.case_mode is JudgeMode.SCORE:
            output = json.dumps(
                {
                    "schema_version": 1,
                    "score": case.score_min,
                    "abstain": False,
                    "reason": "ok",
                },
                separators=(",", ":"),
            )
        else:
            output = '{"schema_version":1,"preference":"TIE","reason":"ok"}'
        assert parse_judge_output(output, case, definitions[cell.id]).schema_version == 1

    assert seen_modes == set(JudgeMode)
    parser_digest = hashlib.sha256(
        (ROOT / "src/harnesslab/judgelab/output.py").read_bytes()
    ).hexdigest()
    assert parser_digest == ("e23503f81e237c2de4a9859916091b36b4e4ec08d028b5bfd8e0167f9028c49b")


def test_j3_route_canary_is_one_call_separate_and_not_authorized() -> None:
    plan, suite, definitions = build_j3_plan(ROOT)
    identity = build_j3_route_canary_identity(plan, suite, definitions)
    frozen = json.loads(J3_CANARY.read_text())

    assert (
        j3_route_canary_digest(plan, suite, definitions)
        == (J3_ROUTE_CANARY_DIGEST)
        == frozen["route_canary_digest"]
    )
    assert identity["call_count"] == frozen["call_count"] == 1
    assert identity["application_retry_count"] == frozen["application_retry_count"] == 0
    assert identity["selected_mode"] == frozen["selected_request"]["mode"] == "LABEL"
    assert identity["selected_slot_id"] == frozen["selected_request"]["slot_id"]
    assert identity["selected_case_id"] == frozen["selected_request"]["case_id"]
    assert (
        identity["request_identity_digest"] == frozen["selected_request"]["request_identity_digest"]
    )
    assert identity["qualification_evidence_eligible"] is False
    assert identity["qualification_evidence_reuse_prohibited"] is True
    assert frozen["state"] == "NOT_AUTHORIZED_NOT_RUN"
    assert frozen["qualification_evidence"] == {"eligible": False, "reuse_prohibited": True}
    assert frozen["future_evidence_requirements"] == [
        "execution_timestamp",
        "provider_request_or_response_id",
        "requested_model",
        "observed_model",
        "input_tokens",
        "output_tokens",
        "reasoning_tokens_if_exposed",
        "total_tokens",
        "latency",
    ]


def test_j3_relay_price_matrix_and_zero_call_controls_are_frozen() -> None:
    frozen = json.loads(J3_PLAN.read_text())
    assert frozen["relay_price_state"] == "PENDING_EMPIRICAL_SUCCESSFUL_CALL_RECORD"
    assert frozen["qualification_spend_budget"] == "NOT_YET_FROZEN"
    assert frozen["billing_policy"] == {
        "official_xai_direct_pricing_used": False,
        "relay_cost_estimate": "NOT_INVENTED",
        "future_excel_parsing_in_scope": False,
    }
    assert frozen["route_provenance"]["classification"] == "THIRD_PARTY_RELAY"
    assert frozen["route_provenance"]["xai_direct"] is False
    assert frozen["route_provenance"]["official_xai_endpoint"] is False
    matrix = frozen["formal_matrix"]
    assert matrix == {
        "plan_digest": ("sha256:c18afc7b003a379f3456b23649e6d161da55e4fb5a34b4702dffbff35fb3604a"),
        "schedule_digest": (
            "sha256:f3ac0384cddafd4b4dd7b811f66a0e117cdc7e68b758cd111d5e6a4d6726dd2a"
        ),
        "profile_c": "UNCHANGED",
        "j3_bound_into_matrix": False,
        "authorization_state": "NOT_AUTHORIZED",
    }
    assert frozen["authorization"] == {
        "spend_authorized": False,
        "route_canary_authorized": False,
        "j3_qualification_authorized": False,
        "matrix_authorized": False,
        "real_provider_calls": 0,
        "real_judge_calls": 0,
        "real_matrix_calls": 0,
    }
    assert (
        hashlib.sha256((RELEASE / "core-real-matrix-v6-control.json").read_bytes()).hexdigest()
        == "9061656741e62d6683cb231a7d26c05d26c934f00f4c76a4dae3a8a2e4851e50"
    )
    assert (
        hashlib.sha256(
            (RELEASE / "core-real-matrix-v6-throughput-r2.json").read_bytes()
        ).hexdigest()
        == "2a4309a5f06f490898fc42c7ff402cbdd7d38d743321c2c799ee82b66c46d8cc"
    )
