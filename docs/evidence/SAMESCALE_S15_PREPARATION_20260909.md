# SameScale S1.5 preparation — 2026-09-09

This is a dated pre-merge verification record, not proof of main integration or repository rename.
Live state belongs to [Current Milestone](../../CURRENT_MILESTONE.md); the execution procedure
belongs to [Project Blueprint](../PROJECT_BLUEPRINT.md).

## Inputs and repository inventory

| Item | Observed value |
| --- | --- |
| Remote main | `3335668f4f11e384a9f99fb0a8692f07d8937902` |
| Candidate / planning freeze | `89cb54070bdec79414399f21fa141cd8134ea518` |
| Accepted S1 | `0c6c6c9be89f22fe2e8f345a7d6e84720bb609f3` |
| Ancestry | Main is an ancestor; 0 main-only / 5 candidate-only commits; no divergence |
| Candidate scope versus main | 113 files; 8,576 insertions / 869 deletions, including Real Analyst, P0, S0, S1 and route freeze |
| Existing repository | `a27497/harnesslab-ai`, private, default branch `main` |
| Repository identity | Numeric ID `1342785518`; node ID `R_kgDOUAlH7g` |
| Access/configuration | Current account ADMIN; main unprotected; repository ruleset listing empty |
| Target-name lookup | `a27497/samescale` returned HTTP 404; this is not a reservation or proof a rename will succeed |
| Existing tag | `v1.0.0-core` → `e3cab6f180f2bbcd6c8f134aa3d710c503fe6e87` |
| PR/issue inventory | No PR for this feature branch; open issue/PR listing empty |
| Worktrees | Current integration worktree plus six others, retained without file/branch changes |

The five commits, oldest first, are `79056a1`, `20d9070`, `eceefec`, `0c6c6c9`, `89cb540`.
The original integration/conflict decisions remain in the
[2026-09-08 integration record](../MAINLINE_REAL_AGENT_INTEGRATION_20260908.md), including its
dated follow-up. Its old blocked Real-smoke status is historical, not today's live state.

## Scoped compatibility review

- Reviewed main/candidate changed-file inventory and the queue/executor claim-attempt guards,
  verified trace read, additive Analyst model export and migration. Existing main migrations
  are retained; the added migration is the single `20260908_0007` successor of `20260904_0006`.
- The deleted owner-only `harnesslab.leases` module has no remaining source/test/script imports;
  main's authoritative lifecycle, its DB model and original migrations remain. This is scoped
  integration review, not a new repository-wide security audit.
- Between accepted S1 and the candidate, source, frontend, migrations, profiles, release/tasks,
  Docker configuration, pyproject/uv lock and frozen evidence have no Git differences. This task
  introduces no runtime behavior change and no `samescale` executable.
- Active canonical references need only current entrypoint/handoff reconciliation. No hardcoded
  `a27497/harnesslab-ai` URL was found in the checked workflows, product Docker files or package
  metadata. The dated FIRST_APPLICATION Actions link is historical and remains unchanged.
- `origin` is shared Git configuration across linked worktrees. A later URL update affects their
  fetch/push destination; their working files, directories and local branch tips are separate
  and are not cleanup targets.

## Existing advanced-readiness limitation

During actual Overview navigation, the server raised `ModuleNotFoundError: No module named
'scripts'` from `src/harnesslab/release/reconciliation.py:stable_sources`, reached through
`/api/workbench/core-readiness`. The normal console-entrypoint server did not make the repository
`scripts` namespace importable. The corresponding imports are present in both remote main and
accepted S1; this preparation did not introduce or repair them.

The legacy route/navigation assertion passed, but its advanced readiness API did not. Browser
page-exception checks do not detect every failed background HTTP response. Offline/history and
persisted Fake report/review checks passed independently. Treat this as an explicit pre-existing
startup/distribution limitation for S2 verification, not a successful Core Readiness acceptance.
This evidence is a scoped diagnosis, not a claim that all other advanced endpoints were checked.

## Verification

| Check | Result |
| --- | --- |
| Candidate Fast CI | [Run 34385963877](https://github.com/a27497/harnesslab-ai/actions/runs/34385963877): SUCCESS on exact candidate SHA; all recorded steps succeeded |
| Focused Python acceptance | **157 passed in 36.00s**, zero skipped; showcase/contracts/sessions/E2E/mainline integration/distribution/lifecycle/CLI/CI/release contracts |
| Database | New disposable PostgreSQL 18 container; migrations through `20260908_0007`; historical/restore/demo databases not used |
| Frontend | **53 tests passed across 5 files**; type check and Vite production build passed |
| Browser | **7 grouped checks passed**, Chromium `151.0.7922.34`; desktop 1440×1000 / mobile viewport 390×844; no uncaught browser exceptions or checked horizontal overflow |
| Visual inspection | Current desktop/mobile offline report screenshots inspected |

Browser checks reused the S1 acceptance script with an isolated S1.5 fixture and loopback port 8015.
Actual API checks covered offline graph/citation/focus, frozen historical provenance, persisted
Fake create/step/reload/finalize/propose/review, legacy Overview and mobile controls. The sole
injected historical HTTP 409 remained labeled as injection; retry returned to the actual API.
The fixture was one queued synthetic run, never executed. Server Real enablement remained false;
no paid/provider/Harness/Judge campaign was launched. Fake approval remained review-only.

Local scratch evidence is under `artifacts/samescale-s15/`; Python/frontend/build logs and JUnit
are copied there from the temporary test outputs. Browser tooling reused an existing temporary
environment; repository dependencies and lockfiles were not changed.
The temporary QA server and test PostgreSQL container/volume were removed after verification;
the two pre-existing demo/restore containers were retained.

Main merge, canonical rename, post-merge/post-rename CI, canonical clone/fetch, old-URL redirects,
and tag/PR/run continuity after rename are **NOT_RUN** at this preparation point. New live Real,
full A–K and S2 clean-environment productization are outside this verification. The preparation
checks do not mark S1.5 accepted or start S2.
