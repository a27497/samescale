# CI branch main synchronization — 2026-10-13 (Asia/Shanghai)

Merge `main@adaa083bedb5ceb8aa167a3e9bfc6d704b200468` (PR #14) into
`codex/ci-feedback-20261013@f8a7897db57d216e4c97c4bdee4d756e24b8ac39` (PR #15).
Use a normal two-parent merge: no rebase, force push, main mutation or PR merge.

## Preservation and conflicts

Only CURRENT_MILESTONE.md and docs/PROJECT_BLUEPRINT.md conflict. Both sides appended independent
live/historical records at the top. Retain the CI policy/receipts and all product positioning,
multi-tool intake, UX and copy closeout observations; add the current synchronization scope and mark
old headings as historical. The common previous content remains once. No effective product claim or
CI policy is dropped. The merge product source/frontend/README/public-contract trees exactly match
main; CI workflow/scripts/selectors/shards/contracts exactly match the prior CI branch. The extra
changes are this dated report and the two project documents. Frozen evidence is unchanged.

## Grouping decision

Keep all four groups and every selector/assertion unchanged. The prior exact-head remote Fast run
[38288007927](https://github.com/a27497/samescale/actions/runs/38288007927) reported group jobs
185/109/66/74s. The original diagnosis and first optimized remote run showed a module-scoped
reconciliation snapshot taking 122.01s locally / 125.53s remotely, before its dependent cases.
Splitting those cases across runners repeats qualification setup; distributing other modules into
group 0 only increases the longest path. Small fixture-independent cases cannot equalize a dominant
125s setup. A useful larger refactor would change fixture/preparation behavior or share derived
results, beyond this merge-only scope and potentially weakening independent execution guarantees.
No nominal balancing is claimed from normal hosted-runner variance. New actual timings are reported
from final-SHA jobs at handoff, without summing parallel job durations as feedback latency.

## Actual local checks

Run in the independent CI worktree with `PYTHONPATH=src:.` and the existing locked development venv:

- `pytest -q tests/test_ci_routing.py tests/test_ci_workflow_contracts.py tests/test_s3_ci_regression.py`:
  **46 PASS / 4.25s**.
- `pytest -q tests/test_external_evidence_generic.py`: **26 PASS / 3.92s**. Supplied synthetic files;
  no real Agent/model, existing database or Docker Verifier execution.
- `ruff check .` and `ruff format --check .`: **PASS / 849 formatted files**.
- `mypy src tests scripts`: **PASS / 433 source files**.
- Whitespace, conflict-marker absence, main ancestry after commit, both-parent tree-preservation and
  original dirty-worktree byte comparison are checked before pushing.

JUnit and final exact-SHA remote job/log/mergeability receipts are local review artifacts under
`/home/dev/samescale-deliverables/ci-main-sync-20261013/`. The final report supplies actual remote run
links and measured completion, rather than this commit anticipating its own future CI verdict.

## Limits

No product logic, API/data, frozen evidence, original dirty workspace, repository settings/protection,
main or feature branch edits. Normal push to PR #15's existing branch only; no PR merge/deployment.
Existing path-routing/required-check policy stays unchanged. Full PR checking and guarded offline
replay remain mandatory in workflow logic; repository protection configuration is outside this task.
Manual Full Release/self-hosted jobs, real Agent/Provider, fresh production UAT and browser verification
are not executed here. The original automatic bounded inventory is retained; new multi-tool generic
cases are checked locally above, not falsely counted as part of that bounded remote inventory.
