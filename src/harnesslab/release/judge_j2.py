from __future__ import annotations

from pathlib import Path

from harnesslab.contracts.common import Protocol
from harnesslab.contracts.model import ModelProfile, ReasoningProfile
from harnesslab.contracts.provider import ThinkingMode, ThinkingTransport
from harnesslab.judgelab.models import (
    JudgeCalibrationPlan,
    JudgeCellSpec,
    JudgeDefinition,
    JudgeSuite,
    digest,
)
from harnesslab.judgelab.plan import (
    build_calibration_plan,
    load_calibration_spec,
    resolve_definitions,
    resolve_suite,
)
from harnesslab.judgelab.prompt import build_provider_request, judge_request_identity
from harnesslab.release.smoke import SmokeControlPlaneError

J2_CALIBRATION_ID = "core-real-judge-v6-j2"
J2_CELL_ID = "judge-claude-opus5-vercel-gateway-anthropic-messages"
J2_MODEL = "anthropic/claude-opus-5"
J2_SCIENTIFIC_ROUTE_IDENTITY = "VERCEL_AI_GATEWAY_PINNED_ANTHROPIC"
J2_GATEWAY_BASE_URL = "https://ai-gateway.vercel.sh"
J2_GATEWAY_PROVIDER_ONLY = ("anthropic",)
J2_CREDENTIAL_REFERENCE = "AI_GATEWAY_API_KEY"
J2_CALLS = 63
J2_REPEAT_COUNT = 3
J2_SAFE_PARALLELISM = 1
J2_APPLICATION_RETRY_COUNT = 0
J2_PLAN_DIGEST = "sha256:51de0129138b7624d2a13bb8f047714aaeedf0a0154620dced0939aea3a267e7"
J2_ROUTE_CANARY_ID = "core-real-judge-v6-j2-route-canary"
J2_ROUTE_CANARY_DIGEST = "sha256:2577d4458734ce07a3e45b60274b045390d69b77967344cd2dd866eb0010af9c"


class J2ControlPlaneError(SmokeControlPlaneError):
    """The frozen J2 candidate differs from its keyless preregistration."""


def configured_j2_profile() -> ModelProfile:
    """Build the secret-free Opus 5 profile pinned to Vercel's Anthropic provider."""

    return ModelProfile(
        requested_model=J2_MODEL,
        provider="vercel-ai-gateway",
        base_url=J2_GATEWAY_BASE_URL,
        route="/v1/messages",
        protocol=Protocol.MESSAGES,
        reasoning=ReasoningProfile(max_output_tokens=256),
        thinking_mode=ThinkingMode.DISABLED,
        thinking_transport=ThinkingTransport.ANTHROPIC_MESSAGES_THINKING_OBJECT,
        vercel_gateway_route_identity=J2_SCIENTIFIC_ROUTE_IDENTITY,
        vercel_gateway_provider_only=J2_GATEWAY_PROVIDER_ONLY,
        request_timeout_seconds=90,
        credential_reference=J2_CREDENTIAL_REFERENCE,
    )


def build_j2_plan(
    repository_root: Path,
) -> tuple[JudgeCalibrationPlan, JudgeSuite, dict[str, JudgeDefinition]]:
    """Construct the frozen 63-slot J2 qualification plan without credentials or calls."""

    profile = configured_j2_profile()
    suite_root = repository_root / "judge_suites/core-calibration/1.0.0"
    base_spec = load_calibration_spec(suite_root / "calibration.yaml")
    suite = resolve_suite(base_spec, repository_root)
    base_definitions = resolve_definitions(base_spec, repository_root)
    source_cell = base_spec.judge_cells[0]
    definition = base_definitions[source_cell.id]
    cell = JudgeCellSpec(
        id=J2_CELL_ID,
        definition_reference=source_cell.definition_reference,
        definition_digest=source_cell.definition_digest,
        model_profile=profile,
        profile_identity=digest(profile),
        runner_contract="provider-adapter-v1",
    )
    spec = base_spec.model_copy(
        update={
            "calibration_id": J2_CALIBRATION_ID,
            "name": "HarnessLab Core Claude Opus 5 Judge Qualification V6 J2",
            "judge_cells": (cell,),
        }
    )
    plan = build_calibration_plan(spec, suite, {cell.id: definition})
    if plan.repeat_count != J2_REPEAT_COUNT or len(plan.slots) != J2_CALLS:
        raise J2ControlPlaneError("J2 plan must contain exactly 63 slots over three repeats")
    if plan.plan_digest != J2_PLAN_DIGEST:
        raise J2ControlPlaneError("J2 qualification plan differs from the frozen digest")
    return plan, suite, {cell.id: definition}


def build_j2_route_canary_identity(
    plan: JudgeCalibrationPlan,
    suite: JudgeSuite,
    definitions: dict[str, JudgeDefinition],
) -> dict[str, object]:
    """Bind one request for future routing proof; it is never qualification evidence."""

    cell = plan.judge_cells[0]
    slot = plan.slots[0]
    cases = {case.case_id: case for case in suite.public.cases}
    request = build_provider_request(
        definition=definitions[cell.id],
        case=cases[slot.case_id],
        slot=slot,
        profile=cell.model_profile,
    )
    return {
        "schema_version": 1,
        "route_canary_id": J2_ROUTE_CANARY_ID,
        "authorization_state": "NOT_AUTHORIZED_NOT_RUN",
        "call_count": 1,
        "application_retry_count": J2_APPLICATION_RETRY_COUNT,
        "qualification_plan_digest": plan.plan_digest,
        "profile_identity": cell.profile_identity,
        "selected_slot_id": slot.slot_id,
        "selected_case_id": slot.case_id,
        "selected_mode": slot.case_mode.value,
        "request_identity_digest": digest(judge_request_identity(request)),
        "scientific_route_identity": J2_SCIENTIFIC_ROUTE_IDENTITY,
        "provider_only": list(J2_GATEWAY_PROVIDER_ONLY),
        "qualification_evidence_eligible": False,
        "qualification_evidence_reuse_prohibited": True,
        "routing_evidence_requirements": {
            "final_provider": "anthropic",
            "cross_provider_fallback": "PROHIBITED",
            "model_fallback": "PROHIBITED",
            "inspect_available_vercel_routing_metadata": True,
            "observable_upstream_attempt_rule": "EXACTLY_ONE_SUCCESSFUL_ANTHROPIC_ATTEMPT",
            "unobservable_upstream_attempt_rule": "REPORT_NOT_OBSERVABLE_DO_NOT_FABRICATE",
        },
    }


def j2_route_canary_digest(
    plan: JudgeCalibrationPlan,
    suite: JudgeSuite,
    definitions: dict[str, JudgeDefinition],
) -> str:
    value = digest(build_j2_route_canary_identity(plan, suite, definitions))
    if value != J2_ROUTE_CANARY_DIGEST:
        raise J2ControlPlaneError("J2 route-canary differs from the frozen digest")
    return value
