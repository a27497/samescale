"""Read-only reconciliation of the accepted V6 evidence into the Core contract.

No executor is called here. The successor plan selects immutable accepted evidence;
its digest is an authority anchor, not a user-adjustable target for stronger results.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from harnesslab.comparability.models import canonical_digest
from harnesslab.judgelab.report import JudgeCalibrationReport
from harnesslab.release.badcases import build_badcases
from harnesslab.release.contracts import (
    CoreReleaseError,
    load_core_corpus,
    load_release_evidence,
    load_resume_claim_map,
)
from harnesslab.release.judge_j4 import build_j4_plan
from harnesslab.release.models import (
    AcceptedRealEvidencePlan,
    EvidenceBinding,
    EvidenceState,
    PairedClaimPolicy,
    ReleaseEvidenceManifest,
    ResumeClaimMap,
)
from harnesslab.tasks.package import TaskPackage

PLAN_REFERENCE = "release/core-real-evidence-plan-v6.json"
# Derived from the accepted K-B4 head and the byte-identical persisted J4 report.
ACCEPTED_PLAN_DIGEST = "sha256:2da47adae863182d76cea3a89a2dbe1fa527767a2903f99c711ff31b79805c57"
MATRIX_PREFIX = "release/core-real-matrix-v6-"
PAIR_REFERENCE = "release/kb4-gpt-codex-timeout-sensitivity.json"
PAIR_ID = "gpt56-relay-direct-vs-codex"
ABLATION_ID = "codex-gpt56-reasoning-effort"
JUDGE_REFERENCE = "release/core-real-judge-v7-j4-report.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CoreReleaseError(message)


def read_object(root: Path, reference: str) -> dict[str, Any]:
    value = json.loads((root / reference).read_text())
    require(isinstance(value, dict), f"expected object: {reference}")
    return dict(value)


def raw_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_accepted_plan(root: Path) -> AcceptedRealEvidencePlan:
    plan = AcceptedRealEvidencePlan.model_validate_json((root / PLAN_REFERENCE).read_text())
    require(plan.digest == ACCEPTED_PLAN_DIGEST, "accepted successor plan authority drifted")
    for reference, expected in plan.source_digests.items():
        require(raw_digest(root / reference) == expected, f"accepted source digest: {reference}")
    return plan


def verified(identity: str, digest: str, limitation: str | None = None) -> EvidenceBinding:
    return EvidenceBinding(
        state=EvidenceState.VERIFIED, identity=identity, digest=digest, limitation=limitation
    )


def stable_sources(
    root: Path,
) -> tuple[AcceptedRealEvidencePlan, list[dict[str, Any]], dict[str, Any]]:
    from scripts.analyze_formal_matrix_final import _validate_dataset
    from scripts.analyze_kb4_timeout_sensitivity import comparison_controls, pair_views

    plan = load_accepted_plan(root)
    corpus = load_core_corpus(root / plan.corpus_reference)
    require(corpus.digest == plan.corpus_digest, "V6 corpus digest mismatch")
    for task in corpus.tasks:
        package = TaskPackage.load(root / task.package_path)
        require(
            (
                package.definition.id,
                package.definition.version,
                package.definition.content_digest,
                package.verifier_digest,
                package.definition.workspace.digest,
            )
            == (
                task.task_id,
                task.version,
                task.task_digest,
                task.verifier_identity,
                task.workspace_input_identity,
            ),
            f"V6 task definition drifted: {task.task_id}",
        )
    rows = [
        json.loads(line)
        for line in (root / (MATRIX_PREFIX + "analysis-dataset.jsonl")).read_text().splitlines()
    ]
    dataset_manifest = read_object(root, MATRIX_PREFIX + "analysis-dataset-manifest.json")
    _validate_dataset(
        rows, dataset_manifest, raw_digest(root / (MATRIX_PREFIX + "analysis-dataset.jsonl"))
    )
    control = read_object(root, MATRIX_PREFIX + "control.json")
    require(
        control["plan_digest"] == dataset_manifest["plan_digest"] == plan.experiment_plan_digest,
        "V6 source plan binding mismatch",
    )
    tasks = {t.task_id: t for t in corpus.tasks}
    schedule = {s for block in control["schedule_blocks"] for s in block["slot_ids"]}
    require(
        {r["slot_id"] for r in rows} == schedule,
        "V6 dataset does not match all 630 scheduled slots",
    )
    for row in rows:
        task = tasks[row["task_id"]]
        require(
            (
                row["task_version"],
                row["task_digest"],
                row["verifier_identity"],
                row["task_package_path"],
            )
            == (task.version, task.task_digest, task.verifier_identity, task.package_path),
            "V6 dataset task identity mismatch",
        )
    sensitivity = read_object(root, PAIR_REFERENCE)
    comparison_controls(root, control)
    pairs = pair_views(sensitivity["slots"])
    require(pairs == sensitivity["pairs"], "Comparability results do not reproduce")
    for pair_id, complete, comparable, partial, incomparable in (
        (PAIR_ID, 82, 0, 82, 0),
        (ABLATION_ID, 83, 42, 0, 41),
    ):
        summary = pairs[pair_id]["summary"]["effective"]
        require(
            summary["capability_complete"] == complete
            and summary["complete_pair_comparability"]
            == {
                "COMPARABLE": comparable,
                "PARTIALLY_COMPARABLE": partial,
                "NOT_COMPARABLE": incomparable,
            }
            and summary["formal_eligible"] is False
            and summary["tasks_with_five_formal_pairs"] == 0,
            "accepted Pair/Ablation eligibility drifted",
        )
    judge_plan = build_j4_plan(root)
    judge = JudgeCalibrationReport.model_validate_json((root / JUDGE_REFERENCE).read_text())
    qualification = read_object(root, "release/core-real-judge-v7-j4-result.json")
    require(
        judge_plan.plan_digest == judge.plan_digest == plan.judge_plan_digest
        and judge.calibration_id == plan.judge_calibration_id
        and judge.report_digest == plan.judge_report_digest
        and judge.suite_digest == judge_plan.suite_digest
        and len(judge.cells) == 1
        and judge.cells[0].qualification_status == "QUALIFIED_FOR_SUITE"
        and judge.cells[0].l0_override_count == 0
        and judge.cells[0].run_counts == qualification["execution"]["run_counts"]
        and qualification["execution"]["completed_slots"] == 63
        and qualification["execution"]["real_judge_calls"] == 63,
        "accepted J4 report/plan/qualification mismatch",
    )
    # Historical reporter always emitted NOT_RUN, including real campaigns. Preserve it.
    require(judge.real_judge_smoke == "NOT_RUN", "historical Judge report was rewritten")
    return plan, rows, pairs


def build_candidate(root: Path) -> tuple[ReleaseEvidenceManifest, ResumeClaimMap]:
    plan, _rows, pairs = stable_sources(root)
    corpus = load_core_corpus(root / plan.corpus_reference)
    badcases = build_badcases(root)
    base = load_release_evidence(root / "release/history/pre-kc-release-evidence.json")
    old_claims = load_resume_claim_map(root / "release/history/pre-kc-resume-claim-evidence.json")
    claim_changes = {
        "real-matrix-results": {
            "status": "VERIFIED",
            "evidence_refs": [f"experiment-report:{plan.experiment_id}"],
            "limitations": [
                (
                    "630 logical slots: 599 capability results, 29 infrastructure outcomes, "
                    "and 2 cancellations; bounded recoveries remain separately recorded."
                )
            ],
        },
        "real-judge-quality": {
            "status": "VERIFIED",
            "evidence_refs": [f"judge-report:{plan.judge_calibration_id}"],
            "claim": (
                "Qualified the real grok-4.6 Judge via the approved relay on "
                "core-calibration-objective@2.0.0."
            ),
            "limitations": [
                (
                    "63 evaluations, 54 judged and 9 correct UNKNOWN abstentions; zero L0 "
                    "overrides. Qualification is limited to this repository-curated suite, "
                    "not universal Judge quality."
                )
            ],
        },
        "real-badcases": {
            "status": "VERIFIED",
            "evidence_refs": [f"badcase:{s.slot_id}" for s in badcases.slots],
            "claim": "Documented three canonical verifier-backed factual V6 failures.",
            "limitations": ["All root causes are null; controlled attribution claims remain zero."],
        },
        "harness-uplift": {
            "status": "NOT_VERIFIED",
            "evidence_refs": [],
            "limitations": [
                (
                    "All 82 capability-complete Direct/Codex pairs are PARTIALLY_COMPARABLE; "
                    "formal eligibility is false. No Harness-uplift causal claim is "
                    "supported."
                )
            ],
        },
    }
    claims = ResumeClaimMap.model_validate(
        {
            "schema_version": old_claims.schema_version,
            "claims": [
                {**c.model_dump(mode="json"), **claim_changes.get(c.claim_id, {})}
                for c in old_claims.claims
            ],
        }
    )
    attribution = read_object(root, "release/kb4-final-attribution-report.json")
    require(
        attribution["controlled_attribution_claim_count"] == 0, "causal attribution is forbidden"
    )
    updates: dict[str, Any] = {
        "schema_version": 2,
        "core_corpus": verified(corpus.corpus_id, corpus.digest),
        "release_commit": EvidenceBinding(
            state=EvidenceState.NOT_VERIFIED,
            limitation=(
                "Deferred: detached finalization must bind the exact final Git commit "
                "without changing that commit."
            ),
        ),
        "experiment_plan": verified(
            f"experiment-plan:{plan.experiment_id}", plan.experiment_plan_digest
        ),
        "real_matrix": verified(
            f"experiment-report:{plan.experiment_id}",
            raw_digest(root / (MATRIX_PREFIX + "final-analysis.json")),
            (
                "Accepted V6 report over the exact frozen 630-slot effective dataset; "
                "infrastructure and cancellations stay outside capability results."
            ),
        ),
        "paired_lane": verified(
            f"experiment-pair:{PAIR_ID}",
            canonical_digest(pairs[PAIR_ID]),
            "82/90 complete, all PARTIALLY_COMPARABLE; formal eligibility false; "
            "no Harness uplift.",
        ),
        "controlled_ablation": verified(
            f"experiment-ablation:{ABLATION_ID}",
            canonical_digest(pairs[ABLATION_ID]),
            (
                "Integrity VERIFIED; 83/90 complete, 42 COMPARABLE, 41 NOT_COMPARABLE; "
                "formal eligibility false; causal reasoning-effort claims forbidden."
            ),
        ),
        "judge_suite": verified(
            f"judge-suite:{build_j4_plan(root).suite_id}@2.0.0", build_j4_plan(root).suite_digest
        ),
        "judge_report": verified(
            f"judge-report:{plan.judge_calibration_id}",
            plan.judge_report_digest,
            (
                "Real execution verified through J4 plan, all 63 persisted evaluations, "
                "qualification and report; historical report smoke field remains NOT_RUN."
            ),
        ),
        "analyst_report": verified(
            "kb4-attribution:final",
            canonical_digest(attribution),
            "Accepted factual synthesis; zero controlled attribution claims.",
        ),
        "badcase_evidence": [
            verified(f"badcase:{s.slot_id}", canonical_digest(s.model_dump(mode="json")))
            for s in badcases.slots
        ],
        "resume_claim_map": verified("release/resume-claim-evidence.json", claims.digest),
        "remote_ci": EvidenceBinding(
            state=EvidenceState.NOT_VERIFIED,
            limitation=(
                "Deferred: exact final-head Full Release CI is required at the later "
                "candidate gate; K-B4 CI is historical evidence only."
            ),
        ),
        "paired_claim_policy": PairedClaimPolicy.NO_HARNESS_UPLIFT_CLAIM,
        "real_statuses": {
            key: EvidenceState.DEFERRED_NOT_VERIFIED
            if key == "REAL_DEEPSEEK_SMOKE"
            else EvidenceState.VERIFIED
            for key in base.real_statuses
        },
        "core_release_ready": False,
        "real_evidence_authorization_required": False,
    }
    manifest = ReleaseEvidenceManifest.model_validate({**base.model_dump(mode="json"), **updates})
    return manifest, claims


def verify_candidate(root: Path) -> ReleaseEvidenceManifest:
    expected, claims = build_candidate(root)
    require(
        load_release_evidence(root / "release/release-evidence.json") == expected,
        "current release candidate is not the deterministic accepted-evidence reconciliation",
    )
    require(
        load_resume_claim_map(root / "release/resume-claim-evidence.json") == claims,
        "current release Claim Map drifted",
    )
    return expected


def accepted_comparison_summaries(pairs: dict[str, Any]) -> tuple[Any, Any]:
    from harnesslab.release.final_verifier import AblationEvidenceSummary, PairEvidenceSummary

    def fields(pair_id: str) -> dict[str, Any]:
        data = pairs[pair_id]["summary"]["effective"]
        return {
            "total_observations": data["capability_complete"],
            "comparable": data["complete_pair_comparability"]["COMPARABLE"],
            "partially_comparable": data["complete_pair_comparability"]["PARTIALLY_COMPARABLE"],
            "not_comparable": data["complete_pair_comparability"]["NOT_COMPARABLE"],
            "per_task_observations": {
                t["task_id"]: t[
                    "formal_comparable" if pair_id == ABLATION_ID else "capability_complete"
                ]
                for t in data["by_task"]
            },
            "formal_eligible": data["formal_eligible"],
            "source_digest": canonical_digest(pairs[pair_id]),
        }

    pair = PairEvidenceSummary(
        pair_id=PAIR_ID,
        left_cell_id="model-gpt56-relay-responses",
        right_cell_id="harness-codex-gpt56-medium",
        **fields(PAIR_ID),
    )
    ablation = AblationEvidenceSummary(
        ablation_id=ABLATION_ID,
        base_cell_id="harness-codex-gpt56-medium",
        variant_cell_id="harness-codex-gpt56-high",
        changed_dimension="reasoning_effort",
        **fields(ABLATION_ID),
    )
    return pair, ablation


def verify_v6_live_sources(root: Path, evidence: Any, artifact_roots: tuple[Path, ...]) -> None:
    from scripts.analyze_kb4_timeout_sensitivity import build

    from harnesslab.comparability.manifest import load_manifest_facts
    from harnesslab.evidence.reader import trusted_artifact_path
    from harnesslab.experiment.evidence import validate_manifest_against_slot
    from harnesslab.experiment.outcomes import normalize_manifest_evidence

    plan, rows, _pairs = stable_sources(root)
    require(
        evidence.plan.digest == plan.experiment_plan_digest, "persisted V6 plan is not accepted"
    )
    slots = {s.slot_id: s for s in evidence.plan.run_slots}
    # Every primary is already verified by the native Experiment loader. Recoveries
    # remain separate physical attempts and never rewrite primary DB outcomes.
    for row in rows:
        if not row["recovery_attempted"]:
            continue
        path = trusted_artifact_path(row["recovery_manifest_path"], artifact_roots)
        require(
            raw_digest(path) == row["recovery_manifest_digest"], "recovery manifest digest mismatch"
        )
        raw = json.loads(path.read_text())
        slot = slots[row["slot_id"]]
        validate_manifest_against_slot(
            raw,
            load_manifest_facts(path, verifier_control_identity=slot.task.verifier_identity),
            slot,
        )
        outcome = normalize_manifest_evidence(raw)
        require(
            outcome.outcome.value == row["recovery_normalized_outcome"]
            and outcome.source_taxonomy == row["recovery_source_outcome"]
            and raw["run_id"] == row["recovery_run_id"],
            "recovery immutable outcome or identity mismatch",
        )
        side = json.loads(
            trusted_artifact_path(row["recovery_sidecar_path"], artifact_roots).read_text()
        )
        require(
            all(
                side[k] == row[k]
                for k in ("slot_id", "cell_id", "recovery_attempt_identity", "recovery_run_id")
            )
            and side["manifest_digest"] == row["recovery_manifest_digest"],
            "recovery sidecar linkage mismatch",
        )
    original_root = Path(
        read_object(root, MATRIX_PREFIX + "checkpoint-630.json")["artifact_roots"]["matrix"]
    )
    trusted_artifact_path(original_root, artifact_roots)
    rebuilt = build(root, original_root)
    require(
        rebuilt == read_object(root, PAIR_REFERENCE),
        "live Pair/Ablation evidence no longer reproduces",
    )


def verify_j4_live_report(
    root: Path, plan: Any, report: Any, records: Any, artifact_roots: tuple[Path, ...]
) -> None:
    from harnesslab.evidence.reader import trusted_artifact_path
    from harnesslab.judgelab.report import build_judge_report
    from harnesslab.judgelab.suite import load_judge_definition, load_judge_suite
    from harnesslab.release.judge_j4 import J4_RELAY_MODEL_ALIASES
    from harnesslab.release.judge_methodology_v2 import OBJECTIVE_SUITE_REFERENCE

    require(
        plan == build_j4_plan(root), "persisted J4 plan does not match its authoritative definition"
    )
    require(
        len(records) == 63 and len({r.slot_id for r in records}) == 63,
        "J4 must contain exactly 63 unique evaluations",
    )
    for record in records:
        require(record.artifact_manifest_path is not None, "J4 artifact is missing")
        trusted_artifact_path(record.artifact_manifest_path, artifact_roots)
        require(
            record.observed_judge_model in J4_RELAY_MODEL_ALIASES,
            "J4 observed model is not an approved real alias",
        )
    suite = load_judge_suite(root / OBJECTIVE_SUITE_REFERENCE)
    definition = load_judge_definition(root / OBJECTIVE_SUITE_REFERENCE / "definition.yaml")
    rebuilt = build_judge_report(
        plan=plan,
        suite=suite,
        definitions={plan.judge_cells[0].id: definition.model_dump(mode="json")},
        records=records,
    )
    accepted = JudgeCalibrationReport.model_validate_json((root / JUDGE_REFERENCE).read_text())
    require(
        rebuilt == report == accepted,
        "J4 immutable evaluations do not reproduce the accepted report",
    )


def verify_v6_snapshot(root: Path, snapshot: Any) -> None:
    from harnesslab.experiment.outcomes import validate_terminal_run_lifecycle

    plan, rows, pairs = stable_sources(root)
    experiment = snapshot.experiment
    require(
        experiment.authoritative_loader_verified
        and experiment.accepted_successor_digest == plan.digest
        and experiment.plan.digest == plan.experiment_plan_digest
        and experiment.record_status in {"queued", "completed"},
        "accepted V6 loader or plan binding is missing",
    )
    require(
        experiment.experiment_id == experiment.report_experiment_id == plan.experiment_id
        and experiment.report_plan_digest == plan.experiment_plan_digest
        and experiment.report_run_count == 630
        and experiment.report_digest == raw_digest(root / (MATRIX_PREFIX + "final-analysis.json")),
        "V6 report identity or digest mismatch",
    )
    require(
        (experiment.pair, experiment.ablation) == accepted_comparison_summaries(pairs),
        "Pair/Ablation observed evidence or formal eligibility drifted",
    )
    require(
        len(experiment.runs) == 630 and len({r.run_id for r in experiment.runs}) == 630,
        "V6 requires exactly 630 unique primary runs",
    )
    actual = {r.slot_id: r for r in experiment.runs}
    require(set(actual) == {row["slot_id"] for row in rows}, "V6 primary slot set mismatch")
    for row in rows:
        run = actual[row["slot_id"]]
        require(
            (
                run.run_id,
                run.cell_id,
                run.task_id,
                run.task_version,
                run.task_digest,
                run.repeat_index,
                run.verifier_identity,
                run.status.value,
                run.normalized_outcome.value,
                run.source_outcome,
                run.evidence_digest,
            )
            == (
                row["run_id"],
                row["cell_id"],
                row["task_id"],
                row["task_version"],
                row["task_digest"],
                row["repeat_index"],
                row["verifier_identity"],
                row["primary_status"],
                row["primary_normalized_outcome"],
                row["primary_source_outcome"],
                row["evidence_digest"],
            ),
            "V6 primary run identity/outcome differs from the accepted dataset",
        )
        validate_terminal_run_lifecycle(run.status, run.normalized_outcome)
    judge = snapshot.judge
    accepted_judge_plan = build_j4_plan(root)
    require(
        judge.authoritative_report_verified
        and judge.plan == accepted_judge_plan
        and judge.record_status == "completed"
        and judge.calibration_id == judge.report_calibration_id == plan.judge_calibration_id
        and judge.report_plan_digest == plan.judge_plan_digest
        and judge.report_digest == plan.judge_report_digest
        and judge.report_suite_id == accepted_judge_plan.suite_id
        and judge.report_suite_version == accepted_judge_plan.suite_version
        and judge.report_suite_digest == accepted_judge_plan.suite_digest
        and judge.evaluation_count == judge.completed_evaluation_count == 63
        and judge.observed_models == ("grok-4.6-build",)
        and judge.l0_override_count == 0
        and judge.real_judge_smoke == "VERIFIED",
        "J4 release authority is incomplete or inconsistent",
    )
