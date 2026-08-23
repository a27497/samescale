from __future__ import annotations

import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict
from scipy.stats import spearmanr

from harnesslab.db.models.judgelab import JudgeEvaluationRecord
from harnesslab.judgelab.models import (
    EvaluationAuthorityResolution,
    GoldSource,
    JudgeCalibrationPlan,
    JudgeEvidence,
    JudgeMode,
    JudgeRunOutcome,
    JudgeSuite,
    QualificationStatus,
    canonical_json,
    digest,
    resolve_authority,
)
from harnesslab.judgelab.runner import canonical_preference, load_and_verify_evidence


class JudgeReportError(RuntimeError):
    """Persisted Judge evidence cannot produce an authoritative calibration report."""


class JudgeCellCalibration(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    judge_cell_id: str
    requested_judge_model: str
    run_counts: dict[str, int]
    label_metrics: dict[str, Any]
    score_metrics: dict[str, Any]
    pairwise_metrics: dict[str, Any]
    capability_metrics: dict[str, Any]
    l0_case_count: int
    l0_judge_disagreement_count: int
    l0_override_count: int
    authority_resolutions: tuple[EvaluationAuthorityResolution, ...]
    qualification_status: QualificationStatus
    qualification_reasons: tuple[str, ...]


class JudgeCalibrationReport(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: int = 1
    calibration_id: str
    suite_id: str
    suite_version: str
    suite_digest: str
    plan_digest: str
    definition_identities: tuple[dict[str, str], ...]
    cells: tuple[JudgeCellCalibration, ...]
    limitations: tuple[str, ...]
    statistical_config_version: str = "judge-calibration-statistics-v1"
    real_judge_smoke: str = "NOT_RUN"

    def canonical_json(self) -> str:
        return canonical_json(self)

    @property
    def report_digest(self) -> str:
        return digest(self)

    def markdown(self) -> str:
        lines = [
            f"# Judge calibration: {self.calibration_id}",
            "",
            f"- Suite: `{self.suite_id}@{self.suite_version}` (`{self.suite_digest}`)",
            f"- Plan: `{self.plan_digest}`",
            f"- Report: `{self.report_digest}`",
            f"- REAL_JUDGE_SMOKE: `{self.real_judge_smoke}`",
        ]
        for cell in self.cells:
            label_summary = (
                f"- Label accuracy / macro F1: {cell.label_metrics['accuracy']} / "
                f"{cell.label_metrics['macro_f1']}"
            )
            score_summary = (
                f"- Score MAE / Spearman: {cell.score_metrics['mae']} / "
                f"{cell.score_metrics['spearman_rho']}"
            )
            l0_summary = (
                f"- L0 disagreements / overrides: {cell.l0_judge_disagreement_count} / "
                f"{cell.l0_override_count}"
            )
            reason_summary = "; ".join(cell.qualification_reasons)
            lines.extend(
                [
                    "",
                    f"## {cell.judge_cell_id}: {cell.qualification_status.value}",
                    "",
                    label_summary,
                    score_summary,
                    f"- Pairwise accuracy: {cell.pairwise_metrics['gold_accuracy']}",
                    f"- Position consistency: {cell.pairwise_metrics['position_consistency_rate']}",
                    f"- Verbosity bias rate: {cell.pairwise_metrics['verbosity_bias_rate']}",
                    l0_summary,
                    f"- Reasons: {reason_summary or 'all suite thresholds satisfied'}",
                ]
            )
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in self.limitations)
        lines.append("")
        return "\n".join(lines)


def _ratio(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator, 6) if denominator else None


def _counts(evidence: list[JudgeEvidence]) -> dict[str, int]:
    counts = Counter(item.outcome.value for item in evidence)
    return {
        "planned": len(evidence),
        "judged": counts[JudgeRunOutcome.JUDGED.value],
        "abstained": counts[JudgeRunOutcome.ABSTAINED.value],
        "judge_output_errors": counts[JudgeRunOutcome.JUDGE_OUTPUT_ERROR.value],
        "provider_failures": counts[JudgeRunOutcome.PROVIDER_ERROR.value],
        "artifact_errors": counts[JudgeRunOutcome.ARTIFACT_ERROR.value],
    }


def _categorical_repeat(values: dict[str, list[str]]) -> float | None:
    rates = [max(Counter(items).values()) / len(items) for items in values.values() if items]
    return round(sum(rates) / len(rates), 6) if rates else None


def _label_metrics(evidence: list[JudgeEvidence], suite: JudgeSuite) -> dict[str, Any]:
    gold = {item.case_id: str(item.expected) for item in suite.gold.gold}
    items = [item for item in evidence if item.case_mode is JudgeMode.LABEL]
    counts = _counts(items)
    evaluable = [item for item in items if item.outcome is not JudgeRunOutcome.PROVIDER_ERROR]
    valid = [item for item in evaluable if item.outcome is JudgeRunOutcome.JUDGED]
    predictions = {
        item.evaluation_id: str(item.parsed_judgment["label"])
        for item in valid
        if item.parsed_judgment is not None
    }
    denominator = len(evaluable)
    correct = sum(predictions.get(item.evaluation_id) == gold[item.case_id] for item in valid)
    classes = sorted({gold[item.case_id] for item in items if gold[item.case_id] != "UNKNOWN"})
    confusion = {
        expected: {
            predicted: sum(
                gold[item.case_id] == expected
                and predictions.get(item.evaluation_id, "NO_VALID_JUDGMENT") == predicted
                for item in evaluable
            )
            for predicted in [*classes, "UNKNOWN", "NO_VALID_JUDGMENT"]
        }
        for expected in sorted(set(gold[item.case_id] for item in items))
    }
    f1s: list[float] = []
    for label in classes:
        tp = sum(
            gold[item.case_id] == label and predictions.get(item.evaluation_id) == label
            for item in evaluable
        )
        fp = sum(
            gold[item.case_id] != label and predictions.get(item.evaluation_id) == label
            for item in evaluable
        )
        fn = sum(
            gold[item.case_id] == label and predictions.get(item.evaluation_id) != label
            for item in evaluable
        )
        f1s.append((2 * tp / (2 * tp + fp + fn)) if (2 * tp + fp + fn) else 0.0)
    repeated: dict[str, list[str]] = defaultdict(list)
    for item in evaluable:
        repeated[item.case_id].append(predictions.get(item.evaluation_id, item.outcome.value))
    return {
        "case_count": len({item.case_id for item in items}),
        "planned_judgments": counts["planned"],
        "valid_judgments": counts["judged"],
        "abstains": counts["abstained"],
        "judge_output_errors": counts["judge_output_errors"],
        "provider_failures": counts["provider_failures"],
        "evaluable_judgments": denominator,
        "coverage": _ratio(denominator, counts["planned"]),
        "accuracy": _ratio(correct, denominator),
        "confusion_matrix": confusion,
        "macro_f1": round(sum(f1s) / len(f1s), 6) if f1s else None,
        "repeat_consistency": _categorical_repeat(repeated),
    }


def _score_metrics(evidence: list[JudgeEvidence], suite: JudgeSuite) -> dict[str, Any]:
    gold = {
        item.case_id: float(item.expected)
        for item in suite.gold.gold
        if item.mode is JudgeMode.SCORE
    }
    items = [item for item in evidence if item.case_mode is JudgeMode.SCORE]
    counts = _counts(items)
    by_case: dict[str, list[float]] = defaultdict(list)
    for item in items:
        if item.outcome is JudgeRunOutcome.JUDGED and item.parsed_judgment is not None:
            score_value = item.parsed_judgment["score"]
            if not isinstance(score_value, int | float) or isinstance(score_value, bool):
                raise JudgeReportError("persisted SCORE judgment is not numeric")
            by_case[item.case_id].append(float(score_value))
    aggregates = {case_id: statistics.median(values) for case_id, values in by_case.items()}
    ordered = sorted(aggregates)
    mae = (
        round(
            sum(abs(aggregates[case_id] - gold[case_id]) for case_id in ordered) / len(ordered), 6
        )
        if ordered
        else None
    )
    rho: float | None = None
    rho_reason: str | None = None
    if len(ordered) < 2:
        rho_reason = "fewer than two covered SCORE cases"
    elif len(set(gold[case_id] for case_id in ordered)) < 2:
        rho_reason = "constant gold scores"
    elif len(set(aggregates[case_id] for case_id in ordered)) < 2:
        rho_reason = "constant predicted scores"
    else:
        value = float(
            spearmanr(
                [gold[case_id] for case_id in ordered],
                [aggregates[case_id] for case_id in ordered],
            ).statistic
        )
        if math.isnan(value):
            rho_reason = "Spearman correlation is mathematically undefined"
        else:
            rho = round(value, 6)
    dispersions = [statistics.pstdev(values) for values in by_case.values() if values]
    evaluable_count = counts["planned"] - counts["provider_failures"]
    return {
        "case_count": len(gold),
        "planned_judgments": counts["planned"],
        "covered_case_count": len(aggregates),
        "evaluable_judgments": evaluable_count,
        "coverage": _ratio(evaluable_count, counts["planned"]),
        "mae": mae,
        "spearman_rho": rho,
        "spearman_not_available_reason": rho_reason,
        "mean_within_case_standard_deviation": round(sum(dispersions) / len(dispersions), 6)
        if dispersions
        else None,
        "abstains": counts["abstained"],
        "judge_output_errors": counts["judge_output_errors"],
        "provider_failures": counts["provider_failures"],
    }


def _pairwise_metrics(evidence: list[JudgeEvidence], suite: JudgeSuite) -> dict[str, Any]:
    gold_items = {item.case_id: item for item in suite.gold.gold if item.mode is JudgeMode.PAIRWISE}
    items = [item for item in evidence if item.case_mode is JudgeMode.PAIRWISE]
    counts = _counts(items)
    trials: dict[tuple[str, int], list[JudgeEvidence]] = defaultdict(list)
    for item in items:
        trials[(item.case_id, item.logical_repeat_index)].append(item)
    logical: list[dict[str, Any]] = []
    for (case_id, _repeat), pair in sorted(trials.items()):
        provider_infra = any(item.outcome is JudgeRunOutcome.PROVIDER_ERROR for item in pair)
        values = [canonical_preference(item) for item in pair]
        position_evaluable = len(pair) == 2 and not provider_infra
        consistent = position_evaluable and values[0] is not None and values[0] == values[1]
        verdict = (
            values[0]
            if (len(values) == 1 and not provider_infra) or (position_evaluable and consistent)
            else None
        )
        capability_error = any(
            item.outcome in {JudgeRunOutcome.ABSTAINED, JudgeRunOutcome.JUDGE_OUTPUT_ERROR}
            for item in pair
        )
        logical.append(
            {
                "case_id": case_id,
                "provider_infra": provider_infra,
                "position_evaluable": position_evaluable,
                "position_consistent": consistent,
                "verdict": verdict,
                "capability_error": capability_error,
                "canonical_values": tuple(values),
            }
        )
    evaluable = [row for row in logical if not row["provider_infra"]]
    correct = sum(row["verdict"] == str(gold_items[row["case_id"]].expected) for row in evaluable)
    ties = [row for row in evaluable if gold_items[row["case_id"]].expected == "TIE"]
    position_rows = [row for row in logical if row["position_evaluable"]]
    position_consistent = sum(row["position_consistent"] for row in position_rows)
    abstain_trials = sum(
        any(item.outcome is JudgeRunOutcome.ABSTAINED for item in pair)
        for pair in trials.values()
        if not any(item.outcome is JudgeRunOutcome.PROVIDER_ERROR for item in pair)
    )
    output_error_trials = sum(
        any(item.outcome is JudgeRunOutcome.JUDGE_OUTPUT_ERROR for item in pair)
        for pair in trials.values()
        if not any(item.outcome is JudgeRunOutcome.PROVIDER_ERROR for item in pair)
    )
    repeated: dict[str, list[str]] = defaultdict(list)
    for row in evaluable:
        for variant_index, value in enumerate(row["canonical_values"]):
            state = (
                str(value)
                if value is not None
                else "CAPABILITY_ERROR"
                if row["capability_error"]
                else "NO_VALID_JUDGMENT"
            )
            repeated[f"{row['case_id']}:{variant_index}"].append(state)
    verbosity = [row for row in evaluable if gold_items[row["case_id"]].probe.verbosity_probe]
    longer = sum(
        row["verdict"] == gold_items[row["case_id"]].probe.longer_candidate for row in verbosity
    )
    provider_infra_trials = len(logical) - len(evaluable)
    capability_errors = sum(row["capability_error"] for row in evaluable)
    return {
        "logical_pair_count": len(logical),
        "planned_logical_pairs": len(logical),
        "evaluable_logical_pairs": len(evaluable),
        "provider_infra_trials": provider_infra_trials,
        "coverage": _ratio(len(evaluable), len(logical)),
        "gold_accuracy": _ratio(correct, len(evaluable)),
        "position_evaluable_count": len(position_rows),
        "position_consistency_rate": _ratio(position_consistent, len(position_rows)),
        "tie_accuracy": _ratio(sum(row["verdict"] == "TIE" for row in ties), len(ties)),
        "unknown_abstain_rate": _ratio(abstain_trials, len(evaluable)),
        "judge_output_error_rate": _ratio(output_error_trials, len(evaluable)),
        "provider_infra_count": counts["provider_failures"],
        "capability_error_count": capability_errors,
        "capability_error_opportunities": len(evaluable),
        "repeat_consistency": _categorical_repeat(repeated),
        "verbosity_probe_count": len(verbosity),
        "longer_candidate_preference_count": longer,
        "verbosity_bias_rate": _ratio(longer, len(verbosity)),
        "order_swapped_requests": sum(item.order_variant.value == "SWAPPED" for item in items),
    }


def _threshold_reasons(
    label: dict[str, Any],
    score: dict[str, Any],
    pairwise: dict[str, Any],
    capability: dict[str, Any],
    policy: object,
) -> tuple[str, ...]:
    from harnesslab.judgelab.models import QualificationPolicy

    parsed = QualificationPolicy.model_validate(policy)
    reasons: list[str] = []
    checks = (
        (label["coverage"], parsed.minimum_coverage, "label coverage", "min"),
        (label["accuracy"], parsed.minimum_label_accuracy, "label accuracy", "min"),
        (label["macro_f1"], parsed.minimum_macro_f1, "label macro F1", "min"),
        (score["coverage"], parsed.minimum_coverage, "score coverage", "min"),
        (pairwise["coverage"], parsed.minimum_coverage, "pairwise coverage", "min"),
        (score["mae"], parsed.maximum_score_mae, "score MAE", "max"),
        (pairwise["gold_accuracy"], parsed.minimum_pairwise_accuracy, "pairwise accuracy", "min"),
        (
            pairwise["position_consistency_rate"],
            parsed.minimum_position_consistency,
            "position consistency",
            "min",
        ),
        (
            pairwise["verbosity_bias_rate"],
            parsed.maximum_verbosity_bias_rate,
            "verbosity bias rate",
            "max",
        ),
    )
    for value, threshold, name, direction in checks:
        if (
            value is None
            or (direction == "min" and value < threshold)
            or (direction == "max" and value > threshold)
        ):
            reasons.append(f"{name}={value} violates {direction}imum threshold {threshold}")
    if parsed.require_spearman and (
        score["spearman_rho"] is None or score["spearman_rho"] < parsed.minimum_spearman_rho
    ):
        reasons.append(
            f"Spearman={score['spearman_rho']} does not meet {parsed.minimum_spearman_rho}"
        )
    repeats = [label["repeat_consistency"], pairwise["repeat_consistency"]]
    if any(value is None or value < parsed.minimum_repeat_consistency for value in repeats):
        reasons.append("categorical repeat consistency is below policy")
    if (
        capability["abstain_output_error_rate"] is None
        or capability["abstain_output_error_rate"] > parsed.maximum_abstain_error_rate
    ):
        reasons.append("combined abstain/output-error rate exceeds policy")
    return tuple(reasons)


def _capability_metrics(
    label: dict[str, Any], score: dict[str, Any], pairwise: dict[str, Any]
) -> dict[str, Any]:
    opportunities = (
        label["evaluable_judgments"]
        + score["evaluable_judgments"]
        + pairwise["capability_error_opportunities"]
    )
    errors = (
        label["abstains"]
        + label["judge_output_errors"]
        + score["abstains"]
        + score["judge_output_errors"]
        + pairwise["capability_error_count"]
    )
    return {
        "evaluable_opportunities": opportunities,
        "abstain_output_error_count": errors,
        "abstain_output_error_rate": _ratio(errors, opportunities),
    }


def build_judge_report(
    *,
    plan: JudgeCalibrationPlan,
    suite: JudgeSuite,
    definitions: dict[str, object],
    records: tuple[JudgeEvaluationRecord, ...],
) -> JudgeCalibrationReport:
    if len(records) != len(plan.slots):
        raise JudgeReportError("persisted Judge evaluation set is incomplete")
    slots = {slot.slot_id: slot for slot in plan.slots}
    cells = {cell.id: cell for cell in plan.judge_cells}
    evidence_by_cell: dict[str, list[JudgeEvidence]] = defaultdict(list)
    for record in records:
        slot = slots.get(record.slot_id)
        if slot is None or record.artifact_manifest_path is None or record.artifact_digest is None:
            raise JudgeReportError("persisted Judge slot lacks artifact identity")
        cell = cells[record.judge_cell_id]
        definition = definitions[cell.id]
        from harnesslab.judgelab.models import JudgeDefinition

        parsed_definition = JudgeDefinition.model_validate(definition)
        try:
            evidence = load_and_verify_evidence(
                Path(record.artifact_manifest_path),
                expected_slot=slot,
                suite_digest=plan.suite_digest,
                definition_digest=parsed_definition.definition_digest,
                profile_identity=cell.profile_identity,
                expected_artifact_digest=record.artifact_digest,
            )
        except Exception as exc:
            raise JudgeReportError(str(exc)) from exc
        if (
            record.status != "completed"
            or record.outcome != evidence.outcome.value
            or record.requested_judge_model != evidence.requested_judge_model
            or record.observed_judge_model != evidence.observed_judge_model
        ):
            raise JudgeReportError("persisted Judge evaluation disagrees with immutable evidence")
        evidence_by_cell[cell.id].append(evidence)
    gold = {item.case_id: item for item in suite.gold.gold}
    reports: list[JudgeCellCalibration] = []
    for cell_id in sorted(evidence_by_cell):
        items = evidence_by_cell[cell_id]
        label = _label_metrics(items, suite)
        score = _score_metrics(items, suite)
        pairwise = _pairwise_metrics(items, suite)
        capability = _capability_metrics(label, score, pairwise)
        l0_case_ids = {
            item.case_id
            for item in suite.gold.gold
            if item.gold_source is GoldSource.DETERMINISTIC_L0
        }
        authority_resolutions: list[EvaluationAuthorityResolution] = []
        for item in items:
            if item.outcome is not JudgeRunOutcome.JUDGED:
                continue
            value: str | float | None
            if item.case_mode is JudgeMode.PAIRWISE:
                value = canonical_preference(item)
            elif item.parsed_judgment is None:
                value = None
            elif item.case_mode is JudgeMode.LABEL:
                value = str(item.parsed_judgment["label"])
            else:
                score_value = item.parsed_judgment["score"]
                if not isinstance(score_value, int | float) or isinstance(score_value, bool):
                    raise JudgeReportError("persisted SCORE judgment is not numeric")
                value = float(score_value)
            if value is None:
                continue
            gold_case = gold[item.case_id]
            resolution = resolve_authority(
                l0_deterministic=(
                    gold_case.expected
                    if gold_case.gold_source is GoldSource.DETERMINISTIC_L0
                    else None
                ),
                l1_human_gold=(
                    gold_case.expected
                    if gold_case.gold_source is GoldSource.CURATED_HUMAN_L1
                    else None
                ),
                l2_judge=value,
            )
            authority_resolutions.append(
                EvaluationAuthorityResolution(
                    evaluation_id=item.evaluation_id,
                    case_id=item.case_id,
                    **resolution.model_dump(mode="python"),
                )
            )
        l0_resolutions = [item for item in authority_resolutions if item.authority_level == "L0"]
        disagreements = sum(item.judge_disagreement for item in l0_resolutions)
        overrides = sum(item.l0_override_count for item in l0_resolutions)
        reasons = _threshold_reasons(label, score, pairwise, capability, plan.qualification_policy)
        status = (
            QualificationStatus.QUALIFIED_FOR_SUITE
            if not reasons
            else QualificationStatus.NOT_QUALIFIED
        )
        reports.append(
            JudgeCellCalibration(
                judge_cell_id=cell_id,
                requested_judge_model=cells[cell_id].model_profile.requested_model,
                run_counts=_counts(items),
                label_metrics=label,
                score_metrics=score,
                pairwise_metrics=pairwise,
                capability_metrics=capability,
                l0_case_count=len(l0_case_ids),
                l0_judge_disagreement_count=disagreements,
                l0_override_count=overrides,
                authority_resolutions=tuple(authority_resolutions),
                qualification_status=status,
                qualification_reasons=reasons,
            )
        )
    if any(cell.l0_override_count != 0 for cell in reports):
        raise JudgeReportError("L0 override count must be zero by construction")
    identities = tuple(
        {
            "judge_cell_id": cell.id,
            "definition_digest": cell.definition_digest,
            "profile_identity": cell.profile_identity,
        }
        for cell in sorted(plan.judge_cells, key=lambda item: item.id)
    )
    return JudgeCalibrationReport(
        calibration_id=plan.calibration_id,
        suite_id=plan.suite_id,
        suite_version=plan.suite_version,
        suite_digest=plan.suite_digest,
        plan_digest=plan.plan_digest,
        definition_identities=identities,
        cells=tuple(reports),
        limitations=(
            "Qualification is bound only to this small repository-curated suite.",
            "Curated human gold is not a large-scale human, expert-panel, or inter-rater study.",
            "Verbosity measurements are probes and do not establish universal bias absence.",
            "HarnessLab blinds controlled metadata but candidate text may self-identify.",
        ),
    )
