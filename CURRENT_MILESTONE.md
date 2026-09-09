# SameScale Product — Current Milestone

Updated: 2026-09-09. Milestone: **S0 — Codex-native development environment and P0 baseline**.
State: **ACCEPTED — S0 local acceptance complete**. Delivery identity is the Git commit containing
this handoff; verify push/CI from the remote branch and Actions, not from this document alone.

This is the single live task handoff. [Project Blueprint](docs/PROJECT_BLUEPRINT.md) owns the S0
plan; [Public Product Contract](PUBLIC_PRODUCT_CONTRACT.md) owns user-facing behavior and claims.
[Project Status](docs/PROJECT_STATUS.md) preserves earlier P0 and real-smoke evidence.

## Baseline and authorization

- Existing repository: `git@github.com:a27497/harnesslab-ai.git`; no new repository or Git init.
- Current worktree: `/home/dev/projects/harnesslab-ai-integration`.
- Feature branch: `codex/l-real-agent-main-integration`, tracking the same branch on `origin`.
- Starting HEAD: `79056a1a4619863970b8d5b37102434427cec5f3`.
- Frozen P0 migration commit: `20d90700e5963ca9db3c86379e190da27cafb258`. All 16 input files in
  that commit were checked byte-for-byte against the original dirty-tree snapshot before committing.
- The starting tree was dirty: 11 modified tracked files and 5 new P0 files. They are part of the
  requested migration baseline, not discarded or treated as already committed evidence.
- Six other worktrees were present, on `main`, `codex/kc-release-contract-reconciliation`,
  `codex/m1-evaluation-system-2-gap-reconciliation`,
  `codex/m8a-keyless-candidate-inventory-preregistration`, `codex/l1-architecture-ownership-audit`,
  and `codex/kb3-core-real-matrix-v5`. S0 does not modify those worktrees.
- Current request authorizes S0 implementation, acceptance, commit, and push of this feature branch.
  It does not authorize merge, tags, deployment/publication, or paid Provider/Harness/Judge campaigns.

P0 input files retained:

```text
README.md
docs/FIRST_APPLICATION.md
docs/PROJECT_STATUS.md
frontend/src/App.vue
frontend/src/api/analyst.ts
frontend/src/router/index.ts
frontend/src/types/analyst.ts
frontend/src/views/AnalystView.vue
frontend/tests/analyst.spec.ts
frontend/tests/workbench.spec.ts
frontend/src/components/InvestigationReport.vue        (new)
frontend/src/views/AnalystHomeView.vue                 (new)
frontend/tests/analyst-home.spec.ts                    (new)
src/harnesslab/analyst/api.py
src/harnesslab/analyst/showcase.py                     (new)
tests/test_analyst_showcase.py                         (new)
```

## S0 delivery

- Preserve and validate the three P0 entrypoints and host-validated reports.
- Root `AGENTS.md`, this handoff, the public contract, and
  [repo-local Skill](.agents/skills/samescale-product/SKILL.md) provide the development entry.
- README and legacy blueprint/status point to the new entry without rewriting historical evidence.
- Fast CI includes the P0 showcase backend and home/report frontend regressions.
- The existing wheel includes the new development documents and Skill, preserving relative links
  in its bundled build context. This adds documentation only, with no dependency/lock changes.
- Preserve runtime names, locks, schema, commands, frozen artifacts, and historical compatibility.

## Acceptance record

S0 checks are keyless and run against the existing locked toolchain: Python 3.12.14, uv 0.12.5,
Node 24.18.1, npm 11.16.0. Database tests use a newly created disposable PostgreSQL 18 container,
not either of the pre-existing demo/restore databases.

| Check run in S0 | Result |
| --- | --- |
| `tests/test_analyst_showcase.py` + `tests/test_analyst_contracts.py` | 19 passed; offline/history separation, host validation, corruption fails closed, package path |
| `tests/test_analyst_sessions.py` + `tests/test_analyst_e2e.py` | 78 passed in 18.39s after migrations through `20260908_0007`; disposable database only |
| `tests/test_ci_workflow_contracts.py` | 15 passed after updating the existing expected CI test list and requiring the showcase suite |
| `tests/test_release_contracts.py` | 12 passed; retained historical release contracts |
| `tests/test_product_distribution.py` | 5 passed; existing distribution/build contracts |
| `npm run test --prefix frontend` | 50 passed across 5 files |
| `npm run build --prefix frontend` | Type check and Vite production build passed |
| Ruff check/format + mypy on changed Python files | Passed for `api.py`, `showcase.py`, `test_analyst_showcase.py`, and `test_ci_workflow_contracts.py` |
| `uv run --locked python scripts/verify_fresh_setup.py` | Repository preflight passed; clean-clone Actions reproduction explicitly NOT_RUN |
| Skill creator `quick_validate.py .agents/skills/samescale-product` + UI metadata inspection | Passed; valid name/frontmatter, links, default prompt, implicit discovery left enabled |
| Documentation links and authority review | 59 local Markdown links resolve across 9 S0 documents; live state/plan/public claims have separate owners |
| `uv build --wheel` and ZIP inspection | Build passed; development files, bundled relative links, and original evidence bytes preserved |
| P0 / frozen evidence comparison | 16/16 original input files in P0 commit match; all 5 real-smoke files match starting HEAD and the wheel |
| `git diff --check` | Passed |

Totals: **129 distinct Python tests and 50 frontend tests passed**; reruns are not added to totals.
The CI test initially rejected the expanded frontend command because its expected list omitted
the new home suite. The list was updated, a backend showcase inclusion assertion added, and all
15 CI contract tests then passed. No application assertion was weakened.

The temporary PostgreSQL container and its volume were removed after the 78-test run. Existing
demo/restore containers and other worktrees were retained. No Provider requests or real campaigns
were launched. P0 browser results remain historical: a new interactive browser rehearsal and
full A–K/release CI were **NOT_RUN** in S0. Skill filesystem/schema validation does not claim an
independent new Codex-session discovery test. Remote Fast CI is a separate exact-commit result.

## Stopping point and remaining limits

The authorized delivery consists of the frozen P0 commit followed by the S0 setup commit, pushed
to the existing feature branch. The task handoff reports the verified remote SHA and CI state;
this document does not claim a CI result before the push. No S1 or later product work starts
automatically. Any future milestone needs a
bounded user request. Human ownership remains **NOT_VERIFIED**; original real-session restoration,
previous runtime/security debts, and full release acceptance remain separate scopes.
