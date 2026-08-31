from __future__ import annotations

from pathlib import Path

from harnesslab.contracts.common import Protocol
from harnesslab.contracts.model import ModelProfile, ReasoningProfile
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

J3_CALIBRATION_ID = "core-real-judge-v6-j3"
J3_CELL_ID = "judge-grok46-aiwanwu-relay-chat-completions"
J3_MODEL = "grok-4.6"
J3_BASE_URL = "https://aiwanwu.cc/v1"
J3_ROUTE = "/chat/completions"
J3_SCIENTIFIC_ROUTE_IDENTITY = "GROK_4_6_VIA_AIWANWU_RELAY"
J3_CREDENTIAL_REFERENCE = "HARNESSLAB_AIWANWU_API_KEY"
J3_REASONING_EFFORT = "high"
J3_CALLS = 63
J3_REPEAT_COUNT = 3
J3_SAFE_PARALLELISM = 1
J3_APPLICATION_RETRY_COUNT = 0
J3_PLAN_DIGEST = "sha256:3e8bc9249171e1fcc8675e31d9efdd208c8173d2fcd2a41d00d374dc95fb06c8"
J3_ROUTE_CANARY_ID = "core-real-judge-v6-j3-route-canary"
J3_ROUTE_CANARY_DIGEST = "sha256:5fd668f2705514217db87df11bd01ae6ab9ef1c8bba092df32fde63033ceca33"


class J3ControlPlaneError(SmokeControlPlaneError):
    """The frozen J3 relay candidate differs from its keyless preregistration."""


def configured_j3_profile() -> ModelProfile:
    """Build the secret-free Grok 4.6 profile for the named third-party relay."""

    return ModelProfile(
        requested_model=J3_MODEL,
        provider="aiwanwu-relay",
        base_url=J3_BASE_URL,
        route=J3_ROUTE,
        protocol=Protocol.CHAT_COMPLETIONS,
        reasoning=ReasoningProfile(effort=J3_REASONING_EFFORT, max_output_tokens=256),
        request_timeout_seconds=90,
        credential_reference=J3_CREDENTIAL_REFERENCE,
    )


def _construct_j3_plan(
    repository_root: Path,
) -> tuple[JudgeCalibrationPlan, JudgeSuite, dict[str, JudgeDefinition]]:
    profile = configured_j3_profile()
    suite_root = repository_root / "judge_suites/core-calibration/1.0.0"
    base_spec = load_calibration_spec(suite_root / "calibration.yaml")
    suite = resolve_suite(base_spec, repository_root)
    base_definitions = resolve_definitions(base_spec, repository_root)
    source_cell = base_spec.judge_cells[0]
    definition = base_definitions[source_cell.id]
    cell = JudgeCellSpec(
        id=J3_CELL_ID,
        definition_reference=source_cell.definition_reference,
        definition_digest=source_cell.definition_digest,
        model_profile=profile,
        profile_identity=digest(profile),
        runner_contract="provider-adapter-v1",
    )
    spec = base_spec.model_copy(
        update={
            "calibration_id": J3_CALIBRATION_ID,
            "name": "HarnessLab Core Grok 4.6 aiwanwu Relay Judge Qualification V6 J3",
            "judge_cells": (cell,),
        }
    )
    plan = build_calibration_plan(spec, suite, {cell.id: definition})
    return plan, suite, {cell.id: definition}


def build_j3_plan(
    repository_root: Path,
) -> tuple[JudgeCalibrationPlan, JudgeSuite, dict[str, JudgeDefinition]]:
    """Construct the frozen 63-slot J3 qualification plan without credentials or calls."""

    plan, suite, definitions = _construct_j3_plan(repository_root)
    if plan.repeat_count != J3_REPEAT_COUNT or len(plan.slots) != J3_CALLS:
        raise J3ControlPlaneError("J3 plan must contain exactly 63 slots over three repeats")
    if plan.plan_digest != J3_PLAN_DIGEST:
        raise J3ControlPlaneError("J3 qualification plan differs from the frozen digest")
    return plan, suite, definitions


def build_j3_route_canary_identity(
    plan: JudgeCalibrationPlan,
    suite: JudgeSuite,
    definitions: dict[str, JudgeDefinition],
) -> dict[str, object]:
    """Bind one LABEL request for future relay proof, never qualification evidence."""

    cell = plan.judge_cells[0]
    slot = next(item for item in plan.slots if item.case_mode.value == "LABEL")
    cases = {case.case_id: case for case in suite.public.cases}
    request = build_provider_request(
        definition=definitions[cell.id],
        case=cases[slot.case_id],
        slot=slot,
        profile=cell.model_profile,
    )
    return {
        "schema_version": 1,
        "route_canary_id": J3_ROUTE_CANARY_ID,
        "authorization_state": "NOT_AUTHORIZED_NOT_RUN",
        "call_count": 1,
        "application_retry_count": J3_APPLICATION_RETRY_COUNT,
        "qualification_plan_digest": plan.plan_digest,
        "profile_identity": cell.profile_identity,
        "selected_slot_id": slot.slot_id,
        "selected_case_id": slot.case_id,
        "selected_mode": slot.case_mode.value,
        "request_identity_digest": digest(judge_request_identity(request)),
        "scientific_route_identity": J3_SCIENTIFIC_ROUTE_IDENTITY,
        "requested_model": J3_MODEL,
        "reasoning_effort": J3_REASONING_EFFORT,
        "qualification_evidence_eligible": False,
        "qualification_evidence_reuse_prohibited": True,
    }


def j3_route_canary_digest(
    plan: JudgeCalibrationPlan,
    suite: JudgeSuite,
    definitions: dict[str, JudgeDefinition],
) -> str:
    value = digest(build_j3_route_canary_identity(plan, suite, definitions))
    if value != J3_ROUTE_CANARY_DIGEST:
        raise J3ControlPlaneError("J3 route-canary differs from the frozen digest")
    return value
