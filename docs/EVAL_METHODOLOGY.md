# Evaluation methodology

Phase A establishes vocabulary and contracts. Phase B implements deterministic task validation,
Phase C isolates untrusted workspace verification, Phase D implements the first M-Lane direct
model path, Phase E implements the Codex H-Lane, and Phase F adds Claude/DeepSeek H-Lanes plus
deterministic evidence comparability. Phase G implements the experiment engine, repeated-run
statistics, P-Lane pairing, and controlled ablation. Phase H implements suite-scoped Judge
calibration as an L2 layer.

## Evaluation lanes

- **M-Lane (Model-only Evaluation):** evaluate model capability through direct model execution,
  without a coding harness, while holding task conditions stable. Phase D supplies deterministic
  subject-visible text and accepts only a strict JSON patch; the model receives no tools, hidden
  verifier, or oracle.
- **H-Lane (Harness Evaluation):** evaluate a coding harness through its tools and workspace while
  holding the requested model, task, and verifier facts stable. Phases E/F record frozen runtime,
  profile, safe trajectory coverage, and final workspace, then delegate correctness exclusively
  to the isolated hidden verifier.
- **P-Lane (Paired Model-vs-Harness Evaluation):** compare direct-model execution with harness
  execution on controlled micro tasks where the necessary context and verifier are equivalent, in
  order to measure harness uplift. Phase G pairs exact task/repeat slots and requires the Phase F
  Comparability result before a pair can enter formal statistics.
- **J-Lane (JudgeLab):** calibrate and compare judging methods against stronger references.

## Evidence hierarchy

**Deterministic Ground Truth > Human Gold > LLM Judge.** Hidden tests, builds, lint, schemas,
explicit rules, and protected-file checks must not be overridden by an LLM's preference. Human
gold labels cover questions deterministic checks cannot settle. LLM judges are calibrated aids,
not an authority over reproducible facts.

## Deterministic task polarity

A Phase B task package is accepted only when the untouched baseline fails its hidden verifier and
a separately materialized oracle overlay passes. This baseline-fail/oracle-pass rule detects
vacuous tests and broken reference solutions before the task can become evaluation evidence.
Verifier reports may contain bounded partial scores and per-check outcomes; a score is evidence,
not permission to reinterpret a failing verifier as a pass.

Malformed verifier output, timeout, non-zero verifier exit, or protected-file mutation fails
closed and remains distinguishable from an ordinary subject result. Phase B executes only trusted
repository fixtures on the host. It does not claim sandbox isolation for untrusted code.

## Outcome and trajectory

Outcome evidence asks whether the final artifact is correct. Trajectory evidence asks how the
system reached it: tool calls, retries, edits, costs, and policy compliance. A successful outcome
does not erase a problematic trajectory, and an efficient trajectory does not turn an incorrect
artifact into a success.

## Comparability

A comparison is meaningful only when task/version/digest, input workspace, context, verifier,
requested and observed model, provider route, resource budget, network policy, harness/profile,
prompt, and trace coverage are explicit. Phase F implements a deterministic assessment of these
facts; it does not infer absent identities.

For `HARNESS_UPLIFT`, task/workspace/context/verifier/model/route/budget/network fields are hard
controls, while harness/profile/prompt differences are intended treatments. A missing observed
model yields `PARTIALLY_COMPARABLE`; a known observed-model mismatch yields `NOT_COMPARABLE`.
Incomplete trace coverage limits trace-dependent attribution but does not erase final correctness.
`MODEL_COMPARISON` treats requested/observed model differences as its declared treatment.

Requested model is the model identifier sent by the experiment definition. Observed model is the
identity reported or otherwise evidenced during the run. They can differ because aliases,
routing, fallbacks, or provider changes exist, so the Run contract stores them separately.

Phase D preserves both identities in direct-model evidence. A missing observed identity does not
invalidate an otherwise completed invocation; a mismatch remains explicit evidence for later
comparability analysis.

Phase E applies the same separation to Codex. If native JSONL does not expose the routed model,
`observed_model` remains null with `not_exposed` status; HarnessLab never copies the requested
identity into an observed field. Phase F consumes this evidence without guessing the missing value.

## H-Lane outcome authority

Codex, Claude, and DeepSeek public messages, native file-change events, and process exit status
describe trajectory, not task correctness. HarnessLab hashes the real workspace before and after
the harness, scans artifacts for
run credentials, and sends the final workspace to the isolated deterministic verifier. Thus an
agent message claiming success followed by `turn.completed` and exit zero can still produce
`VERIFIED_FAIL`. Harness failures remain separate from verifier failures.

## Repeated experiments and failure attribution

Single runs are samples, not stable rankings. Phase G labels one valid capability observation
per intended task `SMOKE`, at least three per task `INFORMAL`, and at least five per task `FORMAL`
when controls are valid. Observations from unrelated tasks are never pooled to upgrade this tier.
An n=1-per-task smoke cannot enter formal ranking, paired claims, or confidence-interval
conclusions. Formal paired evidence similarly requires five `COMPARABLE` pairs per intended task.

Infrastructure failures (service outage, sandbox startup, credential routing, worker, verifier,
or artifact failure) are classified separately from capability failures. The capability success
rate denominator is capability passes plus capability failures, never all planned slots. A
five-slot cell with one infrastructure failure reports planned=5, capability n=4, and infra=1
without a replacement run.

Harness configuration, authentication, timeout, process, protocol, profile-violation, and artifact
failures are infrastructure/control failures rather than subject capability failures. Only a
Harness model-turn failure enters the capability-failure denominator; cancellation remains its own
disclosed outcome.

Phase G reports Wilson 95% intervals for binary capability outcomes. The standard pass@k estimator
is calculated per task and macro-aggregated; n<k is `NOT_AVAILABLE`. Continuous latency, token,
tool, and step evidence includes count, p50, p95, and deterministic bootstrap intervals when
meaningful. Paired binary evidence uses the exact two-sided binomial test over McNemar
discordances; paired continuous evidence resamples exact task/repeat differences.

`NOT_COMPARABLE` pairs remain execution evidence but are excluded from formal uplift, causal, and
ranking claims. `PARTIALLY_COMPARABLE` pairs remain explicitly limited exploratory evidence. Cost
is `NOT_AVAILABLE`, not zero, unless immutable evidence provides a trustworthy explicit value.

## Judge calibration

Phase H calibrates LABEL, SCORE, and PAIRWISE. The Core suite separates public cases from hidden
gold, whose source is deterministic L0 or repository-curated human L1. Gold values and notes never
enter provider requests or JudgeEvidence.

Every pairwise repeat evaluates A/B and B/A as one logical trial. LEFT/RIGHT positions are
canonicalized to stable candidate A/B identity. Order disagreement remains visible position
inconsistency; no implementation selects whichever order matched gold. L1 TIE cases with one
longer but substantively equivalent candidate provide a limited verbosity-bias probe. LABEL and
PAIRWISE report categorical repeat agreement; SCORE reports within-case dispersion.

LABEL reports accuracy, confusion, macro F1, and failure counts. SCORE uses median aggregation and
reports coverage, MAE, Spearman, dispersion, and explicit reasons when correlation is undefined.
PAIRWISE reports planned/evaluable logical trials, coverage, position-evaluable count and
consistency, abstention/output/provider counts, repeat consistency, and verbosity probe results.
Provider infrastructure reduces coverage and is excluded from accuracy, F1, repeat, position, and
capability-error denominators. Abstentions and output errors remain Judge capability failures.

Qualification is versioned and suite-scoped. Phase H Core uses `ALL_REQUIRED_CHECKS_PASS`: every
required check yields `QUALIFIED_FOR_SUITE`; any failed check yields `NOT_QUALIFIED`. `LIMITED` is
reserved and is not assigned by an unversioned failed-reason count. Passing this small corpus is not
universal Judge reliability, a population-level claim, an expert panel, an inter-rater study, or
external benchmark validation.

Authority is independent of qualification. L0 remains authoritative when present, otherwise L1
does, while L2 annotates. A Judge PASS cannot change L0 FAIL and a Judge FAIL cannot change L0
PASS. Reports derive these facts through `resolve_authority`; the L0 override count is zero by
construction, and JudgeLab never updates Phase G outcomes,
verifier results, or capability denominators.

## Workbench evidence presentation and Regression compare

Phase I presents approved Phase G/H evidence; it does not create another statistics authority.
Every displayed numeric value originates in a typed API response backed by PostgreSQL and the
existing immutable report/statistics contracts. Vue may format or select a dimension but does not
recalculate success rate, Wilson intervals, pass@k, latency percentiles, infra rate, Judge metrics,
qualification, evidence tier, or comparability.

Missing evidence uses `NOT_REPORTED` with a null value. It is distinct from a reported numeric
zero and from `NOT_COMPARABLE`. A direct-model run without Normalized Trace reports
`TRACE=NOT_REPORTED`; a missing explicit cost reports `COST=NOT_REPORTED`. Provider pricing is not
estimated from model names.

Each Matrix task×cell point filters the shared verified Phase G observations before calling
`summarize_cell()`. Capability n is pass+fail, infra is separate, and unrelated tasks are never
pooled into a point. Task-scoped `PairEvidence` controls Matrix comparison status; no pair is
`NOT_REPORTED` rather than assumed comparable.

Regression compare aligns actual persisted capability manifests by task and repeat under an
explicit `MODEL_COMPARISON`, `HARNESS_UPLIFT`, or exploratory `GENERAL` intent, and delegates
eligibility to the Phase F `ComparabilityEngine`. It returns report identities, raw directional
success-rate delta, evidence tiers, infra counts, paired count, and reason codes. Critical controls
remain `NOT_COMPARABLE` even if values look favorable; declared treatments are not mistaken for
hard-control drift. The page makes no causal or new significance claim and never reruns subjects.

Polling refreshes only durable PostgreSQL lifecycle state and stops at a terminal experiment.
Route reconstruction triggers a new API fetch; Pinia is not persisted as authoritative evidence.

## Attribution Analyst evidence claims

Phase J adds no evidence authority. The hierarchy remains
`L0 deterministic > L1 repository-curated human gold > L2 LLM Judge`; Analyst prose is a
read-only explanation layer over persisted facts.

Every factual conclusion is a `VERIFIED_FACT` composed of deterministic `FactAssertion` values.
Each assertion binds a logical run, trace-event, task-version, cell, pair, or ablation reference to
a tool namespace, bounded field path, `EQ` operator, and expected JSON value. The trusted host
resolves the field from catalog evidence and requires canonical JSON equality. Digest bindings
connect entries to plans, reports, manifests, or normalized traces where applicable. An invented
citation, wrong namespace, missing path, or contradictory value rejects the draft. Fact citations
and authoritative prose are derived canonically from the validated assertions, not supplied by the
backend.

A `HYPOTHESIS` is interpretation not deterministically established by available evidence and must
name evidence needed to verify or falsify it. Natural-language confidence never upgrades a
hypothesis. Without a declared controlled ablation, causal attribution remains a hypothesis.

A controlled ablation supports facts about its observed paired result, treatment, evidence tier,
and Comparability limitations. It does not erase `PARTIALLY_COMPARABLE`, `NOT_COMPARABLE`, small-n,
or informal-evidence limits. The Analyst introduces no statistics formula or significance result,
and the approved infrastructure denominator remains unchanged.

## Core release evaluation plan

The Core corpus freezes 18 validated tasks, balanced six each across Python, Java, and TypeScript,
with six behavioral categories. The planned real Matrix expands seven configured cells across every
task at five repetitions per task/cell: direct `gpt-5.6-sol` through an operator-trusted relay,
`qwen3.8-max` through OpenCode Go Messages, non-thinking `deepseek-v4-pro` through DeepSeek official,
Codex relay medium/high, Claude Code Harness × Qwen through OpenCode Go, and DeepSeek Harness E1 ×
`deepseek-v4-flash` through DeepSeek official. DeepSeek E2 remains deferred. Model identity and
Harness identity remain distinct. Formal evidence is evaluated per task; unrelated observations
are never pooled to manufacture n ≥ 5.

The Codex medium/high controlled ablation changes only reasoning effort and remains
`CONFIGURED_NOT_RUN`. The direct-relay/Codex-medium P-Lane shares a configured semantic route but is
`CONFIGURED_NOT_VERIFIED`; authorized smoke must establish runtime routing and observed-model facts
before the ComparabilityEngine can decide. No real result, rank, uplift, cost, latency,
Judge-quality, or regression statement is present in the v2 keyless state. The eight-call smoke plan must
complete without an abort condition before any full Matrix authorization is considered.
