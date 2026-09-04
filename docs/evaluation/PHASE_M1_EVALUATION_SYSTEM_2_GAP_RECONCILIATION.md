# Phase M.1 — Evaluation System 2.0 Contract and Gap Reconciliation

Status: contract and implementation plan only

Baseline: `origin/main` / `e3cab6f180f2bbcd6c8f134aa3d710c503fe6e87` (`v1.0.0-core`)

External executions in this phase: **0**

Frozen evidence mutations in this phase: **0**

## Purpose and decision boundary

This document reconciles the Evaluation System 2.0 target with the implementation and tests that exist at the Phase M.1 baseline. It is deliberately not a feature implementation, a new evaluation result, or a reinterpretation of historical release evidence. Every status below refers to reusable product capability at this baseline, not to whether a historical campaign once achieved a similar outcome.

The repository already has strong task, execution, evidence, comparison, and release primitives. The principal gap is that those primitives are not yet assembled into governed Discriminative and Stress suites with leakage-resistant selection, evidence-bound funnel decisions, generic runtime budget enforcement, and one durable run lifecycle. Frozen artifacts under `release/` remain historical facts. They must be consumed by digest and reference, not edited to make the product appear more complete.

Status vocabulary for the capability matrix is intentionally restricted:

- `COMPLETE`: the target capability is implemented as a reusable product contract and is proven by focused tests.
- `PARTIAL`: a reusable implementation exists, but one or more target semantics, integrations, or proofs are absent.
- `FOUNDATION_ONLY`: lower-level primitives or candidate material exist, but the target capability itself has no governed product contract.
- `MISSING`: neither the target capability nor a material reusable foundation exists.

## 1. Current-state inventory

### IMPLEMENTED_AND_PROVEN

| Area | What is implemented and proven | Primary evidence |
| --- | --- | --- |
| Immutable task packages | Strict manifests bind instruction, context, workspace, verifier/oracle, lane support, expected tools, protected paths, and resource hints. Package materialization and evidence validation fail closed. | `src/harnesslab/tasks/models.py`, `src/harnesslab/tasks/package.py`, `src/harnesslab/tasks/validation.py`, `src/harnesslab/tasks/verifier.py`; `tests/test_task_package.py`, `tests/test_task_verifier.py` |
| Core corpus | Eighteen stable micro-task identities are bound by `release/core-corpus-v4.json`; task version `1.0.2` is reconciled against exact task/workspace/verifier identities. The earlier `release/core-corpus.json` is immutable historical version `1.0.0`. | `release/core-corpus-v4.json`, `src/harnesslab/release/reconciliation.py`; `tests/test_release_contracts.py`, `tests/test_kc_release_reconciliation.py` |
| Deterministic task health | Baseline-fails, oracle-passes, repeated-health, protected-path, and robustness checks exist. Tier B adds snapshot, hidden-asset, robustness, and failure-boundary gates. | `src/harnesslab/tasks/health.py`, `src/harnesslab/tasks/tier_b.py`; `tests/test_tier_a_verifier_robustness.py`, `tests/test_tier_b_repo_engineering.py` |
| Immutable experiment definition and planning | Strict matrix specifications, cells, tasks, repetitions, pairs/ablations, content-addressed plans, exact task identities, slots, controls, and blocked schedules exist. | `src/harnesslab/experiment/spec.py`, `src/harnesslab/experiment/plan.py`; `tests/test_experiment_plan.py`, `tests/test_eval_methodology_v2.py` |
| Durable queued execution | PostgreSQL-backed idempotent enqueue, leases, heartbeats, cancellation flags, bounded selection, unique attempt artifact identities, verification, and normalized outcomes exist. | `src/harnesslab/experiment/queue.py`, `src/harnesslab/experiment/executor.py`; `tests/test_experiment_queue.py`, `tests/test_experiment_executor_safety.py`, `tests/test_experiment_e2e.py` |
| Evidence and statistics | Immutable manifests are reopened and digest-checked. Capability and infrastructure outcomes are separated. Pass rate, Wilson intervals, pass@k, paired binary tests, continuous bootstrap, evidence tiers, and explicit-cost availability rules exist. | `src/harnesslab/evidence/reader.py`, `src/harnesslab/experiment/outcomes.py`, `src/harnesslab/experiment/statistics.py`, `src/harnesslab/experiment/report.py`; `tests/test_experiment_statistics.py`, `tests/test_experiment_e2e.py` |
| Comparability | Frozen controls and evidence determine `COMPARABLE`, `PARTIALLY_COMPARABLE`, or `NOT_COMPARABLE`; noncomparable observations cannot silently support formal claims. | `src/harnesslab/comparability/`, `src/harnesslab/experiment/report.py`; `tests/test_comparability.py`, `tests/test_experiment_comparability.py` |
| Judge authority boundary | Deterministic L0 verification remains authoritative; Judge qualification, blinding/order swaps, calibration, abstention, evidence, and reporting cannot reverse L0 failure. | `src/harnesslab/judgelab/`, `src/harnesslab/custom_eval/evaluation.py`; `tests/test_judge_contracts.py`, `tests/test_judge_plan.py`, `tests/test_judge_e2e.py`, `tests/test_custom_eval.py` |
| Deterministic failure facts | A typed failure taxonomy, capability/infra scope, immutable evidence origin, deterministic cluster identities, hypotheses, correlation/controlled-association labels, BadCase export, and explicit causal caveats exist. | `src/harnesslab/diagnosis/models.py`, `src/harnesslab/diagnosis/service.py`; `tests/test_diagnosis.py` |

### IMPLEMENTED_PARTIAL

| Area | Implemented portion | Why it is only partial |
| --- | --- | --- |
| Task quality and splits | Immutable task identities, provenance, Tier A/Tier B qualification, development/held-out roles, exposure states, lineage overlap rejection, and deterministic split freezing. | No suite-membership axis, canonical Evaluation System 2.0 population, persistent exposure-event registry, access policy, promotion/demotion ledger, or release-claim gate. Difficulty is ungoverned task metadata. |
| Evaluation funnel | `PREFLIGHT`, repeat-count modes (`n=1`, `n=3`, `n=5`), explicit decisions, and `auto_promote=false` are modeled. | Current stages are `PREFLIGHT/SMOKE/BREADTH/INFORMAL/FORMAL/DISCRIMINATIVE_STRESS`, not the target six stages. Planning does not support the last stage, and a `GO` value is not bound to admission criteria or evidence. |
| Preflight | Broad generic checks exist for local resources, configurations, routes, task behavior, lane support, compatibility declarations, network policy, comparability, envelopes, and estimated budget. | Checks are split across generic, registry, Matrix, and release-specific paths. No single plan-derived execution gate proves all target checks; live route/runtime readiness is intentionally absent; some formal comparability risks are nonblocking. |
| Cost and budget | Deterministic keyless estimates cover calls, input/output tokens, requests, turns, known/unknown pricing, ceilings, heterogeneous cells, and Judge components. | Wall time and tool calls are absent from the estimator; actual consumption is not reconciled to estimates; generic orchestration does not stop on the full budget contract or persist partial-evidence budget termination. |
| Run lifecycle | Both the persisted executor state machine and a stricter immutable Phase M lifecycle/attempt-ledger value model exist. | They are not wired together. There is no durable generic attempt ledger, `BUDGET_EXHAUSTED` persistence, operator pause/resume/retry API, or checkpointed in-run resume. |
| Failure clustering | Deterministic clusters and diagnosis are queryable and displayed. | One exact full-dimension tuple can over-fragment evidence; there is no versioned projection contract, cohort/cross-experiment aggregation, or explicit missing/unknown grouping policy. |
| Product control surfaces | Registry builder/preflight/snapshot and read-only Workbench evidence views exist. | The Workbench is not an Evaluation System 2.0 execution/control plane; cancel, pause, resume, selected retry, stage decisions, suite governance, and budget-stop controls are not exposed as governed product operations. |

### FOUNDATION_ONLY

| Area | Foundation | Boundary |
| --- | --- | --- |
| Discriminative Suite | Stable Core tasks, exact task identities, repeated evaluation modes, paired comparisons, and historical multi-configuration evidence exist. | There is no versioned Discriminative Suite, admission algorithm, candidate-panel contract, rejection ledger, coverage policy, or currently qualified membership. Historical discrimination does not automatically qualify a task against future configurations. |
| Stress Suite | Three Tier B repository-engineering packages are deterministically qualified, with multi-file or multi-module work and robustness checks. `TaskTier.C` names long-horizon work. | There is no Stress Suite definition, measurable stress-dimension rubric, admission evidence, runtime trajectory measurement, portfolio coverage rule, or qualified Stress membership. |

### NOT_IMPLEMENTED

- Versioned suite manifests for `CORE`, `DISCRIMINATIVE`, and `STRESS` membership that reference immutable task identities without rewriting task packages.
- Bias-resistant empirical admission for Discriminative tasks and measurable, portfolio-aware admission for Stress tasks.
- A persistent exposure/access-event ledger and an irreversible holdout-demotion policy.
- Evidence-bound stage decision records, with entry/exit criteria, authorized executor, and exact source digests.
- A unified generic execution preflight projected from an immutable experiment plan/snapshot.
- Generic enforcement and reconciliation of wall time, output tokens, turns, tool calls, provider requests, and monetary cost.
- A durable attempt ledger wired to the queue/executor, explicit `BUDGET_EXHAUSTED`, general pause/resume, selected retry, and checkpoint semantics.
- Versioned failure-cluster projections and cross-experiment aggregation.

### HISTORICAL_RELEASE_ONLY

The following are valid, valuable evidence, but are not reusable product capability merely because they exist:

- V2–V6 Core real-smoke and Matrix controllers, fixed call ceilings, canary/pilot/remaining selections, no-retry rules, and release authorization flags under `src/harnesslab/release/`.
- The 630-slot V6 accepted Matrix and its 79 separately bound bounded recoveries. Its persisted campaign record remains `queued` while all primary rows are terminal; the release reconciler proves completion without rewriting that bookkeeping fact.
- `release/core-real-matrix-v6-partial-budget-stop.json` and other K-B budget-stop receipts tied to a particular campaign, pricing assumption, currency, selection, and operator authorization.
- K-B/K-C Pair, ablation, Judge, BadCase, claim-map, and final-release reconciliation logic. It proves exact historical facts, including false formal eligibility and zero causal attribution; it is not a generic promotion service.
- Frozen preregistrations and `NOT_RUN` artifacts. A planned or authorized run remains `NOT_RUN` until immutable execution evidence says otherwise.

## 2. Capability reconciliation matrix

| Capability | Target semantics | Current implementation | Exact sources and tests | Status | Missing contract or integration | Dependencies | Scientific risk | Engineering risk | External execution required? |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Discriminative Suite | A versioned, compositionally balanced set of immutable tasks that reliably separates preregistered configurations without favoring a chosen model or harness; admission and retirement are evidence-bound and auditable. | Task packages, Core corpus, repeated plans, comparability, paired statistics, and historical Matrix evidence are mature. No Discriminative Suite object or admission workflow exists. | `src/harnesslab/tasks/models.py`; `src/harnesslab/experiment/plan.py`, `src/harnesslab/experiment/statistics.py`, `src/harnesslab/experiment/report.py`; `release/core-corpus-v4.json`; `tests/test_task_package.py`, `tests/test_experiment_statistics.py`, `tests/test_experiment_comparability.py` | `FOUNDATION_ONLY` | Suite manifest, candidate panel, preregistered thresholds, qualification/rejection ledger, representation quotas, retirement/supersession, evidence freshness rules. | Task quality identities; Dev/Holdout policy; funnel decisions; budget/preflight. | Post-hoc cherry-picking, optimizing to a favored system, floor/ceiling tasks, unstable rankings, or reuse of noncomparable/stale results. | Identity drift, nonreproducible selection, and incompatible admission implementations. | **No** for contracts and keyless validation. **Yes, separately authorized**, for empirical admission or refresh. |
| Stress Suite | A versioned set whose members demonstrate measurable long-trajectory, multi-file, tool, repair-loop, dependency/build, context, or protocol stress; size alone never qualifies a task. | Three qualified Tier B repository tasks and a long-horizon tier name exist. No stress rubric or suite membership exists. | `src/harnesslab/tasks/tier_b.py`; `tasks/repo-java-widget-update/`, `tasks/repo-python-ledger-transfer/`, `tasks/repo-typescript-resilient-client/`; `release/tier-b-qualification-v1.json`; `tests/test_tier_b_repo_engineering.py` | `FOUNDATION_ONLY` | Stress dimensions and thresholds, structural/behavioral evidence schema, portfolio coverage, execution-derived trajectory evidence, qualification expiry/retirement. | Task quality; trace normalization; budget/lifecycle; preflight. | Artificial bloat or comparison of runs that reached different effective workloads. | Verifier brittleness, excessive cost/timeouts, and inconsistent trace normalization. | **No** for structural qualification. **Yes, separately authorized**, for trajectory/protocol qualification and performance claims. |
| Task Quality Tiers | Qualification quality, suite purpose, difficulty/stress, and exposure are separate axes. Every membership binds exact package/workspace/verifier identities and qualification evidence. | `TaskFamily`, `BenchmarkTier`, `QualificationStatus`, identity/provenance, Tier A/B gates, and split identities exist. | `src/harnesslab/tasks/quality.py`, `src/harnesslab/tasks/splits.py`, `src/harnesslab/tasks/tier_b.py`; `tests/test_task_quality_and_splits.py`, `tests/test_tier_b_repo_engineering.py` | `PARTIAL` | Sidecar suite membership; governed difficulty/stress descriptors; canonical registry; qualification lifecycle and evidence freshness; access/exposure events. | Existing package identities and qualification artifacts. | Conflating hard with valid or attaching evidence-free quality labels. | Package/schema drift and duplicate or conflicting lineage records. | **No** for model and registry contracts; task behavioral qualification remains local/keyless where possible. |
| Dev / Holdout separation | Leakage-resistant populations with explicit visibility, access logging, lineage exclusion, irreversible exposure semantics, and claim-scoped holdout use. | Split roles, exposure `NOT_USED/USED/UNKNOWN`, exact identity and lineage overlap checks, and frozen split digest exist. | `src/harnesslab/tasks/splits.py`; `tests/test_task_quality_and_splits.py` | `PARTIAL` | Canonical population, durable event ledger, role-specific access controls, claim windows, promotion/demotion workflow, release gate, export redaction. | Task identity/provenance; suite registry; authentication/authorization if made multi-user. | False “unseen” claims, verifier/gold leakage, repeated holdout tuning, or pretending a new version erases exposure. | Incomplete event capture, authorization bypass, and inconsistent visibility enforcement across surfaces. | **No**. Existing Core evidence is read-only input and cannot establish untouched holdout status. |
| Cost and Budget | Estimate and enforce a frozen per-run, per-stage, and campaign envelope across wall time, output tokens, turns, tool calls, provider requests, and cost; preserve partial evidence and stop before unauthorized spend. | Generic exact-Decimal estimators cover calls/tokens/requests/turns/cost and unknown prices. Methodology names all six dimensions. Some lanes enforce local time/token/turn limits. Release V6 has campaign-specific stop logic. | `src/harnesslab/budget/models.py`, `src/harnesslab/budget/estimator.py`; `src/harnesslab/experiment/methodology.py`; `src/harnesslab/registry/runtime.py`; `src/harnesslab/release/v6.py`, `src/harnesslab/release/v6_authorization.py`, `src/harnesslab/release/v6_canary.py`; `tests/test_phase_m_budget.py`, `tests/test_kb2r_matrix_preflight.py`, `tests/test_registry_lite.py`, `tests/test_kb3_v6_canary.py` | `PARTIAL` | Wall/tool dimensions in generic estimates; actual-usage ledger; atomic reservations; executor stop decisions; unknown-price policy; partial-evidence terminal semantics; estimate-vs-actual report. | Frozen plan/envelope; lifecycle/attempts; normalized usage; pricing evidence supplied by operator. | Unequal effective envelopes, informative censoring, or converting a campaign budget stop into task failure. | Overspend races, fabricated prices, lost partial evidence, and inconsistent lane enforcement. | **No** for implementation/tests. Price refresh or real consumption needs separate supplied evidence/authorization; no current pricing call is needed here. |
| Funnel Evaluation | Exact stages `0 Preflight`, `1 Smoke n=1`, `2 Informal n=3`, `3 Formal n=5`, `4 Discriminative`, `5 Stress`; every transition is an explicit immutable decision based on exact evidence. Never auto-promote. | Repeat modes and an explicit/no-auto funnel exist, but current stage vocabulary includes Smoke/Breadth/Informal/Formal and combines Discriminative/Stress. Plan construction excludes the combined final stage. | `src/harnesslab/experiment/methodology.py`, `src/harnesslab/experiment/plan.py`; `release/evaluation-methodology-v2.json`; `tests/test_eval_methodology_v2.py` | `PARTIAL` | Target stage enum/version; per-stage entry/exit criteria; decision artifact with evidence digests; authorized decision role; reuse/freshness policy; stage-specific plan support. | Suite manifests; preflight; budget; lifecycle; statistics/comparability. | Optional stopping, outcome-guided promotion, or double-counting reused observations. | Silent identity/control drift, cosmetic `GO`, and accidental auto-escalation of cost. | **No** for contracts. Stages 1–5 require separate execution authorization when actually run. |
| Experiment Preflight | A keyless, zero-provider-call decision derived from the exact frozen plan/snapshot; covers environment, routes, runtimes, tasks, compatibility, network, comparability, and budget, and blocks execution on mandatory failure. | Generic preflight plus registry and Matrix overlays cover most dimensions. Some checks are declaration/presence checks, and variants are not unified. | `src/harnesslab/preflight/models.py`, `src/harnesslab/preflight/service.py`, `src/harnesslab/preflight/io.py`, `src/harnesslab/preflight/cli.py`; `src/harnesslab/api/routes/preflight.py`; `src/harnesslab/registry/service.py`, `src/harnesslab/registry/runtime.py`; `tests/test_phase_m_preflight.py`, `tests/test_phase_m_interfaces.py`, `tests/test_kb2r_matrix_preflight.py`, `tests/test_registry_lite.py` | `PARTIAL` | One plan-derived projection; normalized check IDs/severity; deep but keyless runtime self-tests; mandatory formal comparability gate; authorization receipt; execution-time digest verification. | Immutable plan/snapshot; task health; budget; runtime registry. | Nonblocking comparability invalidity or readiness claims unsupported by the tested environment. | Drift between preflight and run and duplicated/release-specific implementations. | **No**. Live provider probes are explicitly outside generic preflight unless separately authorized as a later stage. |
| Run Lifecycle | Durable semantic states `QUEUED`, `PREPARING`, `RUNNING`, `VERIFYING`, `COMPLETED`, `FAILED_CAPABILITY`, `FAILED_INFRA`, `CANCELLED`, `BUDGET_EXHAUSTED`; immutable attempts and evidence-preserving controls. | Persisted executor states plus a detached Phase M lifecycle/attempt-ledger model. Queue leasing, heartbeat, cancel flag, bounded remaining work, and attempt-specific artifact IDs exist. | `src/harnesslab/contracts/run.py`; `src/harnesslab/experiment/queue.py`, `src/harnesslab/experiment/executor.py`, `src/harnesslab/experiment/lifecycle.py`; `src/harnesslab/db/models/experiment.py`; `tests/test_experiment_lifecycle.py`, `tests/test_experiment_queue.py`, `tests/test_experiment_executor_safety.py`, `tests/test_experiment_e2e.py` | `PARTIAL` | Wire semantic lifecycle to persistence; append-only attempts; budget state; pause/resume/retry commands and authorization; checkpoint model; primary/recovery evidence references; v2 recovery policy. | Queue migration; budget enforcement; artifact store; control API/CLI. | Overwritten primary facts or budget/infra outcomes entering the capability denominator. | Ambiguous retries, lease reclaim mistaken for resume, and duplicate external effects. | **No** for implementation/keyless simulation. Recovery/execution tests must use fakes until explicitly authorized. |
| Failure Clustering | Deterministic, versioned grouping over factual dimensions; diagnosis is labeled association; optional LLM prose is separate evidence; causality is never inferred from clustering. | Typed deterministic grouping currently hashes the full tuple of model, harness, task, language, family, failure class/scope, trace, tool, and workspace-diff patterns. Hypotheses and causal caveats exist. | `src/harnesslab/diagnosis/models.py`, `src/harnesslab/diagnosis/service.py`; `docs/BADCASES.md`; `tests/test_diagnosis.py`, `tests/test_workbench_api.py` | `PARTIAL` | Versioned projection definitions; choosable dimension subsets; missing/unknown semantics; cohort and cross-experiment aggregates; provenance for any optional generated explanation. | Trusted evidence reader; task/suite metadata; Workbench queries. | Correlation or cluster prevalence presented as root cause. | Over-fragmentation, unstable cluster identity, and sensitive-trace leakage. | **No**. LLM clustering is neither needed nor authorized for M.1. |

No capability is marked `COMPLETE`: the matrix grades the full Evaluation System 2.0 target, not isolated primitives.

## 3. Discriminative Suite contract

### Purpose

The Discriminative Suite measures whether preregistered configurations produce materially different verifier-backed outcomes. It is not a leaderboard selected after observing a preferred model, and it is not synonymous with “tasks on which one historical model failed.”

### Versioned membership

A future immutable `EvaluationSuiteManifest` should contain a suite ID/version, purpose `DISCRIMINATIVE`, exact `TaskIdentity` references, qualification-evidence references/digests, the frozen candidate configuration panel, admission-policy version, population/split role, coverage strata, admitted/rejected decisions, and supersession/retirement references. Membership is a sidecar relation. It must not mutate `TaskPackageManifest`, `TaskFamily`, or the frozen Core corpus merely to add a suite label.

### Proposed admission criteria

A task may be admitted only when all of the following are true:

1. **Deterministic validity:** its exact identity is qualified under the applicable Tier A or Tier B keyless gates; baseline fails, oracle passes, repeated health passes, and protected/hidden boundaries hold.
2. **Development-only screening:** admission data comes from a declared development population. A held-out task cannot be screened for discrimination and remain held out.
3. **Preregistered panel:** at least two fully specified configurations, comparison controls, repetitions, thresholds, and exclusions are frozen before observing results. The panel must be selected for intended product coverage, not because it makes a favored configuration win.
4. **Comparable coverage:** at least 80% of planned observations per configuration are capability-eligible, and the observations used for admission are `COMPARABLE`; infrastructure outcomes are reported separately and never converted to capability failures.
5. **Repeated evidence:** use `n=3` per configuration for qualification. For at least one preregistered pair, the task has at least two discordant comparable paired repetitions and the per-task pass-rate gap is at least `2/3`. Direction does not matter.
6. **No floor or ceiling:** across the complete preregistered panel the task has at least one verifier-backed pass and at least one verifier-backed capability failure. A universally passing or universally failing task is rejected for this suite, even if it remains useful elsewhere.
7. **Stability:** the qualifying contrast must reproduce in a second independently scheduled `n=3` qualification block, with the same direction and at least one discordant comparable pair. This is qualification evidence, not a license to keep rerunning until the threshold is met.
8. **Representation guard:** suite-level quotas by language, task family, scenario family, and benchmark role are frozen before final selection. When more candidates pass than a quota allows, selection uses a deterministic, system-neutral rule such as task-identity order or a committed seed.
9. **Audit trail:** all screened candidates, failures, exclusions, infrastructure attrition, and retirement decisions remain in an append-only ledger. Failed candidates cannot disappear from the denominator.

Thresholds are policy version `discriminative-admission-v1`; changing them creates a new policy and suite version. They are proposed contract values, not claims that any current task qualifies.

### Bias and leakage controls

- Configuration identity includes model route/observed model, harness/lane, reasoning effort, tools, context, resource envelope, and comparison controls. Renaming a cell does not create a new scientific condition.
- Admission uses symmetric difference. It cannot require that a named configuration wins.
- Results from `PARTIALLY_COMPARABLE` or `NOT_COMPARABLE` pairs may inform diagnostics but cannot satisfy admission.
- Task authors, prompts, harnesses, or resource envelopes may be tuned using development results only. Any such use records exposure.
- Qualification evidence expires for a future candidate panel when a material configuration/control dimension changes. Old evidence remains valid for its original claim.

### Existing tasks and need for new tasks

The eighteen Core tasks may be screened as **exposed development candidates** by referencing their immutable identities and historical evidence. Some may be discriminative for the exact historical V6 panel, but M.1 does not compute or assert membership, and that evidence cannot automatically qualify them for a future panel. They may never be represented as untouched holdout tasks.

The three Tier B repository tasks may also be screened after an authorized model/configuration pilot. Their keyless qualification proves task integrity, not discrimination; `release/tier-b-smoke-preregistration.json` and `release/tier-b-smoke-keyless-plan.json` remain `NOT_RUN` with zero real provider calls.

New tasks will be required if admitted candidates fail representation quotas, if the panel has floor/ceiling behavior, or if product-relevant capabilities are absent. New tasks must be authored and qualified under the same preregistered rules; they are not automatically better because they are new.

### Required audit tasks before implementation claims

- Produce a keyless candidate inventory that joins exact task identity, quality evidence, provenance, exposure, historical evidence availability, and representation strata.
- Define the candidate configuration panel and intended population without using outcome data.
- Build a read-only historical screener that reports what the proposed policy would decide, labeled retrospective and non-qualifying.
- Add adversarial tests for favored-system thresholds, dropped failures, infrastructure-to-capability conversion, noncomparable admission, and post-hoc quota changes.
- Require a separate authorization artifact before any fresh empirical qualification run.

## 4. Stress Suite contract

### Purpose

The Stress Suite measures behavior under identifiable engineering pressure. Repository size, token count, or runtime alone is insufficient: arbitrary bloat can raise all three without increasing task complexity.

### Stress dimensions and measurable evidence

Every candidate must pass deterministic task qualification and satisfy at least three stress dimensions below. At least one qualifying dimension must be `trajectory`, `context`, or `protocol`, so a three-file edit cannot qualify solely through structural labels.

| Dimension | Proposed measurable admission criterion | Required evidence |
| --- | --- | --- |
| Long trajectory | In two independently scheduled successful qualification blocks, median normalized trajectory has at least 8 semantic events and at least 4 tool invocations, without counting heartbeats or duplicate retries. | Immutable normalized traces bound to exact task/configuration/envelope; fresh external execution authorization required. |
| Multi-file / multi-module | Oracle patch changes at least 3 files across at least 2 directories or declared modules, and the verifier contains an assertion whose success depends on the cross-boundary behavior. | Oracle diff summary plus verifier coverage map; keyless. |
| Tool dependence | Success requires at least 2 distinct declared tool capabilities, or one repository tool plus a separate build/test tool, and withholding each required capability produces the preregistered failure boundary. | Expected-tool contract and keyless capability-withholding tests where safe; otherwise authorized controlled run. |
| Repair-loop pressure | At least 2 independently useful partial states are specified; each passes a distinct milestone but fails final verification for a different factual reason. A successful trajectory must demonstrate evidence collection after an initial failing check, not merely repeated identical commands. | Milestone fixtures/keyless verifier tests plus normalized trace evidence for the behavioral portion. |
| Dependency/build complexity | A frozen manifest/lock identity is required and the task crosses at least 2 deterministic phases such as compile/build and test/integration. Dependencies must be cached or allowed by the declared network policy. | Manifest/lock digests, phase commands, baseline/oracle evidence; keyless. |
| Context pressure | The visible workspace contains at least 20 relevant source/config/test files or 50 KiB of relevant text, with a relevance manifest identifying the dispersed facts needed by the oracle. Generated/vendor bulk is excluded. | Frozen workspace inventory and relevance manifest; keyless. |
| Protocol sensitivity | The task requires a structured tool/runtime protocol, and at least 2 distinct injected protocol faults are correctly classified as infrastructure/tool failures without corrupting capability scoring. | Fault-injection fixtures and classification tests; keyless unless the real protocol itself must be qualified. |

The suite manifest records the satisfied dimensions and exact evidence for each. It also freezes portfolio floors: at least three tasks per represented dimension, at least two languages where the dimension is language-independent, and no single task contributes more than one third of all dimension credits. Until those floors are met, the suite is a candidate set, not a released Stress Suite.

### Current candidates

`repo-java-widget-update`, `repo-python-ledger-transfer`, and `repo-typescript-resilient-client` are credible candidates because their Tier B artifacts prove repository snapshot integrity, hidden-asset isolation, robustness, and multi-file/multi-module work. The current evidence does not prove the trajectory, context, protocol, or tool-dependence thresholds above. They therefore cannot be silently promoted to Stress membership.

New tasks are required to cover missing dimensions and portfolio floors. Candidate creation should prefer natural repository constraints over artificial file/token inflation. A future task may be a member of both a purpose suite and a quality tier; those axes must remain distinct.

## 5. Task quality, difficulty, suite purpose, and identity

### Separate axes

| Axis | Meaning | Allowed use |
| --- | --- | --- |
| Task identity | Exact task ID/version plus task, workspace, and verifier digests. | Scientific and execution identity; any semantic change requires a new identity/version. |
| Quality qualification | `DEV_CANDIDATE`, `QUALIFIED`, or `RETIRED`, backed by Tier A/Tier B-style evidence. | Whether the task is trustworthy enough to execute or report. It does not say the task is hard. |
| Suite membership | `CORE`, `DISCRIMINATIVE`, or `STRESS`, versioned as a sidecar membership. | Why the task is selected. A task may appear in more than one suite version if each membership is independently justified. |
| Difficulty / stress profile | Observed pass-rate band and factual stress dimensions, each tied to a population, configuration panel, and evidence version. | Description and stratification. It must not substitute for verifier quality. |
| Population / exposure | `DEVELOPMENT` or `HELD_OUT`, plus exposure status and events. | Controls tuning and claim eligibility. Holdout is not a quality tier. |

The existing `BenchmarkTier.TIER_A/TIER_B` is best retained as a qualification-method family, not redefined to mean easy/hard or Core/Stress. Existing free-form `metadata.difficulty` is descriptive only until governed by an evidence-backed schema.

### Required identity and metadata

A suite membership record needs: suite ID/version/purpose; exact `TaskIdentity`; package path as a locator, never authority; qualification artifact identity/digest/policy version; provenance and parent identities; development/holdout split identity; exposure state; visibility policy for instruction, workspace, public tests, verifier, oracle/gold, and results; representation strata; difficulty observation with configuration/evidence scope; discriminative admission metrics when applicable; stress dimensions when applicable; admitted/rejected/retired state; reason codes; actor/authorization reference; timestamps; supersedes/superseded-by references.

Derived tasks inherit lineage exposure. A new version does not become unseen merely because its digest changes. A material instruction, workspace, verifier, oracle, or expected-tool change creates a new task identity and requires requalification; historical identities and evidence remain immutable.

## 6. Leakage-resistant Development / Holdout contract

### Development population

- Instructions, workspaces, public tests, and development outcomes may be used for task authoring, prompt/harness tuning, admission screening, debugging, and regression work.
- Hidden verifier/oracle assets remain access-controlled even for development use. Their results may be exposed according to policy, but raw gold artifacts are not automatically exportable.
- Every qualifying use records task identity, lineage, actor/system, purpose, visibility level, experiment/claim reference, and time in an append-only exposure ledger.

### Held-out population

- Entry requires `NOT_USED` exposure for the task and every provenance ancestor. `UNKNOWN` fails closed.
- Instruction/workspace access is limited to the declared execution window. Verifier/oracle/gold contents remain sealed from model, harness author, task tuner, and result-selection logic.
- The population and selection rule are frozen before the claim. Failures, infrastructure attrition, and exclusions stay visible.
- Holdout results may answer the preregistered claim once. Using results to change tasks, prompts, harnesses, models, routing, envelopes, thresholds, or selection irreversibly demotes the affected task/lineage to development for later claims.
- Repeated measurement is allowed only when preregistered as repetitions for the same claim. A later claim requires a fresh eligible holdout population or an explicitly labeled exposed-regression result.

### Promotion, demotion, and versioning

- `DEVELOPMENT -> HELD_OUT` is forbidden after any exposure. The safe path is to source a new, non-overlapping lineage and qualify it without outcome-guided tuning.
- `HELD_OUT -> DEVELOPMENT` is an irreversible event once outcome-relevant information is used or leaked.
- `QUALIFIED` is orthogonal: both development and held-out tasks must be qualified. Qualification never erases exposure.
- Any semantic task change creates a new identity, but lineage constraints still prevent the child and an exposed ancestor from straddling development and holdout.
- Split and exposure policy changes create a new frozen split/policy version; old claims keep their original binding.

### Core disposition

The released eighteen-task Core corpus has been used throughout historical qualification, smoke, Matrix, diagnosis, release reconciliation, tests, and documentation. It is exposed. It can serve Core regression and Discriminative development screening, but it is **not an untouched holdout** and must never be advertised as one. The existing split model correctly rejects `USED` and `UNKNOWN` holdout identities; a canonical exposure ledger must make this product-enforceable rather than dependent on institutional memory.

## 7. Cost and Budget reconciliation

### Generic product capability already present

The generic budget package can deterministically estimate heterogeneous subject and Judge components, call counts, input/output tokens, provider requests, harness turns, exact-Decimal cost, known/unknown prices, and ceiling status. Methodology contracts already name wall-clock time and tool calls as additional dimensions. Registry runtime resolution can constrain a Direct cell to its frozen output/turn/request envelope. This is reusable foundation and should be extended, not replaced.

### K-B/K-C controls that must remain release-specific

V6 smoke/Matrix selections, fixed call ceilings, particular provider routes, attempt receipts, CNY assumptions, partial-budget-stop evidence, real-call authorization flags, canary/pilot/remaining behavior, and accepted recovery bindings describe one historical release campaign. They should be adapted only through generic interfaces; their frozen artifacts and semantics must not be rewritten or generalized by importing campaign IDs into product models.

### Target budget contract

Every future plan freezes envelopes at run, stage, and campaign scope for:

1. wall-clock seconds;
2. output tokens;
3. model/harness turns;
4. tool calls;
5. provider requests; and
6. monetary cost with currency and authoritative pricing-evidence reference.

Each dimension is `ENFORCED`, `OBSERVED_ONLY`, or `NOT_AVAILABLE`. `UNKNOWN` price never becomes zero. The executor reserves the next bounded unit of work atomically, refuses it if the campaign ceiling would be exceeded, records normalized observed usage, and reconciles estimate/reservation/actual. Hitting an enforced ceiling terminates the attempt as `BUDGET_EXHAUSTED`, preserves all immutable traces and verifier facts, and prevents automatic retry. Reports state which partial outcomes remain scientifically usable; they never coerce budget termination into ordinary task failure.

At the baseline, `execution_budget_exhausted` from harness lanes is included in the capability denominator by `src/harnesslab/experiment/outcomes.py` and is explicitly tested in `tests/test_experiment_statistics.py`. Evaluation System 2.0 must decide this using the frozen contract: task-level inability within an intentionally comparable resource envelope may remain a capability failure, while campaign/operator budget exhaustion is lifecycle `BUDGET_EXHAUSTED`. The two need distinct source reason codes and must not be merged by string similarity.

No current pricing lookup, provider call, or real execution is needed to implement or test this contract. Tests use supplied price fixtures and fake usage streams.

## 8. Funnel Evaluation contract and reconciliation

### Target stages

| Stage | Name | Required input | Exit evidence | External execution authorization |
| --- | --- | --- | --- | --- |
| 0 | Preflight | Exact frozen plan/snapshot, task/suite identities, runtime declarations, budget and network policy. | Passing immutable preflight receipt bound to plan digest; zero provider/Judge calls. | Never for generic preflight. |
| 1 | Smoke `n=1` | Stage 0 receipt and a frozen one-repeat selection. | All scheduled slots terminal or explicitly accounted for; capability/infra split; budget reconciliation; explicit decision. | Required. |
| 2 | Informal `n=3` | Eligible Stage 1 evidence and frozen three-repeat plan. | Per-task `n=3` evidence, comparability/coverage checks, explicit decision. | Required. |
| 3 | Formal `n=5` | Eligible Stage 2 evidence and frozen five-repeat plan. | Formal evidence tier where available, all exclusions visible, explicit decision. | Required. |
| 4 | Discriminative | Versioned Discriminative Suite and eligible earlier-stage configuration identities. | Suite-scoped comparison report; no automatic claim or promotion. | Required. |
| 5 | Stress | Versioned Stress Suite, compatible envelopes, and eligible earlier evidence. | Stress-dimension and outcome report, budget/infra facts, explicit terminal decision. | Required. |

Stage numbers are product semantics. The current `SMOKE` can map to Stage 1, `INFORMAL` to Stage 2, and `FORMAL` to Stage 3. `BREADTH` is a selection shape rather than a target stage and should become plan metadata. Current `DISCRIMINATIVE_STRESS` must split into Stages 4 and 5. Frozen `release/evaluation-methodology-v2.json` remains unchanged; a new methodology version supplies the new vocabulary.

### Promotion decision

Every transition uses an immutable `StageDecision` containing source/target stages, exact plan and report digests, suite/split/policy versions, coverage and comparability facts, budget facts, decision `GO/STOP`, reason codes, actor/authorization identity, and creation time. `GO` is valid only when the target entry policy and source exit policy are mechanically satisfied. The decision authorizes plan creation for the next stage, not execution.

There is no auto-promotion. The current `auto_promote=false` invariant is retained. A scheduler, UI, or API may recommend a transition, but it cannot create a `GO` decision or start external work without the explicit decision and separate execution authorization.

### Evidence chain and reuse

- A later stage references earlier immutable evidence; it does not copy or relabel it.
- Earlier completed slots may be reused only when task, cell, controls, envelope, repeat index, methodology, and evidence eligibility are identical. The plan lists reused and newly scheduled slot IDs explicitly.
- Reuse cannot turn `n=1` into three independent observations or mix recovery evidence with primary evidence without a preregistered policy.
- Any material identity/control change starts a new chain. Old evidence remains reportable for its original claim.
- Stage 4/5 results never retroactively qualify suite membership unless the run was explicitly preregistered as qualification evidence.

## 9. Experiment Preflight classification

Classification concerns the reusable implementation at this baseline. A reusable presence/syntax check may still have a documented depth gap.

| Target check | Current implementation and evidence | Classification | Reconciliation gap |
| --- | --- | --- | --- |
| Docker | Runtime availability inspection with no provider calls. | `GENERIC_REUSABLE` | Bind normalized result to the exact plan and required runtime version/capabilities. |
| Database | Readiness check exists. | `GENERIC_REUSABLE` | Prove required schema/migrations and queue permissions, not merely reachability. |
| Disk | Free-space check exists. | `GENERIC_REUSABLE` | Derive threshold from plan/artifact envelope and record filesystem identity. |
| Images | Required local image presence is checked without pulling. | `GENERIC_REUSABLE` | Bind immutable image digest/platform, not tag alone. |
| Credentials presence | Required configuration names/presence and format are checked without emitting secret values. | `GENERIC_REUSABLE` | Normalize provider/runtime requirements from plan and preserve strict redaction. |
| Provider route identity | Syntax, configured route, and frozen identity consistency are checked without a probe. | `GENERIC_REUSABLE` | Keep this distinct from live availability. |
| Provider route live availability | Release/operator flows have campaign-specific observations, but generic preflight deliberately does no provider call. | `MISSING` | If ever required, implement as a separately authorized Stage 1 smoke, never disguise it as keyless preflight. |
| Harness runtime presence | Executable presence and declared support are checked. | `GENERIC_REUSABLE` | Add a keyless self-test/version/capability handshake where the runtime supports it. |
| Release runtime/operator health | V6 and registry paths contain campaign/route-specific health assumptions and authorization checks. | `RELEASE_SPECIFIC` | Consume through an adapter; do not move release IDs or historical states into generic preflight. |
| Task validity | Package load plus behavioral baseline/oracle validation exists. | `GENERIC_REUSABLE` | Cache only by exact identity and qualification-policy version. |
| Lane support | Task-declared and runtime lane support are checked. | `GENERIC_REUSABLE` | Reconcile declaration with the exact selected binding implementation. |
| Model/harness compatibility | Declared compatibility and registry binding checks exist. | `GENERIC_REUSABLE` | Make incompatibility blocking and bind observed model only after execution; preflight must not claim observation. |
| Network policy | Task/runtime/provider policy consistency is checked. | `GENERIC_REUSABLE` | Verify effective container/runtime egress configuration where keylessly observable. |
| Comparability risk | Frozen controls are compared and risk can be reported. | `GENERIC_REUSABLE` | Formal stages must fail closed on blocking control differences; current optional nonblocking mode is insufficient. |
| Estimated budget | Calls, tokens, requests, turns, cost, known/unknown pricing, ceilings, and matrix components are estimated. | `GENERIC_REUSABLE` | Add wall/tool dimensions, stage/campaign scopes, reservations, and actual reconciliation. |
| Canary/full-Matrix spend receipt | V6 selection-specific limits and real-run authorization exist. | `RELEASE_SPECIFIC` | Replace with generic stage selection plus explicit authorization; preserve the frozen receipts. |

The target service should accept the immutable experiment snapshot/plan as its authority, derive all checks through adapters, emit one digest-bound receipt, and make the executor verify that receipt immediately before claiming work. It must not make provider or Judge calls.

## 10. Run Lifecycle and operator controls

### Semantic state model

| Target state | Baseline mapping | Required reconciliation |
| --- | --- | --- |
| `QUEUED` | Persisted. | Retain. |
| `PREPARING` | Persisted; legacy `CLAIMED` adapts to it. | Make preparation/lease facts append-only attempt events. |
| `RUNNING` | Persisted. | Bind heartbeat and consumption ledger to attempt. |
| `VERIFYING` | Persisted; legacy `SCORING` semantically maps here. | Treat scoring as an internal substate, not a distinct external outcome. |
| `COMPLETED` | Persisted. | Require evidence digest and terminal usage reconciliation. |
| `FAILED_CAPABILITY` | Persisted as `FAILED_SUBJECT`; lifecycle adapter exists. | Migrate external vocabulary without rewriting historical manifests. |
| `FAILED_INFRA` | Persisted. | Require typed reason and recovery eligibility decision. |
| `CANCELLED` | Persisted and cancellation can be requested. | Persist requester/reason/time and define cooperative termination boundary. |
| `BUDGET_EXHAUSTED` | Exists only in the detached lifecycle value model; not in `RunStatus`/DB queue. | Persist it and distinguish run-envelope capability exhaustion from campaign/operator budget stop. |

### Control semantics

| Operation | Target semantics | Baseline reality | Contract decision |
| --- | --- | --- | --- |
| Pause | Stop new claims at experiment/stage scope; running attempts reach a declared safe boundary. | No general operator pause state/API. Provider availability can indirectly suppress claims. | New durable control event; never mutate completed evidence. |
| Resume | Clear a pause after revalidating plan, preflight, budget, and leases; continue only remaining logical slots. | Re-running `run_bounded` consumes remaining queued slots, but this is not an explicit pause/resume contract. | New authorized resume event. Existing idempotent queue selection is reused. |
| Cancel | Prevent new claims and cooperatively stop active attempts; record terminal evidence when safe. | Queue cancellation flag and transition checks exist; no full CLI/Workbench control plane. | Extend existing cancellation with scoped request/receipt and product API. |
| Retry infrastructure failure | Create a new attempt only when typed policy and explicit authorization permit it; primary attempt remains immutable. | V1 requeue resets row fields; methodology-v2 recovery is rejected; detached lifecycle permits one recovery. | Wire append-only attempt ledger; default max one; no automatic external retry. |
| Retry selected tasks | Freeze exact slot IDs, reason, attempt policy, budget, and authorization. | Executor accepts low-level `slot_ids`, but no governed retry request exists. | Add immutable selection/control record. |
| Run remaining tasks | Select queued, never-started logical slots from the original plan; do not recreate completed slots. | Bounded executor and release `remaining` behavior demonstrate the primitive. | Generalize selection and receipt; retain idempotent enqueue. |
| Checkpoint/resume within a run | Resume only from a task/runtime-declared deterministic checkpoint whose digest and external-effect semantics are verified. | No generic checkpoint model. Lease reclaim restarts an attempt and is not checkpoint resume. | Default is a new attempt; checkpoint support is future opt-in, never inferred. |

Pause, resume, cancel, retry, and remaining-run operations are semantic control records, not cosmetic status edits. They cannot change primary outcomes, evidence bytes, or prior attempt states.

### Attempt and evidence invariants

- A logical slot has one immutable primary attempt identity and zero or more separately identified recovery attempts.
- Every attempt has an append-only state/event ledger, resource ledger, authorization reference, artifact identity/digest, and terminal reason.
- Lease expiry may make work recoverable but does not prove the previous attempt produced no external effect. Reclaim must create/reconcile an attempt explicitly.
- Recovery never overwrites primary evidence or silently becomes the primary outcome. Reports state the selection policy.
- Methodology-v2 recovery remains blocked until this durable contract exists. Frozen V6 recovery bindings remain historical examples, not rows to migrate or rewrite.

## 11. Failure clustering, diagnosis, explanation, and causality

Four layers must remain separate:

1. **Deterministic grouping:** verified facts are normalized and grouped by a versioned projection of model, harness, task, language, task family, failure class/scope, trace pattern, tool pattern, and workspace-diff pattern. Same inputs and policy produce the same cluster identity.
2. **Diagnostic association:** rules or analysts may attach hypotheses such as correlation or controlled-ablation association. The statement names the supporting and contradicting evidence and remains a hypothesis.
3. **LLM-generated explanation:** optional future prose may summarize an already formed cluster. It is a separate artifact bound to prompt/model/input digests, clearly labeled generated, redacted, and unable to add/remove members, alter failure class, or raise causal strength. No LLM clustering or explanation is needed for M.1.
4. **Causal attribution:** clustering never establishes causality. Even controlled ablation supports only the scoped association permitted by comparability and design. A root-cause claim requires a separately defined causal standard and evidence.

The current exact full-tuple grouping is deterministic and useful, but may split one phenomenon by task ID or exact trace/diff pattern. A future `ClusterProjection` must name a subset of dimensions, normalization version, missing/unknown behavior, cohort filters, and evidence cutoff. Raw-fact identities stay stable; derived cluster identities change when the projection version changes. Cross-experiment views must never merge incompatible evidence or expose raw secrets.

## 12. Scientific and engineering invariants

1. **Capability denominator:** infrastructure failures, cancellation, and campaign/operator budget exhaustion remain outside the capability denominator. A task-level failure within an intentionally comparable resource envelope may enter it only under the frozen outcome policy.
2. **Verifier authority:** deterministic L0 verification is authoritative. A Judge, diagnosis, or narrative cannot reverse it.
3. **Trace boundary:** Trace supports factual diagnosis and association, not causality.
4. **Identity before label:** tasks, cells, suites, plans, controls, pricing inputs, decisions, runs, attempts, and reports are referenced by immutable identity/digest. Paths and display names are locators only.
5. **No evidence rewriting:** frozen K-B/K-C release artifacts, primary attempts, and historical states are never edited to satisfy a new contract.
6. **Truthful execution state:** `NOT_RUN`, `NOT_REACHED`, infrastructure failure, cancellation, and budget exhaustion remain distinct from capability failure and success.
7. **No automatic promotion:** every funnel transition is an explicit evidence-bound decision and execution requires separate authorization.
8. **No optional stopping:** repetitions, thresholds, exclusions, and candidate panels are preregistered. Failed candidates and infrastructure attrition remain visible.
9. **Comparability fails closed:** noncomparable evidence cannot support formal comparative or causal claims; partial comparability is labeled and limited.
10. **Observational limits:** observed differences, clusters, correlations, and generated explanations do not automatically become causal or root-cause claims.
11. **Holdout leakage is irreversible:** qualification or versioning cannot erase exposure or provenance lineage.
12. **Difficulty is not quality:** task validity, suite purpose, observed difficulty, stress dimensions, and exposure are independent axes.
13. **Budgets fail closed:** unknown price is not zero; no next unit of work starts beyond an enforced reservation; partial evidence is preserved.
14. **Attempts are append-only:** retries/recovery create new attempt identities; primary evidence remains immutable and recovery remains separately identifiable.
15. **Idempotent logical scheduling:** enqueue/resume/remaining operations cannot duplicate a logical slot, while attempt identity still distinguishes actual re-execution.
16. **Official / Custom isolation:** Official task, suite, plan, evidence, and claim namespaces remain isolated from Custom evaluation; Custom evidence cannot satisfy Official qualification or release claims.
17. **Preflight is keyless:** generic Stage 0 performs zero provider/Judge calls and cannot claim live observed-model or route availability.
18. **Core history remains scoped:** historical V6/K-C results prove only their bound tasks, configurations, controls, evidence, and claims.
19. **Secrets and hidden assets stay isolated:** manifests, reports, logs, exports, and generated explanations disclose only allowlisted normalized facts.

## 13. Reuse map

| Capability | Decision | Reuse boundary |
| --- | --- | --- |
| Discriminative Suite | `NEW_COMPONENT` | Add a sidecar suite/admission contract while reusing task identities, qualification, planning, comparability, and statistics. Do not add mutable labels to task packages. |
| Stress Suite | `NEW_COMPONENT` | Add stress rubric/membership/evidence contracts while reusing Tier B qualification, traces, tools, and verifiers. |
| Task Quality Tiers | `EXTEND_EXISTING` | Keep `quality.py`, `splits.py`, and Tier A/B semantics; add orthogonal membership, governed descriptors, and lifecycle references. |
| Dev / Holdout | `EXTEND_EXISTING` | Keep fail-closed split/lineage validation; add durable exposure events, visibility policy, and claim windows. |
| Cost and Budget | `EXTEND_EXISTING` | Extend generic estimator with missing dimensions and consumption/reservation integration. Treat V6 controllers only as adapter/test inputs. |
| Funnel Evaluation | `EXTEND_EXISTING` | Version methodology and planning; retain explicit decisions and `auto_promote=false`; split stage vocabulary and add decision evidence. |
| Experiment Preflight | `EXTRACT_AND_GENERALIZE` | Project one generic receipt from the plan using existing generic/registry checks; isolate release-specific overlays behind adapters. |
| Run Lifecycle | `EXTEND_EXISTING` | Wire the stricter lifecycle/attempt model into the existing queue/executor/DB. Do not build a second executor. |
| Failure Clustering | `EXTEND_EXISTING` | Preserve normalized facts and current diagnosis; add versioned projections and aggregate queries. |

## 14. Bounded implementation slices

Each slice is a separate reviewable task. No slice authorizes real provider/Judge execution by itself.

### Slice 1 — Versioned Evaluation Suite Manifest

- **Objective:** implement immutable sidecar manifests for Core, Discriminative, and Stress membership, with exact task/qualification/split identities, policy versions, decisions, and supersession.
- **Dependencies:** existing `TaskIdentity`, `TaskQualification`, `TaskSplitFreeze`, canonical digest utilities.
- **Likely modules:** new `src/harnesslab/evaluation_suites/`; adapters in `src/harnesslab/tasks/`; schemas only, no DB migration.
- **Acceptance:** strict/fail-closed models; canonical digest; duplicate/lineage/conflicting-membership rejection; Core v4 can be referenced without mutation; no membership is fabricated.
- **Validation:** focused unit tests, mutation/adversarial tests, keyless load of existing task identities.
- **External authorization:** none; real calls must remain zero.
- **Stop condition:** stop if implementing membership requires changing a frozen package/corpus/evidence artifact; use a sidecar reference instead.

### Slice 2 — Quality, admission, and exposure governance

- **Objective:** encode versioned Discriminative and Stress admission policies, qualification/rejection records, visibility rules, exposure events, irreversible demotion, and claim-scoped holdout eligibility.
- **Dependencies:** Slice 1; existing quality/split/Tier B contracts.
- **Likely modules:** `src/harnesslab/evaluation_suites/`, `src/harnesslab/tasks/quality.py`, `src/harnesslab/tasks/splits.py`; optional append-only persistence designed separately.
- **Acceptance:** difficulty/quality/purpose/exposure axes remain distinct; favored-system and lineage-leak cases fail; existing Core resolves only as exposed development; Tier B tasks resolve only as Stress candidates.
- **Validation:** property/mutation tests for threshold symmetry, lineage overlap, `UNKNOWN` exposure, demotion, policy versioning, and hidden-asset redaction.
- **External authorization:** none for contracts and fixtures.
- **Stop condition:** stop before any candidate empirical qualification or access to sealed holdout assets.

### Slice 3 — Funnel v3 and immutable Stage Decisions

- **Objective:** add target stages 0–5, evidence-bound `StageDecision`, stage entry/exit policy, explicit reuse/new-slot selection, and plan support for Discriminative/Stress.
- **Dependencies:** Slices 1–2; existing methodology, plan, report, statistics, comparability.
- **Likely modules:** `src/harnesslab/experiment/methodology.py`, `plan.py`, new decision model/service, registry projection.
- **Acceptance:** no automatic promotion; a bare `GO` fails; identity/control drift starts a new chain; reused slots are exact; frozen methodology-v2 artifact remains byte-identical.
- **Validation:** keyless transition matrix and adversarial evidence-digest/control/repetition tests.
- **External authorization:** none.
- **Stop condition:** stop if a transition can schedule or execute external work without both a valid decision and separate authorization.

### Slice 4 — Plan-derived generic preflight and budget reservation

- **Objective:** consolidate generic/registry checks into one plan-derived receipt, add wall/tool estimates, scoped reservations, unknown-price policy, and execution-time receipt verification.
- **Dependencies:** Slice 3; current preflight/budget/runtime registry.
- **Likely modules:** `src/harnesslab/preflight/`, `src/harnesslab/budget/`, `src/harnesslab/registry/runtime.py`, experiment plan adapter.
- **Acceptance:** zero external calls; all target dimensions have normalized check IDs and blocking policy; release-specific checks use adapters; concurrent fake reservations cannot exceed a ceiling.
- **Validation:** deterministic fake runtimes/prices/usage, race tests, plan-drift tests, secret-redaction tests.
- **External authorization:** none; a live route probe is out of scope.
- **Stop condition:** stop if a check would contact a provider/Judge or if unknown price is treated as zero/approved.

### Slice 5 — Durable lifecycle, attempts, and controls

- **Objective:** make the Phase M lifecycle authoritative in persistence, add append-only attempts/resource events, `BUDGET_EXHAUSTED`, and scoped pause/resume/cancel/retry/remaining controls.
- **Dependencies:** Slice 4; existing queue/executor/artifact contracts.
- **Likely modules:** `src/harnesslab/experiment/lifecycle.py`, `src/harnesslab/experiment/queue.py`, `src/harnesslab/experiment/executor.py`, `src/harnesslab/contracts/run.py`, DB models/migration, CLI/API controls.
- **Acceptance:** primary evidence cannot be overwritten; v2 recovery requires an authorized new attempt; remaining work is idempotent; checkpoint resume is rejected unless explicitly supported; operator state is read back exactly.
- **Validation:** fake-binding end-to-end tests, crash/lease/concurrency/cancel/budget-stop tests, migration compatibility tests.
- **External authorization:** none; all execution tests use deterministic fakes.
- **Stop condition:** stop if migration cannot preserve historical statuses/artifact references or if retry can create unbounded attempts.

### Slice 6 — Versioned failure-cluster projections and product read surfaces

- **Objective:** add projection policies, missing/unknown semantics, cohort/cross-experiment aggregation, and clearly separated deterministic facts, diagnostic associations, and optional explanations.
- **Dependencies:** Slices 1 and 5; trusted evidence and Workbench services.
- **Likely modules:** `src/harnesslab/diagnosis/`, `src/harnesslab/api/workbench_service.py`, Workbench read models/UI.
- **Acceptance:** cluster identities reproduce; changing projection versions does not rewrite raw facts; generated text cannot change membership/causal strength; secrets remain redacted.
- **Validation:** deterministic golden/property tests and API tests using synthetic evidence only.
- **External authorization:** none; no LLM call is required or allowed by default.
- **Stop condition:** stop if aggregation requires weakening evidence validation or if UI language implies causal attribution.

### Slice 7 — Candidate qualification and bounded staged evidence

- **Objective:** inventory existing candidates, author only the missing task coverage, run keyless qualification, then—under a separate explicit authorization—collect bounded Discriminative/Stress qualification and funnel evidence.
- **Dependencies:** Slices 1–6 complete and independently reviewed; approved candidate panel, pricing inputs, preflight receipt, budget, and execution authorization.
- **Likely modules:** suite manifests/policies, new task packages only where coverage requires them, standard experiment planner/executor/reporter.
- **Acceptance:** all candidates/rejections remain visible; Core is development-only; Tier B is not pre-promoted; qualification thresholds/quotas are preregistered; primary/recovery evidence is separate; reports make no unsupported performance or causal claim.
- **Validation:** keyless gates first, then bounded Stage 1→later execution only as authorized; independent readback and digest verification after each stage.
- **External authorization:** **required** for every provider/Judge execution stage; authorization states exact plan, selection, maximum calls/cost, and stop policy.
- **Stop condition:** stop on preflight failure, missing/unknown price where policy requires cost enforcement, budget ceiling, unauthorized next stage, evidence-integrity failure, or unmet promotion criteria. Never rerun merely to obtain a favorable result.

## 15. Exactly one recommended next task

**Phase M.2 — Implement the Versioned Evaluation Suite Manifest contract (Slice 1).**

This is the smallest high-leverage foundation: it creates an immutable place to express Core, Discriminative, and Stress membership while reusing existing task identities, qualification, splits, and digests. It requires no database migration, no pricing data, no external call, and no frozen artifact change. All later admission, holdout, funnel, preflight, lifecycle, and reporting work can then reference one stable suite identity instead of introducing incompatible labels in multiple subsystems.

M1_EVALUATION_SYSTEM_2_RECONCILIATION_READY
