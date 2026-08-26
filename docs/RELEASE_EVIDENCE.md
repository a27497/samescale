# Core Release Evidence

The Phase K hard stop is implemented by strict models in `src/harnesslab/release`, canonical JSON artifacts in `release/`, and `scripts/verify_gate_k.py`. Documentation does not make evidence true; identities, digests, authoritative source references, state, and independent validation do.

## Core real-evidence v2 artifacts

- `core-corpus.json` binds the 18 package, task, semantic-family, benchmark-role, workspace, verifier, lane, toolchain, baseline, and oracle identities. Exactly one clamp control spans all three languages; the other 15 families are independent.
- `core-real-evidence-plan.json` is `core-real-evidence-v2` / `core-real-matrix-v2`. It binds eight configured-not-smoked profiles, seven cells, truthful provider provenance, the unchanged Pair and ablation, frozen Judge profile/suite, exact call/token ceilings, four runtime configuration references, and authorization blockers.
- `core-real-smoke-plan.json` is `core-real-smoke-v2` and freezes seven one-task subject smokes and one Judge case: eight top-level launches, 14,256 maximum output tokens, exact evidence expectations, credential references, and sixteen fail-closed abort conditions. `harnesslab release smoke preflight` validates it keylessly; only an authorized `execute --allow-real-smoke` can enter the shared production orchestrator. The first v2 attempt executed calls 1-2 and aborted at call 2 after Qwen reached the configured output-token budget; calls 3-8 were not run. R4 preserves future output-budget-truncated public results for subject-output evaluation without changing the frozen budget.
- `history/core-real-v2-attempt-1.json` preserves the first v2 attempt as a safe summary with exact plan/receipt digests and no operator-local paths or raw provider content. `history/core-real-v2-attempt-2.json` extends that immutable history with the post-R4 four-launch attempt: the three direct calls produced one verified failure and two verified passes, then Codex-medium stopped on infrastructure before a durable Codex call artifact existed; calls 5-8 were not run, with no retry or fallback. `history/core-real-v2-attempt-3.json` preserves the post-R5 one-launch attempt: direct GPT timed out during response reading, calls 2-8 were not run, and the raw evidence was rejected because it disclosed a private runtime URL value. The tracked summary records only the stable route identity and a presence-only audit.
- `history/core-real-v1.json` preserves the v1 plan IDs and canonical digests through the authoritative starting commit and exact Git blob/byte identities. It truthfully records all three v1 attempts without copying operator-local artifacts.
- `opencode-go-route-snapshot.json` freezes the selected official Qwen3.8 Max Messages and GLM-5.2 Chat Completions model IDs/endpoints, OpenCode Go third-party provenance, operator-confirmed benchmark permission, and the absence of a live model probe.
- `release-evidence.json` is the prospective `v1.0.0-core` evidence manifest. `REAL_PROVIDER_SMOKE` and `REAL_CODEX_SMOKE` are `NOT_VERIFIED`; the other four `REAL_*` states are `NOT_RUN`, and readiness is false.
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
