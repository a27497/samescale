# Core Release Evidence

The Phase K hard stop is implemented by strict models in `src/harnesslab/release`, canonical JSON artifacts in `release/`, and `scripts/verify_gate_k.py`. Documentation does not make evidence true; identities, digests, authoritative source references, state, and independent validation do.

## Core real-evidence v3 convergence contract

`core-real-evidence-plan-v3.json` (`core-real-evidence-v3` / `core-real-matrix-v3`) and
`core-real-smoke-plan-v3.json` (`core-real-smoke-v3`) supersede v2 for final real validation without
rewriting v2. They retain the same eight calls, order, task, models, providers, routes, reasoning
efforts, credentials, token ceilings, verifier, security boundaries, and no-retry/no-fallback
policy. The only subject-budget change is a uniform 180-second wall-clock timeout for Calls 1-7;
the Judge remains 90 seconds. Select them explicitly with `--plan-version v3`.

The v3 Matrix still expands to 7 cells × 18 tasks × 5 repeats = 630 logical runs with zero calls
during preflight, and every subject profile carries the same 180-second timeout. The separately
gated `harnesslab release matrix canary --allow-real-matrix-canary` uses the normal PostgreSQL
queue, executor, and production bindings for exactly `core-python-deduplicate` × all seven cells ×
repeat zero. It is not a substitute for the full Matrix and cannot authorize one.

## Core real-evidence v2 artifacts

- `core-corpus.json` binds the 18 package, task, semantic-family, benchmark-role, workspace, verifier, lane, toolchain, baseline, and oracle identities. Exactly one clamp control spans all three languages; the other 15 families are independent.
- `core-real-evidence-plan.json` is `core-real-evidence-v2` / `core-real-matrix-v2`. It binds eight configured-not-smoked profiles, seven cells, truthful provider provenance, the unchanged Pair and ablation, frozen Judge profile/suite, exact call/token ceilings, four runtime configuration references, and authorization blockers.
- `core-real-smoke-plan.json` is `core-real-smoke-v2` and freezes seven one-task subject smokes and one Judge case: eight top-level launches, 14,256 maximum output tokens, exact evidence expectations, credential references, and sixteen fail-closed abort conditions. `harnesslab release smoke preflight` validates it keylessly; only an authorized `execute --allow-real-smoke` can enter the shared production orchestrator. The first v2 attempt executed calls 1-2 and aborted at call 2 after Qwen reached the configured output-token budget; calls 3-8 were not run. R4 preserves future output-budget-truncated public results for subject-output evaluation without changing the frozen budget.
- `history/core-real-v2-attempt-1.json` through `history/core-real-v2-attempt-13.json` preserve the complete immutable v2 attempt history. Attempts 1-8 record the successive output-budget, provider-timeout, Codex startup/route/sandbox, and execution-budget classification observations without promoting any individual success to complete smoke evidence. Attempt 13 reached Calls 1-4 and stopped at a Codex timeout; its Calls 5-8 sweep is preserved separately at `diagnostics/core-real-v2-attempt-13.json` as `DIAGNOSTIC_ONLY` and `release_promotable=false`.

Release-history digest values are derived with
`harnesslab release smoke evidence-summary --artifact-root <root>`. The receipt digest domain is
`RAW_FILE_SHA256`; each directory-backed
call evidence digest domain is `ARTIFACT_TREE_DIGEST`. History review must verify these derived
values and must not substitute manually copied hashes. The command reads only the strict smoke
receipt and allowlisted normalized evidence fields; it never invokes a provider or writes beneath
the evidence root.

`harnesslab release component-smoke execute` produces `DIAGNOSTIC_ONLY` evidence solely for frozen
calls not attempted by the supplied smoke receipt. Such reports declare `release_promotable=false`
and cannot satisfy any `REAL_*` release state. They exist to expose independent component defects
without repeating a release-smoke call.

The production Matrix plane is the existing Phase G PostgreSQL queue and executor, bound strictly
to `core-real-matrix-v2`. `harnesslab release matrix preflight` expands 7 cells by 18 frozen tasks by
5 repeats (630 logical runs) with zero provider calls. Execution requires both
`--allow-real-matrix` and an explicit `--max-runs`; concurrency defaults to one and is bounded at
eight. Completed logical slots are resumed idempotently and are not duplicated.

`harnesslab release telemetry summarize --artifact-root <root>` aggregates only safe observed
latency, usage, request-count, trace, and verifier facts. When the repository has no authoritative
price snapshot, it reports `PRICE_INPUT_REQUIRED` rather than inventing cost data.
- Attempt 9 reached Claude Call 6 and stopped fail-closed when Claude Code 2.1.241 exited with `process_error` before any normalized event or observed model. R12 then made zero real calls while diagnosing the invalid MCP shape and bare/tool-surface contradiction and keylessly verifying the isolated non-bare startup profile. Post-R12 Attempts 10-12 stopped at GPT Call 1 on relay read timeouts near the frozen 90-second boundary; Calls 2-8 were `NOT_RUN`, so none reached Claude. Attempt 12 specifically timed out while waiting for response headers; no HTTP response headers became available to HarnessLab before the frozen timeout. Accordingly, post-R12 real Claude verification remains `NOT_RUN` / `NOT_REACHED`: none validates or invalidates the R12 repair. Attempts 3, 6, 10, 11, and 12 independently establish a recurring Call-1 relay read-timeout reliability problem, but root cause remains `NOT_DETERMINED`. No v2 attempt completed all eight calls, and no attempt is Matrix or release verification.
- Attempt 13 established that both Codex medium and the separately diagnostic Codex high reached only `THREAD_STARTED` and `TURN_STARTED` before the v2 timeout, with no agent message, command/tool activity, or workspace mutation. Exact persisted Call-6 workspace replay executed the same Hidden Verifier successfully at score 1.0, so the original verifier error is transient infrastructure or not determined. Controlled keyless Call-7 reproduction found and repaired the pinned DeepSeek CLI's missing Node `--expose-internals` startup requirement. No provider root cause is inferred from these facts.
- R16 adds bounded direct-provider transport-phase traces for future timeout evidence: `CONNECT_TCP`, `START_TLS`, `SEND_REQUEST_HEADERS`, `SEND_REQUEST_BODY`, and `RECEIVE_RESPONSE_HEADERS`. The trace records only request-relative start/completion milliseconds and the locked httpcore source/version; raw callback payloads are ignored and never persisted. Attempt 12 predates R16, so no phase trace is retrofitted into Attempts 1-12.
- `history/core-real-v1.json` preserves the v1 plan IDs and canonical digests through the authoritative starting commit and exact Git blob/byte identities. It truthfully records all three v1 attempts without copying operator-local artifacts.
- `opencode-go-route-snapshot.json` freezes the selected official Qwen3.8 Max Messages and GLM-5.2 Chat Completions model IDs/endpoints, OpenCode Go third-party provenance, operator-confirmed benchmark permission, and the absence of a live model probe.
- `release-evidence.json` is the prospective `v1.0.0-core` evidence manifest. `REAL_PROVIDER_SMOKE` and `REAL_CODEX_SMOKE` are `NOT_VERIFIED`; the other four `REAL_*` states are `NOT_RUN`, and readiness is false.
- Its `remote_ci` binding remains prospective and `NOT_VERIFIED`. R12 exact-head keyless GitHub Actions run `32996166257` succeeded at `6abac258e81d89f7ad45aa51dce2541f911a6033`, but final-release CI must bind the exact head containing all mandatory real evidence and a ready manifest; engineering CI success is not final release verification.
- `resume-claim-evidence.json` maps engineering claims to source/gate evidence and leaves real-performance claims `NOT_VERIFIED`.
- `badcases.json` reserves exactly three empty evidence slots.

Canonical models reject extra fields. `VERIFIED` bindings require both an identity and SHA-256 digest. `NOT_RUN` and `DEFERRED_NOT_VERIFIED` cannot carry a result identity or digest. Readiness is derived from mandatory bindings and cannot be independently set true.

## Keyless contract mode

```bash
uv run --locked python scripts/verify_gate_k.py
```

It validates the task corpus from source, v1 history, OpenCode Go routes/transport/provenance, exact smoke bindings and mutation rejection, smoke and Matrix ceilings, Pair/ablation structure, immutable proxy identity, effective Docker egress topology, docs, resume references, BadCase placeholders, secret boundaries, CI ordering, fresh-clone contract, and tag guard. Passing means the hard stop works. Expected R4 output includes `OUTPUT_BUDGET_TRUNCATION_SEMANTICS=PASS`, `OPENCODE_GO_ROUTE_CONTRACT=PASS`, `OPENCODE_GO_CREDENTIAL_TRANSPORT=PASS`, `OPENCODE_GO_PROVENANCE=PASS`, `V1_HISTORY_PRESERVED=PASS`, `V2_SMOKE_PLAN=8_CALLS_14256_TOKENS`, `CORE_RELEASE_READY=FALSE`, and `REAL_CALLS_THIS_REPAIR=0`.

## Final release mode

After authorized Phase K-B execution, replace prospective bindings with trusted evidence and run:

```bash
uv run --locked python scripts/verify_gate_k.py --final-release \
  --database-url "$DATABASE_URL" \
  --artifact-root /trusted/harnesslab/artifacts \
  --github-run-id <exact-successful-ci-run-id>
```

The verifier does not treat database connectivity or an arbitrary matching file SHA as release
evidence. It loads the completed `core-real-matrix-v2` through the existing authoritative
experiment loader, reconstructs the exact 18-task/7-cell/n=5/630-slot plan, rebuilds the actual
report, and checks semantic bindings for `experiment-plan:`, `experiment-report:`,
`experiment-pair:`, and `experiment-ablation:` identities. It independently verifies the trusted
Judge report and its 63 completed real-profile evaluations, L0 override count, three factual
BadCases, real-claim references, and the exact-head successful GitHub Actions workflow with Gates
A-K. The Pair policy is explicitly either `HARNESS_UPLIFT_CLAIM` (which requires all 90 observations
to remain genuinely `COMPARABLE`) or `NO_HARNESS_UPLIFT_CLAIM`; `NOT_COMPARABLE` evidence is never
relabeled. Only successful semantic verification returns a receipt accepted by the tag guard.
Missing or corrupt evidence returns `NOT_VERIFIED` and never creates a tag.

Run completion as evidence is distinct from task success. Phase K validates the authoritative
Phase G terminal mapping: `capability_pass`/`completed`, `capability_fail`/`failed_subject`,
`infra_failure`/`failed_infra`, and `cancelled`/`cancelled`. The Phase G loader remains authoritative
for immutable artifact requirements, so infrastructure and cancellation rows may lack a subject
artifact. They remain outside the capability denominator and cannot be converted into capability
failures. Formal Pair/Ablation evidence still requires its exact comparable capability observations,
and all three Core BadCases must be verifier-backed `capability_fail` rows.

`scripts/verify_fresh_setup.py` default mode is only a pinned preflight contract. Its explicit
`--actions-reproduction` mode runs only after the ordered Gates A-K in GitHub Actions, binds the
attestation to the exact `GITHUB_SHA`, verifies pinned runtimes and an unmodified tracked checkout,
and deliberately does not invoke Gates A-K recursively.

`analyst_report` is optional to readiness, but if used its identity/digest must be preserved and its facts remain subject to Phase J binding. Monetary cost is not derived because no frozen price evidence exists.
