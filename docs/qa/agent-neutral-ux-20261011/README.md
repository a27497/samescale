# Multi-tool import UX correction verification — 2026-10-11 UTC

Base: `feat/acceptance-workbench-v2@f3c25fba18011cf02c37b57a4a172ac3291602df`.
Worktree: `/home/dev/.worktrees/samescale-agent-neutral-20261012`.
Scope is six follow-up UX corrections, normal commit/push only; no PR, merge or deployment.
The existing artifact-directory suffix is retained; actual checks ran on 2026-10-11 UTC.

## Delivered behavior

1. “全部来源” filters approved metadata after unlock. Only the existing backend parses `auto-v1`
   supplied files at intake. Metadata-free auto sources remain under both Codex and Claude filters;
   declared harnesses retain their own filter. Only code-only sources enter the code-only filter.
   Actual browser tests selected each auto source under the opposite filter and confirmed the correct
   imported adapter from supplied bytes, rather than falsely binding the UI selection as tool identity.
2. Only metadata-free legacy `codex-*`, `native-hook-v1`, `verified-hook-v1` imply Codex. All other
   formats display “未报告” until tool metadata/conversion resolves them. Recorded metadata takes priority.
   The generic hook approval was visibly unreported before import; tests also render metadata-free
   generic stream/H-Lane/auto/future formats. All four legacy formats retain the Codex attribution.
3. Unverified details, including code-only, show the exact record-bound existing CLI command,
   task admission / original policy / pinned Verifier prerequisites, explicit confirmation,
   one-attempt/no-retry semantics and reload instructions. No browser execution authorization or API
   privilege was added. Missing prerequisites and zero checks stay NOT_VERIFIED.
4. Missing fields and verification reasons use Chinese explanations (reactive English also available).
   Unknown future fields remain explicitly unreported. Raw field/reason/status codes, original Episode,
   diagnostics and Trace remain in default-collapsed technical details. Raw original-state duplication
   is removed from the human summary without changing the status semantics.
5. Page and route headings use “验收任务”; Codex/Claude/code-only intake is described separately
   from the existing Codex-only local planning configuration and closed real-Codex execution. Cursor /
   DeepSeek may provide code-only inputs; their native log adapters are not claimed.
6. Tool selection is absent before unlock. Approval/consent, operator/origin, pins, privacy, corruption
   and provenance gates are unchanged; backend sources and immutable evidence were not modified.

## Actual local results

Commands use task-worktree sources (`PYTHONPATH=src:.`) and the existing locked Python environment
`/home/dev/projects/samescale/.venv`; dependencies/frameworks were not changed. DATABASE_URL was unset,
so no historical/demo/existing database was accessed.

- `env -u DATABASE_URL PYTHONPATH=src:. /home/dev/projects/samescale/.venv/bin/pytest -q tests/test_external_evidence.py tests/test_external_evidence_p1.py tests/test_external_evidence_generic.py tests/test_external_evidence_docker.py`:
  **81 passed in 47.77s**, including old identities, malformed/sensitive/pin/corrupt input refusal,
  shared private API gates and all three actual Docker parameterizations. FrozenEvidenceGuard passed.
- `npm --prefix frontend test`: **243 passed / 19 files**, final run 7.32s. Added source-filter,
  legacy/unknown metadata, locked selection, exact independent-verification guidance and localized
  summary coverage. Final suite was rerun after the last summary/guidance edit.
- `npm --prefix frontend run build`: **PASS**, includes `vue-tsc --noEmit` and Vite production build.
  First type check caught a test-only DOMWrapper `get(...).exists()` misuse; corrected to `find(...).exists()`.
  Final type/build passed. No failed or skipped cases are counted as passed.
- Focused `ruff check` / `ruff format --check`: **PASS**, external-evidence sources and four test modules,
  11 files. Focused strict `mypy src/harnesslab/external_evidence`: **PASS**, 7 source files.
- Actual Chromium with production assets and real private FastAPI: **48 checks PASS**, 1440×1000,
  zero page runtime errors. No request mocks, database, real Agent or Provider; only proactively created
  synthetic supplied files. [Check inventory and request paths](browser-checks.json).
  The final screenshots were visually inspected. CLI guidance was checked against the existing CLI and
  verifier implementation; the page never sends a verification/authorization/execute request.
- Existing documentation setup contract: **1 PASS**, `pytest -q tests/test_release_contracts.py::test_release_docs_and_fresh_setup_contract_exist`; local link existence checks in all **6** updated Markdown files PASS.
- `git diff --check`: **PASS**. The original dirty worktree tracked diff byte-compared identical to its
  earlier saved baseline; its untracked files were never touched. Frozen paths have no patch changes.

## Docker prerequisites and actual parameterized outcomes

`tests/test_external_evidence_docker.py` calls `tests/local_execution_helpers.py:prepare_execution_fixture`.
It requires a reachable Docker daemon and these **already cached** local image references. Missing
images produce `RuntimeError: Existing pinned local test images required; do not build or pull`;
the tests do not silently skip or fetch/build images.

| Reference | Local content ID observed in this environment | Role |
| --- | --- | --- |
| `harnesslab-phase-c:0.3.1` | `sha256:3af8b725f30eace3438f7ff3220cbd6d85ebeb6f7de9fecda8de53eb9487949b` | Pinned isolated hidden Verifier execution |
| `harnesslab-phase-e-codex:0.149.0` | `sha256:a1dcc819a4b7d7b6b01a1e91bf0a2ecabc068911e949d9db6da51beac2d5ef53` | Shared fixture inspects image metadata and binds the TaskStore runtime-image policy; Codex is not launched by these tests |

The daemon ran actual isolated Verifiers against a copied micro-python-clamp task and supplied final
Workspaces. Initial baseline-fail / oracle-pass task admission comes from real Verifier observations,
not a fabricated qualification result. Synthetic input logs never establish a verdict.

| Test parameter | Actual result | Checked outcomes |
| --- | --- | --- |
| `codex-hooks` | PASS | baseline VERIFIED_FAIL (3 checks); oracle VERIFIED_PASS (3 checks); timeout NOT_VERIFIED / 0 checks; interrupted attempt refuses |
| `claude-code` | PASS | same isolated outcomes; completion claim does not establish acceptance |
| `code-only` | PASS | same isolated outcomes without original Agent run evidence |

Each parameter also verifies original acceptance remains NOT_VERIFIED, one physical attempt,
no Agent rerun/automatic retry, unchanged saved record bytes and export/replay of the separate receipt.
These are the **3 cases inside the 81**, not another additive suite. No new Agent/model/Provider ran.

## Local artifacts and limits

Local directory: `/home/dev/samescale-deliverables/agent-neutral-ux-20261012/`.

- `locked-import-1440.png`, `auto-source-filter-1440.png`, `code-only-import-1440.png`.
- `code-only-summary-next-step-1440.png`, `code-only-full-1440.png`, `claude-summary-1440.png`.
- `acceptance-tasks-1440.png`, browser checks/driver/server, backend/frontend/build/static logs.
- `private-fixture/` and `synthetic-browser-export.json` contain only created synthetic sources,
  private test policies and projected records. The operator credential is a non-live test placeholder.
  No user sessions or private reasoning were collected. Screenshots/raw fixtures remain local.

No full PostgreSQL planning/execution lifecycle was run; the tasks browser page checked its disabled
configuration state and supported-tools text, while frontend tests cover unlocked planning behavior.
No real models/sessions, new production task admission, Cursor/DeepSeek native adapters, arbitrary
uploads, baseline+diff application, large/binary Workspace support, deployed website or remote CI result
is established. Independent acceptance still requires separate operator authority and trusted inputs.
