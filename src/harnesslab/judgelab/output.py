from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from harnesslab.judgelab.models import (
    JudgeDefinition,
    JudgeMode,
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


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise JudgeOutputError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def parse_judge_output(text: str, case: PublicCase, definition: JudgeDefinition) -> ParsedJudgment:
    try:
        encoded = text.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise JudgeOutputError("Judge output is not valid UTF-8") from exc
    if len(encoded) > MAX_JUDGE_OUTPUT_BYTES:
        raise JudgeOutputError("Judge output exceeds byte limit")
    if text != text.strip() or text.startswith("```"):
        raise JudgeOutputError("Judge output must be one bare JSON object")
    try:
        raw = json.loads(text, object_pairs_hook=_reject_duplicate_pairs)
    except (json.JSONDecodeError, RecursionError, UnicodeDecodeError) as exc:
        raise JudgeOutputError("Judge output is malformed JSON") from exc
    if not isinstance(raw, dict):
        raise JudgeOutputError("Judge output must be a JSON object")
    if PRIVATE_FIELDS.intersection(raw):
        raise JudgeOutputError("private-reasoning fields are forbidden")
    try:
        if case.mode is JudgeMode.LABEL:
            label_judgment = LabelJudgment.model_validate(raw)
            if label_judgment.label not in case.allowed_labels and not (
                definition.allow_abstention and label_judgment.label == "UNKNOWN"
            ):
                raise JudgeOutputError("Judge label is not allowed")
            parsed: ParsedJudgment = label_judgment
        elif case.mode is JudgeMode.SCORE:
            score_judgment = ScoreJudgment.model_validate(raw)
            if score_judgment.abstain != (score_judgment.score is None):
                raise JudgeOutputError("score abstention and null invariant violated")
            if score_judgment.score is not None and not (
                case.score_min <= score_judgment.score <= case.score_max  # type: ignore[operator]
            ):
                raise JudgeOutputError("Judge score is outside the declared range")
            if score_judgment.abstain and not definition.allow_abstention:
                raise JudgeOutputError("Judge definition does not allow abstention")
            parsed = score_judgment
        else:
            pairwise_judgment = PairwiseJudgment.model_validate(raw)
            if pairwise_judgment.preference == "UNKNOWN" and not definition.allow_abstention:
                raise JudgeOutputError("Judge definition does not allow abstention")
            parsed = pairwise_judgment
    except ValidationError as exc:
        raise JudgeOutputError("Judge output failed strict schema validation") from exc
    if len(parsed.reason) > definition.maximum_public_justification_length:
        raise JudgeOutputError("public justification exceeds configured length")
    return parsed
