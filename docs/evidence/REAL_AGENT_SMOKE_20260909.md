# REAL_AGENT_SMOKE — 2026-09-09

Result: **VERIFIED / COMPLETED** for the bounded Attribution Analyst vertical slice.

## Bound identity

- Session: `analyst-0be376756a4f447bbdeeb44a58b292b5`
- Experiment scope: `core-real-matrix-v6`
- Scope digest: `sha256:d3d026cfbfbe014b943705a894ad06e125f59ad6060b73c05daf84588b7aa73e`
- Provider profile: `deepseek-official-v4flash-responses-smoke-v6`
- Frozen profile digest: `sha256:79ef9941dadca567c46ad1345a93e544e2c58a6346e5dc2489d6124e0638cfad`
- Model/route: `deepseek-v4-flash` via the official Responses route
- Final execution: `4` decisions, `9` read-only tool calls
- Provider request budget used: `4/4`
- Observed usage: `161015` input + `15617` output = `176632` tokens
- Observed priced cost: `$0.09146104`
- Observed latency total: `107305` ms
- Canonical report digest: `sha256:1733eace25488c8e435e2fd1f7d5e6d1ae7c676a047259ab3edc3dd6315c19b1`
- Proposal digest: `sha256:24eec75a37c2695d39c1383b64208fa57ef56f3ef606873c75e3291aaa4b7820`

## What was verified

The real model dynamically selected bounded HarnessLab evidence tools over persisted `core-real-matrix-v6` evidence. The host executed only the declared read-only tools, preserved the evidence catalog, validated exact structured facts against cited evidence, and rejected an invalid final attribution rather than accepting unsupported facts. The bounded repair path then supplied host-controlled rejection metadata plus exact valid fact candidates; the final report passed host validation and reached `COMPLETED`.

The accepted v6 session selected task, run, cell-comparison, failure and ablation tools; it did not select `inspect_trace`. Separate real v3/v5 trajectories did select and complete `inspect_trace`. Those sessions remain separate historical tool-selection/failure evidence and are not represented as if their trace evidence belonged to the v6 report.

The accepted report is deliberately conservative: it does **not** claim that Codex-high outperforms Claude on `core-java-deduplicate`. The available cell/per-task evidence is informal or insufficient, contains substantial infrastructure/execution-budget loss, and does not support a formal causal pairwise conclusion.

The model also proposed one regression plan restricted to the bound task/cells/evidence. That proposal was reviewed and approved only as a review artifact. `execution_authorized=false`; approval did not enqueue or execute any experiment, Harness, Judge, provider campaign, or regression run.

## Failure/repair evidence retained

Earlier bounded sessions remain historical evidence. They exposed: DeepSeek Responses structured-output compatibility; output-token accounting that includes reasoning; durable `incomplete_response/max_output_tokens` telemetry; realistic tool-budget trajectories; and the need for host-side semantic finalization recovery. No historical failed session was refunded, rewritten, or resumed after its frozen contract was exhausted.

The final implementation keeps all factual validation fail-closed. Recovery does not weaken citations or silently rewrite a model draft: the host emits only allowlisted rejection codes and an exact catalog of valid scalar assertions. If no decision budget remains, invalid attribution still terminates as `INVALID_ATTRIBUTION`.

## Evidence files

- `report.json` — canonical validated AttributionReport.
- `report.md` — host-rendered report.
- `proposal.json` — validated review-only regression proposal.
- `approval.json` — digest-bound approval with `execution_authorized=false`.
- `session-summary.json` — sanitized usage, budgets, terminal preflight and identities.

File SHA-256:
- `approval.json`: `sha256:0b3c26307d650d76e27225805aa97c35ee6a89195e48b46807e067ff164e2f78`
- `proposal.json`: `sha256:27b8c407eb7e75a78e82f53a1b517051c799b8e43f649709728edd4d7d160448`
- `report.json`: `sha256:a71bf5bb8550828dfdcce38d79621f1c75cc2e1f5d21cc749e51c373ea957131`
- `report.md`: `sha256:e59ef45b181ee6942fa999a40aed0d914af5ee869c7f03e9e2216c5dac9a4783`
- `session-summary.json`: `sha256:10ffef60fd7ccdb7a4dc6173fcd12ffd3e880ff25884909a587d52a2ae2c0f52`

## Boundaries that remain

This smoke verifies the **Attribution Analyst real-provider vertical slice**, not a new Matrix campaign and not final security acceptance. It does not change the accepted V6 Matrix/Judge evidence, does not establish a new harness-uplift or reasoning-effort causal claim, and does not close known F5 cancellation/orphan-process debt or the H-Lane protected-file gap. The local reviewer label is an operator assertion, not authenticated human identity.
