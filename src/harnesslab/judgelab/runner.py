from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from harnesslab.judgelab.models import (
    JudgeDefinition,
    JudgeEvaluationSlot,
    JudgeEvidence,
    JudgeMode,
    JudgeOutputFailureKind,
    JudgeRunOutcome,
    LabelJudgment,
    PairwiseJudgment,
    PublicCase,
    ScoreJudgment,
    digest,
)
from harnesslab.judgelab.output import JudgeOutputError, parse_judge_output
from harnesslab.judgelab.prompt import build_provider_request, judge_request_identity
from harnesslab.model_lane.models import (
    ProviderAdapter,
    ProviderError,
    ProviderInvocationError,
    ProviderUsage,
)


class JudgeArtifactError(RuntimeError):
    """Immutable JudgeEvidence is missing, changed, or bound to another slot."""


@dataclass(frozen=True)
class JudgeRunResult:
    artifact_path: Path | None
    artifact_digest: str | None
    evidence: JudgeEvidence


def _sha256_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def canonical_preference(evidence: JudgeEvidence) -> str | None:
    if evidence.parsed_judgment is None or evidence.case_mode is not JudgeMode.PAIRWISE:
        return None
    preference = str(evidence.parsed_judgment["preference"])
    if preference in {"TIE", "UNKNOWN"}:
        return preference
    if evidence.order_variant.value == "ORIGINAL":
        return "A" if preference == "LEFT" else "B"
    return "B" if preference == "LEFT" else "A"


class JudgeRunner:
    def __init__(self, artifact_root: Path) -> None:
        self.artifact_root = artifact_root

    async def run(
        self,
        *,
        slot: JudgeEvaluationSlot,
        case: PublicCase,
        suite_id: str,
        suite_version: str,
        suite_digest: str,
        definition: JudgeDefinition,
        profile_identity: str,
        profile: object,
        adapter: ProviderAdapter,
    ) -> JudgeRunResult:
        request = build_provider_request(
            definition=definition, case=case, slot=slot, profile=profile
        )
        if case.mode not in definition.supported_modes:
            raise ValueError("JudgeDefinition does not support the calibration case mode")
        prompt_hash = digest(judge_request_identity(request))
        provider_result = None
        provider_error = None
        parsed = None
        judge_output_failure_kind: JudgeOutputFailureKind | None = None
        outcome = JudgeRunOutcome.JUDGED
        try:
            provider_result = await adapter.invoke(request)
            if provider_result.refused:
                outcome = JudgeRunOutcome.ABSTAINED
            else:
                try:
                    judgment = parse_judge_output(
                        provider_result.public_output_text, case, definition
                    )
                except JudgeOutputError as exc:
                    outcome = JudgeRunOutcome.JUDGE_OUTPUT_ERROR
                    judge_output_failure_kind = exc.kind
                else:
                    parsed = judgment.model_dump(mode="json")
                    if (
                        (isinstance(judgment, LabelJudgment) and judgment.label == "UNKNOWN")
                        or (isinstance(judgment, ScoreJudgment) and judgment.abstain)
                        or (
                            isinstance(judgment, PairwiseJudgment)
                            and judgment.preference == "UNKNOWN"
                        )
                    ):
                        outcome = JudgeRunOutcome.ABSTAINED
        except ProviderInvocationError as exc:
            outcome = JudgeRunOutcome.PROVIDER_ERROR
            provider_error = ProviderError(
                category=exc.category,
                timeout_phase=exc.timeout_phase,
                status_code=exc.status_code,
                request_id=exc.request_id,
                response_status=exc.response_status,
                latency_ms=exc.latency_ms,
            )
        model_profile = request.profile
        evidence = JudgeEvidence(
            evaluation_id=f"eval-{slot.slot_id.removeprefix('sha256:')}",
            calibration_id=slot.calibration_id,
            judge_cell_id=slot.judge_cell_id,
            case_id=slot.case_id,
            case_mode=slot.case_mode,
            case_public_digest=slot.case_public_digest,
            suite_id=suite_id,
            suite_version=suite_version,
            suite_digest=suite_digest,
            definition_id=definition.definition_id,
            definition_version=definition.version,
            definition_digest=definition.definition_digest,
            model_profile_identity=profile_identity,
            requested_judge_model=model_profile.requested_model,
            observed_judge_model=(provider_result.observed_model if provider_result else None),
            provider=model_profile.provider,
            endpoint=(
                f"{model_profile.base_url}{model_profile.route}"
                if model_profile.base_url is not None
                else model_profile.provider_route_identity
            ),
            protocol=model_profile.protocol.value,
            prompt_hash=prompt_hash,
            order_variant=slot.order_variant,
            logical_repeat_index=slot.repeat_index,
            provider_request_id=(
                provider_result.request_id
                if provider_result
                else provider_error.request_id
                if provider_error
                else None
            ),
            provider_usage=(provider_result.usage if provider_result else ProviderUsage()),
            latency_ms=(
                provider_result.latency_ms
                if provider_result
                else provider_error.latency_ms
                if provider_error
                else None
            ),
            public_response_digest=(
                _sha256_text(provider_result.public_output_text) if provider_result else None
            ),
            parsed_judgment=parsed,
            outcome=outcome,
            judge_output_failure_kind=judge_output_failure_kind,
            provider_failure=(provider_error.category if provider_error else None),
            provider_error=provider_error,
        )
        content_digest = _sha256_text(evidence.canonical_json(include_content_digest=False))
        evidence = evidence.model_copy(update={"evidence_content_digest": content_digest})
        path = (
            self.artifact_root
            / slot.calibration_id
            / slot.judge_cell_id
            / f"{slot.slot_order:05d}-{slot.slot_id.removeprefix('sha256:')}.json"
        )
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                "w", encoding="utf-8", dir=path.parent, delete=False
            ) as handle:
                handle.write(evidence.canonical_json())
                handle.write("\n")
                temporary = Path(handle.name)
            os.replace(temporary, path)
        except OSError:
            failed = evidence.model_copy(
                update={"outcome": JudgeRunOutcome.ARTIFACT_ERROR, "evidence_content_digest": None}
            )
            return JudgeRunResult(None, None, failed)
        return JudgeRunResult(path, _sha256_bytes(path.read_bytes()), evidence)


def load_and_verify_evidence(
    path: Path,
    *,
    expected_slot: JudgeEvaluationSlot,
    suite_digest: str,
    definition_digest: str,
    profile_identity: str,
    expected_artifact_digest: str,
) -> JudgeEvidence:
    try:
        file_bytes = path.read_bytes()
    except OSError as exc:
        raise JudgeArtifactError("JudgeEvidence is unreadable") from exc
    if _sha256_bytes(file_bytes) != expected_artifact_digest:
        raise JudgeArtifactError("JudgeEvidence artifact digest mismatch")
    try:
        evidence = JudgeEvidence.model_validate_json(file_bytes)
    except (UnicodeDecodeError, ValueError) as exc:
        raise JudgeArtifactError("JudgeEvidence is unreadable") from exc
    content_digest = _sha256_text(evidence.canonical_json(include_content_digest=False))
    if content_digest != evidence.evidence_content_digest:
        raise JudgeArtifactError("JudgeEvidence content digest mismatch")
    expected = {
        "evaluation_id": f"eval-{expected_slot.slot_id.removeprefix('sha256:')}",
        "calibration_id": expected_slot.calibration_id,
        "judge_cell_id": expected_slot.judge_cell_id,
        "case_id": expected_slot.case_id,
        "case_mode": expected_slot.case_mode,
        "case_public_digest": expected_slot.case_public_digest,
        "order_variant": expected_slot.order_variant,
        "logical_repeat_index": expected_slot.repeat_index,
        "suite_digest": suite_digest,
        "definition_digest": definition_digest,
        "model_profile_identity": profile_identity,
    }
    mismatches = [name for name, value in expected.items() if getattr(evidence, name) != value]
    if mismatches:
        raise JudgeArtifactError(f"JudgeEvidence identity mismatch: {','.join(mismatches)}")
    return evidence
