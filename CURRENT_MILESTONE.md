# SameScale Product — Current Milestone

## Final Git closeout — 2026-09-30

User supplied the latest independent Grok targeted UAT: **PASS**.
**M1/M2/M3/N1/N2/P1 CLOSED; NEW REGRESSION=NONE**. Product development has stopped.
Public Demo **FIXTURE_OFFLINE / read-only**, identity `public-demo-20260930-9569db12e23a`.
Offline Fake permits side-effect-free computation; persistent Analyst sessions are forbidden in
Public Demo and remain available in local/private workspaces. Frozen release snapshot
`REAL_JUDGE_SMOKE=VERIFIED`; current JudgeLab registry `NOT_RUN`: different evidence scopes.

Backend full **1722 PASS** and offline regression **73 PASS** reused from unchanged source;
frontend full **99 PASS**, typecheck, production build, full Ruff and mypy **PASS** during closeout.
**Public Demo Gate PASS (12/12, Tailnet/loopback); Evidence integrity PASS (451 protected files unchanged)**.
QA database 23 tables / 68 rows and Demo identities/digest unchanged during acceptance.
**Tailnet QA verified** by user-supplied Grok UAT; **public internet / sslip.io / trusted TLS NOT_VERIFIED**.
No paid model execution or deployment/network changes. [Closeout evidence](docs/evidence/uat-closeout-20260930/README.md).

Git publication and branch/main CI are pending the authorized closeout sequence.
SameScale Job Search Freeze completion will be recorded after successful integration.
Older dated entries below retain their historical scope; latest acceptance above supersedes pending QA claims.

## Evidence Integrity / Public Demo Recovery — 2026-09-30

Recovery completed with **ORIGINAL_NOT_FOUND**: 4,432 filesystem manifests, all 4,748
reachable Git blobs, existing archives/worktrees and runner candidates yielded no original
QA digest match. The old 36 QA identities/digests remain unchanged and fail with HTTP 409.
A new read-only fixture/offline bundle `public-demo-20260930-9569db12e23a` contains 12 new
Runs and 108 artifact files, stored outside the repository/test workspace with a complete
hash inventory and a separate byte-preserving backup. The default `/demo` journey uses
these new identities. Legacy seeding is retired; tests require explicit temporary roots,
refuse protected databases, reject frozen-evidence writes/deletes and compare inventories.

Backend **1706/1706 PASS**, Frontend **87/87 PASS**, typecheck/build **PASS**, offline S3
**73 PASS** and two replay passes. The full suite's **406 protected files BEFORE == AFTER**.
Local Demo Gate **12/12 PASS**; desktop/mobile browser acceptance **38/38 PASS**. See
[recovery evidence](docs/evidence/public-demo-recovery-20260930/README.md).

Implementation commit `18664549ff18c07c0b4ab2472abf5d2032f57977` was pushed to
`origin/codex/evidence-integrity-demo`; the remote SHA matches. The current workbench service
was restarted with the new bundle, a mandatory startup integrity gate and execution/configuration
writes disabled. Startup **PASS**, service **active/running**, deployed loopback gate **12/12 PASS**.
The authorized public URL `https://samescale.34.81.153.182.sslip.io/demo` failed with
**Connection refused**. Chromium at 1365px and 390px both failed with
`net::ERR_CONNECTION_REFUSED`. All 12 public HTTP checks and the public journey are
**NOT_VERIFIED**; TLS was not reached. **PUBLIC_DEMO_READY = false**.
See [deployment receipt](docs/evidence/public-demo-recovery-20260930/deployment-public.json),
[public gate](docs/evidence/public-demo-recovery-20260930/production-public.json), and
[browser failure](docs/evidence/public-demo-recovery-20260930/deployment-public.json).
Work stopped at the failed production acceptance as requested; no network/certificate/secret
changes or paid calls. Post-deployment facts are retained in public-safe successor receipts during final Git closeout.
`getsamescale.com/demo/` is a separate static showcase and was not deployed by this task.

## Trusted-evidence product closeout — 2026-09-29

Started from `8ad71d87fc0977fff008c956165d877d2f9c0b83` on `main` with a clean
worktree. The requested regression, provenance, diagnosis, failed-run, readiness,
provider, navigation, and responsive UI corrections are implemented but uncommitted.
The full backend suite passed **1696/1696** on an isolated migrated PostgreSQL test
database; focused diagnosis/API tests passed **43/43**. Frontend tests passed
**83/83**, TypeScript and production build passed, and the offline S3 gate passed
**73 tests** with two replay passes and no external calls. Local Chromium acceptance
covered desktop and mobile workflows, empty/error states, downloads, navigation,
page errors, and overflow; see [closeout evidence](docs/evidence/trust-closeout-20260929/README.md).

**Public-demo blocker:** the pre-existing workbench API test fixture deleted the shared
QA artifact directory during the first focused test. QA's 36 saved manifest digests and
database records remain unchanged, but original artifact bytes could not be recovered
locally. Regenerated scratch artifacts have different digests and were not substituted.
The QA experiment-detail endpoint now fails integrity validation with HTTP 409. The
test fixture has been isolated to temporary artifact/runtime paths. The QA instance
must not be presented as a working public demo until a trusted backup restores the
original artifacts or a separately authorized new QA dataset/instance is created.
Local browser acceptance does not verify user-network access, real Provider execution,
or the existing QA deployment. No commit, push, deployment, or paid call was made.

## Tailscale black-box QA handoff — 2026-09-29

This handoff packages the completed UI usability work and starts a separate keyless QA
instance. It does not advance a product phase or replace the older manual-test services.

- Production frontend build passed after the QA navigation improvement. It is served by
  `harnesslab serve` without reload in tmux session `qa` at `100.68.169.36:8068`. FastAPI serves
  the built SPA and `/api` on the same origin; there is no browser localhost dependency or CORS
  requirement. The socket is bound only to the Tailscale IPv4 address. An INPUT firewall chain
  allows this port on `tailscale0` and loopback and drops it on other interfaces. The QA startup
  environment includes the repository root in `PYTHONPATH` for the existing Core Readiness
  source import.
- The app has `HARNESSLAB_ENVIRONMENT=qa` and an isolated `samescale_qa` PostgreSQL database in
  `samescale-qa-postgres`, published only to host loopback on port 55471. QA configuration is
  private under `/home/dev/.local/state/samescale-qa/`; no production database or Provider key is
  configured. Alembic reached `20260915_0010`.
- `scripts/seed_qa_demo.py` used the existing Fake provider/Fake Codex executor and independent
  task verifier to persist three synthetic examples: `phase-i-matrix-baseline` (9 terminal
  runs), `phase-i-matrix-candidate` (9), and `phase-i-matrix-multi-task` (18, including 9
  `failed_subject` runs). The multi-task diagnosis reports 9 failure runs in 3 cells. The first
  two examples support a directional regression comparison. These are QA samples, not Real
  benchmark or model-ranking evidence.
- Frontend tests **82/82 PASS**, TypeScript and production build **PASS**. Database health returned
  `ok`; Core Readiness returned HTTP 200 with the expected `NOT_READY` status; `/`, `/overview`,
  `/diagnosis`, and `/regression` returned HTTP 200. Eight core routes
  rendered in local headless Chromium; the populated diagnosis and deep-linked regression views
  were checked separately. The regression API returned three comparisons for the default cell
  mapping, including two `PARTIALLY_COMPARABLE` and one `NOT_COMPARABLE` result.
- Tailscale access from a second machine, browser compatibility outside local Chromium, and
  credential-dependent Real execution remain **NOT_VERIFIED**. No push or merge was performed.

## UI usability closeout — 2026-09-26

User-authorized UI audit and P0/P1 fixes only, on `main` base `179f261`; the frontend changes
were uncommitted at audit closeout and are included in the QA handoff commit above. The earlier
manual-access notes below are preserved. No feature phase advances.

- Audited 20 major entries at 1440px desktop and 390px mobile, including real empty/unavailable
  states. No P0 blocker was found in the checked presentation paths. Fixed P1 small metadata/form
  text, excessive Profile expansion and Harness whitespace, wide-table overflow, unbounded
  capability-table height, missing Provider empty/error recovery, and offscreen mobile navigation
  focus. Investigation entry and Advanced hierarchy remain intact; no visual redesign.
- Frontend tests: **82 PASS / 10 files**; TypeScript and production build **PASS**. Final 40 route
  screenshots have no page-level horizontal overflow or page-script errors. Key pages also pass
  at 320/390/768/1280/1920px, with Profile expansion, filtering, keyboard table scrolling and menu
  focus/close/return verified. A collapsed-menu focus issue and populated-detail grid overflow
  found during regression were corrected before the final checks.
- Historical report reading and citation/return passed at desktop/mobile. Provider loading,
  empty and error/recovery were explicitly browser-injected. Populated experiment/Matrix/runs/
  statistics/Trace/Judge/regression views were checked with existing synthetic unit-test fixtures
  intercepted in the browser, not persisted evidence or new results. Current database lists are
  empty and local editing is disabled; real persistence/configuration writes were not exercised.
- View business scripts are unchanged apart from the presentation component import. API clients,
  types/stores, backend contracts, migrations and frozen evidence are unchanged. No model, Judge,
  subject, verifier, replay, commit or push. The built frontend is served by the existing instance.
- Browser checks used local HTTPS Host/SNI routing with the existing self-signed certificate
  verification bypassed; user-network/TLS trust, physical-device/non-Chromium and full screen-reader
  acceptance are not claimed. Screenshot audit and regression details are local task artifacts
  at `/tmp/samescale-usability-20260926/REPORT.md`, outside immutable evidence.
- Remaining P2 only: language/copy consistency, repeated headings, brand/icon details, and minor
  color/radius polish. **UI closeout complete; STOP.**

## Manual test access — 2026-09-26

User-authorized startup and source-IP allowlist maintenance only; no new product phase.
The current SameScale entry is `https://samescale.34.81.153.182.sslip.io/analyst`, using
a dedicated HTTPS virtual host on the existing gateway and forwarding to the
existing `samescale-live.service` at `127.0.0.1:8057`, serving this checkout at
`179f261`. The previous frozen `ef135bb` manual-test instance and its database remain intact.
The workspace user service is enabled with linger. Earlier HTTP forwarding sockets on ports
80 and 8000 remain enabled, but user access to port 8000 failed as described below.
LectureLens retains `https://34.81.153.182/` on port 443. Its original virtual-host block
and application services are unchanged; the shared gateway gained only the SameScale block
and was gracefully reloaded, not restarted.

- The user reported `ERR_EMPTY_RESPONSE` on port 8000. During a coordinated refresh,
  packet capture saw no inbound port-8000 packets and the host INPUT counter did not change.
  This locates the failure before host ingress; the exact upstream cause is not established.
- The new HTTPS virtual host allows only `103.127.218.203` and loopback. Its DNS resolves to
  `34.81.153.182`. It currently reuses the gateway's self-signed IP certificate, so browsers
  can report both an untrusted issuer and hostname mismatch; this is not trusted-TLS acceptance.
  Local Host/SNI routing, SameScale HTML, startup assets, health, Registry models, historical
  and comparison examples returned HTTP 200. User-network access is pending confirmation.
- LectureLens HTML before/after the gateway reload is byte-identical; its gateway container ID,
  start time and restart count are unchanged, and backend/agent/model services remain active.

- Added `103.127.218.203/32` to the persistent HTTP firewall and systemd socket allowlists.
  The dedicated port-8000 socket allows only that IP and loopback. Existing port-80 entries remain;
  the persistent HTTP firewall now covers ports 80 and 8000.
- Verified the new port-8000 entry returns the SameScale page title, database health `ok`, and
  HTTP 200 for Registry models and the comparison example. LectureLens still returns its own
  page, its backend/agent/model services are active, and its gateway container ID, start time,
  and restart count are unchanged across this operation.
- Verified locally through the HTTP forwarding entry with the public Host header: database-backed
  health, 16 SPA entry routes, referenced startup assets, all seven Registry GET endpoints,
  experiment/calibration lists, scoped session listing, Core Readiness response, historical and
  comparison examples, and the offline Fake example returned HTTP 200.
  These checks establish endpoint availability, not full browser or functional acceptance.
- Current experiment/calibration lists are empty; local configuration editing reports disabled.
  No new Provider/model/Judge campaign was launched. Paid execution and credential-dependent
  workflows were not verified.
- HTTPS access from the user's network remains NOT_VERIFIED; port-8000 user access FAILED.
  Cloud firewall inspection was unavailable
  because gcloud has no active account and this VM exposes no service account. Host allowlist and
  forwarding checks passed; no claim is made about cloud firewall configuration.

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
