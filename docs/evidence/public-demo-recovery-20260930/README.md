# Evidence Integrity / Public Demo Recovery — 2026-09-30

Started at `8ad71d87fc0977fff008c956165d877d2f9c0b83`, `main`, with the previous trust-closeout modifications uncommitted. Those changes are retained and included in this closeout. No paid Provider or Judge call was made.

## Original QA recovery

`RECOVERY = ORIGINAL_NOT_FOUND`. [Survey](recovery-survey.json) hashes 4,432 filesystem manifests and inventories current/old worktrees, archive and deployment candidates, including `samescale-dirty-20260924`. [Git search](git-original-search.json) hashes all 4,748 reachable blobs. [Privileged follow-up](privileged-original-search.json) checks 17 otherwise inaccessible historical/runner directories; no manifest candidate there. There is no exact match for any of the 36 [original saved QA identities/digests](original-records.json). Candidate paths, sizes, SHA256 and corresponding original record comparisons are in the survey. Search stops without regenerating an original.

The [before/after identity comparison](identity-preservation.json) confirms all 36 original QA records, paths, attempts, and digests are unchanged. Original QA experiment detail still returns HTTP 409, and the browser presents **Historical evidence — artifact integrity failed**. It is not the default demo.

## New evidence identity

New bundle: `public-demo-20260930-9569db12e23a`.

- Baseline: `public-demo-20260930-9569db12e23a-baseline`.
- Candidate: `public-demo-20260930-9569db12e23a-candidate`.
- 12 distinct new Run identities; 108 new artifact files; new generated time, manifests, and digests.
- Provenance: `FIXTURE_OFFLINE`. The existing Fake Codex adapter feeds the normal evidence pipeline and independent task verifier. No real Provider/model execution or causal claim.
- Bundle digest: `sha256:593a54eff3ef0f89212d3097ea3d1f3349d1b7b085f618d2ca8f9805746171d7`.
- Storage is outside the repository/test tree, at the [seed record](seed.json)'s manifest path. Files are read-only; directories have no write permission. A byte-preserving backup is under `/home/dev/archives/samescale-public-demo-20260930/`; this is a backup of **new** evidence, not recovered old QA evidence.

The new bundle lists run/attempt/experiment identities, plan digests, independent verifier verdicts, and a relative-path SHA256/size inventory. Runtime checks bind those to the database and configured manifest digest. Missing files, changed hashes, changed attempts/identities, invalid provenance or broken references fail closed. No regeneration/fallback exists. The public artifact endpoint exposes only the fixture's digest-checked verifier stdout JSON, with its original byte hash; private/native transcripts remain excluded.

## Test isolation and protection

The incident arose because the QA seed imported test builders whose defaults used `.phase-i-test-artifacts`, while the test fixture called `shutil.rmtree` on that same shared directory. The prior closeout isolated the fixture; this change removes the builders' shared defaults and retires the legacy seed altogether. New demo builders live outside the test modules and require explicit storage roots. Audit found the remaining cleanup operations confined to temporary fixture trees or intentional corruption tests.

`tests/conftest.py` refuses protected QA/live/demo database names before collection. Python audit protection rejects writes/deletes in frozen release, historical documentation and explicitly registered demo roots. Before/after inventories also detect subprocess mutation. The full suite used a separately created, migrated `samescale_integrity_test_20260930` database and pytest temporary artifact/runtime roots.

[Full integrity inventory](integrity-suite.json): **406 files BEFORE == AFTER**, including the new bundle manifest and all 108 artifact files. All path, size and SHA256 entries match. The full suite includes 10 new tests covering cleanup rejection, protected databases, mandatory temporary roots, identity binding, read-only operation, downloads and missing/mismatched evidence.

## Acceptance before deployment

- [Backend](backend-full.txt): **1706/1706 PASS**.
- [Frontend](frontend-tests.txt): **87/87 PASS**.
- [Typecheck and build](frontend-build.txt): **PASS**.
- [Offline S3 / replay](offline-result.json): **73 PASS**, two replay passes, zero external/provider/model/Judge calls.
- Ruff, format, mypy and `git diff --check`: PASS.
- [Local Demo Gate](local-gate.json): all **12/12 PASS**. [Unavailable-origin gate](unavailable-gate.json) remains false with every unresolved item `NOT_VERIFIED`.
- [Browser](browser-local/acceptance.json): **38/38 PASS**, Chromium at 1365×900 and 390×844; new entry → experiment → failed run → diagnosis → regression → original verifier artifact. Refresh, browser Back, deep links, download/hash, actual old integrity failure, injected no-config state, and overflow/page errors are checked. Screenshots are in `browser-local/`.

The deployment startup gate is `scripts/verify_public_demo_storage.py`; the HTTP gate is `scripts/public_demo_gate.py`. Production status is recorded in CURRENT_MILESTONE and the production acceptance artifacts after deployment. Local success does not establish public-network or TLS acceptance.
