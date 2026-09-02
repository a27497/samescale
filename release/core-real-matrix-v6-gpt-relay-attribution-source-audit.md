# HarnessLab GPT/Codex Relay Attribution Source Audit

## Decision

**GO_PARTIAL_ATTRIBUTION**

There is a deterministic, collision-free subset of **73 Direct GPT primary calls**, covering **72 fully matched Direct GPT slots** plus **1 partially matched slot**. There are no exact-ID matches. Codex medium/high provider calls and all recovery calls lack the frozen call-level time/identity evidence required for deterministic relay assignment, so no Codex slot is matched.

This is not broad enough for population-level GPT/Codex relay-latency attribution. A later analysis may use the deterministic subset only as an explicitly selected subset/sensitivity analysis. It must not force a Codex or recovery join.

## Frozen-source safeguards

- Frozen dataset SHA256: `sha256:d07f6c96e3bd7882137355cb8b5d2d5682e3d51bffcedce6292375d4a54bbd1d` (unchanged)
- Final analysis JSON/Markdown: unchanged at their preregistered hashes
- Frozen dataset rows: 630; GPT logical slots audited: 270
- New subject/provider calls: 0; new recoveries: 0; new Judge calls: 0
- Experiment DB: not accessed
- Raw relay CSV: private path outside the repository, mode `0o600`; not committed

## Relay CSV validation

| Check | Result |
|---|---:|
| SHA256 | `sha256:d10ec4dec9e1c941ed5fd2899b317e2588357737bfadacab92f1062776cdf7fb` |
| Rows | 3497 |
| Columns | 18 |
| Exact duplicate rows | 0 |
| Min time | `2026-08-27T00:56:30.913600+08:00` |
| Max time | `2026-09-02T12:45:13.291965+08:00` |
| Model | `gpt-5.6-sol` (3497) |
| Endpoint | `/v1/responses` (3497) |
| Medium / High | 1584 / 1913 |

API-key and IP values were profiled for completeness but are intentionally not emitted.

## What `execution_budget_exhausted` means

`harness_error:execution_budget_exhausted` is a **wall-clock outer Codex process timeout**, configured to **180 seconds** for the audited GPT Codex cells. All 217 available primary/recovery Codex manifests independently record that same limit. It is not a token, cost, model-call-count, tool-call-count, turn-count, or step-count limit.

The backend wraps prompt input plus process stdout/stderr and process wait in `asyncio.timeout(plan.timeout_seconds)`, kills the process on timeout, and measures elapsed time with a monotonic clock. The trace classifier emits `execution_budget_exhausted` only for a clean-progress timeout: started thread/turn, at least one successful command, no terminal, no malformed/profile-violation/disqualifying error/retry/tool events, and no command infrastructure failure. Otherwise the typed result remains a generic timeout.

Relay waiting can technically consume this 180-second outer budget, so wall-clock sensitivity is **YES**. This audit does **not** establish that relay latency caused any observed exhaustion.

Source anchors:

- `src/harnesslab/harness_lane/models.py:18-35` — taxonomy and capability classification
- `src/harnesslab/harness_lane/trace.py:256-298,349-365` — strict exhaustion predicate and timeout mapping
- `src/harnesslab/harness_lane/docker_backend.py:402-433` — enforced wall-clock timeout and monotonic duration
- `src/harnesslab/harness_lane/adapter.py:151-170` — profile timeout copied into the execution plan
- `release/core-real-matrix-v6-control.json` — 180-second configuration for all three audited GPT cells
- frozen Codex manifests — `profile.execution_timeout_seconds=180` in all 217 available primary/recovery manifests

## Join audit

Level A fails: the relay CSV contains no request/response/relay correlation ID, while Direct GPT manifests do contain provider response IDs. No common immutable ID exists.

Level B succeeds only for a Direct GPT primary-success subset. A match requires all of:

1. exact model, reasoning effort, and `/v1/responses` endpoint;
2. relay `Time` inside the frozen logical primary window;
3. relay `Input Tokens + Cache Read Tokens + Cache Creation Tokens` exactly equal Harness provider `input_tokens`;
4. relay output tokens exactly equal Harness provider output tokens;
5. exactly one relay row satisfies the full rule; and
6. that relay row is not assigned to any other call.

Duration, nearest-time selection, token-nearest selection, and manual tie-breaking are not used. The rule yields 73 matches and zero incompatible row assignments.

Level C is retained only as candidate evidence. The primary windows span `2026-09-01T10:47:41.517671+00:00` through `2026-09-02T04:41:29.844475+00:00`. Of 3497 relay rows, 1229 fall inside at least one matching-effort GPT primary window; after deterministic assignments, **1156 rows remain ambiguous window candidates**. They are not confirmed Harness calls. Recovery windows are unavailable.

## Coverage by cell

| Cell | Logical slots | Call-level Harness evidence | Composite calls | Fully matched slots | Partially matched | Unmatched slots | Known unmatched call records |
|---|---:|---:|---:|---:|---:|---:|---:|
| Direct GPT | 90 | 90 | 73 | 72 | 1 | 17 | 31 |
| Codex medium | 90 | 0 | 0 | 0 | 0 | 90 | NOT_VERIFIED |
| Codex high | 90 | 0 | 0 | 0 | 0 | 90 | NOT_VERIFIED |

The 31 known unmatched records are Direct GPT authoritative primary/recovery manifests. A total unmatched provider-call count is **NOT_VERIFIED** because Codex call counts and one unobserved Direct primary attempt are unavailable. Likewise, the 1,156 ambiguous items are relay rows, not a proven count of ambiguous Harness calls.

For every deterministic match, the secret-free match map preserves the relay CSV data-row/file-line identity, match class and predicates, call metrics, and the requested slot-level count/sum/median/max exposure fields. Seventy-two entries are complete one-call logical-slot totals; the remaining entry is explicitly marked incomplete because that slot also has unmatched attempt/recovery evidence.

Coverage is materially selection-biased by execution structure: Direct GPT has a matched successful-result subset; Codex has zero matched slots. This rules out full attribution. Within Direct GPT, all three frozen capability-fail slots are fully matched, 69 of 83 passes are fully matched, one pass is partial, and all four infra outcomes are unmatched; those Direct-only rates do not repair the missing Codex population.

## Provider-call structure

- Direct GPT: each recorded runner attempt performs one provider request (`src/harnesslab/model_lane/providers.py:226-317`; `src/harnesslab/model_lane/models.py:291-319`). There are 104 authoritative primary/recovery call records, but the logical-slot distribution is a lower bound because one extra primary attempt is not represented by the selected manifest. The observed record-count distribution is min=1, p25=1.0, median=1.0, p75=1.0, p90=2.0, max=2.
- Codex medium/high: provider-call count per logical slot is **NOT_VERIFIED**. The frozen streams expose one outer agent run and agent/tool events, not immutable Responses-call events; the event schemas at `src/harnesslab/harness_lane/models.py:181-235` contain no timestamp or provider request/response ID. No median, p25, p75, p90, min, or max is reported.

No `non_relay_elapsed_residual_ms` is calculated in this source audit because Codex call coverage is absent and the later sensitivity analysis is out of scope.

## Failure-attribution source availability

Overall availability is **PARTIAL**. All selected Codex capability-failure attempts have sanitized native and normalized traces. The frozen evidence can directly support the typed execution-budget category and can often support bounded review of commands, changed paths, public messages, workspace state, and verifier outputs. It does not expose private reasoning or provider-call timing/count, so planning/strategy and context-loss/dilution cannot be uniformly or causally distinguished.

This task does not classify any discordant pair. It only confirms that later semantic attribution is feasible for a bounded subset and must retain `PARTIAL` limitations.

## Scientific interpretation

The frozen primary analysis remains valid as **observed end-to-end configuration performance**. GPT latency is route/configuration-confounded because GPT-5.6 used a third-party relay. Use **“Observed end-to-end latency under frozen route/configuration.”** Do not call it pure model latency or pure Harness latency.
