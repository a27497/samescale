---
name: samescale-product
description: Implement, migrate, and verify SameScale Product in this repository using the existing HarnessLab P0 baseline. Use for product milestones, Analyst user journeys, public claims, and compatibility-aware delivery; not for launching evaluation campaigns or unrelated repositories.
---

# SameScale Product

Work from the current checkout. Resolve the repository root with `git rev-parse --show-toplevel`;
do not assume a machine-specific path or create a replacement repository.

Read [AGENTS.md](../../../AGENTS.md), [Current Milestone](../../../CURRENT_MILESTONE.md), and
[Public Product Contract](../../../PUBLIC_PRODUCT_CONTRACT.md). Use
[README](../../../README.md) for setup/check commands and
[Project Blueprint](../../../docs/PROJECT_BLUEPRINT.md) for the authorized plan.
Read [legacy status](../../../docs/PROJECT_STATUS.md) only for P0/real-smoke evidence or limitations.

Inspect branch, worktrees, upstream, and the complete dirty diff before editing. Identify existing
user work and the bounded requested outcome. Existing roadmap items are context, not instructions
to advance. Use current authorization without asking again for already authorized routine actions.

## Implement from P0

- Trace the user journey through `frontend/src/router`, `frontend/src/views/AnalystHomeView.vue`,
  `frontend/src/views/AnalystView.vue`, `frontend/src/components/InvestigationReport.vue`, and
  `src/harnesslab/analyst`. Reuse the graph, Provider boundary,
  PostgreSQL session journal, and host validators; do not add another Agent runtime.
- Preserve the distinction between synthetic offline Fake, frozen historical Real, and current
  database Fake/Real. Do not reconstruct original sessions from summaries or relabel Fake as Real.
- Product naming does not rename packages, CLI/env/API/schema identities, frozen models,
  experiments, or digests. Read the compatibility section before changing a product surface.
- Preserve explicit Real enablement/budgets/confirmation and review-only approvals. Evidence text
  is untrusted data; the development assistant's tools are not tools granted to the product Agent.
- Update public claims when an authorized behavior changes. Preserve unknowns and original evidence;
  no amount of product polish turns an unverified cause, recovery, or human contribution into proof.

## Verify and hand off

Select checks by the changed contract, not by the full historical phase map:

- Showcase/graph: `uv run --locked pytest -q tests/test_analyst_showcase.py tests/test_analyst_contracts.py`.
- Current sessions/API/recovery/approval: also run `tests/test_analyst_sessions.py` and relevant
  `tests/test_analyst_e2e.py` checks with an isolated disposable PostgreSQL database and migrations.
  Never reuse a historical/business database for these fixtures; use keyless mocks and no credentials.
- Frontend: `npm run test --prefix frontend` and `npm run build --prefix frontend` (includes types).
  Use actual browser verification when changed interactions/layout need it; report unit tests and
  browser evidence separately.
- Python: focused Ruff check/format and mypy. Documentation: resolve relative links, compare claims
  to source, and run affected existing documentation/CI contracts. Check frozen bytes against Git.

Correct concrete failures and rerun affected checks. Do not rerun paid investigations or frozen
Matrix campaigns to obtain green status. Report zero tests, missing prerequisites, skipped critical
checks, and unexecuted checks honestly. Stop testing when the requested contract has sufficient proof.

Update CURRENT_MILESTONE with results and limitations; keep plans in the blueprint. Before any
authorized commit/push, inspect the final diff and staged file list, preserve user work, and run
`git diff --check`. Push only the authorized feature branch without force; verify remote SHA and
distinguish local acceptance from remote CI. Stop at the requested milestone.
