# CI feedback and pre-merge regression policy

The existing automatic CI inventory remains complete: all 29 bounded Python selectors, their collected
cases, Python lint/format/types, frontend contracts/types, and guarded S3 offline replay. This change
only schedules them differently. Manual Full Release CI (qualification, Gates A–K and fresh setup),
self-hosted workflows, product code, models, dependencies and frozen evidence are unchanged.

## Triggers

Scope is the **entire branch since its merge-base with origin/main**, including removed/renamed old
paths. It is not just the last commit/push. Missing history/reference, empty comparisons and unknown
paths default to full checking. Every PR and every main push always uses full scope.

| Change / event | Scope policy | Frontend | Python static checks | Bounded Python regressions | S3 offline |
| --- | --- | --- | --- | --- | --- |
| Frontend-only branch push (ordinary docs also allowed) | policy/whitespace | full Vitest + build/types | deferred to PR | existing DTO privacy boundary | always |
| Ordinary docs-only branch push | policy/whitespace | deferred to PR | deferred to PR | deferred to PR | always |
| Backend/tests/scripts/shared/CI/dependency/unknown branch push | policy/whitespace | full | full | all 4 isolated groups | always |
| Every PR, including frontend/docs-only | policy/whitespace | full | full | all 4 isolated groups | always |
| Every main push | policy/whitespace | full | full | all 4 isolated groups | always |

Ordinary docs are root README.md/CURRENT_MILESTONE.md/PUBLIC_PRODUCT_CONTRACT.md and `docs/**/*.md`,
excluding frozen evidence, recruiter assets and docs/ANALYST.md (a frozen badcase input). Other root
policy/license/configuration files and structured documents default to full. Any earlier backend/CI
change in a mixed branch keeps later frontend/docs pushes full, even after a cancelled previous run.
There are no top-level path filters that leave a required workflow pending forever.

## Parallel execution and integrity

The former serial `gates` job is split into routing, Python static checks, frontend, and 4 backend jobs,
then an always-running result check. Each backend job owns its own PostgreSQL service/database. No
xdist/shared database, new runtime dependency, omitted selectors or modified product assertion.

`.github/ci-core-selectors.json` is the exact original selector list from main@5bfb674. A dependency-free
unit test pins its independent fingerprint. `.github/ci-core-shards.json` partitions that list, verified
as exhaustive and nonoverlapping. Modules stay together to avoid repeating session/module fixtures.
Each backend job collects the same complete inventory, emits its count/hash and selected count, runs
its own collected IDs, then requires matching nonzero JUnit counts with no failure/error/skip.

- Group 0: release reconciliation (expensive shared qualification fixture).
- Group 1: DTO privacy boundary + Tier-B deterministic baseline/oracle checks.
- Group 2: Analyst sessions + local planning/execution.
- Group 3: remaining safety/contracts/frozen evidence/CI checks plus CI routing regressions.

All four groups must succeed, with fail-fast disabled. Failure, cancellation, missing required job or
unexpected skip cannot pass the full result check. Missing routing results also fail closed.
Lightweight pushes publish **push-feedback**, never the full **gates** check context. All full cases
retain **gates**. Keep **gates** and **offline-regression** as the required pre-merge checks, at the
current PR merge/head identity; a lightweight push-feedback success is not full regression acceptance.

**Existing repository setting gap:** main currently has no branch protection or ruleset (read-only
inspection returned Branch not protected and no rulesets). The workflow automatically runs full PR
checks but cannot itself stop an unprotected merge/direct push. An authorized repository administrator
must enable required checks for enforced pre-merge blocking. This task does not modify repository
settings or PR #14 and does not claim an enforcement guarantee that does not exist.

## Caching and timing

Existing pinned uv/cache and `uv sync --locked` remain. Frontend setup-node now caches npm downloads by
frontend/package-lock.json, but still performs `npm ci`, full Vitest and production build/type checking.
No cached result replaces an executed regression. S3 keeps its network namespace, pristine temporary
HOME, offline restrictions, fixed goldens, two replays and positive test receipts on every event.

Baseline remote push 38284462908: gates 339s, bounded tests 261s (587 PASS), static checks 26s,
frontend 21s. Offline run 38284462903: job 63s, isolated replay/regression step 45s. Dependency sync was
2s, so caches alone are not the principal solution. A separate disposable local database reproduced
the same 587 tests in 260.55s: release reconciliation module 133.90s (122.01s setup), DTO 33.95s,
Tier-B 28.29s. These local module times diagnose the composition; they are not remote speed estimates.
Remote optimized measurements belong in the dated QA report and final handoff after actual runs.

The remaining lower bound is the shared reconciliation fixture. Parallel runners shorten wall time
but add setup/collection cost and runner-minutes; fairness/availability of hosted runners affects queues.
Frontend/docs lightweight scenarios are policy-tested; unless explicitly measured separately, their
end-to-end remote duration must not be claimed as observed. No release/full lifecycle/real Agent or
Provider execution is implied by keyless CI success.
