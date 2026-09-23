# SameScale Product — Current Milestone

## D1 Configuration Decision — BLOCKED / INSUFFICIENT EVIDENCE — 2026-09-23

The user selected historical S1 Official Codex as current, Claude Code as candidate, and real
LectureLens B/A tasks. [Frozen D1 protocol and observed result](docs/evidence/d1-config-decision-20260923/README.md)
bind exactly **2 configs × 2 tasks × 5 trials = 20**, with task/workspace/config/prompt/verifier,
600-second subject and 300-second verifier bounds, tools, declared output budget and taxonomy.
Freeze identity `sha256:db53f913e451a931157aa710817459def3e1cc78b5f6acd946c40741e438a25e`;
commit `6792663ffa18420d16e757317d9e343fe9505b9a` was pushed. Exact-head
[Fast CI 35819575364](https://github.com/a27497/samescale/actions/runs/35819575364) and
[Offline CI 35819575362](https://github.com/a27497/samescale/actions/runs/35819575362) **PASS**.

- **2 attempted / 20 planned**: B × Official Codex trial 1 `verified_pass`, independent verifier
  **20/20**, subject **224.417 s**; B × Claude trial 1 `harness_error / NOT_VERIFIED`, subject
  **601.327 s**, verifier **NOT_RUN**, usage/cost `UNKNOWN / NOT_AVAILABLE`. Frozen stop rule
  prevented further dispatch: **18 NOT_RUN**. Historical S1 runs are not counted.
- Observed failure mechanism: 600-second evaluation-contract timeout. Root cause `UNKNOWN`;
  Model, Harness and Tool failure `NOT_ESTABLISHED`; workspace contract `NOT_VERIFIED`. Original
  cleanup `FAIL` from five empty scratch directories is retained. Separate post-stop cleanup
  removed only those empty directories, 0 files; original receipt/bundle readback passed.
- D1 Acceptance **NOT MET**. Decision within these two tasks/configurations/versions/environment/
  budget: **`INSUFFICIENT EVIDENCE`**. Consistency, five-trial median and comparable steps per
  verified success `NOT_VERIFIED`; observed cost per verified success `NOT_AVAILABLE`.
- **D2 NOT_STARTED; Job Search Freeze NOT_REACHED.** The order in the current request stops at
  this genuine frozen-protocol blocker. No changed timeout, retry, new Bad Case or additional
  Agent run is made to fill missing cells. Existing natural failures remain historical evidence,
  not a completed D2 chain.

## Phase 0 — isolated development baseline — 2026-09-22

### Phase 0 COMPLETE — Offline CI evidence-recording repair — 2026-09-23

- The replay/regression step on `b9e8b60` passed, while the following Actions log step remained
  running until cancellation. It printed the complete pytest/JUnit payload (about 1 MB locally).
  The current repair records a bounded SHA-bound receipt, JUnit pass count and SHA-256 digests for
  pytest/JUnit and both replay logs. Missing, malformed, failed or skipped JUnit evidence fails
  closed; the regression step and its frozen evidence are unchanged.
- Local static checks PASS: full Ruff, format (723 files), strict mypy (384 files); frontend
  type check, 17 specs / 167 tests and build PASS. Unified offline regression PASS: 123 tests,
  two replay passes, five frozen output digests matched, zero external/model/verifier calls.
  Focused workflow/recording contracts: 37 PASS. Mirrored Fast CI backend: 518 PASS on a new,
  migrated disposable PostgreSQL 18 instance. The prior 15-minute timeout remains a bound,
  not evidence of successful remote recording.
- Clean detached candidate at `69e814fb0e5a682a94f098d91a4e920aba3bfbd4` passed locked
  dependency installation, full Ruff/format/mypy, 167 frontend tests/build, 37 focused contracts,
  123 isolated offline regression tests and the bounded record step. The original development
  worktree remains untouched.
- Pushed `69e814fb0e5a682a94f098d91a4e920aba3bfbd4`; remote SHA matches. Exact-head
  [Fast CI 35818146603](https://github.com/a27497/samescale/actions/runs/35818146603)
  **PASS** and [Offline CI 35818146785](https://github.com/a27497/samescale/actions/runs/35818146785)
  **PASS**. The recording step completed in about one second, with JUnit count and file digests in
  the Actions receipt. Phase 0 is complete; D1 pre-run provenance and protocol freeze is next.
  The older STOP records below describe earlier attempts, not the current authorization.

### Offline CI timeout closeout — STOP / INCOMPLETE — 2026-09-22

- One-line CI commit `b9e8b606c94bc0df8470d2e45180d203dacc411e` changes only the Offline
  job timeout from 10 to **15 minutes**; pushed to `codex/phase0-baseline-20260922`.
  Tests, evidence recording, Replay/Verifier/guard and frozen evidence are unchanged.
- Local workflow/CI contracts **36 PASS**, unified isolated offline **122 PASS**, full Ruff /
  format (**722 files**) / strict mypy (**383 files**) PASS. The exact existing recording
  command completed locally in **0.064 seconds**, writing 1,066,807 log bytes and 1,265 summary
  bytes; this does not establish remote recording health.
- Exact-HEAD [Fast CI 35748291808](https://github.com/a27497/samescale/actions/runs/35748291808)
  **PASS**. [Offline CI 35748291694](https://github.com/a27497/samescale/actions/runs/35748291694)
  **CANCELLED**; check-run annotation: `The job has exceeded the maximum execution time of 15m0s`.
- Offline job timestamps (UTC): started **15:34:25**, cancelled **15:54:27**, wall time **20m02s**.
  Setup **1s**, checkout **2s**, uv setup **6s**, locked dependencies **3s**, replay/regression
  **1m24s PASS**. Evidence recording started **15:36:02** and has no completion timestamp or
  successful conclusion; **18m25s elapsed from recording start to job cancellation**, not a
  measured successful step duration. Post steps did not start.
- The increased bound did not resolve the recording stall. No claim of normal/non-stuck recording;
  no higher timeout, CI changes or rerun after this result. **Phase 0 INCOMPLETE; Phase 1 not ready
  and not started.** No main merge, deployment, Agent/model/Claude/Judge/Campaign execution.
- This post-CI milestone record remains local/uncommitted; final pushed HEAD is the CI-only commit
  above. Earlier repair observations below retain their original scope and results.


### Replay CLI / neutral offline boundary repair — STOP / INCOMPLETE

- Shared `ReplayError` and unchanged `offline_guard` now live in
  `harnesslab.evidence.offline_boundary`. S2 replay, Hook replay and Demo export use the same
  guard; `analyst.offline_replay` explicitly re-exports the same `ReplayError` for compatibility.
  Analyst retains no process/network execution surface. Gate J and its assertion are unchanged.
- Original Fast CI's two import failures were reproduced with `PYTHONPATH` unset. Their direct
  script regressions now remove `PYTHONPATH` explicitly and execute from the repository root.
  A separately exported candidate with a fresh locked venv also passed both CLI scenarios.
- Local acceptance: Hook/Verifier/Episode **68 PASS**, unchanged Gate J scope and guard rejection
  checks **2 PASS**; unified offline **122 PASS**; bounded Fast CI backend **518 PASS**;
  full Ruff / format (**722 files**) / strict mypy (**383 files**) PASS; frontend **17 specs /
  167 PASS / 0 FAIL / 0 unhandled**, build/vue-tsc PASS. No skipped or weakened checks.
- Both S2 replays match all five frozen output digests. Guard and exception AST match their
  originals. Frozen evidence, historical result summaries, failure attribution and replay output
  semantics are unchanged; CI PYTHONPATH and scope checks are unchanged.
- Prior stopped attempt: putting the guard in Analyst caused the scope check to flag its denial
  string; backend stopped at **134 PASS / 1 FAIL** without commit/push. The explicitly authorized
  neutral-module relocation resolves that blocker; no unrelated failure occurred this round.
- Repair commit `b05b507af0d91c5ff5e88d2e261cc5a34ecc031e` was pushed to
  `codex/phase0-baseline-20260922`; remote branch SHA matches. Exact-HEAD
  [Fast CI 35745223513](https://github.com/a27497/samescale/actions/runs/35745223513) **PASS**
  (518 backend / 167 frontend tests; static/build checks PASS).
- Exact-HEAD [Offline CI 35745223557](https://github.com/a27497/samescale/actions/runs/35745223557)
  finished **CANCELLED**. The replay/regression step succeeded, but the Actions log/summary step
  did not finish. Check-run annotation: `The job has exceeded the maximum execution time of 10m0s`.
  Full job log was unavailable (`log not found`). No new regression failure was reported; the
  workflow itself did not PASS. STOP: no CI changes or rerun under this import/boundary scope.
- **Phase 0 INCOMPLETE; Phase 1 not ready and not started.** This post-CI status is a local
  milestone update, not another commit; the final pushed and verified HEAD remains the repair SHA.
  No Agent/model/Claude/Judge/Campaign, main merge or deployment.

Base `ef135bbdd49639afc28e2701d811329f3418281d` (fetched origin/main); candidate branch `codex/phase0-baseline-20260922`. [Acceptance and scope](docs/evidence/phase0-candidate-20260922/README.md) / [local receipt](docs/evidence/phase0-candidate-20260922/local-acceptance.json).

- Explicit allowlist: final Product QA / Planning and Harness eligibility; required verified frontend, read-only API and Demo dependencies; passive Hook → independent verifier → VERIFIED_FAIL → frozen CUSTOM case → deterministic Offline Replay. Historical S1/L1 untracked campaigns/tests/fixtures, installer/wheel packaging and duplicate evidence are excluded.
- **Local PASS:** frontend **17 spec / 167 tests / 0 failures / 0 unhandled errors**; Hook/Verifier/Episode **68** plus boundary **13** = **81 PASS**; unified offline **122 PASS**; mirrored bounded CI backend **518 PASS**. Ruff, format (721 files), strict mypy (382 files), build/vue-tsc PASS. No tests skipped or weakened.
- Five candidate typing errors fixed without behavior changes. Ruff excludes only immutable `docs/evidence/**`; other maintained Python stays checked. Three fixture digests, Hook bundle/case, copied evidence and old S2/S3/S4 bytes unchanged; S2's five output digests match in both replay runs.
- Original dirty worktree stays untouched (4,009 files and Git state checked). Candidate missing Demo dependencies were added individually after import/CLI audit; initial failures remain recorded. No unrelated source repair or history rewriting.
- GitHub acceptance requires **both automatic workflows on the final candidate HEAD**, not historical CI: [candidate Actions](https://github.com/a27497/samescale/actions?query=branch%3Acodex%2Fphase0-baseline-20260922). Local source-digest readback binds the accepted code to the final commit; no extra evidence-only commit is needed to claim its own SHA.
- This is a development baseline, not a new campaign or capability comparison. The seeded verification-only session establishes workspace contract failure, not a Codex capability/instruction-compliance failure. No Agent/model/Claude/Judge, Campaign, merge main or deployment; **Phase 1 is not started**.

## 求职冻结 — Phase S4 COMPLETE / STOP — 2026-09-21

**S1：PARTIAL REAL BENCHMARK / BLOCKED；S2 / S3 / S4：COMPLETE。**
[Recruiter Demo](docs/recruiter/demo/index.html) · [3–5 分钟演示稿](docs/RECRUITER_DEMO.md) ·
[面试材料与简历事实](docs/JOB_SEARCH_FREEZE.md) ·
[S4 final report](docs/evidence/s4-job-search-freeze-20260921/README.md) ·
[冻结清单](docs/evidence/s4-job-search-freeze-20260921/freeze-manifest.json)。

- 复用 S2/S3 reader、bundle/输出摘要与 CI receipt，单文件 HTML 展示 task → configurations → result → Trace Diff → diagnosis → Offline Replay → CI。
- 分享包仅 `docs/recruiter/demo/`；无原始命令、内部 endpoint、凭据引用、源码或私密推理。
  桌面 1360px / 手机 390px 视口本地浏览器验收 PASS，HTTP 请求与 page errors 均 0。
- 独立 staged tree 的统一离线 gate **73 tests PASS**（65 S2/S3 + 8 S4）；Ruff/format/mypy PASS。
  实现 SHA `5bdc03f8addce7532fdfc053c383cb66895e3b3b` 的
  [Offline CI](https://github.com/a27497/samescale/actions/runs/35645815474) 与
  [Fast CI](https://github.com/a27497/samescale/actions/runs/35645815456) 均 PASS；GitHub receipt 与本地一致。
- 新 Provider/model/Claude/Judge 调用 **0**；没有新 subject、命令或 verifier 执行。
  历史 evidence、原始失败及无关 dirty work 保留；仅追加 S4 文档区块和既有 CI 的 S4 tests。
- S1 仍仅 2/16 cells：Codex recorded 20/20 verified_pass，Claude timeout/NOT_VERIFIED、verifier NOT_RUN，14 NOT_RUN；无能力排名、完整 benchmark 或 Harness 因果结论。
- 3–5 分钟是讲解预算，未做招聘者理解度实测；简历材料是项目事实，不证明未经确认的个人贡献或面试准备度。

**求职版已冻结，STOP。不规划 S5，不继续开发新功能；无 PR、merge main 或 deploy。**
以下阶段与 L1 状态仅保留为历史上下文，不自动授权后续工作。

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
