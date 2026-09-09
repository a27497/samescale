# Phase I Workbench

## Read-only architecture

The Phase I Workbench observes persisted evidence. Operators still create experiments and Judge
calibrations through the approved CLI paths. Evidence pages cannot start a subject provider,
Harness, experiment worker, or Judge; they cannot cancel/delete runs, change outcomes or scores,
or modify tasks and gold. The separate Analyst page can request one explicitly confirmed model
decision for a saved investigation when the server enables its real backend. Proposal approval
records review only; it cannot start any external execution.

FastAPI routes live under `/api/workbench`. They use strict Pydantic response DTOs rather than
serializing SQLAlchemy rows. PostgreSQL supplies durable identity and lifecycle state. Existing
ExperimentPlan/ExperimentReport and JudgeCalibrationReport contracts supply authoritative metrics.
Immutable disk artifacts are reopened only behind a persisted run/calibration identity and after
their resolved path is confined to server-configured trusted artifact roots. Clients cannot supply
or extend those roots; tests override the dependency explicitly.

## API inventory

- `GET /api/workbench/experiments`
- `GET /api/workbench/experiments/{experiment_id}`
- `GET /api/workbench/experiments/{experiment_id}/matrix`
- `GET /api/workbench/experiments/{experiment_id}/runs`
- `GET /api/workbench/experiments/{experiment_id}/report`
- `GET /api/workbench/experiments/{experiment_id}/status`
- `GET /api/workbench/runs/{run_id}`
- `GET /api/workbench/runs/{run_id}/trace`
- `GET /api/workbench/judgelab/calibrations`
- `GET /api/workbench/judgelab/calibrations/{calibration_id}`
- `POST /api/workbench/regression/compare` (read-only computation over persisted reports)
- `GET /api/workbench/core-readiness`

Experiment and run lists use bounded `limit`/`offset`. Public errors use stable codes such as
`NOT_FOUND`, `ARTIFACT_UNAVAILABLE`, `ARTIFACT_INTEGRITY_ERROR`,
`INVALID_ARTIFACT_REFERENCE`, and `INVALID_REGRESSION_REQUEST` without tracebacks or server paths.

## API to Vue flow

One typed Axios client owns HTTP calls. Pinia stores filters, the selected Matrix metric, bounded
query results, and polling lifecycle; it is not evidence storage and does not persist metrics to
localStorage. Vue Router reconstructs experiment/run/calibration identity from the URL and each
page fetches the API again. Vite proxies `/api` to FastAPI during development.

```bash
uv run harnesslab serve
cd frontend
npm ci
npm run dev
```

Quality commands are `npm run type-check`, `npm run test`, and `npm run build`.

## Matrix heatmap and numeric authority

The ECharts heatmap consumes API-provided success, latency p50/p95, infra-rate, pass@k, sample
count, evidence tier, and comparability DTOs. Every task×cell point is summarized from only that
task's verified persisted observations through the Phase G `summarize_cell()` implementation.
Infrastructure remains outside the capability denominator, and pass@k is `NOT_REPORTED` when
`n < k`. Vue only selects and formats metrics; it never reconstructs formulas.

Infrastructure counts are displayed independently from capability success. Tooltips and the
textual chart summary include task, cell, metric, `n`, tier, comparability, and reason codes.

## Missing evidence and comparability

Numeric evidence is `{status: REPORTED | NOT_REPORTED, value: number | null}`. A reported zero is
not missing. `COST=NOT_REPORTED` means no trustworthy explicit cost was persisted; Phase I has no
pricing database and never estimates current prices. `TRACE=NOT_REPORTED` means no Normalized
Trace exists, not a successful empty trace.

Comparability is a separate dimension. `NOT_COMPARABLE` remains blocked and reason-coded;
`PARTIALLY_COMPARABLE` remains limited. Matrix comparability is keyed by persisted task and cell
pair evidence; an unpaired task×cell is `NOT_REPORTED`, never invented as `COMPARABLE`.

## Trace safety

The trace client supplies only `run_id`. The backend resolves the persisted manifest inside a
trusted server-side artifact root, validates
its digest and deterministic attempt identity, confines `trace/normalized.json` to the run bundle,
verifies its digest, and parses the strict Normalized Trace model. Arbitrary path query parameters
are rejected. Native transcripts, private reasoning, credential references, absolute artifact
paths, hidden verifier/oracle files, and database configuration never enter frontend DTOs.

`REASONING_PRESENT` communicates presence only and always renders a content-withheld message.
`FULL_STREAM` and `FINAL_OUTPUT_ONLY` remain verbatim coverage labels.

## JudgeLab and Regression

Judge calibration detail reopens the trusted-root-confined persisted report and verifies
calibration/report identity. Lists expose `REPORTED`, `NOT_REPORTED`, or `INTEGRITY_ERROR`, so a
corrupt completed report cannot look like ordinary missing qualification evidence.
`QUALIFIED_FOR_SUITE` is displayed with the frozen suite/version scope, never as universal Judge
reliability. Provider infra, all approved metrics, L0 disagreements, and zero L0 overrides remain
visible. `REAL_JUDGE_SMOKE=NOT_RUN` is preserved.

Regression compare reads two immutable reports and their trusted-root-confined run manifests. A
bounded explicit intent (`MODEL_COMPARISON`, `HARNESS_UPLIFT`, or `GENERAL`) is assessed by the
Phase F `ComparabilityEngine` for task/repeat-paired capability observations. Declared model or
Harness treatments are allowed only under the matching intent; task, workspace, context, verifier,
provider route, budget, network, and the intent-specific Harness/model controls remain protected.
`GENERAL` is exploratory and cannot silently become a strong formal claim. Raw directional deltas
remain visually subordinate to blocked comparability. Regression never reruns subjects, claims
statistical significance, or attributes cause.

## Model-comparison closeout

`GET /api/workbench/experiments/{experiment_id}/model-comparison-analysis` is a read-only view for
an arbitrary persisted experiment whose frozen intent is `MODEL_COMPARISON` and whose matrix has
exactly two direct-model cells. It derives model A/B pairings from the immutable
`paired_slot_identity`; it does not require or add a P-Lane declaration and does not mutate the
experiment plan.

The response is the same canonical machine-readable closeout produced by
`harnesslab report model-comparison EXPERIMENT_ID [--output PATH]`. It includes planned/acquired
slots, the capability denominator, PASS/FAIL/INFRA, per-model rates, all four matched capability
pair outcomes, per-model capability and matched-capability-pair percentage-point differences with
an explicit `MODEL_B_MINUS_MODEL_A` orientation, infra/missing pairs, language and task-family
breakdowns when task metadata reports them, comparability reasons, control drift, trace and
observed identity coverage, recovery-marker coverage, known usage, and explicit cost status.
Incomplete cost evidence always has `status=NOT_AVAILABLE` and no total; a known subtotal may be
reported separately and cannot be read as a complete experiment cost.

Failure presentation uses disjoint labels for capability failure, provider infrastructure,
verifier infrastructure, budget exhaustion, incomplete provider output, control drift, other
infrastructure, and unacquired slots. Database `attempt` is disclosed only as a lease-claim count.
It is never interpreted as a recovery attempt without an explicit immutable recovery marker.

For `QUICK` or any `n=1` plan the response carries
`conclusion_semantics.scope=EXPLORATORY_DESCRIPTIVE`. The Workbench renders that limitation before
the two denominator-specific pass-rate differences and comparability details.

## Polling and Core readiness

The frontend polls the PostgreSQL-backed status route only for non-terminal experiments, normally
every three seconds, and stops after a durable terminal state. Browser reload performs a fresh
fetch. No Redis, WebSocket, SSE, or message broker was added.

Core readiness is derived from structured persisted plans/reports/calibrations. `TASK_CORPUS` is
ready only with 15-25 persisted task identities, and Judge readiness counts only completed reports
whose trusted path, identity, and integrity validate. Missing formal,
real Matrix, real Judge, Phase J, or release-document evidence remains blocking or unverified, so
the Phase I dashboard truthfully reports `NOT_READY`. It never creates a Git tag.

## Real evidence status

Gate I is deterministic and keyless:

- `REAL_PROVIDER_SMOKE=NOT_VERIFIED`
- `REAL_CODEX_SMOKE=NOT_VERIFIED`
- `REAL_CLAUDE_SMOKE=NOT_RUN`
- `REAL_DEEPSEEK_SMOKE=NOT_RUN`
- `REAL_MATRIX_EVIDENCE=NOT_RUN`
- `REAL_JUDGE_SMOKE=NOT_RUN`

The original Phase I evidence views remain distinct from the later Analyst investigation controls.
LangGraph stays server-side in the Analyst package; no RAG, scheduler, remote worker, authentication,
or SaaS platform is added by this slice. [Analyst](ANALYST.md) documents the current API and UI.
