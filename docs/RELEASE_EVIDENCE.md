# Core Release Evidence

The Phase K hard stop is implemented by strict models in `src/harnesslab/release`, canonical JSON artifacts in `release/`, and `scripts/verify_gate_k.py`. Documentation does not make evidence true; identities, digests, authoritative source references, state, and independent validation do.

## K-A artifacts

- `core-corpus.json` binds the 18 package, task, workspace, verifier, lane, toolchain, baseline, and oracle identities.
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
  --remote-head <exact-successful-ci-sha>
```

The operator uses a trusted PostgreSQL evidence store and server-owned artifact root. Real Matrix, Pair, ablation, Judge, and three BadCase bindings use `artifact:<relative-path>` identities and matching SHA-256 digests. The release commit binds `git:<sha>`, remote head equals the checkout, every mandatory release and `REAL_*` state is `VERIFIED`, verified resume references resolve, and tag authorization is true. Missing or corrupt evidence returns `NOT_VERIFIED` and never creates a tag.

`analyst_report` is optional to readiness, but if used its identity/digest must be preserved and its facts remain subject to Phase J binding. Monetary cost is not derived because no frozen price evidence exists.
