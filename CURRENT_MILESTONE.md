# SameScale Product — Current Milestone

## Phase S4 — Recruiter Demo + Job-search Freeze：验收收口中 — 2026-09-21

[Recruiter Demo](docs/recruiter/demo/index.html)、[3–5 分钟讲解稿](docs/RECRUITER_DEMO.md) 与
[面试/简历事实](docs/JOB_SEARCH_FREEZE.md) 已生成；[S4 report](docs/evidence/s4-job-search-freeze-20260921/README.md)。
8 项导出/安全投影测试 PASS，桌面与手机 file:// 离线浏览器验收 PASS，HTTP 请求 0。
独立 staged tree 的统一离线入口 **73 tests PASS**，全树 Ruff/format/mypy PASS；
GitHub 当前 S4 SHA 尚待验收。
Provider/model/Claude/Judge 新调用 0；S1 保持 partial/blocked，S2/S3 complete。
完成本次 S4 验收即求职冻结并 STOP，不规划 S5、不继续新功能、不 merge main、不 deploy。

## Phase S3 — CI Regression Integration：COMPLETE — 2026-09-21

[Final report](docs/evidence/s3-ci-regression-20260921/README.md) 与
[final status](docs/evidence/s3-ci-regression-20260921/final-status.json) 已产出。
统一入口 `bash scripts/ci_s3.sh NEW_OUTPUT_DIRECTORY`：隔离网络、清空环境、临时 HOME，
不执行 subject/命令/verifier；Provider/model/Claude/Judge 调用 **0**。

- 独立 staged tree **65 tests PASS**，两次 replay 的 5 个输出逐字节匹配 S2 冻结摘要。
  evidence/digest、replay、trace/schema/parser、changed-files attribution、failure taxonomy
  回归均有 fail-closed 覆盖；Ruff/format/mypy PASS。
- 实现 SHA `b2d729bc8d1c9eb793511b54a7b235a72e67cb9b` 已推送当前 feature branch；
  [Offline CI](https://github.com/a27497/samescale/actions/runs/35643033783) 与
  [Fast CI](https://github.com/a27497/samescale/actions/runs/35643033753) 均 **PASS**。
  SHA-bound GitHub receipt 与本地结果完全一致，65 项 JUnit 回读通过。
- 初次 CI 的 artifact 配额失败保留；后续改用 Actions 日志/summary，无删除历史 artifact。
  2085 个起始文件原内容保全；仅追加 S3 文档块，其他 dirty work 未纳入 scoped commits。

**S3 COMPLETE 后停止，不进入 S4；无 PR、merge main、deploy 或真实 benchmark workflow。**
S1 保持 PARTIAL REAL BENCHMARK / BLOCKED；不支持能力排名、完整配置比较或 Harness 因果结论。
下方为保留的历史状态，不自动启动其他阶段。

## KB4 CI compatibility repair — 2026-09-21

Repair base is `d46d02c249c862ccbf76cebaa90e353b4041d067`; only the two repair files and
related Milestone hunks are included in this compatibility commit.
Both failures from Fast CI 35563979439 were reproduced in the working tree and exported HEAD.
Commit `23ece300` legitimately evolved `harness_lane/adapter.py`, `docker_backend.py` and `trace.py`;
the historical-source compatibility map omitted these three paths. Each original digest matches
the Git blob at accepted commit `b3c36154871225d8af1cf4247258b129f8698f1c`.
The repair adds only those historical bindings to the existing map, plus three regression cases
checking unchanged report reproduction and rejection of historical-binding tampering.
All 185 tracked release/evidence files retain HEAD bytes; frozen results and conclusions are unchanged.
The two failed tests and directly related KB4 regressions pass: **74 tests** in an exported HEAD
with only the two repair files overlaid. Focused Ruff check/format and mypy pass.
No Provider/model/Judge/real L1 execution. Remote CI has not been rerun; local results do not claim
remote success. The user authorized this scoped commit and non-force push of the current feature
branch, followed by exact-HEAD CI inspection. Stop after reporting CI; do not expand the repair,
merge, deploy or launch real execution. Unrelated dirty work is preserved.

## L1 A Candidate evidence closeout — 2026-09-21

**L1 remains INCOMPLETE; comparison INCONCLUSIVE.** The only authorized `A/candidate/1`
attempt on `lecturelens-embedded-subtitle-language-metadata@1.0.1` is **NOT_VERIFIED / STOPPED**.
Subject timeout was **600 seconds**; recorded duration **601.037 seconds**. Verifier did not run;
five modified files were saved; token usage is **UNKNOWN**. Request ID and HTTP status were not
recorded. The 6000-token output declaration had no session hard cap. Model, relay and Provider
root cause remain **NOT_ESTABLISHED**.

[Original attempt evidence](docs/evidence/l1-a-candidate-real-20260921/README.md) and
[portable closeout supplement](docs/evidence/l1-a-candidate-closeout-20260921/README.md) retain
separate identities and the original NOT_VERIFIED Episode. Authorization
`3ce7b6074a1e4a5396ade94519c44824` and execution `a4869bcecb1148debd84bed5f7259d20` are
**consumed**; no retry, resume, Judge or new real attempt is authorized. Three prior rounds are
preserved; no Episode is overwritten or spliced. Subject/proxy and execution-network cleanup passed.

This closeout commits only this attempt's stable evidence, explanatory material and this L1
status hunk. Other accumulated work remains unstaged. Evidence/diagnostic quick checks: **21 passed**;
snapshot checks are recorded in the supplement. Push and CI are limited to the current feature
branch `codex/l-real-agent-main-integration`; verify CI against the pushed HEAD separately.
No merge to main or deployment is authorized.

**Post-timeout offline diagnosis recorded (2026-09-21):** [stable audit evidence](docs/evidence/l1-a-candidate-offline-audit-20260921/README.md)
and [L1 diagnosis supplement](docs/SAMESCALE_L1_A_CANDIDATE_DIAGNOSIS.md) retain the separate audit.
Public checks **25/25**, type-check/build passed. The unchanged frozen verifier reports **71/75**
checks (business **68/72**), acceptance FAILED; A3 duplicate variant/extension handling fails on both
pages. Independent supplemental acceptance **12/22** reproduces A4 private-use defects including
`en-x-demo`; A7 fails overall due to the shared language defects. The audit proves reproducible
saved-workspace defects, not an original Episode grade or an engineering-completion percentage.
Initial audit directory permission failures are recorded separately from Candidate functional failures.
Original evidence and five saved files remain unchanged; the real attempt remains **NOT_VERIFIED**,
verifier NOT_RUN. Authorization/execution IDs remain consumed. No timeout root cause is established.
A Current's historical 75/75 and this later offline 71/75 are not a completed comparable pair;
comparison remains INCONCLUSIVE and L1 INCOMPLETE.

**L1 stopping point:** diagnosis recorded in evidence commit `d46d02c`; no Candidate repair or
new execution. The separately authorized KB4 commit/push and CI check are described above.
No PR, merge, deployment, or frozen-evidence rewrite is authorized.

<details>
<summary>Historical S1.5 handoff — retained from the prior commit, not current state or authorization</summary>

Updated: 2026-09-09. Milestone: **S1.5 — mainline integration and SameScale canonical identity**.
State: **ACCEPTED — main integration and canonical identity verified; S2 NOT_STARTED**.
S1 implementation, local tests and Browser QA remain accepted at
`0c6c6c9be89f22fe2e8f345a7d6e84720bb609f3`. The verified main integration is
`e3ac8dde59f4d8fd6755541363bf3f1e4010ac69` (PR #1); its exact main CI passed.
The canonical-document handoff is the commit containing this update and its subsequent merge;
verify that final remote SHA/CI separately after publication. No new runtime capability was added.

This is the single live handoff. [Project Blueprint](docs/PROJECT_BLUEPRINT.md) owns the frozen
macro-route and S1.5/S2 acceptance criteria;
[Public Product Contract](PUBLIC_PRODUCT_CONTRACT.md) owns supported behavior and naming boundaries.
[Project Status](docs/PROJECT_STATUS.md) retains historical P0/real-smoke evidence. The previous S0
handoff is preserved in Git at `eceefeccbfb47607cb0463ad410ef429fc2c032c`.

## Baseline and authorization

- Canonical repository/remote: `git@github.com:a27497/samescale.git` (private).
  Renamed in place from `a27497/harnesslab-ai`; repository ID `1342785518` is unchanged.
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
canonical identity** is **ACCEPTED**. S2 is **Local Productization & Developer
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
The canonical repository is now `a27497/samescale`, and the shared origin points there. The additive
CLI belongs to S2, while package/env/API/schema/volume and frozen evidence identities retain
HarnessLab compatibility. The [public product contract](PUBLIC_PRODUCT_CONTRACT.md) and README
record the verified repository identity while preserving current runtime claims.

## S1.5 integration and identity acceptance

| Check | Verified result |
| --- | --- |
| Feature candidate | `3f2578ad9e2c7e747d5806b98822c02af3ce943e`; [Fast CI 34387656649](https://github.com/a27497/samescale/actions/runs/34387656649) SUCCESS |
| Main integration | [PR #1](https://github.com/a27497/samescale/pull/1), merge commit `e3ac8dde59f4d8fd6755541363bf3f1e4010ac69`; accepted S1 remains an ancestor; merge tree equals the tested candidate |
| Main CI | [Fast CI 34388340034](https://github.com/a27497/samescale/actions/runs/34388340034) SUCCESS on the exact merge SHA |
| Repository identity | Same numeric ID `1342785518` / node ID `R_kgDOUAlH7g`; name now `a27497/samescale`; private, default branch main, unarchived, same observed account permissions |
| Canonical access | New Git URL fetch/ls-remote passed; independent temporary shallow clone resolved the exact main merge SHA and was removed afterward; this is Git access verification, not S2 clean-install reproduction |
| Old-address compatibility | Old API URL resolves to the same renamed repository; old SSH Git URL resolves the same main/tag; the historical FIRST_APPLICATION Actions run remains accessible under its original URL |
| History continuity | PR #1 retains ID `4488064589` and merge SHA; main CI retains run ID `34388340034`; tag `v1.0.0-core` retains object `d7e7d92155a1588128ef6a4beb7db286a5b3119b` and commit `e3cab6f180f2bbcd6c8f134aa3d710c503fe6e87` |
| Local compatibility | Shared origin updated to canonical SSH URL; all six other worktrees retain their directories/branch tips; their common remote destination changes, not their files |
| Runtime/evidence | Source, frontend, migrations, package/lock identities, Docker configuration and frozen Real/S1 evidence unchanged from accepted S1; no new CLI, database migration or paid execution |

The prepared runtime acceptance below remains applicable because the merged source is identical.
The current follow-up changes only README, the public identity contract and this live handoff.
Its local documentation/distribution/CI contracts passed: **32 tests in 19.27s**; all **34** local
links/anchors resolve and `git diff --check` passes. Six other worktree records match the captured
pre-rename state exactly; only their shared remote destination changes.
Final follow-up commit/main CI must be checked against their exact SHAs; earlier successes are not
substitutes. The known advanced Core Readiness failure remains explicitly outside the accepted
investigation journey and is tracked for S2 startup/distribution work.

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
- The earlier preparation record's merge/rename **NOT_RUN** status is historical; the table above
  records the subsequently verified integration and identity. S2 implementation and clean-environment
  product acceptance remain **NOT_RUN**. No model campaign or historical database migration occurred.

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

S1.5 main integration and repository rename are verified. Finish the authorized canonical-document
handoff on the feature branch, merge it with history preserved and check its exact main CI; then
stop. Do not start S2. The existing main worktree remains at its owner's local tip; updating that
worktree is not required to change the verified remote main. Temporary QA resources were removed;
historical/demo resources and all other worktrees remain intact.

New live Real execution, full A–K/release acceptance, clean-clone reproduction, physical-device and
non-Chromium testing are **NOT_RUN** in S1. Original real-session restoration and human ownership
remain **NOT_VERIFIED**; historical runtime/security debts remain separate scopes. This product
refactor makes no new causal, model-ranking, reasoning-effort, or automatic-repair claim.

</details>
