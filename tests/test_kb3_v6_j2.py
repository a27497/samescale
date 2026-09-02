from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest

from harnesslab.contracts.common import Protocol
from harnesslab.contracts.model import ModelProfile
from harnesslab.contracts.provider import ThinkingMode, ThinkingTransport
from harnesslab.judgelab.models import JudgeMode, digest
from harnesslab.judgelab.prompt import build_provider_request
from harnesslab.model_lane.providers import AnthropicMessagesAdapter
from harnesslab.release.judge import build_real_judge_plan
from harnesslab.release.judge_j2 import (
    J2_APPLICATION_RETRY_COUNT,
    J2_CALLS,
    J2_GATEWAY_BASE_URL,
    J2_GATEWAY_PROVIDER_ONLY,
    J2_MODEL,
    J2_PLAN_DIGEST,
    J2_REPEAT_COUNT,
    J2_ROUTE_CANARY_DIGEST,
    J2_SAFE_PARALLELISM,
    J2_SCIENTIFIC_ROUTE_IDENTITY,
    build_j2_plan,
    build_j2_route_canary_identity,
    configured_j2_profile,
    j2_route_canary_digest,
)

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "release"
J1_RESULT = RELEASE / "core-real-judge-v6-j1-result.json"
J2_PLAN = RELEASE / "core-real-judge-v6-j2-plan.json"
J2_CANARY = RELEASE / "core-real-judge-v6-j2-route-canary.json"


def test_j1_result_is_frozen_not_qualified_without_retune_or_rerun() -> None:
    result = json.loads(J1_RESULT.read_text())
    assert result["state"] == "NOT_QUALIFIED_FOR_CORE_SUITE"
    assert result["qualification_status"] == "NOT_QUALIFIED"
    assert result["plan_digest"] == (
        "sha256:542e114402b1faff63baf4c993a4a6d1d265df5f0c953e62a57345e4dcf29f86"
    )
    assert result["report_digest"] == (
        "sha256:78e4c26a4bb2820ead8d1b5350de933ed7c9172e7ec13a1b434b2326e55f267a"
    )
    assert result["scientific_disposition"] == {
        "core_suite_state": "NOT_QUALIFIED_FOR_CORE_SUITE",
        "glm_retuning_authorized": False,
        "glm_rerun_authorized": False,
        "j1_evidence_reusable_for_j2": False,
    }
    assert result["run_counts"] == {
        "planned": 63,
        "judged": 52,
        "abstained": 10,
        "judge_output_errors": 0,
        "provider_failures": 1,
        "artifact_errors": 0,
    }
    assert set(result["freeze_activity"].values()) == {0}


def test_j2_plan_is_exact_keyless_and_does_not_change_j1() -> None:
    j1, _, _ = build_real_judge_plan(ROOT)
    plan, suite, _definitions = build_j2_plan(ROOT)
    frozen = json.loads(J2_PLAN.read_text())
    cell = plan.judge_cells[0]
    profile = cell.model_profile

    assert j1.plan_digest == (
        "sha256:542e114402b1faff63baf4c993a4a6d1d265df5f0c953e62a57345e4dcf29f86"
    )
    assert plan.plan_digest == J2_PLAN_DIGEST == frozen["plan_digest"]
    assert (
        cell.profile_identity
        == frozen["judge_cell"]["profile_identity"]
        == ("sha256:2906c91977b0f3a28c783c3cb888ec308309c46a7b036885bc62d8222b5ed204")
    )
    assert profile.requested_model == J2_MODEL == "anthropic/claude-opus-5"
    assert profile.provider == "vercel-ai-gateway"
    assert profile.base_url == J2_GATEWAY_BASE_URL == "https://ai-gateway.vercel.sh"
    assert profile.protocol is Protocol.MESSAGES
    assert profile.route == "/v1/messages"
    assert profile.credential_reference == "AI_GATEWAY_API_KEY"
    assert profile.vercel_gateway_route_identity == J2_SCIENTIFIC_ROUTE_IDENTITY
    assert profile.vercel_gateway_provider_only == J2_GATEWAY_PROVIDER_ONLY == ("anthropic",)
    assert profile.thinking_mode is ThinkingMode.DISABLED
    assert profile.thinking_transport is ThinkingTransport.ANTHROPIC_MESSAGES_THINKING_OBJECT
    assert profile.reasoning.effort is None
    assert profile.reasoning.temperature is None
    assert profile.reasoning.max_output_tokens == 256
    assert len(plan.judge_cells) == 1
    assert len(plan.slots) == J2_CALLS == 63
    assert plan.repeat_count == J2_REPEAT_COUNT == 3
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
    assert frozen["calibration"]["safe_parallelism"] == J2_SAFE_PARALLELISM == 1
    assert frozen["calibration"]["application_retry_count"] == J2_APPLICATION_RETRY_COUNT == 0


def test_j2_payloads_pin_anthropic_disable_thinking_and_keep_strict_schemas() -> None:
    plan, suite, definitions = build_j2_plan(ROOT)
    cell = plan.judge_cells[0]
    cases = {case.case_id: case for case in suite.public.cases}
    adapter = AnthropicMessagesAdapter()
    seen_modes = set()
    for slot in plan.slots:
        if slot.case_mode in seen_modes:
            continue
        seen_modes.add(slot.case_mode)
        request = build_provider_request(
            definition=definitions[cell.id],
            case=cases[slot.case_id],
            slot=slot,
            profile=cell.model_profile,
        )
        assert request.output_json_schema is not None
        payload = adapter._payload(request)
        assert payload["model"] == "anthropic/claude-opus-5"
        assert payload["max_tokens"] == 256
        assert payload["thinking"] == {"type": "disabled"}
        assert payload["providerOptions"] == {"gateway": {"only": ["anthropic"]}}
        assert payload["output_config"] == {
            "format": {
                "type": "json_schema",
                "schema": request.output_json_schema.value,
            }
        }
        schema = cast(dict[str, Any], payload["output_config"]["format"]["schema"])
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])
        assert "temperature" not in payload
        assert "effort" not in payload["output_config"]
        assert "models" not in payload["providerOptions"]["gateway"]
        assert "order" not in payload["providerOptions"]["gateway"]
        assert "sort" not in payload["providerOptions"]["gateway"]
        assert "speed" not in payload["providerOptions"]
    assert seen_modes == set(JudgeMode)


def test_j2_profile_rejects_any_provider_allowlist_expansion() -> None:
    raw = configured_j2_profile().model_dump(mode="json")
    raw["vercel_gateway_provider_only"] = ["anthropic", "bedrock"]
    with pytest.raises(ValueError, match="pinned only to Anthropic"):
        ModelProfile.model_validate(raw)


def test_j2_route_canary_is_one_call_separate_and_not_authorized() -> None:
    plan, suite, definitions = build_j2_plan(ROOT)
    identity = cast(dict[str, Any], build_j2_route_canary_identity(plan, suite, definitions))
    frozen = json.loads(J2_CANARY.read_text())

    assert (
        j2_route_canary_digest(plan, suite, definitions)
        == J2_ROUTE_CANARY_DIGEST
        == (frozen["route_canary_digest"])
    )
    assert identity["call_count"] == frozen["call_count"] == 1
    assert identity["selected_slot_id"] == frozen["selected_request"]["slot_id"]
    assert identity["selected_case_id"] == frozen["selected_request"]["case_id"]
    assert identity["selected_mode"] == frozen["selected_request"]["mode"] == "LABEL"
    assert (
        identity["request_identity_digest"] == frozen["selected_request"]["request_identity_digest"]
    )
    assert identity["provider_only"] == ["anthropic"]
    assert identity["qualification_evidence_eligible"] is False
    assert identity["qualification_evidence_reuse_prohibited"] is True
    requirements = identity["routing_evidence_requirements"]
    assert requirements["final_provider"] == "anthropic"
    assert requirements["cross_provider_fallback"] == "PROHIBITED"
    assert requirements["model_fallback"] == "PROHIBITED"
    assert requirements["observable_upstream_attempt_rule"] == (
        "EXACTLY_ONE_SUCCESSFUL_ANTHROPIC_ATTEMPT"
    )
    assert requirements["unobservable_upstream_attempt_rule"] == (
        "REPORT_NOT_OBSERVABLE_DO_NOT_FABRICATE"
    )
    assert frozen["routing_evidence_requirements"] == requirements
    assert frozen["state"] == "NOT_AUTHORIZED_NOT_RUN"
    assert set(frozen["purpose"].values()) == {"MUST_VERIFY"}
    assert frozen["authorization"] == {
        "spend_authorized": False,
        "route_canary_authorized": False,
        "j2_qualification_authorized": False,
        "matrix_authorized": False,
        "real_calls": 0,
    }


def test_j2_budget_key_handling_and_matrix_are_frozen_without_calls() -> None:
    frozen = json.loads(J2_PLAN.read_text())
    budget = frozen["planning_budget"]
    worst_case = (
        Decimal(budget["input_tokens_per_call_ceiling"])
        * Decimal(budget["call_count"])
        * Decimal(budget["input_usd_per_million_tokens"])
        + Decimal(budget["output_tokens_per_call_ceiling"])
        * Decimal(budget["call_count"])
        * Decimal(budget["output_usd_per_million_tokens"])
    ) / Decimal(1_000_000)
    assert worst_case == Decimal("2.983680")
    assert budget["worst_case_usd"] == "2.983680"
    assert budget["classification"] == "PLANNING_WORST_CASE_NOT_ACTUAL_BILL"
    assert budget["fast_mode"] is False
    assert frozen["vercel_free_credit"] == {
        "eligible_class": "UNPAID_USERS",
        "credit_usd": "5",
        "renewal_period_days": 30,
        "fact_only_not_spend_authorization": True,
        "source": "https://vercel.com/ai-gateway/models/claude-opus-5",
    }
    assert frozen["key_handling"] == {
        "tracked_secret_allowed": False,
        "private_config_required": True,
        "private_config_mode": "0600",
    }
    matrix = frozen["formal_matrix"]
    assert matrix["plan_digest"] == (
        "sha256:c18afc7b003a379f3456b23649e6d161da55e4fb5a34b4702dffbff35fb3604a"
    )
    assert matrix["schedule_digest"] == (
        "sha256:f3ac0384cddafd4b4dd7b811f66a0e117cdc7e68b758cd111d5e6a4d6726dd2a"
    )
    assert matrix["profile_c"] == "UNCHANGED"
    assert matrix["j2_bound_into_matrix"] is False
    assert matrix["authorization_state"] == "NOT_AUTHORIZED"
    assert frozen["authorization"] == {
        "spend_authorized": False,
        "route_canary_authorized": False,
        "j2_qualification_authorized": False,
        "matrix_authorized": False,
        "real_provider_calls": 0,
        "real_judge_calls": 0,
        "real_matrix_calls": 0,
    }
    assert hashlib.sha256(
        (RELEASE / "core-real-matrix-v6-control.json").read_bytes()
    ).hexdigest() == ("9061656741e62d6683cb231a7d26c05d26c934f00f4c76a4dae3a8a2e4851e50")
    assert (
        hashlib.sha256(
            (RELEASE / "core-real-matrix-v6-throughput-r2.json").read_bytes()
        ).hexdigest()
        == "2a4309a5f06f490898fc42c7ff402cbdd7d38d743321c2c799ee82b66c46d8cc"
    )
