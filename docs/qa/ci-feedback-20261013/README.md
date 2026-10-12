# CI feedback optimization — 2026-10-13 (Asia/Shanghai)

Base main@5bfb6745d62ac9747b13690093ab4f361999bc39. Independent branch
`codex/ci-feedback-20261013`, implementation commit `f19e7c599c222fcd4e822242fa52ed8fec9d5ade`.
No product/API/data/frozen evidence edit, real model/Agent/provider call, PR, merge or deployment.
feat/acceptance-workbench-v2 and PR #14 were not changed.

## Diagnosis before optimization

Read the original Fast CI, offline, manual Full Release and self-hosted workflows, all 29 bounded
selectors, S3 driver and workflow contracts. Downloaded actual job/step timestamps and logs.
The user's recent push [Fast CI 38284462908](https://github.com/a27497/samescale/actions/runs/38284462908)
was 339s for gates (342s created-to-completion): core 261s / 587 PASS, static 26s, frontend 21s,
locked dependency sync 2s. [Offline 38284462903](https://github.com/a27497/samescale/actions/runs/38284462903)
was 63s for the job, 45s replay/regression. Dependency caching alone cannot explain/fix the long path.

For the same main product-code base used by this branch,
[old Fast CI 38133372210](https://github.com/a27497/samescale/actions/runs/38133372210) was 352s
for gates / 355s workflow elapsed, and
[old offline 38133372230](https://github.com/a27497/samescale/actions/runs/38133372230) was 62s.
The recent feature baseline is shown to match the user's observation; main is the closer code-base
comparison. These are individual observations, not a repeated controlled benchmark.

The unmodified bounded suite was run against a newly created disposable PostgreSQL 18 database,
with no existing data access: **587 PASS / 260.55s**. JUnit module costs show reconciliation 133.90s
(122.01s shared setup), DTO 33.95s, Tier-B 28.29s. The owned test container was removed afterwards.
This led to module grouping rather than distributing individual cases and repeating expensive fixtures.

## Actual first optimized remote results

Both workflows succeeded on exact implementation SHA `f19e7c5...`:
[Fast CI 38287236447](https://github.com/a27497/samescale/actions/runs/38287236447),
[offline 38287236491](https://github.com/a27497/samescale/actions/runs/38287236491).
Fast workflow elapsed **199s**, approximately **42% less** than the recent push's 342s and **44% less**
than the same-main-base run's 355s. Full bounded regression was actually run, not skipped.

| Job or corresponding old serial component | Old recent push | Optimized actual job | Optimized execution step |
| --- | --- | --- | --- |
| Entire Fast CI workflow | 342s | 199s | — |
| scope / policy checks | part of gates | 10s | dependency-free routing/inventory checks |
| Python static checks | 26s step inside gates | 39s | 24s |
| Frontend contracts | 21s step inside gates | 39s | 27s; expanded to all Vitest + production build/types |
| Bounded core regressions | 261s serial step | parallel groups below | slowest group 152s |
| core full 0 — reconciliation | part of 261s | 176s | 152s |
| core full 1 — DTO + Tier-B | part of 261s | 113s | 84s |
| core full 2 — sessions/plans/execution | part of 261s | 71s | 45s |
| core full 3 — remaining contracts/safety/history | part of 261s | 70s | 40s |
| gates result aggregator | part of gates | 6s | requires every applicable job success |
| offline-regression | 63s (45s step) | 69s | 56s; unchanged workflow/guards |

Before, component times were nested in one 339s job. After, jobs overlap; **do not sum job durations
as user feedback latency**. Offline was deliberately retained on every event and is not claimed faster.
The new source execution still shows reconciliation setup **125.53s**, so the remaining lower bound is
observed and protected. Cold npm cache/setup and runner variability affect individual job times.

All 4 jobs recorded the same collection digest/count. Counts: **26 + 7 + 164 + 400 = 597 PASS**,
exactly the original **587** plus **10** routing-policy regressions; no missing/duplicate/skip/error.
[Independent receipt/count proof](inventory-proof.json). Full frontend **223 PASS / 18 files**,
production build/types PASS; all Python lint/format and strict mypy **431 sources PASS**. S3 again
passed **73 tests**, two pinned offline replays and fixed goldens. No paid/provider/Agent runtime.

## Trigger policy and protections

See [the policy table and exact path rules](../../CI_FEEDBACK.md).

- Pure frontend branch push: full frontend tests/build/types + the existing DTO privacy boundary;
  routing/inventory checks and S3 remain. Unrelated backend/static families move to full PR checking.
- Ordinary docs-only branch push: routing/whitespace/inventory checks and S3; backend/static/frontend
  move to full PR checking. Frozen/public projection/structured inputs and policy files are not ordinary docs.
- Backend/tests/scripts/CI/dependency/unknown changes: all frontend/static/backend groups plus S3.
- **Every PR and main push always runs full**, including frontend/docs-only PRs. Cumulative branch
  changes preserve earlier backend/CI work after a later docs commit or cancellation.

Original selector inventory fingerprint is pinned; groups are disjoint/exhaustive. Complete collection,
nonzero matching JUnit counts, no skips/failures/errors and all required job successes are mandatory.
Partial checks use `push-feedback`, never the legacy full `gates` check context. No original product
assertion/test was deleted or relaxed. Workflow-shape assertions were adapted to the new job boundaries,
with new inventory/partition/failure/trigger checks. Existing S3/manual Full Release/self-hosted workflow
files and guards are unchanged. Manual release gates remain at their existing release/dispatch timing.

## Local verification and limits

Original core profile 587 PASS; revised CI/workflow/offline mutation contracts **46 PASS / 4.13s**;
dependency-free routing unittest **10 PASS**; actual local DTO-boundary runner **1 PASS / 37.40s**.
Whole-repo Ruff/format PASS (**842 files**), strict mypy PASS (**431 sources**), whitespace PASS.
Original dirty tracked diff compared byte-identical at closeout; frozen/product/API/frontend trees
have no diff from main. All local artifacts in `/home/dev/samescale-deliverables/ci-feedback-20261013/`.

**Main currently has no branch protection or ruleset**, confirmed by read-only GitHub API. Full PR runs
are automatic, but the workflow alone cannot block an unprotected merge/direct push. An authorized
administrator must require `gates` and `offline-regression` at the current PR merge/head identity
for enforced pre-merge blocking. Settings were not modified; this pre-existing gap is not claimed fixed.

The branch's CI changes conservatively force full scope, so a genuine remote frontend-only/docs-only
lightweight push has **not** been measured; routing is unit-tested, and DTO runner is locally executed.
No new PR/merge_queue integration, real model, production data, manual Full Release/self-hosted campaign
or load/cost benchmark was run. Parallelization adds setup/collection/runner-minute cost, despite lower
wall time. Future suites require maintaining the explicit bounded inventory and balanced groups.
A final receipt-only commit is verified separately on its exact pushed SHA; this report records observed
implementation-run facts, not an anticipated later CI result.
