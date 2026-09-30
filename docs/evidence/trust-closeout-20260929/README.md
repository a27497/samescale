# SameScale trusted-evidence closeout — 2026-09-29

## Starting state

- HEAD: `8ad71d87fc0977fff008c956165d877d2f9c0b83` on `main`, ahead of `origin/main` by one commit.
- Worktree was clean. No commit, push, paid Provider/Judge call, or frozen-evidence rewrite was authorized or performed.
- The observed asymmetric comparison was reproduced against the existing QA API before editing: `phase-i-matrix-multi-task` → `phase-i-matrix-candidate`, `codex-low` mapping, `MODEL_COMPARISON`, common task `micro-python-clamp`, overall 0.50 → 1.00, `NOT_COMPARABLE`, yet direction `IMPROVED`.
- The [corrected API projection](asymmetric-comparison-after.json) from the isolated local instance retains overall 0.50 → 1.00, shows common-task raw 1.00 → 1.00, and reports no eligible direction (`NOT_REPORTED`).

## Evidence semantics checked

- The QA seed script uses Fake provider and Fake Codex with `fake-shared-model`. Those are persisted keyless fixtures. `IMMUTABLE_EXPERIMENT` in Diagnosis describes a persisted experiment record, not a real Provider call; the old `real_run_count` label conflated these meanings.
- `FILE_CHANGE` is an event in the normalized trace. `No Modification` is derived from equal final workspace input/output digests. The two facts can coexist. Neither was changed in saved evidence.
- Core Readiness uses a frozen accepted V6 release snapshot and remains `NOT_READY`; QA experiments form a separate registry and cannot be used to reconcile snapshot counts.
- Provider `enabled`, credential presence and runtime health are independent states. No credential value was read into browser state.

## Browser acceptance

Chrome headless against the changed local source and an isolated, keyless scratch database at 1365×900 and 390×844. [Acceptance JSON](browser/acceptance.json) records Experiment → Run → Diagnosis, BadCases download, Regression, Settings → Providers, Core Readiness, page errors and horizontal overflow. All 26 entries have no failed check or page-level overflow. [Empty/error state JSON](browser/states.json) covers desktop and 320px mobile, with all checks passing. Screenshots are in this directory, including [failed Run](browser/desktop-failed-run.png), [mobile Diagnosis](browser/mobile-diagnosis.png), [mobile Regression](browser/mobile-regression.png), [Providers](browser/desktop-providers.png), and [Core Readiness](browser/desktop-readiness.png). This is local browser evidence, not a paid execution or user-network acceptance.
[Navigation JSON](browser/navigation.json) verifies Overview → Diagnosis, browser Back to the experiment's Runs tab, the explicit Run → Runs return link, and manual Regression comparison state in the URL.

## QA artifact integrity blocker

The pre-existing `tests/test_workbench_api.py` fixture removed the shared `.phase-i-test-artifacts` directory during the first focused test, while the QA instance's 36 persisted fixture records referenced it. The QA database was not modified. A scratch database regenerated the same 36 deterministic run IDs and artifact paths, but all 36 manifest digests differ from the original QA records because the verifier artifacts include run-specific runtime identities. The regenerated files are **not** substituted for the originals, and the QA experiment detail currently returns HTTP 409 on integrity validation. The fixture was changed to use isolated temporary artifact and runtime directories so subsequent tests do not touch this QA path. Original QA artifact bytes were not located locally. The original QA records and digests remain unchanged. This QA instance is **NOT_VERIFIED for public demonstration** until the original artifacts are restored from a trusted backup or an explicitly authorized new QA dataset/instance is established with separate identities.

## Test scope

- Offline S3 gate: 73 passed; two replay passes; zero external/provider/model/Judge/subject/verifier calls.
- Frontend: 83/83 passed; TypeScript check and production build passed.
- Full backend suite: 1696/1696 passed on an isolated migrated PostgreSQL database.
- Focused diagnosis and workbench API tests: 43/43 passed after the final backend change.
