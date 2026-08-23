# Phase I Workbench

## Read-only architecture

The Phase I Workbench observes persisted evidence. Operators still create experiments and Judge
calibrations through the approved CLI paths. The browser has no route that starts a provider,
Harness, experiment worker, or Judge; it cannot cancel/delete runs, change outcomes or scores, or
modify tasks and gold.

FastAPI routes live under `/api/workbench`. They use strict Pydantic response DTOs rather than
serializing SQLAlchemy rows. PostgreSQL supplies durable identity and lifecycle state. Existing
ExperimentPlan/ExperimentReport and JudgeCalibrationReport contracts supply authoritative metrics.
Immutable disk artifacts are reopened only behind a persisted run/calibration identity.

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
count, evidence tier, and comparability DTOs. Vue only selects a metric and formats it. For a
multi-task report that lacks an authoritative task-level numeric statistic, that Matrix point is
`NOT_REPORTED`; the frontend does not reconstruct Phase G formulas.

Infrastructure counts are displayed independently from capability success. Tooltips and the
textual chart summary include task, cell, metric, `n`, tier, comparability, and reason codes.

## Missing evidence and comparability

Numeric evidence is `{status: REPORTED | NOT_REPORTED, value: number | null}`. A reported zero is
not missing. `COST=NOT_REPORTED` means no trustworthy explicit cost was persisted; Phase I has no
pricing database and never estimates current prices. `TRACE=NOT_REPORTED` means no Normalized
Trace exists, not a successful empty trace.

Comparability is a separate dimension. `NOT_COMPARABLE` remains blocked and reason-coded;
`PARTIALLY_COMPARABLE` remains limited. Neither is converted to missing data or a green result.

## Trace safety

The trace client supplies only `run_id`. The backend resolves the persisted manifest, validates
its digest and deterministic attempt identity, confines `trace/normalized.json` to the run bundle,
verifies its digest, and parses the strict Normalized Trace model. Arbitrary path query parameters
are rejected. Native transcripts, private reasoning, credential references, absolute artifact
paths, hidden verifier/oracle files, and database configuration never enter frontend DTOs.

`REASONING_PRESENT` communicates presence only and always renders a content-withheld message.
`FULL_STREAM` and `FINAL_OUTPUT_ONLY` remain verbatim coverage labels.

## JudgeLab and Regression

Judge calibration detail reopens the persisted report and verifies calibration/report identity.
`QUALIFIED_FOR_SUITE` is displayed with the frozen suite/version scope, never as universal Judge
reliability. Provider infra, all approved metrics, L0 disagreements, and zero L0 overrides remain
visible. `REAL_JUDGE_SMOKE=NOT_RUN` is preserved.

Regression compare reads two immutable reports. It aligns same-named cells or an explicit mapping,
reports directional deltas only when both values exist, retains tier/infra/digest facts, and blocks
hard cell or task/workspace/verifier control mismatches with `NOT_COMPARABLE`. Mapping requests are
bounded before sorting or alignment. It does not rerun subjects, claim statistical significance,
or attribute cause.

## Polling and Core readiness

The frontend polls the PostgreSQL-backed status route only for non-terminal experiments, normally
every three seconds, and stops after a durable terminal state. Browser reload performs a fresh
fetch. No Redis, WebSocket, SSE, or message broker was added.

Core readiness is derived from structured persisted plans/reports/calibrations. Missing formal,
real Matrix, real Judge, Phase J, or release-document evidence remains blocking or unverified, so
the Phase I dashboard truthfully reports `NOT_READY`. It never creates a Git tag.

## Real evidence status

Gate I is deterministic and keyless:

- `REAL_PROVIDER_SMOKE=NOT_RUN`
- `REAL_CODEX_SMOKE=NOT_RUN`
- `REAL_CLAUDE_SMOKE=NOT_RUN`
- `REAL_DEEPSEEK_SMOKE=NOT_RUN`
- `REAL_MATRIX_EVIDENCE=NOT_RUN`
- `REAL_JUDGE_SMOKE=NOT_RUN`

No Phase J Analyst, LangGraph, RAG, scheduler, remote worker, authentication, pricing, or SaaS
surface is part of Phase I.
