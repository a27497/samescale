# Phase G experiment and statistics contract

## Identity and expansion

An Experiment contains Cells, each Cell expands across the resolved Task set, and each Task has an
explicit zero-based Repeat slot. ExperimentSpec is strict and versioned; it contains frozen
configuration and credential references, never raw keys. ExperimentPlan resolves task, workspace,
context, verifier, budget, network, model, route, harness, and profile identities, then orders
cells/tasks/repeats deterministically. Canonical plan JSON has no timestamp or random UUID and is
bound by its SHA-256 digest.

## Durable execution

PostgreSQL stores immutable experiment identity, cells, pair/ablation definitions, and unique
logical run slots. Applying the same plan twice is idempotent. A changed plan cannot silently
mutate an existing experiment id.

Workers claim eligible rows transactionally with `SELECT ... FOR UPDATE SKIP LOCKED`. A claim
records owner, expiry, heartbeat, and attempt. Only the active owner can heartbeat or release;
expired work can be reclaimed, and cancellation is durable. While a runner is active, the worker
automatically renews the lease at no more than one third of its TTL. A worker that loses ownership
cannot transition or terminalize the durable row. Each physical attempt receives a distinct
attempt-scoped artifact run id while the logical PostgreSQL run id remains stable. The lifecycle is:

`QUEUED -> CLAIMED -> PREPARING -> RUNNING -> VERIFYING -> SCORING -> COMPLETED`

Terminal alternatives are `FAILED_INFRA`, `FAILED_SUBJECT`, and `CANCELLED`. The bounded local
worker calls existing lane runners; it does not duplicate workspace or Hidden Verifier logic.
PostgreSQL stores manifest references/digests, not transcripts, workspaces, credentials, or private
reasoning. Cancellation short-circuits later transitions and never promotes a cancelled physical
attempt into authoritative capability evidence.

## Repetition and denominators

- n=1 valid capability observation per intended task is `SMOKE` only.
- n>=3 per intended task, but below the formal target, is `INFORMAL`.
- n>=5 per intended task with valid controls is `FORMAL`.
- Other sample counts are `INSUFFICIENT`.

Counts are never pooled across unrelated tasks to upgrade a cell or pair. Formal paired evidence
likewise requires five `COMPARABLE` capability pairs for every intended task.

Infrastructure failure is not model-capability failure. Capability success rate and Wilson 95%
use `capability_passes + capability_failures`. Planned slots, infrastructure failures, and
cancellations are separately disclosed. There is no default replacement run.
Harness `MODEL_TURN_FAILED` and strictly evidenced `EXECUTION_BUDGET_EXHAUSTED` are capability
failures; ambiguous timeout, configuration, authentication, process, protocol, profile-violation,
and artifact failures are infrastructure. Cancellation is reported separately.

## Statistical evidence

Cell reports contain success rate, Wilson 95%, per-task macro pass@1/pass@3/pass@5 when n>=k,
latency/token/tool/step count and p50/p95, deterministic bootstrap intervals, infrastructure rate,
and failure taxonomy. Missing cost is `NOT_AVAILABLE`, not zero.

The model-comparison closeout uses the same denominator policy for two-cell
`MODEL_COMPARISON` plans even though those plans do not declare Harness-uplift P-Lane pairs.
Pairing is recovered only from frozen `paired_slot_identity` values. Infra and unacquired pairs
remain outside the capability denominator and are disclosed separately. The closeout reports two
distinct percentage-point differences with orientation `MODEL_B_MINUS_MODEL_A`:
`per_model_capability_pass_rate_difference_pp` subtracts the per-model capability pass rates, with
each model using its own capability denominator, while
`matched_capability_pair_pass_rate_difference_pp` uses only matched capability pairs and divides
the Model B-only minus Model A-only pass count by the matched-pair denominator. Either value is
`null` when its required denominator is zero. `QUICK`/n=1 output is explicitly
exploratory/descriptive.

Paired binary statistics count left-pass/right-fail and left-fail/right-pass discordances, then use
SciPy's exact two-sided binomial test under p=0.5. No discordances gives p=1.0. Paired continuous
statistics first compute exact task/repeat differences and then resample those differences.
Reports provide effects, intervals, p-values when defined, and sample sizes without narrative
claims of proof or superiority.

## P-Lane and ablation

P-Lane binds M-Lane and H-Lane runs by task identity, initial workspace, frozen verifier control,
and repeat slot. Verifier execution is reported separately. An early capability terminal with
`NOT_EXECUTED` verifier status remains pair-eligible when its frozen control and every other hard
control match; this does not claim that its unverified output was correct. Actual verifier drift is
blocking.
Every pair invokes the Phase F ComparabilityEngine. `NOT_COMPARABLE` remains execution evidence but
is excluded from formal paired statistics. `PARTIALLY_COMPARABLE` is exploratory and surfaces its
reason codes. Unblocked partial capability pairs remain in exploratory paired binary
success/failure counts so early capability failures are not removed by survivorship bias. Only
`COMPARABLE` pairs contribute to repetition tiering, paired continuous statistics, or formal
eligibility.

An Ablation names base/variant cells and one treatment dimension. Phase G currently supports a
controlled reasoning-effort treatment. Undeclared hard-control drift is rejected, and
Comparability limitations prevent causal interpretation.

## Reports and boundaries

The authoritative report path is runner -> persisted manifest -> control validation against the
immutable slot -> persisted run reference/digest -> manifest loader -> statistics/report. Execution
and report reopening use the same validator and outcome normalization policy. Mismatched evidence
is an infrastructure/control-identity failure and is not attached as authoritative experiment
evidence. Canonical JSON and concise Markdown are deterministic for the same persisted state.
Formal ordering includes only sufficiently repeated cells participating in a formal `COMPARABLE`
pair. Plan construction also rejects any task/cell combination whose declared lane is unsupported.

`REAL_MATRIX_EVIDENCE=NOT_RUN` is the default. Gate G is keyless and deterministic. JudgeLab,
judge calibration, UI, analyst agents, RAG, multi-agent frameworks, Redis, Celery, Kafka, and
Kubernetes are not Phase G.
