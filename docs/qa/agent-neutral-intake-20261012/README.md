# Tool-neutral intake acceptance — 2026-10-12

Base: `feat/acceptance-workbench-v2@6affea4cb8287ef0434856fe9437127c4ebb89a1`.
Independent worktree: `/home/dev/.worktrees/samescale-agent-neutral-20261012`.
Only normal commit/push to this branch is authorized; no PR, merge or deployment.

## Delivered behavior

- Generic external record/format IDs, declared harness name/nullable version, converter extensions
  and truthful partial/no-log coverage. Four existing Codex artifact readers remain compatible.
- Claude Code stream-json reuses `multi_harness` NormalizedTrace/parser. Saved completion/self-report
  cannot supply independent acceptance. Code-only intake requires Workspace and task mapping, with
  `NO_RUN_RECORD` and no invented run state/Episode.
- Shared explicit approval, consent, origin/operator permission, pins, privacy and corruption gates.
  Escaped credential-shaped strings, protected trace paths, malformed stream envelopes, mixed/ambiguous
  auto-detection and empty acceptance references refuse; no partial record is persisted on refusal.
- `/external-runs` uses tool-first selection of approved inputs; switching tool clears source/consent.
  No arbitrary file upload, unreviewed source approval or private-session discovery was introduced.
- Private product entry hides built-in examples, including private example deep links. Public website
  mode retains its existing demo routes/assets. README and product identity use the confirmed positioning.

## Actual verification

All commands below used the task worktree/source, not the dirty original editable installation.
The existing locked Python environment was used with `PYTHONPATH=src`; npm installed the unchanged lock.

1. Related backend compatibility batch: **177 passed**, 81.00 s:
   `pytest -q tests/test_external_evidence.py tests/test_external_evidence_p1.py tests/test_external_evidence_generic.py tests/test_external_evidence_docker.py tests/test_multi_harness.py tests/test_episodes.py tests/test_native_hooks.py tests/test_verified_hook_synthetic.py`.
   This included actual isolated Docker Workspace Verifier pass/fail/timeout/consumed-attempt checks for
   Codex hooks, Claude stream and code-only. Agent/process captures were synthetic; no real Agent,
   Provider or model execution. Historical real evidence was only read as regression. Existing frozen
   evidence before/after guard passed.
2. After final empty-reference / malformed-Codex-item tightening, affected final batch: **78 passed**,
   10.29 s: `pytest -q tests/test_external_evidence.py tests/test_external_evidence_p1.py tests/test_external_evidence_generic.py`.
   This overlaps batch 1; the counts must not be summed as independent tests. Five additional refusal
   cases were added, for **182 distinct backend cases exercised across the two batches**.
3. Frontend complete suite: **232 passed / 19 files**, `npm run test --prefix frontend -- --reporter=dot`.
   Includes three input kinds, tool filtering/consent reset, code-only unknown run state, corruption,
   legacy fixture rendering, private no-example entry and public demonstration compatibility.
   Existing RouterLink stub warnings occurred; no failed cases remain.
4. `npm run build --prefix frontend`: **PASS**, includes `vue-tsc --noEmit`, then Vite production build.
5. Focused Ruff check / format: **PASS** (external-evidence sources and modified Python tests).
   Focused strict mypy: **PASS**, 9 source files (same sources/tests). `git diff --check`: **PASS**.
6. Actual Chromium against the production build and private FastAPI: **26 checks PASS**, 1440×1000
   viewport, actual approved synthetic-file import/export, no request mocks, no database and no page
   runtime errors. [Check inventory](browser-checks.json). Screenshots were visually inspected.

Browser check initially required selector/wait corrections: the header repeats as h1/h2, and switching
between content-addressed detail URLs must wait for the new identity/detail. These were test-driver
corrections; the final 26 checks passed. Test fixture assertions were also corrected to the actual
replay response fields, localized status attributes and synthetic verifier failure result.

The pre-migration synthetic record fixture was generated before edits at base `6affea4`, with original
identity `sha256:95fa2cbf98ae7fd58cc2cc2bf8cea2eff2f147a9fd4036dd4c9ad636f34d1004`.
Tests verify that exact old address, stored Workspace, safe export/replay and refusal of unbound new
legacy metadata. Existing original source/task binding fields are unchanged.

## Local artifacts

Directory: `/home/dev/samescale-deliverables/agent-neutral-20261012/` (local, not deployed).

- `import-code-only-1440.png`: tool-first entry and required Workspace/task inputs.
- `code-only-acceptance-1440.png`: unknown original state, no log and independent 0-check state.
- `code-only-result-1440.png`, `claude-code-result-1440.png`, `codex-result-1440.png`: full-page results.
- `browser-checks.json`, `browser-check.mjs`, backend logs, frontend test/build logs and the safe
  synthetic browser export. Operator credential is a test placeholder; no live credential was used.
- `private-fixture/` contains only explicitly created synthetic inputs and the private test store;
  it is not a user-session copy or a built-in product example.

## Limitations

This version selects individually approved files through the existing operator policy. It does not
add a drag-and-drop upload service, baseline+diff application, binary/large-Workspace support or
arbitrary task-text execution. New acceptance still needs separately qualified TaskStore contracts
and an authorized pinned isolated Verifier CLI, rather than an import-triggered run.

Cursor/DeepSeek native log adapters, tool-call/result linking and broad Claude variant coverage are
not delivered; those tools can supply code-only Workspace inputs. No genuine fresh Claude/Cursor/
DeepSeek session or full PostgreSQL product lifecycle/remote CI suite was run. Pattern checks are not
universal DLP; human review and `NOT_ATTESTED` remain mandatory. No claim of source authenticity,
comparison eligibility, model quality or full trace coverage is made.
