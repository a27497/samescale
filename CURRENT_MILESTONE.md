# SameScale Product — Current Milestone

Updated: 2026-09-09. Milestone: **Post-S1 macro-route planning freeze**.
State: **S1 ACCEPTED; forward route frozen; S1.5/S2 NOT_STARTED**.
S1 implementation, local tests and Browser QA remain accepted at
`0c6c6c9be89f22fe2e8f345a7d6e84720bb609f3`. This handoff changes planning only.
The planning delivery identity is the Git commit containing this update; remote push/CI must be
checked against that exact commit rather than inferred from local documentation checks.

This is the single live handoff. [Project Blueprint](docs/PROJECT_BLUEPRINT.md) owns the frozen
macro-route and S1.5/S2 acceptance criteria;
[Public Product Contract](PUBLIC_PRODUCT_CONTRACT.md) owns supported behavior and naming boundaries.
[Project Status](docs/PROJECT_STATUS.md) retains historical P0/real-smoke evidence. The previous S0
handoff is preserved in Git at `eceefeccbfb47607cb0463ad410ef429fc2c032c`.

## Baseline and authorization

- Existing repository/remote: `git@github.com:a27497/harnesslab-ai.git`.
- Worktree: `/home/dev/projects/harnesslab-ai-integration`.
- Feature branch: `codex/l-real-agent-main-integration`, tracking the same branch on origin.
- Planning starting HEAD / accepted S1: `0c6c6c9be89f22fe2e8f345a7d6e84720bb609f3`;
  starting worktree clean and branch tracking origin. S1 originally started from
  `eceefeccbfb47607cb0463ad410ef429fc2c032c`.
- Frozen P0 commit remains `20d90700e5963ca9db3c86379e190da27cafb258`.
- Current user explicitly authorizes updating PROJECT_BLUEPRINT and CURRENT_MILESTONE with the
  forward plan and source-grounded S1.5/S2 acceptance criteria, then commit/push of this branch.
  **Planning only:** no S1.5/S2 implementation, merge, repository/remote rename, tag, deployment,
  external connector or new paid campaign is authorized in this task.
- Six other worktrees were observed and are not task targets. This planning task does not start,
  stop or modify product/database resources.

## Current route and planning handoff

S0 and S1 are complete. The next planned stage is **S1.5 — mainline integration and SameScale
canonical identity**, currently **NOT_STARTED**. S2 is **Local Productization & Developer
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

## Planning verification

- Reviewed source entrypoints, CLI registration, lifecycle/trusted manifest selection, Compose and
  Docker build, static assets, showcase and router, plus existing distribution/lifecycle/CLI and
  fresh-setup contracts. This is scoped source review, not runtime acceptance of future behavior.
- `uv run --locked pytest -q tests/test_product_distribution.py tests/test_release_contracts.py
  tests/test_ci_workflow_contracts.py`: **32 passed in 20.07s**.
- Local Markdown links/anchors and scope/compatibility consistency checked; `git diff --check`
  passed. Only the two planning documents changed; source, public claims, lockfiles and frozen
  evidence remain unchanged. Link verification used the locked uv Python environment because
  plain `python` is not on this shell's PATH.
- S1.5 main integration/canonical rename and S2 implementation/fresh-environment acceptance:
  **NOT_RUN**. No new runtime/browser/database acceptance is claimed by this planning update.
- Planning commit push and remote CI are reported against its exact SHA after commit; remote CI
  is not implied by the local results below.

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

S1 is complete. Stop this task after the two planning documents are checked and committed/pushed
to the current feature branch, with exact remote SHA and CI status reported separately. Wait for a
new scoped request before executing S1.5 or S2; the roadmap itself does not start either stage.
The S1 handoff recorded removal of temporary S1 PostgreSQL/volume and QA server after acceptance,
with historical/demo resources retained; this planning task does not repeat that cleanup.

New live Real execution, full A–K/release acceptance, clean-clone reproduction, physical-device and
non-Chromium testing are **NOT_RUN** in S1. Original real-session restoration and human ownership
remain **NOT_VERIFIED**; historical runtime/security debts remain separate scopes. This product
refactor makes no new causal, model-ranking, reasoning-effort, or automatic-repair claim.
