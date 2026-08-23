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
expired work can be reclaimed, and cancellation is durable. The lifecycle is:

`QUEUED -> CLAIMED -> PREPARING -> RUNNING -> VERIFYING -> SCORING -> COMPLETED`

Terminal alternatives are `FAILED_INFRA`, `FAILED_SUBJECT`, and `CANCELLED`. The bounded local
worker calls existing lane runners; it does not duplicate workspace or Hidden Verifier logic.
PostgreSQL stores manifest references/digests, not transcripts, workspaces, credentials, or private
reasoning.

## Repetition and denominators

- n=1 valid capability observation is `SMOKE` only.
- n>=3 but below the formal target is `INFORMAL`.
- n>=5 with valid controls is `FORMAL`.
- Other sample counts are `INSUFFICIENT`.

Infrastructure failure is not model-capability failure. Capability success rate and Wilson 95%
use `capability_passes + capability_failures`. Planned slots, infrastructure failures, and
cancellations are separately disclosed. There is no default replacement run.

## Statistical evidence

Cell reports contain success rate, Wilson 95%, per-task macro pass@1/pass@3/pass@5 when n>=k,
latency/token/tool/step count and p50/p95, deterministic bootstrap intervals, infrastructure rate,
and failure taxonomy. Missing cost is `NOT_AVAILABLE`, not zero.

Paired binary statistics count left-pass/right-fail and left-fail/right-pass discordances, then use
SciPy's exact two-sided binomial test under p=0.5. No discordances gives p=1.0. Paired continuous
statistics first compute exact task/repeat differences and then resample those differences.
Reports provide effects, intervals, p-values when defined, and sample sizes without narrative
claims of proof or superiority.

## P-Lane and ablation

P-Lane binds M-Lane and H-Lane runs by task identity, initial workspace, verifier, and repeat slot.
Every pair invokes the Phase F ComparabilityEngine. `NOT_COMPARABLE` remains execution evidence but
is excluded from formal paired statistics. `PARTIALLY_COMPARABLE` is exploratory and surfaces its
reason codes. Only `COMPARABLE` pairs can become formal after repetition requirements.

An Ablation names base/variant cells and one treatment dimension. Phase G currently supports a
controlled reasoning-effort treatment. Undeclared hard-control drift is rejected, and
Comparability limitations prevent causal interpretation.

## Reports and boundaries

The authoritative report path is runner -> persisted manifest -> persisted run reference/digest ->
manifest loader -> statistics/report. Canonical JSON and concise Markdown are deterministic for
the same persisted state. Formal ordering includes only sufficiently repeated cells participating
in a formal `COMPARABLE` pair.

`REAL_MATRIX_EVIDENCE=NOT_RUN` is the default. Gate G is keyless and deterministic. JudgeLab,
judge calibration, UI, analyst agents, RAG, multi-agent frameworks, Redis, Celery, Kafka, and
Kubernetes are not Phase G.
