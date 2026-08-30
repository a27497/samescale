# Phase M Evaluation System 2.0 core

Phase M adds a keyless control layer in front of experiment execution. It does not make provider
or Judge calls, change historical task packages, or rewrite historical attempts.

## Architecture

The slice has four independent, composable boundaries:

1. `harnesslab.preflight` collects local facts and evaluates a strict, secret-free
   `PreflightSpecification`. Every finding has a stable reason code, a bounded detail message, and
   remediation. The report has exactly one terminal readiness status: `READY`,
   `READY_WITH_WARNINGS`, or `BLOCKED`.
2. `harnesslab.budget` expands `QUICK`, `INFORMAL`/`COMPARE`, and `FORMAL` to 1, 3, and 5 repeats,
   then calculates subject/Judge calls and aggregate token, provider-request, harness-turn, and
   cost ceilings with exact decimal arithmetic.
3. `harnesslab.tasks.quality` and `harnesslab.tasks.splits` qualify immutable task identities and
   freeze development/holdout membership with provenance and leakage checks. See
   `TASK_QUALITY_AND_SPLITS.md` for the task-data contract.
4. `harnesslab.experiment.lifecycle` provides the nine externally meaningful lifecycle states and
   an immutable physical-attempt ledger. Compatibility adapters read legacy status values without
   modifying historical rows.

The CLI exposes `harnesslab preflight run SPEC.json` and
`harnesslab budget estimate REQUEST.json`. The API exposes pure assessment at
`POST /api/preflight/assess`, host collection at `POST /api/preflight/run`, and estimation at
`POST /api/preflight/budget`.

## Preflight semantics

Applicable checks cover the local Docker runtime, database readiness, disk capacity, required
images, configuration-reference presence and format, frozen provider route identity, harness
runtime/lane/model compatibility, task validity and lane support, network policy, comparability
controls, resource-envelope identity, trace coverage, pricing availability, and the budget ceiling.

Only environment-variable names are persisted or reported. Rejected values and backend exception
messages are not reflected in findings. Docker image checks inspect local state and never pull.
Provider route validation parses configuration identity only; it never probes a provider.

Unknown pricing produces an `UNKNOWN` cost projection with no amount. It is never converted to a
zero-dollar estimate. When a ceiling depends on unknown pricing, preflight reports
`BUDGET_CEILING_INDETERMINATE` and blocks execution. A known worst-case projection over the frozen
ceiling reports `BUDGET_CEILING_EXCEEDED` and also blocks.

## Lifecycle and recovery

The authoritative state sequence is:

`QUEUED -> PREPARING -> RUNNING -> VERIFYING -> COMPLETED`

Allowed non-success terminals are `FAILED_CAPABILITY`, `FAILED_INFRA`, `CANCELLED`, and
`BUDGET_EXHAUSTED`. Transitions fail closed. Capability failure is terminal. Infrastructure
recovery requires explicit authorization, a distinct attempt identity, chronological evidence,
and an eligible preceding `FAILED_INFRA` attempt. The default policy permits one recovery attempt.
The primary attempt and all prior attempts remain frozen in the ledger.

Legacy persistence values remain readable: `claimed` maps to `PREPARING`, `scoring` maps to
`VERIFYING`, and `failed_subject` maps to `FAILED_CAPABILITY`. Phase M writes the legacy
`failed_subject` value for compatibility. No schema migration is required for this slice.

## Control-manifest rule

Preflight and budget manifests are strict JSON and reject unknown fields. They contain references,
identities, public price evidence, and numeric ceilings only. Credential values must remain in the
execution environment. A blocked report is an authorization stop, not a prompt to change model,
provider, route, task, or methodology until a preferred outcome appears.
