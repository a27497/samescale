# SameScale Product — Current Milestone

Updated: 2026-09-09. Milestone: **S1.5 — mainline integration preparation**.
State: **IN_PROGRESS — S1.5 execution authorized; main merge/canonical rename NOT_RUN; S2 NOT_STARTED**.
S1 implementation, local tests and Browser QA remain accepted at
`0c6c6c9be89f22fe2e8f345a7d6e84720bb609f3`. The prepared candidate is
`89cb54070bdec79414399f21fa141cd8134ea518`, plus this local documentation handoff.
No new runtime capability was implemented. A future committed delivery must record its exact
remote SHA/CI; candidate CI is not proof that main or the renamed repository was verified.

This is the single live handoff. [Project Blueprint](docs/PROJECT_BLUEPRINT.md) owns the frozen
macro-route and S1.5/S2 acceptance criteria;
[Public Product Contract](PUBLIC_PRODUCT_CONTRACT.md) owns supported behavior and naming boundaries.
[Project Status](docs/PROJECT_STATUS.md) retains historical P0/real-smoke evidence. The previous S0
handoff is preserved in Git at `eceefeccbfb47607cb0463ad410ef429fc2c032c`.

## Baseline and authorization

- Existing repository/remote: `git@github.com:a27497/harnesslab-ai.git`.
- Worktree: `/home/dev/projects/harnesslab-ai-integration`.
- Feature branch: `codex/l-real-agent-main-integration`, tracking the same branch on origin.
- S1.5 preparation starting HEAD: `89cb54070bdec79414399f21fa141cd8134ea518`;
  starting worktree clean and branch tracking origin. Accepted S1 is
  `0c6c6c9be89f22fe2e8f345a7d6e84720bb609f3`; S1 originally started from
  `eceefeccbfb47607cb0463ad410ef429fc2c032c`.
- Frozen P0 commit remains `20d90700e5963ca9db3c86379e190da27cafb258`.
- The user explicitly authorized committing/pushing this preparation, creating/merging the PR,
  renaming the existing private repository to `a27497/samescale`, and completing S1.5 verification.
  This includes active canonical-reference/origin reconciliation and its verified main handoff.
  S2, tags, deployment and paid campaigns remain outside scope.
- Six other worktrees are not task targets. A new disposable PostgreSQL container and local QA
  server were used for this preparation; existing demo/restore resources were not used or changed.

## Current route and planning handoff

S0 and S1 are complete. **S1.5 — mainline integration and SameScale
canonical identity** is **IN_PROGRESS**, not accepted. S2 is **Local Productization & Developer
Experience**, also **NOT_STARTED**. The authoritative sequence is
**S1.5 → S2 → S3 restricted public Demo → S4 Portfolio/Release → P1 minimal Observe → P2 one
read-only external connector**. Observe is not S2. Goals and detailed acceptance live only in the
[blueprint amendment](docs/PROJECT_BLUEPRINT.md#samescale-macro-route-freeze--2026-09-09).

The source review found existing `harnesslab up/status/doctor/down`, a trusted Docker distribution,
and a DB-free synthetic showcase. `samescale` executable and `demo` command are absent at the
planning baseline; standalone installed-demo assets and clean-environment first use are not
established by S1 acceptance. The S2 plan therefore builds on these components and separates
standalone demo readiness from database-backed `/api/health`.

S1.5 preparation and completed integration/rename have separate acceptance states in the blueprint.
The target repository name `a27497/samescale` is planned, not current; the existing origin above
remains unchanged. The additive CLI belongs to S2, while package/env/API/schema/volume and frozen
evidence identities retain HarnessLab compatibility. These future exceptions do not change today's
[public product contract](PUBLIC_PRODUCT_CONTRACT.md).

## S1.5 preparation results

- Remote main `3335668f4f11e384a9f99fb0a8692f07d8937902` is an ancestor of candidate
  `89cb54070bdec79414399f21fa141cd8134ea518`: five candidate commits, no main-only commits;
  113 changed files include the existing Real Analyst/P0/S0/S1 and planning work.
- Candidate [Fast CI](https://github.com/a27497/harnesslab-ai/actions/runs/34385963877) is
  **SUCCESS** on that exact SHA. This closes the previously pending route-freeze CI result.
- Fresh focused Python acceptance: **157 passed in 36.00s**, zero skipped, with disposable
  PostgreSQL 18 migrated through `20260908_0007`. Frontend: **53 passed**, type check/build passed.
- Actual Chromium desktop/mobile QA: **7 grouped checks passed**, covering offline/history,
  persisted Fake reload/report/review, citation navigation and explicit error retry. The injected
  historical failure is labeled separately; screenshots were inspected. No runtime source changed.
- Server-log review found an existing advanced Core Readiness API failure on Overview navigation:
  `ModuleNotFoundError: scripts` in release reconciliation. Its imports exist in both main and
  accepted S1. The route rendered, but that background endpoint did not pass; this is isolated
  from the checked investigation journey and remains an explicit S2 startup/distribution gap.
- [Dated preparation evidence](docs/evidence/SAMESCALE_S15_PREPARATION_20260909.md) records exact
  repository/tag identity, test scope, known limits and the active/historical reference inventory.
  The blueprint owns the merge/rename/rollback procedure; other worktrees remain intact.
- All 27 local documentation links/anchors resolve; `git diff --check` passes. This preparation
  handoff contains documentation only. The task's temporary QA server and PostgreSQL
  container/volume were removed after verification; historical/demo resources remain untouched.
- Main integration, repository/remote rename and their final CI/continuity checks: **NOT_RUN**.
  S1.5 remains incomplete; S2 implementation and clean-environment product acceptance remain
  **NOT_RUN**. No model campaign or historical database migration was performed.

## Retained route-freeze verification

- Reviewed source entrypoints, CLI registration, lifecycle/trusted manifest selection, Compose and
  Docker build, static assets, showcase and router, plus existing distribution/lifecycle/CLI and
  fresh-setup contracts. This is scoped source review, not runtime acceptance of future behavior.
- `uv run --locked pytest -q tests/test_product_distribution.py tests/test_release_contracts.py
  tests/test_ci_workflow_contracts.py`: **32 passed in 20.07s**.
- Local Markdown links/anchors and scope/compatibility consistency checked; `git diff --check`
  passed. Only the two planning documents changed; source, public claims, lockfiles and frozen
  evidence remain unchanged. Link verification used the locked uv Python environment because
  plain `python` is not on this shell's PATH.
- Route-freeze commit `89cb54070bdec79414399f21fa141cd8134ea518` was pushed and its exact CI
  subsequently passed, as recorded above. These 32 tests are the earlier documentation check,
  not additional tests to add to the current 157-test result.

## Retained S1 delivery

- SameScale shell/mark, browser title and metadata, route titles, top-level CLI/API display
  descriptions, and current README product entry.
  HarnessLab CLI/package/env/API/database identities and existing URLs remain compatible.
- Primary navigation exposes investigation entry and saved investigations. Existing evaluation and
  Registry pages remain in an expandable advanced area that opens on their direct routes.
- Clear offline starting point and distinct historical Real/current-session entries; loading,
  fail-closed errors, explicit retry, and focus on the loaded example.
- Shared report navigation for conclusion, verified facts, limitations/hypotheses, and next steps.
  Citation links expose exact tool data/digests, focus the source, and return to the originating
  fact or hypothesis. Missing hypothesis references are now labeled unavailable as facts already were.
- Current investigation separates scope/session selection, collapsible new setup, progress/report,
  source/usage details, and expandable proposal review. Existing Real budgets/confirmation and
  review-only approval bindings are retained. Reviewer labels now get immediate format guidance
  and validation matching the existing backend.
- No backend execution behavior, schema/migration, lockfile, package identity, historical report,
  frozen evidence, task/profile identity, or database history was changed.

## Retained S1 acceptance record

The following checks were run for the accepted S1 commit, not rerun as part of this planning task.

Existing locked project toolchain: Python 3.12.14, uv 0.12.5, Node 24.18.1, npm 11.16.0.

| Check | Result |
| --- | --- |
| `tests/test_analyst_showcase.py` + `tests/test_analyst_contracts.py` | 19 passed; offline/history separation and evidence validation |
| `tests/test_analyst_sessions.py` + `tests/test_analyst_e2e.py` | 78 passed; isolated disposable PostgreSQL 18, migrations through `20260908_0007` |
| `tests/test_product_distribution.py` + `tests/test_release_contracts.py` + `tests/test_ci_workflow_contracts.py` | 32 passed; distribution, historical release, and CI contracts |
| Combined Analyst/compatibility run | **129 passed in 42.32s**; reruns are not added to totals |
| Focused `tests/test_cli.py` help/version/serve checks | **3 passed, 6 deselected**; 132 distinct Python tests passed in total |
| CLI/API display compatibility | OpenAPI paths, operation IDs, component schemas, and package version exactly match baseline; `/docs` responds successfully |
| Ruff check/format and mypy | Passed for both Python files with display-only edits |
| `npm run test --prefix frontend` | **53 passed across 5 files**; includes new focus, navigation, setup, and invalid-reviewer regressions |
| `npm run build --prefix frontend` | Type check and Vite production build passed |
| Browser QA | **7 grouped checks passed** on actual built application with Chromium; desktop/mobile, actual offline/history API and persisted Fake create/resume/reload/report/propose/approve; one explicitly injected historical failure |
| Visual inspection | Desktop entry/report/current session and mobile entry/report screenshots inspected; no horizontal overflow in checked states |
| Documentation links / compatibility / `git diff --check` | Passed; scope and public claims reconciled; protected identities/frozen evidence unchanged; only CLI/API display strings changed in Python |

[Browser QA record and screenshots](docs/evidence/SAMESCALE_S1_BROWSER_QA_20260909.md) distinguish
actual API/database behavior from injected failures. The initial navigation assertion used obsolete
copy and prevented cleanup, causing two cascading failures; updating the changed navigation contract
resolved all three. Browser QA exposed an invalid reviewer label accepted by the old UI; the new
frontend check preserves the backend's character contract. No application assertion was weakened.

## Stopping point and limits

S1.5 execution is authorized. The pending action is to commit/push the prepared
handoff, create and merge the feature-branch PR with history preserved, and rename the existing
private repository to `a27497/samescale`, then reconcile active canonical references and verify
exact main CI/identity continuity. This handoff does not claim those actions have happened.
Do not start S2. This task's temporary PostgreSQL container/volume and QA server have been removed;
existing historical/demo resources and other worktrees remain intact.

New live Real execution, full A–K/release acceptance, clean-clone reproduction, physical-device and
non-Chromium testing are **NOT_RUN** in S1. Original real-session restoration and human ownership
remain **NOT_VERIFIED**; historical runtime/security debts remain separate scopes. This product
refactor makes no new causal, model-ranking, reasoning-effort, or automatic-repair claim.
