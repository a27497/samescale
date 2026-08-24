# Core Release Evidence

The Phase K hard stop is implemented by strict models in `src/harnesslab/release`, canonical JSON artifacts in `release/`, and `scripts/verify_gate_k.py`. Documentation does not make evidence true; identities, digests, authoritative source references, state, and independent validation do.

## K-A artifacts

- `core-corpus.json` binds the 18 package, task, semantic-family, benchmark-role, workspace, verifier, lane, toolchain, baseline, and oracle identities. Exactly one clamp control spans all three languages; the other 15 families are independent.
- `core-real-evidence-plan.json` defines three unresolved Model-only slots, seven cells, the planned Pair and ablation, frozen Judge suite, exact call/token ceilings, credential references, and authorization blockers.
- `release-evidence.json` is the prospective `v1.0.0-core` evidence manifest. All six `REAL_*` states are `NOT_RUN`, real result bindings carry no identity/digest, and readiness is false.
- `resume-claim-evidence.json` maps engineering claims to source/gate evidence and leaves real-performance claims `NOT_VERIFIED`.
- `badcases.json` reserves exactly three empty evidence slots.

Canonical models reject extra fields. `VERIFIED` bindings require both an identity and SHA-256 digest. `NOT_RUN` and `DEFERRED_NOT_VERIFIED` cannot carry a result identity or digest. Readiness is derived from mandatory bindings and cannot be independently set true.

## Keyless contract mode

```bash
uv run --locked python scripts/verify_gate_k.py
```

It validates the task corpus from source, canonical inventories, Matrix/profile/Pair/ablation structure, docs, resume references, BadCase placeholders, secret boundaries, CI ordering, fresh-clone contract, and tag guard. Passing means the hard stop works. Expected K-A output includes `CORE_RELEASE_READY=FALSE`, `REAL_EVIDENCE_AUTHORIZATION_REQUIRED=TRUE`, and all six `REAL_*=NOT_RUN`.

## Final release mode

After authorized Phase K-B execution, replace prospective bindings with trusted evidence and run:

```bash
uv run --locked python scripts/verify_gate_k.py --final-release \
  --database-url "$DATABASE_URL" \
  --artifact-root /trusted/harnesslab/artifacts \
  --github-run-id <exact-successful-ci-run-id>
```

The verifier does not treat database connectivity or an arbitrary matching file SHA as release
evidence. It loads the completed `core-real-matrix-v1` through the existing authoritative
experiment loader, reconstructs the exact 18-task/7-cell/n=5/630-slot plan, rebuilds the actual
report, and checks semantic bindings for `experiment-plan:`, `experiment-report:`,
`experiment-pair:`, and `experiment-ablation:` identities. It independently verifies the trusted
Judge report and its 63 completed real-profile evaluations, L0 override count, three factual
BadCases, real-claim references, and the exact-head successful GitHub Actions workflow with Gates
A-K. The Pair policy is explicitly either `HARNESS_UPLIFT_CLAIM` (which requires all 90 observations
to remain genuinely `COMPARABLE`) or `NO_HARNESS_UPLIFT_CLAIM`; `NOT_COMPARABLE` evidence is never
relabeled. Only successful semantic verification returns a receipt accepted by the tag guard.
Missing or corrupt evidence returns `NOT_VERIFIED` and never creates a tag.

`scripts/verify_fresh_setup.py` default mode is only a pinned preflight contract. Its explicit
`--actions-reproduction` mode runs only after the ordered Gates A-K in GitHub Actions, binds the
attestation to the exact `GITHUB_SHA`, verifies pinned runtimes and an unmodified tracked checkout,
and deliberately does not invoke Gates A-K recursively.

`analyst_report` is optional to readiness, but if used its identity/digest must be preserved and its facts remain subject to Phase J binding. Monetary cost is not derived because no frozen price evidence exists.
