# Core Release Evidence

This is a versioned release-contract reference. [Current Milestone](../CURRENT_MILESTONE.md) owns
live scope/status; [Project Status](PROJECT_STATUS.md) retains prior evidence. Instructions here
apply only to an explicitly authorized release task.
Historical sections describe their named campaign and do not authorize execution.

The accepted K-B4 completion record is at `3e9fcfeca9cb635d8c40c9206fc278928df9f044`, with recorded
exact-head Full Release CI run `33739101949`. That historical CI is not evidence for a newer head.

The schema-2 V6 candidate selects `core-real-evidence-v6` from
`release/core-real-evidence-plan-v6.json`. It binds the actual persisted `core-real-matrix-v6`
ExperimentPlan (`sha256:c18afc7b003a379f3456b23649e6d161da55e4fb5a34b4702dffbff35fb3604a`)
and `release/core-corpus-v4.json` (task version 1.0.2). V2–V5 plans remain immutable historical
execution contracts. The successor selects accepted evidence and authorizes zero external calls.

The accepted Matrix has 630 logical slots, 599 capability results, 29 infrastructure outcomes,
and two cancellations. All 630 primary manifests and all 79 bounded recovery manifests are
independently checked; primary outcomes are never overwritten. The persisted campaign-level
status is still `queued`, while every primary row is terminal. Release completion therefore
requires the exact accepted terminal run set and recovery bindings, rather than changing that
historical bookkeeping status to `completed`.

Evidence integrity and causal eligibility are separate. Direct/Codex has 82 complete pairs,
all PARTIALLY_COMPARABLE. Medium/high has 83 complete pairs, 42 COMPARABLE and 41 NOT_COMPARABLE;
no task has five comparable repetitions and formal eligibility remains false. The K-C phase map
requires real Pair/Ablation Evidence, not a successful formal causal result. The successor
verifies treatment identity, frozen controls, every accepted comparison, source digests and
actual eligibility. It rejects stronger fabricated evidence. The frozen methodology is unchanged.
`NO_HARNESS_UPLIFT_CLAIM` is selected; the existing `harness-uplift` claim remains NOT_VERIFIED.
No reasoning-effort causal claim is added.

The Claim Map verifies `real-matrix-results`, suite-limited `real-judge-quality`, and
`real-badcases` against their authoritative evidence identities. The three canonical factual
BadCases and their exact digests are unchanged; all root causes are null. The optional
`analyst_report` binding identifies the accepted K-B4 final attribution JSON, with zero
controlled-attribution claims. Historical statements within that frozen report are not rewritten.

The separate 2026-09-09 live Attribution Analyst smoke is product/Agent evidence, not a replacement
for any `REAL_*` release class. It does not rewrite the accepted V6 Matrix/Judge/BadCase bindings or
add a controlled-attribution claim. Its report/proposal/approval evidence is recorded under
`docs/evidence/REAL_AGENT_SMOKE_20260909.md`.

## Accepted V6 evidence contract

The selected evidence classes are recorded in `release/release-evidence.json`; their live summary
and release-binding limitations are in [Project Status](PROJECT_STATUS.md).

### Accepted V6 exact REAL_* evidence mapping

This mapping is part of the accepted V6 release contract. `VERIFIED` applies to each class's
bound evidence scope; it does not independently establish final-head release readiness.

| Class | Accepted V6 state | Authoritative scope |
| --- | --- | --- |
| REAL_PROVIDER_SMOKE | VERIFIED | Accepted V6 direct GPT, Bailian Qwen, DeepSeek Pro and Flash runs; native manifests and real capability results |
| REAL_CODEX_SMOKE | VERIFIED | Accepted V6 Codex medium/high runs and their immutable Harness evidence; unexposed observed model stays unexposed |
| REAL_CLAUDE_SMOKE | VERIFIED | Accepted V6 Claude Code/Bailian Qwen runs and immutable Harness evidence |
| REAL_DEEPSEEK_SMOKE | DEFERRED_NOT_VERIFIED | DeepSeek Harness E1 was explicitly unqualified and removed from Core in `kb2r-r2-core-qualification.json` and V5; direct DeepSeek results never verify this Harness |
| REAL_MATRIX_EVIDENCE | VERIFIED | Exact frozen V6 dataset, final analysis, primary manifests and bounded recovery evidence |
| REAL_JUDGE_SMOKE | VERIFIED | J4 real plan, 63 completed immutable evaluations, observed `grok-4.6-build`, qualified objective suite and reproduced report |

Schema 2 requires the evidence classes applicable to the selected V6 Core cells. DeepSeek E1
remains deferred outside that selection; its failed history is not promoted or deleted. This
exception is restricted to the accepted V6 identity and tested against attempts to mark its
smoke VERIFIED. A future Core selection including E1 would require a new evidence contract.
The completed V6 campaign supersedes prerequisite reachability checks for its selected runtimes;
it does not retroactively complete any failed historical eight-call smoke.

J4 is `core-real-judge-v7-j4`, using `core-calibration-objective@2.0.0`, 63 evaluations
(54 judged and nine correct UNKNOWN abstentions), and zero L0 overrides. The byte-identical
persisted report is copied to `release/core-real-judge-v7-j4-report.json`; its canonical digest is
`sha256:26a7690787b8845c99e16e4f02508cc2cf4761459ede48438d0958eca48ee623`.
The original reporter always defaulted `real_judge_smoke` to `NOT_RUN`, even after authorized
real execution. That field remains untouched. The release mapping instead requires the real
provider-adapter plan, approved observed alias, all 63 artifact digests and slot bindings, and
exact report reproduction through the native Judge reporter. Filenames or qualification labels
alone cannot satisfy the final verifier.

## Reconciliation and immutable history

```bash
uv run --locked python -m scripts.reconcile_kc_release_contract --check
```

Without `--check`, the tool deterministically writes only the current candidate manifest and
Claim Map from accepted sources. It never invokes an executor. The successor plan's anchored
digest prevents rebinding edited outcomes as stronger accepted evidence. Keyless checking also
recomputes Comparability from the frozen facts, validates the corpus and 630-slot dataset,
checks the frozen BadCases, and verifies the suite-limited Judge report.

`release/history/pre-kc-release-evidence.json` and `pre-kc-resume-claim-evidence.json` preserve the
exact pre-reconciliation bytes. The manifest's `release_history` continues to describe only the
immutable v2 smoke attempts: all thirteen remain aborted, complete smoke remains NOT_VERIFIED,
and its historical Matrix state remains NOT_RUN. The active evidence is in the successor
bindings. Historical regression tests now read the historical snapshot explicitly.

The Phase K hard stop is implemented by strict models in `src/harnesslab/release`, canonical JSON artifacts in `release/`, and `scripts/verify_gate_k.py`. Documentation does not make evidence true; identities, digests, authoritative source references, state, and independent validation do.

## Historical v3 convergence contract

`core-real-evidence-plan-v3.json` (`core-real-evidence-v3` / `core-real-matrix-v3`) and
`core-real-smoke-plan-v3.json` (`core-real-smoke-v3`) supersede v2 for final real validation without
rewriting v2. They retain the same eight calls, order, task, models, providers, routes, reasoning
efforts, credentials, token ceilings, verifier, security boundaries, and no-retry/no-fallback
policy. The only subject-budget change is a uniform 180-second wall-clock timeout for Calls 1-7;
the Judge remains 90 seconds. Select them explicitly with `--plan-version v3`.

The v3 Matrix still expands to 7 cells × 18 tasks × 5 repeats = 630 logical runs with zero calls
during preflight, and every subject profile carries the same 180-second timeout. Canary and pilot
are strict selections over that one immutable plan, not separate experiments. `--selection canary`
selects `core-python-deduplicate` × seven cells × repeat zero (7 slots); `--selection pilot` adds
`core-java-deduplicate` and `core-typescript-deduplicate` (21 slots total). The queue always contains
all 630 original slot IDs, so completed canary/pilot slots are already complete for the full Matrix.
Campaign concurrency defaults to two and is capped at four.

V3 Cycle 1 is preserved at `history/core-real-v3-attempt-1.json`; its Calls 6–8 continuation is
separate at `diagnostics/core-real-v3-attempt-1.json` and remains `DIAGNOSTIC_ONLY`. The smoke
aborted after Call 5 and is not represented as complete. `technical-readiness-v3.json` records the
non-release subject-plane and Judge-plane reachability result without changing any strict
`REAL_*` state or `CORE_RELEASE_READY`.

## Historical v2 artifacts

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

`component-smoke evidence-summary` validates a diagnostic report and emits an allowlisted candidate
history object. It does not merge diagnostic observations into a release receipt.

The production Matrix plane is the existing Phase G PostgreSQL queue and executor, bound strictly
to `core-real-matrix-v2`. `harnesslab release matrix preflight` expands 7 cells by 18 frozen tasks by
5 repeats (630 logical runs) with zero provider calls. Execution requires both
`--allow-real-matrix` and an explicit `--max-runs`; the v3 campaign accepts strict
`canary`/`pilot`/`remaining` selections, defaults to concurrency two, and is bounded at four.
Completed logical slots are resumed idempotently and are not duplicated.

`harnesslab release judge preflight` derives the 63-slot `core-real-judge-v3` plan from the existing
v3 GLM-5.2 profile, `core-calibration@1.0.0` suite/definition, repeat count, and unmodified
qualification thresholds. `release judge calibrate --allow-real-judge` resumes pending Judge slots;
schema/output failures and abstentions are calibration outcomes rather than campaign stop reasons.

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
- `badcases.json` originally reserved three empty slots; K-B4.3 now binds the three factual V6 failures documented above.

Canonical models reject extra fields. `VERIFIED` bindings require both an identity and SHA-256 digest. `NOT_RUN` and `DEFERRED_NOT_VERIFIED` cannot carry a result identity or digest. Readiness is derived from mandatory bindings and cannot be independently set true.

## Keyless contract mode

```bash
uv run --locked python scripts/verify_gate_k.py
```

It validates the task corpus from source, v1 history, OpenCode Go routes/transport/provenance, exact smoke bindings and mutation rejection, smoke and Matrix ceilings, Pair/ablation structure, immutable proxy identity, effective Docker egress topology, docs, resume references, the frozen BadCase contract, secret boundaries, CI ordering, fresh-clone contract, and tag guard. Passing means the hard stop works. Expected R4 output includes `OUTPUT_BUDGET_TRUNCATION_SEMANTICS=PASS`, `OPENCODE_GO_ROUTE_CONTRACT=PASS`, `OPENCODE_GO_CREDENTIAL_TRANSPORT=PASS`, `OPENCODE_GO_PROVENANCE=PASS`, `V1_HISTORY_PRESERVED=PASS`, `V2_SMOKE_PLAN=8_CALLS_14256_TOKENS`, `CORE_RELEASE_READY=FALSE`, and `REAL_CALLS_THIS_REPAIR=0`.

## Final release procedure: detached exact-head binding

K-C.1 leaves `release_commit` and `remote_ci` NOT_VERIFIED, with no identity or digest.
`core_release_ready=false` and Tag Guard denies authorization. The accepted K-B4 CI run is
historical evidence, never substituted for CI on a newer commit.

For an explicitly authorized release task, the finalization flow avoids a commit/CI cycle:

1. Commit the reconciled stable candidate, which contains no final SHA or CI run ID.
2. Run Full Release CI on that exact final commit. Any subsequent committed change requires
   a new exact-head Full Release CI run.
3. On the same clean committed checkout, load the actual PostgreSQL evidence and trusted
   artifact roots. Verify the candidate, corpus, primary and recovery manifests, Pair/Ablation,
   Judge, BadCases and Claim Map independently.
4. Resolve the successful Full Release CI attestation for that same SHA, including all four
   qualification jobs, Gates A–K and fresh-setup. Build an **in-memory** final manifest overlay
   containing that SHA and CI identity. Do not commit the overlay or receipt.
5. The semantic verifier checks that the overlay changes only the dynamic bindings/readiness,
   matches the committed candidate, and uses exact-head CI. It returns a receipt binding the
   candidate digest, final manifest digest, final SHA and CI attestation digest. Tag Guard
   requires that receipt and the matching final manifest. Verification itself creates no tag.

Only after separate final-release authorization should the existing entry point be used:

```bash
uv run --locked python scripts/verify_gate_k.py --final-release \
  --database-url "$DATABASE_URL" \
  --artifact-root /trusted/harnesslab/evidence \
  --github-run-id <exact-successful-full-ci-run-id>
```

The trusted root must contain both original Matrix/recovery evidence and J4 evidence. Missing,
corrupt or altered evidence fails closed. Ordinary CI only checks the stable contract and never
invokes final-release mode. K-C.1 does not run this command, Full Release CI, or finalization.

`scripts/verify_fresh_setup.py` default mode is only a pinned preflight contract. Its explicit
`--actions-reproduction` mode runs only after the ordered Gates A-K in GitHub Actions, binds the
attestation to the exact `GITHUB_SHA`, verifies pinned runtimes and an unmodified tracked checkout,
and deliberately does not invoke Gates A-K recursively.

`analyst_report` is optional to readiness, but if used its identity/digest must be preserved and its facts remain subject to Phase J binding. Its optional status does not permit unsupported causal claims.
