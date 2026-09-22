# Phase 0 isolated candidate — 2026-09-22

Base: `ef135bbdd49639afc28e2701d811329f3418281d` (fetched origin/main).
Candidate: `codex/phase0-baseline-20260922`, separate worktree. The original dirty integration worktree remains untouched; no reset/stash/clean or historical evidence rewrite.

## Inclusion boundary

[allowlist.json](allowlist.json) records each copied path, source digest and role. Current QA relies on the existing frontend shell, URL navigation, mode metadata, example projection, configuration components and English dictionary; these dependencies preserve the final 17-spec / 167-test suite. They are not new functionality developed during Phase 0.

Included final fixes: saved-plan read-only recovery, current/frozen Judge labels, preflight feedback, valid ID patterns, English footer, snapshot failure invalidation, unknown inactive methodology, removed selection identity, budget bounds, and Harness eligibility with explicit recovery. Backend changes provide the validated saved-plan API and read-only mode/comparison dependencies.

The existing Demo app and asset helpers are required by UAT U05 and local-configuration isolation tests. Missing `create_demo_app` initially caused Ruff classification failures; source imports were audited and the minimal modules/CLI wiring added explicitly. This is dependency assembly, not an expansion into installer development. Initial diagnostic logs remain recorded.

Excluded from the original dirty work: untracked S1/L1 campaign scripts, Docker variants, tests/fixtures, unrelated preflight/runtime changes, installer and wheel-build hooks, historic campaign evidence, duplicate screenshots/logs, and duplicate verifier package/run copies outside the pinned bundle. Already committed main history remains intact. No broad directory copy of old campaigns and no test deletion/skip/assertion weakening.

## Hook closure and immutable evidence

The selected original Hook callbacks and complete [pinned verification bundle](../real-hook-trace-20260922/verifier-closeout/verification/bundle.json) are copied byte-for-byte. The bundle contains its own prior capture identity, final workspace, task/verifier definitions and independent sandbox report; replay does not need the original temporary workspace, Docker or credentials.

Real session: verification-only against a seeded fixture. Hook exit status remains unknown. Independent verifier: **1/4 PASS, VERIFIED_FAIL**, authority `L0_INDEPENDENT_VERIFIER`, category `workspace_contract_failure`, root cause null, not comparable. This does not prove Codex capability or instruction-compliance failure.

[Frozen regression case](../real-hook-trace-20260922/verifier-closeout/regression-case.json) and the original [Replay A](../real-hook-trace-20260922/verifier-closeout/replay-a.json) / [Replay B](../real-hook-trace-20260922/verifier-closeout/replay-b.json) remain unchanged. Replay never executes an Agent, model, original command or verifier. Bundle anchor: `sha256:7eabbf0805c2e9fb3ec89ecc338850c31dffe2aea513928391f7e3195c5e2971`.

```bash
uv sync --locked
npm ci --prefix frontend --no-audit --no-fund
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy src tests scripts
npm run test --prefix frontend
npm run build --prefix frontend
PYTHONPATH=src:. uv run --locked pytest -q tests/test_native_hooks.py tests/test_verified_hook_replay.py tests/test_episodes.py tests/test_immutable_evidence_lint.py
bash scripts/ci_s3.sh /tmp/NEW-phase0-offline
```

The CI backend tests require a disposable PostgreSQL database and migrations. No historical database is used. CI runs full frontend/build, the focused Hook and evidence-boundary tests, and the unchanged bounded core suites; the existing offline workflow runs the unified 122-test gate.

## Type and lint boundary

The five candidate mypy errors have type-only fixes: distinct AST import-alias variables eliminate four inference conflicts; a typed JSON cast fixes the replay fixture helper's `Any` return. Strict mypy is retained; the 110 errors in excluded historical S1 files are not edited.

Ruff excludes only `docs/evidence/**`, which is immutable/read-only data. Maintained Python remains checked, including src/tests/scripts/tasks, root and other docs paths. Regression tests retain bundle/file digest anchors, lint-negative fixtures and a bounded static execution-dependency guard. The audit is not a proof about arbitrary operator-supplied paths.

## Acceptance

[Local acceptance](local-acceptance.json): full Ruff/format/strict mypy PASS; frontend **17 spec / 167 PASS / 0 failures / 0 unhandled errors**; Hook/Verifier/Episode **68** plus boundary **13** = **81 PASS**; unified offline **122 PASS**; mirrored Fast CI backend **518 PASS**; build/vue-tsc PASS. No skipped tests. [Offline receipt](offline/result.json) retains the five matching S2 output hashes for two replays and zero external/model calls.

The first complete mirrored CI run recorded 517 PASS / 1 FAIL because the Demo test's `check_demo`/`status --demo` dependency was absent. The exact original `src/harnesslab/productization/cli.py` was audited and added; a second complete run passed all 518 tests. Both run logs are preserved; no assertion was changed to get green.

[Original preservation](original-preservation.json), [copied/base frozen preservation](frozen-preservation.json), [assembly audit](assembly-audit.json), and [excluded paths](excluded-paths.json) record the boundary. The preserved integration worktree is not the candidate's runtime dependency.

GitHub acceptance is tied to the final commit's **HarnessLab Fast CI** and **SameScale Offline Regression** checks; see [candidate Actions](https://github.com/a27497/samescale/actions?query=branch%3Acodex%2Fphase0-baseline-20260922). Historical receipts do not substitute for those checks. After committing, source digests are compared with exact HEAD; final CI run IDs and HEAD are recorded in the task handoff, avoiding a new commit merely to record its own SHA.

Phase 1, new subjects/models/campaigns and deployment are outside this task.

Immutable copied patch/log files contain historical whitespace that `git diff --cached --check` reports. Their exact bytes are retained; maintained-source whitespace passes. This does not change Git or Ruff rules. The [review](immutable-whitespace-review.json) records the diagnostic separately from executable-code gates.
