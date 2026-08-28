# HarnessLab Core Real Matrix v3 — Interim Partial Report

## Technical summary

The real Matrix is gracefully paused and fully resumable. PostgreSQL contains exactly 630 logical slots under plan digest `sha256:5b91aea8c2cf812e911358b3a39f75d8d0eada153188c219eaf5176d3b3b107d`: 177 terminal, 453 queued, and 0 running. The pause allowed the four already-leased calls to finish, prevented replacement claims with the existing `FOR UPDATE SKIP LOCKED` queue semantics, and started zero new real calls after the pause boundary.

This is an `INTERIM_PARTIAL_MATRIX_REPORT`, not the completed formal Matrix. Only 15 terminal slots are capability outcomes (2 pass and 13 fail); 162 are infrastructure failures and stay outside capability denominators. Coverage is strongly cell-imbalanced, so no cross-cell ranking, Codex effort uplift, or significance conclusion is supported.

OpenCode Go quota causality is not identifiable at exact-slot grain from the safe typed evidence. Ten Claude/OpenCode slots have typed HTTP 503 events, while 80 other Claude/OpenCode infrastructure terminals are timeout, process-error, or unattributed infra categories. The three direct-Qwen terminals are capability outcomes. Exact quota-affected terminal and slot-ID counts are therefore `NOT_DETERMINED`.

## Exact pause checkpoint

| Metric | Exact value |
|---|---:|
| Matrix logical total | 630 |
| Terminal | 177 |
| Pending queued | 453 |
| Running | 0 |
| Infrastructure failures | 162 |
| Capability terminals | 15 |
| Capability pass | 2 |
| Capability fail | 13 |
| New real calls after pause | 0 |

All 177 terminal rows have an existing authoritative manifest and evidence digest. Attempt identities are 176 rows at attempt 1 and the single authorized DeepSeek repair row at attempt 2. No queued row was cancelled or deleted.

## Cell coverage is too uneven for ranking

| Cell | Terminal | Queued | Cap pass | Cap fail | Infra | p50 latency | p95 latency | Token coverage (in / out) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Claude + Qwen/OpenCode | 90 | 0 | 0 | 0 | 90 | 94.5s | 181.0s | 76/90 runs; 11,745 / 227,264 |
| Codex GPT-5.6 high | 72 | 18 | 0 | 7 | 65 | 180.5s | 180.6s | unavailable |
| Codex GPT-5.6 medium | 3 | 87 | 0 | 0 | 3 | 180.5s | 180.6s | unavailable |
| DeepSeek harness | 3 | 87 | 0 | 0 | 3 | 18.0s | 18.4s | unavailable |
| DeepSeek direct | 3 | 87 | 1 | 2 | 0 | 2.8s | 4.1s | 3/3 runs; 1,073 / 868 |
| GPT-5.6 direct | 3 | 87 | 1 | 1 | 1 | 17.4s | 23.3s | 2/3 runs; 9,521 / 974 |
| Qwen direct/OpenCode | 3 | 87 | 0 | 3 | 0 | 56.2s | 58.3s | 3/3 runs; 1,156 / 5,974 |

Latency percentiles use only terminal rows with persisted duration. Token sums use only rows with persisted token metrics; missing telemetry is not imputed. Persisted steps and tool-call totals are available in the structured checkpoint, but they are implementation-specific trace counts rather than comparable provider turns.

Capability pass rates are descriptive only: Codex high 0/7 (Wilson 95% upper bound 35.4%), DeepSeek direct 1/3 (6.1%–79.2%), GPT direct 1/2 (9.5%–90.5%), and Qwen direct 0/3 (upper bound 56.1%). The intervals are too wide for rank or significance claims.

## Task, language, and repeat coverage remains partial

All 18 tasks, all three languages, and repeats 0–4 have at least one terminal slot because the Claude lane completed all 90 slots. That breadth does not imply balanced evidence:

- Python: 60 terminal / 150 queued; 3 capability terminals and 57 infra failures.
- Java: 60 terminal / 150 queued; 3 capability terminals and 57 infra failures.
- TypeScript: 57 terminal / 153 queued; 9 capability terminals and 48 infra failures.
- Repeat 0: 48 terminal across all 7 cells.
- Repeats 1–4: 32–33 terminal each across only 2 cells.

Codex high and medium have only three matched terminal slots: the Python, Java, and TypeScript deduplicate tasks at repeat 0. None is a matched capability pair, so medium-versus-high uplift and significance are not computable.

## The representative portfolio view needs 120 later calls

The separate `REPRESENTATIVE_SUBSET` view selects three tasks per language, all seven cells, and repeats 0–2 for 189 existing logical slots. It is not a new benchmark and does not change the formal Matrix.

Selected tasks are:

- Python: `core-python-deduplicate`, `core-python-feature-flag`, `core-python-quota`.
- Java: `core-java-deduplicate`, `core-java-feature-flag`, `core-java-quota`.
- TypeScript: `core-typescript-deduplicate`, `core-typescript-feature-flag`, `core-typescript-quota`.

The nine scenario families are distinct. Selection maximized already-terminal coverage within repeats 0–2, used task ID ascending as the tie-break, and never used scores or pass rates. The view has 69 terminal slots and 120 missing slots: 24 OpenCode-dependent and 96 non-OpenCode. No missing slot was executed during this planning step.

## OpenCode quota impact is bounded but not exactly attributable

The OpenCode-dependent cells contain 93 terminal runs: 90 Claude-harness and 3 direct-Qwen. Safe typed evidence identifies zero authentication failures, zero typed 429/quota failures, ten HTTP 503 provider failures, and 80 other Claude infrastructure outcomes. Because the remaining typed categories do not encode quota causality, both `OPENCODE_GO_QUOTA_AFFECTED_TERMINAL_RUNS` and `OPENCODE_GO_AFFECTED_SLOT_IDS_COUNT` remain `NOT_DETERMINED`.

The operational implication is clear even without causal attribution: do not execute further OpenCode-dependent slots until quota resets, and do not reinterpret the 90 Claude infrastructure outcomes as capability evidence.

## Scope, definitions, and method

The unit of analysis is one persisted logical Matrix slot identified by the frozen cell, task, repeat, and plan controls. Terminal means `completed`, `failed_subject`, `failed_infra`, or `cancelled`; capability terminal includes only normalized `capability_pass` and `capability_fail`; infrastructure failures are reported separately and excluded from capability rates.

Counts, outcomes, metrics, and coverage come from the persisted PostgreSQL `experiment_run` rows for `core-real-matrix-v3`. Plan identity and the 630-slot population come from the persisted experiment plan. Quota categories use sanitized manifest fields and sanitized structured transcript event codes/statuses only; raw provider error bodies were not exposed.

## Limitations and robustness boundaries

- The Matrix is 28.1% terminal and 71.9% queued; full-matrix inference is not allowed.
- Cell coverage ranges from 3 to 90 terminal slots and is confounded with execution order and provider availability.
- Only 15 capability outcomes exist, producing very wide confidence intervals.
- Exact OpenCode quota contamination is not encoded at logical-slot grain.
- Token data is absent for all current Codex and DeepSeek-harness terminals and partial for Claude/GPT direct.
- There are zero comparable Codex medium/high capability pairs.
- Judge calibration is `NOT_RUN_DUE_TO_CURRENT_PROVIDER_QUOTA`; this is operational, not a Judge capability conclusion.

## Recommended next steps after quota reset

1. Resume the existing `core-real-matrix-v3` queue without changing its plan digest, logical slots, or attempt identities.
2. Complete the 120 missing representative-view slots first if portfolio landing remains the priority; 24 require OpenCode Go and 96 do not.
3. Rebuild the partial report after the representative view is complete, retaining infrastructure outcomes outside capability denominators.
4. Run the separate 63-call Judge calibration only after provider quota is available and a new task explicitly authorizes resumption.

## Further questions

- Can future sanitized harness evidence add a safe typed quota/rate-limit category so contamination can be attributed without raw provider bodies?
- After quota reset, should the 96 non-OpenCode representative slots run before the 24 OpenCode-dependent slots, or should matched-cell completeness take priority?
- Once matched capability pairs exist, is the portfolio report intended to emphasize descriptive results only or pre-register an inferential comparison?
