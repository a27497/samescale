from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from harnesslab.judgelab.models import (
    JudgeDefinition,
    JudgeMode,
    JudgeOutputFailureKind,
    LabelJudgment,
    PairwiseJudgment,
    ParsedJudgment,
    PublicCase,
    ScoreJudgment,
)

MAX_JUDGE_OUTPUT_BYTES = 16_384
PRIVATE_FIELDS = {"reasoning", "analysis", "scratchpad", "thinking", "hidden_rationale"}


class JudgeOutputError(ValueError):
    """Public Judge output violated the strict mode-specific contract."""

    def __init__(self, kind: JudgeOutputFailureKind) -> None:
        super().__init__(kind.value)
        self.kind = kind


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise JudgeOutputError(JudgeOutputFailureKind.DUPLICATE_KEY)
        result[key] = value
    return result


def parse_judge_output(text: str, case: PublicCase, definition: JudgeDefinition) -> ParsedJudgment:
    try:
        encoded = text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise JudgeOutputError(JudgeOutputFailureKind.NON_UTF8) from exc
    if len(encoded) > MAX_JUDGE_OUTPUT_BYTES:
        raise JudgeOutputError(JudgeOutputFailureKind.TOO_LARGE)
    if text != text.strip() or text.startswith("```"):
        raise JudgeOutputError(JudgeOutputFailureKind.NOT_BARE_JSON)
    try:
        raw = json.loads(text, object_pairs_hook=_reject_duplicate_pairs)
    except (json.JSONDecodeError, RecursionError, UnicodeDecodeError) as exc:
        raise JudgeOutputError(JudgeOutputFailureKind.MALFORMED_JSON) from exc
    if not isinstance(raw, dict):
        raise JudgeOutputError(JudgeOutputFailureKind.NOT_JSON_OBJECT)
    if PRIVATE_FIELDS.intersection(raw):
        raise JudgeOutputError(JudgeOutputFailureKind.PRIVATE_FIELD_PRESENT)
    try:
        if case.mode is JudgeMode.LABEL:
            label_judgment = LabelJudgment.model_validate(raw)
            if label_judgment.label not in case.allowed_labels and not (
                definition.allow_abstention and label_judgment.label == "UNKNOWN"
            ):
                raise JudgeOutputError(JudgeOutputFailureKind.LABEL_NOT_ALLOWED)
            parsed: ParsedJudgment = label_judgment
        elif case.mode is JudgeMode.SCORE:
            score_judgment = ScoreJudgment.model_validate(raw)
            if score_judgment.abstain != (score_judgment.score is None):
                raise JudgeOutputError(JudgeOutputFailureKind.SCORE_INVARIANT)
            if score_judgment.score is not None and not (
                case.score_min <= score_judgment.score <= case.score_max  # type: ignore[operator]
            ):
                raise JudgeOutputError(JudgeOutputFailureKind.SCORE_OUT_OF_RANGE)
            if score_judgment.abstain and not definition.allow_abstention:
                raise JudgeOutputError(JudgeOutputFailureKind.ABSTENTION_NOT_ALLOWED)
            parsed = score_judgment
        else:
            pairwise_judgment = PairwiseJudgment.model_validate(raw)
            if pairwise_judgment.preference == "UNKNOWN" and not definition.allow_abstention:
                raise JudgeOutputError(JudgeOutputFailureKind.ABSTENTION_NOT_ALLOWED)
            parsed = pairwise_judgment
    except ValidationError as exc:
        raise JudgeOutputError(JudgeOutputFailureKind.STRICT_SCHEMA_VALIDATION) from exc
    if len(parsed.reason) > definition.maximum_public_justification_length:
        raise JudgeOutputError(JudgeOutputFailureKind.JUSTIFICATION_TOO_LONG)
    return parsed
