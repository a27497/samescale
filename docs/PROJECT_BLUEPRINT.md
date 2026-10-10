# SameScale Product Project Blueprint (HarnessLab-compatible)

## 当前授权：Phase 2.5 订阅执行准备 — 2026-10-10

从 `main@3cbefb6731d07c6eddb3463c895eeef60b2f0fd9` 新建独立干净 worktree，连续完成无推理的
开发 CLI / 冻结 Runtime / 协议核验、订阅控制契约、安全隔离的无付费协议替身、独立真实工程
任务准入，以及 Phase-1/2 授权/Worker/证据/取消/崩溃恢复兼容性验收。开发 CLI 的 ChatGPT 登录
仅用于核实方式；不得读取实际 Token、发送模型/额度/账户 RPC、登录/登出、自动刷新、消费
订阅、升级冻结版本、挂载开发登录目录，或将凭据注入 Subject/Verifier/Workspace/日志/API。

真实 `REAL_CODEX` 本阶段无条件拒绝。订阅模式不要求 API Key、API 按量计费或美元硬上限；
Token 和额度信息仅按真实可观测能力报告，不可强制的限制不得写成硬上限。一次明确授权、
一个物理尝试、实际超时/请求/轮次限制、禁止自动重试、取消清理、失败保全与安全门禁沿用
现有队列。冻结 Runner 的 Subject 内认证与 TLS CONNECT passthrough 不满足凭据隔离/请求计数；
采用独立受信任控制器的 **offline double** 验证架构，保持真实 credential loader/transport 不存在。
未来真实接入须另行审查受信任 HTTP 认证边界、订阅 route/额度/全部重试路径；缺失即拒绝。

真实任务采用独立复制的 `core-python-deduplicate@1.0.2`，实际 network-none 隐藏 Verifier 完成
baseline-fail/oracle-pass，证据绑定到 Custom 准入，不更改 Official 资格。协议替身使用既有 clamp
fixture，结果维持 synthetic；不得把它当作真实任务资格或模型表现。保护 UI-2 全部 17 项改动、
所有既有 worktree、服务、数据库、官网及冻结证据。仅创建可销毁验收数据库并对其迁移。
允许提交、正常 push 新分支、Draft PR、exact-SHA CI；不 merge/deploy/迁移既有 DB。
验收/阻塞写 CURRENT_MILESTONE。首次真实推理及必要的产品凭据/账号元数据访问需用户单独
授权；额度购买、自动修复、第二次尝试和 Phase 3 均不属于此授权。交付后 **STOP**。
以下记录保留各自历史范围，不构成额外执行权限。

## 当前授权：产品化 MVP Phase 2 — 2026-10-09

从已验收 `main@304c516e274d094888e3205666419cd3811d0912` 的独立 worktree 开发，完成
不可变单配置计划 → 独立一次性授权/预算确认 → 单 slot 本地持久化队列 → 独立 Worker →
Codex H-Lane 证据 → 独立隔离 Verifier → 不可变结果与私有 UI 读取。复用 Custom Task Store、
TaskPackage、Registry、原 Runner/adapter、DockerSandbox、execution_lease 和 Episode reader；
不用第二个 Cell，不改动旧双配置队列、历史记录、冻结 Demo 或官网。

新 authorization/attempt/result 表追加记录，旧计划与 Episode 不变。API 只授权、入队、取消、查询；
Docker 只属于独立 Worker。单计划授权唯一、幂等键、行锁/SKIP LOCKED、lease owner/TTL 与本地
flock 管理互斥。attempt=1 后不得 requeue；失联后先清理该尝试自有容器，再读取封存、摘要绑定
的结果或保留 INTERRUPTED。禁止因网络重试、Worker/服务重启或租约过期再次发起潜在付费执行。

当前执行策略只允许固定、准入的隔离 `FAKE_CODEX` fixture。实际 Subject 容器产生 JSONL 与最终
Workspace，原 H-Lane Runner 脱敏、记录实际改动，另一个无网络、只读 Workspace 的 Docker
Verifier 独立判断。真实 Codex 没有费用/token 硬限制，REAL_CODEX 授权必须拒绝；参考预算不是
硬上限。Fake 0 模型调用/$0 与 Subject 进程超时是真正边界；Verifier timeout 来自冻结任务契约。
实际 Codex executable/version/protocol、真实任务准入及生产 Worker 运行不属于本次已验证事实。
首次真实评测仍需独立授权、可强制预算/真实 dispatch gate、CLI/镜像/隔离/Provider 验证；
[具体安装与剩余条件](LOCAL_EXECUTION.md)。这不是自动执行的后续计划。

验收只使用新建可销毁 DB/测试服务、Fake subject 和隔离 Verifier；覆盖正负判定、超时、重复提交、
并发领取、拒绝权限/身份/预算漂移、真实 Worker 进程崩溃、保全/重启读取、取消与证据篡改。
保护原 UI-2 的 17 项修改、其他 worktree、冻结证据、历史数据库、官网及现有服务；不部署、升级
Codex、修改生产配置、执行真实 Agent/Provider 或付费模型。允许本分支 commit、正常 push、
面向 main 的 Draft PR 和 exact-SHA CI；禁止合并。Grok 保留 NOT_CONFIRMED。
交付后 **STOP**，不自动执行真实 Codex 或启动 Phase 3。以下旧授权均保留历史范围。

## 当前授权：产品化 MVP Phase 1 — 2026-10-10

从 `main@eb115417772bc36063afd6151c0d6da449ab7883` 的独立干净 worktree，完成可信本地任务接入、
一个 Codex 配置、一个合格 Custom 任务和一次计划尝试，预检、明确确认、不可变保存及私有 UI 读取。
复用 Custom Task Store、TaskPackage、Registry/本地配置和现有 PostgreSQL；双配置实验契约不变。
白色/Cobalt 体系增加 `/plans` 与 `/plans/:planId`，保留调查、离线 Demo 和官网原有范围。

准入由操作员拥有、不可共享写的服务端策略指定源根、独立 store、外置历史 qualification/validation
及精确本地运行镜像摘要。只读取文件/本地 Docker 元数据，不导入任务 Python、不执行 Verifier 或
Provider 健康探测。结构检查与操作员信任的既有行为验收分开；哈希绑定不认证证据来源。
成功预检才写入 15 分钟有效的 receipt；保存前重新绑定任务、Workspace、准入、配置、镜像和程序身份。
确认仅授权保存，UUID 幂等键与 receipt 唯一约束处理重试/并发，PostgreSQL 拒绝两张新表的 UPDATE/DELETE。
已保存原计划始终保留，当前漂移单独展示；未创建 Run/Episode、执行队列或付费授权。

验收覆盖非法路径/文件、预算、来源/身份/配置漂移、权限隔离、并发幂等、数据库不可变与重启恢复；
仅使用新建隔离 PostgreSQL 和合成测试数据。保护原 UI-2 的 17 项修改、其他 worktree、冻结证据、
历史记录、官网及现有服务。允许新分支 commit、正常 push、面向 main 的 Draft PR 及 exact-SHA CI；
不合并、部署、修改现有数据库/服务、升级 Codex 或运行真实 Agent/Provider/Verifier。
Grok 最终复评保留 **NOT_CONFIRMED**。整个 Phase 1 交付后 **STOP**，Phase 2 未获启动授权。

### Phase 2 的具体接口与缺口（规划，不启动）

- 输入 `SavedPlan.plan_id/plan_digest`、单 `custom_plan.run_slots[0]`、完整 `PlanMaterial`；
  由服务端策略解析 managed snapshot 和凭据引用，不从 UI 接收任意命令/路径/secret。
- 增加独立的执行授权/预算确认与 Worker claim/队列契约。Phase 1 的 `confirm_plan_only`、
  receipt 和 `execution_authorized=false` 不得转换成授权；`POST /api/local-plans/plans/{id}/execute`
  当前固定 403。Legacy 双 Cell executor 不能直接消费新单 slot 计划。
- Worker 必须重新核验所有身份和准入、读取镜像精确 ID、验证容器实际 Codex CLI 版本/协议，
  再创建隔离 subject Workspace，排除 verifier/oracle/context hidden assets，并应用 timeout、
  网络 allowlist、资源与退出/取消/清理约束。Phase 1 的 wall-time 支持来自已有 runner；
  token/费用只是参考，硬费用上限与额度预留尚无实现，必须继续如实标注或补齐安全预算机制。
- 复用 native Codex runner/passive Hook 的 Trace 与 final Workspace 收集，但需新增 plan→attempt→
  Run/Episode 关联、独立不可变 execution attempt/receipt、幂等 claim、故障恢复与安全 artifact 读取。
  现有 `CUSTOM/NOT_VERIFIED` Episode 不能被后续验收改写。
- 独立隔离 Verifier 接收绑定的 final Workspace + 外置 hidden assets，保存 L0 结果、checks、
  退出码/摘要与基础设施分类，再连接现有 diagnosis/offline replay。Fresh baseline/oracle qualification
  也须在独立隔离边界完成；Phase 1 只消费操作员信任的历史记录，不解决证据来源认证。
- Phase 2 必须重新获得真实执行/付费授权后才进行一个真实工程任务验收。未覆盖 live Provider、
  真正预算执行、真实 CLI 探测、Worker、Verifier 隔离与完整真实运行闭环，均不得宣称已通过。

以下旧“当前授权”标题为保留的历史记录，不是本阶段的停止点或新授权。

## 当前授权：三轮 UI/P0 Git 安全收口与 PR（2026-10-10）

仅整理 `codex/product-ui-closeout-v1-20261009` 候选工作区已有的两轮 UI 优化、第三轮 P0
修复、对应测试与验收文档；不重新实现原 UI-2，不启动新的设计或产品功能。
核对实际差异、敏感信息、证据绑定、前端测试、类型／隔离构建和离线保护回归。
保护原 UI-2 的 17 项未提交修改、其他 worktree、冻结 evidence、数据库、官网及运行服务。
无关键差异、保护风险或阻塞测试失败后，允许候选分支 commit、正常 push、创建面向 main
的审查 PR，并核对 exact SHA 的 Fast CI / Offline Regression。未完成 CI 如实标记 pending。
Grok 最终独立复评没有确认报告，不宣称最终 PASS；隔离网关修正不作为生产已修复事实。
禁止 reset、强推、清理其他工作区、合并 main、部署、真实 Agent/Provider 或付费调用。
交付 PR、检查结果和剩余限制后 **STOP**。下方三轮验收保留各自原始授权范围。

## 当前授权：Grok 第二轮复评后的 P0 定向收口（2026-10-09）

继承同一分支两轮未提交成果，保留白色 / Cobalt 与信息架构，仅解决已指出的状态层级、
实验统计口径、不可比原始值权重、未知 Run、具体 console / network 错误及预填名称。
先核对当前后端字段；生命周期 / Verifier 执行不得代替任务验收，FILE_CHANGE 状态仅解释
事件。统计采用已有权威计数，未报告不得由通过率猜测。完整原文、ID、SHA、引用与复制 / 下载保留。
附带修复 Trace 遮挡、被动徽标多余焦点及中英重复读屏、动态侧栏位移；不扩展业务能力。

未知 Run 的临时网关规则只在工作区外隔离副本检查 / 修正，安全 HTML 页面可以进入应用，
API 白名单不得扩展，真实 403 不得冒充 404；旧公网、服务、数据库与 UI-2 不变。
真实 Chromium 在 1366 / 1440px 验证调查链路、实验列表 / 概览 / 运行、身份 / 来源 / 返回及异常，
同时调查旧本地与实际 HTTPS 的具体错误。不能按错误数量认定 Bug 数量。
相关测试、类型检查、隔离构建、写拒绝与私有隔离验收通过，提供同视口截图、每项 P0 状态及限制。
不修改冻结证据、Demo、后端 / API / DB，不调用 Agent/Provider、不产生付费资源；
保持未提交，不 push、merge、部署。完成后 **STOP 等待人工确认**。

## 当前授权：第二轮产品 UI/UX 优化（2026-10-09）

直接继承 `codex/product-ui-closeout-v1-20261009` 的未提交第一轮成果，不重新实施第一轮。
治理核心五页、Experiments 与共享组件中的长技术字段：默认显示可读名称、结果与必要的
区分信息，完整原值可展开、复制、引用或下载；同名身份不得混淆。Demo 从自报／验收
对照开始，随后沿证据、诊断、候选对比调查。精简重复入口、说明与底部导航；历史 Real
优先展示基于明确核验字段的中文概览，完整英文原文继续可查。改进已复现的预填、异常、
导航与返回滚动问题，以及长列表／Trace 的阅读与展开。

保留第一轮字号、白色／Cobalt、整体结构与 Real/Fake、Verifier、FILE_CHANGE、不可比语义。
后端／DB／API／冻结证据／真实结果／Demo 身份不变，不调用真实 Agent/Provider；保护原
UI-2 与现有服务。独立预览以 1366/1440px Chromium 验证完整调查链路、身份／复制／下载／
引用／不可比／错误／返回，并和第一轮原始截图比较。相关前端测试、类型检查和隔离构建
通过后，提供验收记录与剩余问题。保持未提交，不 push、merge 或部署；完成后 **STOP**。

## 当前授权：第一轮产品 UI/UX 收口（2026-10-09）

从 `314fe71c` 的独立开发分支，仅收口五个核心工作台页面及 Demo 经过的 Experiments 列表／
详情。保留白色主题、Cobalt、整体结构及 Agent 自报与独立 Verifier 对照。实施前核对源码与
数据契约；统一字号、行高、标签、中文文案与主次操作。修正 Real/Fake 提示隔离、Verifier
进程与任务结论、FILE_CHANGE 与最终工作区差异、不可比方向门禁。原始描述值、来源身份、
机器状态与引用仍可检查；摘要一致性不等于来源认证，未知文本不得推断或改写。

验收为相关前端测试、类型检查、隔离构建，以及真实 Chromium 在 1366/1440px 的五页与
Experiments 检查、同视口前后截图及未修复／未覆盖清单。保护原 UI-2 dirty 工作区和在运行
服务；不写默认服务构建目录，不变更后端／DB／API／冻结证据／Demo 身份，不调用真实
Agent 或 Provider。本轮只完成本地实现与验收，完成后 **STOP 等待人工视觉确认**；不推送、
合并或正式部署。此前发布／Git 收口记录不为本轮授予发布权限。

## 当前授权：Visual v1 Git 收口与 exact-SHA CI（2026-10-08）

用户已正式通过 Visual v1 人工视觉验收。仅核查并整理已验收前端源码、测试和产品／验收
文档，保留历史观察记录并准确记载正式人工通过；复用源文件未变的本地验收，执行必要的
发布前范围／敏感信息／证据／工作区保护检查。合理提交并正常推送当前开发分支，核对
最终本地／远端 SHA 一致，验证其 Fast CI 与 Offline Regression。CI 问题仅在本阶段范围
内做最小修复，范围外阻塞则 STOP。保护原 UI-2、后端契约、冻结 evidence 和 Demo 数据；
禁止 force push、改写历史、创建 PR、合并 main、部署或真实 Agent/Provider。完成后
**STOP 等待合并审查授权**。下方验收及旧阶段授权均为历史范围。

## 当前授权：SameScale Visual Design v1（2026-10-08）

本轮最终审核补充授权仅修 Run 生命周期／Verifier 三态诊断入口与 Public Demo 补充证据
重试的过期数据问题；保留五页布局、主题、语言体系及全部既有候选修改。增加针对性
中英文／三态／正常异常恢复测试，执行前端回归、类型检查和隔离构建；标签受影响的
Run / Demo 补充 1440px 中英文截图。原工作区、后端、API 和证据均只读；完成后 STOP。

仅在 `/home/dev/.worktrees/samescale-visual-v1` 将五张已人工确认的 Stitch 截图与 DESIGN.md
落地为共享 Shell、Home、Run Detail、Diagnosis、Regression、Public Demo。沿用现有 Vue 3
架构和真实 API／权限，完成产品化中文文案与 zh-CN / en-US 界面切换；不重新探索主题。
业务映射和文案交接材料为参考，当前源码、公共产品契约和用户本轮约束决定功能。
保护原 UI-2 dirty 工作区、后端／schema／权限、冻结 evidence 和 Demo 原始数据；
保留全部路由／深链接、真实操作、门禁、安全导出和高级入口，不新增虚构能力。

验收：五页及 Shell 桌面视觉对照、真实保存证据与受控异常的浏览器检查、五页两种语言
在 1366/1440/1920px 的截图、相关前端回归、类型检查、隔离构建和保护性核验。
构建／预览不得写现有服务的默认 frontend/dist；保留既有小屏功能但不新增移动端设计。
不执行真实 Agent/Provider、不部署、不提交／推送／合并。结果写 CURRENT_MILESTONE 和
验收报告；完成后 **STOP 等待人工视觉验收**。以下旧授权均保留历史范围，不启动后续阶段。

## 最终授权：求职冻结版 Git closeout（2026-09-30）

开发停止。仅审计 UAT / Public Demo recovery / Tailnet QA 收口修改，排除临时运维残留，
核对公开仓库安全和 evidence scope，执行必要 gate；提交并 push 当前分支，CI PASS 后
仅合并已验收范围到 main、push 并核对 main CI。成功后记录冻结完成并停止。
不新增功能，不运行付费 Provider，不部署或修改 TLS / firewall / Tailscale。
以下是原历史授权，不能扩大本轮范围。

## 当前授权：UAT closeout（2026-09-30）

仅修 Grok `PASS_WITH_ISSUES` 暴露的 3 MAJOR 和 Comparability 空值、Diagnosis 空态入口、
Connections 文案语言。Offline Demo 在证明固定 Fake、无 DB/artifact/Provider/network 副作用后
精确放行；Public Sessions 保持服务器只读拒绝并对齐页面入口；区分冻结 release 与当前
JudgeLab registry 的 smoke scope，不改历史结果。验收为 backend/frontend full、typecheck/build、
offline/integrity、12 项 Public Demo Gate 和当前 Tailnet 地址 1365/390px 定向浏览器复测。
保持 `public-demo-20260930-9569db12e23a` 身份，完整性失败即停止；不启动 Real 路径、付费
Provider、新功能或公网/Tailscale/TLS 配置工作。不含 commit/push 授权；完成后停止。
以下记录保留原历史授权，不扩大本轮范围。

## 当前授权：Evidence Integrity / Public Demo Recovery（2026-09-30）

只读查找原 QA artifact 并逐字节比对原 digest；找不到则保留旧身份与 integrity failure，
创建独立的新 fixture/offline Public Demo 身份。消除共享测试目录默认值，保护冻结与 Demo
evidence，加入运行时完整性校验和部署前/生产 Demo gate。通过全量测试、离线 replay、
桌面/手机浏览器与本地 gate 后，授权提交上一轮 trust closeout 和本轮恢复修改、push、
部署当前实例；生产 gate 或浏览器失败时停止且不得宣称 ready。不新增付费调用或普通 UI 功能。

## 当前授权：Phase S4 — Recruiter Demo + Job-search Freeze（2026-09-21）

复用 S1–S3 真实历史 evidence、既有 Offline Replay/CI 和单文件离线 HTML 模式，交付
3–5 分钟的 task → configurations → result → Trace Diff → diagnosis → replay → CI 路径。
导出显式筛选的公开字段；提供 README Engineering Highlights、演示脚本、面试材料与简历事实。
验收要求来源完整性、公开投影边界、必要测试与桌面/手机本地 Demo 验收；需要时仅 scoped
commit/push 当前 feature branch 并核验实际 SHA 的 CI。不得新增 Provider/model/Claude/Judge 调用。
保留 dirty work 与历史 evidence；S1 partial/blocked，S2/S3/S4 complete 后进入求职冻结并 STOP。
不规划 S5，不继续新功能，不 merge main、不 deploy。以下为历史阶段上下文，不自动启动。

## 当前授权：Phase S3 — CI Regression Integration（2026-09-21）

将 S2 Offline Replay + Trace Diff 接入普通 GitHub push/pull_request CI，本地与 CI 使用同一
入口和合同。冻结 representative evidence 与已观察到的输出；对 evidence/digest drift、
replay inconsistency、trace/schema/parser、changed-files attribution 和 failure taxonomy
回归 fail closed。回归无网络、无凭据，不执行 Provider/model/Claude/Judge/真实 benchmark。
验收要求本地回归 PASS、实际 pushed SHA 的 GitHub CI PASS、S3 final report 与 CURRENT_MILESTONE。
仅授权当前 feature branch 所需 scoped commit/push；保留 dirty work 与历史 evidence。
不做 S1 能力排名/完整比较，不 PR、merge main、deploy；完成 S3 后停止，不进入 S4。
下方阶段授权和旧产品阶段命名仅为历史上下文，不扩大本次 CI 集成范围。

Planning authority: **HL-BLUEPRINT-2026-09-05**, the user-supplied authoritative blueprint and
first-application delivery contract, amended by the **2026-09-09 SameScale macro-route freeze**
below. The user's latest explicit decisions govern scope.
[Current Milestone](../CURRENT_MILESTONE.md) records live state and the stopping point;
[Project Status](PROJECT_STATUS.md) retains P0 and real-smoke evidence;
this document defines goals and acceptance, not completion or execution authorization.

The [2026-08-25 phase map](FINAL_BLUEPRINT_PHASE_MAP_2026-08-25.md) is historical reference.
Its K-B4 or sequential M-S roadmap does not override this route. Preserve historical phase records
and evidence rather than rewriting them to match a new product description.

## SameScale Product S0 amendment — 2026-09-09

The S0 user request authorized a bounded start of SameScale productization from existing P0.
Reuse the current repository, feature branch, and dirty P0 implementation; do not initialize Git
or rebuild Core. This amendment supersedes only the older deferral of SameScale for S0.

S0 acceptance: inspect Git/worktrees and preserve user work; verify P0 offline/history/current-session
boundaries; establish root AGENTS, CURRENT_MILESTONE, PUBLIC_PRODUCT_CONTRACT, and a discoverable
repo-local `samescale-product` Skill; reconcile entrypoint documentation; retain frozen evidence and
HarnessLab runtime compatibility; run focused keyless checks; then commit and push the current
feature branch as explicitly requested. Verification results belong to CURRENT_MILESTONE.

SameScale is the product direction; the [public contract](../PUBLIC_PRODUCT_CONTRACT.md) freezes
the supported P0 claims and naming boundaries. S0 does not include global rebranding, a new runtime,
new paid campaigns, database restoration, public launch, merge, or implementation of S1 onward.
The first-application and architecture constraints below remain applicable within that scope.

## SameScale Product S1 amendment — 2026-09-09

The S1 request authorized implementation, tests, Browser QA, and commit/push of the existing
feature branch. This superseded S0's branding deferral for the following surfaces.

- Present SameScale in the application shell, browser metadata, CLI/API display descriptions, and
  current README entry. Preserve
  HarnessLab CLI/package/env/API/schema identities and historical evidence bytes.
- Make investigation entry and saved sessions the primary navigation; keep evaluation routes in
  an expandable advanced area that opens on direct evaluation navigation.
- Give new users a clear offline starting point, separate historical Real and current Fake/Real
  entries, explicit loading/error/retry states, and focus moved to the loaded result.
- Refactor the shared report into navigable conclusion, verified evidence, limitations/hypotheses,
  and next steps. Citations reveal exact tool data/digests and return to their originating fact;
  absent references stay unavailable.
- Separate current-session selection, new setup, progress/results, and proposal review. Preserve
  existing backend calls, frozen budgets, Real confirmation, stale-state clearing, and review-only
  approval bindings. No new runtime or database migration.
- Accept with frontend regressions/build, focused Analyst/compatibility contracts, disposable
  PostgreSQL checks, and desktop/mobile Browser QA of the built local app. Label browser fixtures
  separately from real API/database verification.

Results belong in CURRENT_MILESTONE. That authorization stopped after S1; it did not authorize
main integration, repository rename, later stages, new campaigns, deployment, or tags.

## SameScale macro-route freeze — 2026-09-09

This amendment owns the forward product sequence and supersedes conflicting older roadmap/NEXT
text. The current request authorizes **planning, documentation checks, and commit/push of the
existing feature branch only**. S1.5 and S2 execution is not authorized by this plan.
S0/S1 acceptance is recorded in CURRENT_MILESTONE and its linked Git history.

| Stage | Scope | Exit target |
| --- | --- | --- |
| S0 | Codex-native development environment and P0 baseline | Stable development foundation |
| S1 | SameScale external brand and core investigation UX | Recognizable SameScale product and evidence journey |
| S1.5 | Mainline integration and SameScale canonical identity | S1 integrated into `main`; prepare and execute the existing repository's `harnesslab-ai` → `samescale` rename, with verified identity continuity |
| S2 | **Local Productization & Developer Experience** | `samescale` CLI with `demo/up/status/doctor/down`; a simple, verified first-use path to a keyless local demo |
| S3 | Restricted public Demo | `demo.getsamescale.com` safely exposes an explicitly bounded demo experience |
| S4 | Portfolio / Release closure | Website → Demo → cited investigation result forms a coherent, recruiter-ready delivery |
| P1 | Minimal real engineering evidence input / Observe | Investigate one imported development Episode beyond existing experiment evidence |
| P2 | One read-only external connector | Prefer GitHub; use MCP as the connection protocol only if needed |
| Later | SSE / RAG / MCP extensions and other capabilities | Add only for a concrete JD or demonstrated user need |

**Observe is P1, not S2.** S1.5 → S2 → S3 → S4 precedes P1 → P2. This order freezes
scope, not dates or permission to start the next stage. Historical Phase P/S and M–S labels are
separate capability-map identities. Do not reinterpret their evidence as these product stages.

### Source basis and remaining product gaps

The S1 source baseline is commit `0c6c6c9be89f22fe2e8f345a7d6e84720bb609f3`.
These are source observations, not new execution/acceptance results:

| Existing implementation | Implication for the next stages |
| --- | --- |
| [CLI registration](../pyproject.toml) exposes only `harnesslab`; [CLI](../src/harnesslab/cli.py) already wires `up/status/doctor/down/serve` | S2 adds a compatible `samescale` entrypoint and a demo command; it reuses the existing lifecycle rather than building another runtime |
| [Lifecycle](../src/harnesslab/productization/lifecycle.py) selects a trusted Compose manifest, waits for services and endpoints, and preserves volumes on shutdown | Extend existing startup/diagnostic contracts; protect current project/volume identities and arbitrary-working-directory trust boundaries |
| [Compose](../docker-compose.yml) and [product image](../docker/product/Dockerfile) supply PostgreSQL → migrations → FastAPI plus built Vue, with loopback host ports | Full local product startup already has a base; S2 must prove installation and lifecycle from a fresh environment |
| [Showcase](../src/harnesslab/analyst/showcase.py) supplies synthetic offline Fake and digest-checked historical Real; [static serving](../src/harnesslab/api/static.py) discovers a source/container frontend build | DB-free investigation exists, but there is no `demo` launcher; a source build is not proof that an installed wheel contains a usable standalone UI |
| Wheel metadata embeds frontend sources and a trusted Docker build context | Verify the installed artifact outside the checkout; do not mistake bundled source for compiled demo assets |
| [Router](../frontend/src/router/index.ts) sends `/` to `/analyst`; current sessions still require database evidence | Preserve the S1 entry/report journey and explain which paths need the full product |
| [Fresh setup script](../scripts/verify_fresh_setup.py) distinguishes preflight from actual Actions reproduction | A successful preflight cannot satisfy S2's real clean-environment startup acceptance |

### S1.5 — Mainline integration and SameScale canonical identity

Scope is delivery/identity continuity, not new investigation behavior. Canonical product name is
**SameScale**; the target repository is `a27497/samescale`, continuing `a27497/harnesslab-ai`.
Repository slug and current distribution URLs may change in this stage. Python distribution
`harnesslab-ai`, npm package `harnesslab-workbench`, `src/harnesslab`, `harnesslab` CLI,
`HARNESSLAB_*`, API/schema/migration identities, Compose project/volumes, task/profile/session
identities, frozen tags and evidence remain compatible. The additive `samescale` CLI belongs to S2.

| ID | Acceptance criterion | Required evidence |
| --- | --- | --- |
| S1.5-1 | Prepare an integration and rename inventory against current remote `main` and the S1 feature branch: divergence/conflicts, active URLs, badges, CI/release links, clone instructions and local worktree/remotes. Classify current references versus immutable historical identities; define forward changes and rollback steps. | Exact input SHAs, scoped change list and compatibility/rollback record; no global replacement or repository recreation |
| S1.5-2 | Integrate accepted S1 and this route into `main` with Git history preserved. Resolve conflicts without discarding existing main work or changing the accepted S1 boundaries. | Recorded integration commit; accepted S1 SHA remains an ancestor; remote `main` matches the recorded result; required CI on that result passes, separately from local checks |
| S1.5-3 | Execute the existing repository rename to `samescale` within the later authorized S1.5 task. Keep repository visibility and access scope unchanged. Update active canonical references and the authorized local remote; preserve old evidence URLs/text. | Same repository identity before/after; canonical clone/fetch succeeds; old URL behavior is checked and reported, not assumed; main/history/tags and relevant PR/issue/CI links verified after rename |
| S1.5-4 | Reconcile current README/product contract/setup references with the canonical repository identity and explicit HarnessLab compatibility. Other worktrees are inventoried and handed off, not moved/deleted or rewritten as cleanup. | Link/reference audit and exact scoped diff; unchanged package/env/API/schema/volume/evidence identities; rollback instructions preserve history and data |
| S1.5-5 | Verify the integrated tree's S1 entry/report and compatibility before declaring integration accepted. | Focused Analyst/showcase/CLI/distribution/CI contracts; frontend tests/build; desktop/mobile smoke of offline/history and saved Fake review using disposable PostgreSQL where required; frozen bytes checked against the accepted S1 baseline |

Preparation alone may be recorded as **PREPARED**. If merge, rename, access or required CI is
unavailable, retain the concrete blocker and mark the corresponding acceptance **NOT_RUN** or
**NOT_VERIFIED**. S1.5 is accepted only when both main integration and canonical rename are
verified. Do not start S2 automatically. No tag, public launch, package-wide rename, new campaign,
or historical evidence rewrite is part of this stage.

#### Prepared integration and rename procedure

Use the existing `codex/l-real-agent-main-integration` branch as the candidate, retaining all
five accepted commits from the original main baseline through the route freeze. The integration
includes the preceding Real Analyst/P0/S0 work, not just S1 display changes. The dated
[preparation evidence](evidence/SAMESCALE_S15_PREPARATION_20260909.md) records exact inputs and
verification; CURRENT_MILESTONE records whether the external steps have actually occurred.

1. Commit/push the preparation handoff on the feature branch and obtain passing CI on that exact
   head. Re-read remote main and candidate before creating a PR; if either changed, reassess the
   affected delta. Use a normal merge commit into `main`, preserving the accepted S1 ancestor;
   do not squash, rebase published history, force-push, or delete the source branch.
2. Verify the merged remote main SHA and its CI. Leave the other worktrees' local branches/files
   intact; the existing main worktree may remain behind remote main until its owner updates it.
3. Rename the existing private repository to `a27497/samescale` without changing its owner,
   visibility, access policy, default branch or numeric repository identity. Verify canonical
   API/Git access and old-URL behavior; do not recreate or transfer the repository. Preserve tags,
   issue/PR history and original Actions run identities.
4. Reconcile active README/public-contract/current-handoff references and clone instructions with
   the verified canonical URL. Retain `harnesslab-ai` in Python metadata, all historical documents
   and frozen source/evidence. The existing historical CI link in FIRST_APPLICATION remains a
   historical reference; verify its accessibility instead of rewriting its evidence identity.
5. Update `origin` to `git@github.com:a27497/samescale.git` and verify fetch/readback. Git remote
   configuration is shared across these linked worktrees: disclose that effect, but do not rename
   their directories, switch/reset their branches, or clean their files. Reconcile the small
   canonical-document follow-up through the same reviewed feature-branch/merge path and check
   its exact main CI before marking S1.5 accepted.

Rollback is forward and evidence-preserving: on pre-merge failure, keep main unchanged and correct
the candidate; on post-merge regression, use a reviewed revert of the recorded merge commit and
its dependent documentation, never reset published main. Do not downgrade any historical database
as an automatic rollback. If rename validation fails, retain the verified repository ID and restore
the old slug/remote only if available and authorized; otherwise record the actual accessible URL
and blocker. Keep all existing commits, tags and data throughout recovery. No speculative cleanup
or repeated unchanged retry is part of this procedure.

### S2 — Local Productization & Developer Experience

The minimum supported acceptance environment is a fresh Linux environment using the locked
Python/uv versions; the full stack additionally uses local Docker Engine and Compose v2. Document
other platforms as verified only after actual checks. First dependency installation may need
network access. Keyless means no Provider/Judge credentials or calls, not zero installation
prerequisites. No dependency upgrade or new framework is required.

Choose two explicit modes using the existing API, Vue UI and lifecycle:

- **First-use demo:** after one documented installation sequence, `samescale demo` starts a
  loopback API plus compiled frontend and prints a working investigation URL. It runs the existing
  synthetic offline case without Docker, PostgreSQL, keys or persistence. Historical Real remains
  a separate digest-checked read-only record. DB-backed saved investigations explain their
  prerequisite. Ship/resolve the built assets for the installed artifact; do not require users to
  run Vite, build Vue manually, or recover the developer checkout to launch this mode.
- **Full local product:** `samescale up` reuses the trusted Compose graph for PostgreSQL,
  migrations and the bundled API/UI. Host Node/Java/Alembic/frontend build commands are not required
  for this path; locked builds run inside Docker. It does not seed or reconstruct historical
  Real sessions or silently start an investigation.

The following table is a **target command contract**, not a claim that these commands exist today.

| Command | Acceptance behavior |
| --- | --- |
| `samescale --help/--version` | Install an additive entrypoint into the existing CLI; expose `demo/up/status/doctor/down` and preserve legacy commands/options/version identity through `harnesslab` |
| `samescale demo` | Report startup progress and actual readiness, default to loopback, serve `/` → `/analyst` and deep-link refresh; clearly report nonpersistent synthetic data and zero Provider/Judge calls; Ctrl-C shuts down its foreground server |
| `samescale up` | Validate prerequisites/configuration, build or use the selected image, migrate and wait with bounded timeouts; print success and URL only after PostgreSQL, migration, API health and UI readiness pass; repeated startup preserves data |
| `samescale status` | Distinguish demo availability from full-stack stopped/partial/ready/failed state; report checked mode/endpoint and truthful exit status; do not mutate services or invoke models |
| `samescale doctor` | Offer a documented demo-specific check as well as full-product diagnostics; absent Docker/database cannot fail a healthy standalone demo; explain failed prerequisites and the next corrective command without printing secrets |
| `samescale down` | Stop only the selected managed full stack, retain database/artifact volumes, succeed repeatably, and document foreground demo shutdown; never kill an unrelated process on the same port |

Keep `/api/health`'s existing database round-trip semantics; DB-free demo readiness must check its
own UI/showcase path rather than turn a failed database check into a pass. Legacy lifecycle defaults
continue to address the existing `harnesslab` Compose project and volumes; a new executable name
must not make current data appear lost by silently selecting a new project.

| ID | Acceptance criterion | Required evidence |
| --- | --- | --- |
| S2-1 | One current README installation/start path leads to the first demo using the installed artifact from outside the source checkout. No manual frontend build, undocumented absolute path, Codex plugin, `.env` secret or local developer cache is required. | Exact source/artifact identity, prerequisite versions and commands from a disposable clean environment; first-start timing recorded without an invented performance claim |
| S2-2 | Both entrypoints satisfy the command contract; demo and full-stack readiness remain distinct. | Focused CLI/lifecycle tests, installed-wheel entrypoint/assets checks, existing API/static/Analyst contracts; errors and exit codes documented and asserted |
| S2-3 | Actual browser use completes offline demo → conclusion → citation/source → limitations/next steps, with reload and desktop/mobile layout. Historical Real stays distinct; inaccessible DB paths explain setup; no Fake/Real relabeling. | Browser evidence against the built installed product, not mocked success responses; no database or Docker required for the standalone demo check |
| S2-4 | Actual full-stack lifecycle passes first `up`, repeated `up`, `status`, `doctor`, `down`, repeated `down`, and restart. A disposable persisted Fake investigation and its review state survive restart. | Isolated Compose project/ports/volumes; migration head, real endpoint/UI checks and before/after session identity; no historical/demo business database fixtures |
| S2-5 | Missing/unsupported prerequisites, Docker stopped, port collision, invalid config, missing/corrupt UI assets, build/image-pull failure, migration failure and readiness timeout produce bounded failure and a useful recovery step. Correction followed by retry succeeds; stale success or raw credential-bearing stderr is never displayed. | Focused failure tests with injection labeled; actual port-collision/retry and stop/restart smoke; explicit distinction between configuration/not-running exit `2`, operational failure exit `1`, and success exit `0` |
| S2-6 | Default lifecycle/demo cannot use ambient provider credentials, expose private diagnostics, execute an untrusted CWD Compose/`.env`, remove data volumes or start Real/Harness/Judge work. | Existing trust/isolation and keyless contracts plus tests for the added launcher; observed zero model requests, not merely a printed `PROVIDER_CALLS=0` string |
| S2-7 | Documentation and public contract reflect only verified delivered behavior. | Focused distribution/lifecycle/CLI/API checks; frontend tests/build and Browser QA where changed; fresh-environment evidence above; CURRENT_MILESTONE records pass/failure/NOT_RUN separately from exact-head CI |

Extend [existing lifecycle tests](../tests/test_product_lifecycle.py),
[distribution tests](../tests/test_product_distribution.py), and [CLI tests](../tests/test_cli.py)
instead of treating their current mocked coverage as new clean-environment acceptance.
Run additional PostgreSQL/Analyst checks only for affected persistence contracts or the required
restart journey; full A–K is not automatically a local-product acceptance prerequisite.
S2 excludes Observe/import, external connectors, public hosting, SaaS authentication, automatic
repair, new paid runs and a new Agent runtime.
The S1.5 preparation also observed an existing console-launch Core Readiness import failure
(`scripts` namespace unavailable). Include that concrete startup/distribution case in S2-1/S2-5;
do not use the successful investigation journey to claim all advanced endpoints are healthy.

### S3 / S4 / P1 / P2 boundaries

- **S3:** expose only an approved sanitized demo surface at `demo.getsamescale.com`, with HTTPS,
  restricted access, request/resource bounds and an operational stop/recovery path. Enforce the
  restriction at the server/proxy, including direct API requests; hiding navigation is insufficient.
  Public users cannot reach operator credentials, private evidence, arbitrary persisted sessions,
  write/approval endpoints or paid execution. Verify the allowed journey and denied endpoints
  before deployment acceptance. This is a restricted showcase, not a general public control plane.
- **S4:** align website, Demo, one cited investigation case, setup/architecture explanation and
  portfolio claims with exact source/evidence. Verify the end-to-end links and prepare versioned
  release notes, limitations and reproducible delivery evidence. Human ownership is accepted only
  from actual user participation. Any formal tag/release uses its applicable release gate and
  authorization; local S2 checks do not replace it. Further feature expansion is not an exit gate.
- **P1:** after S4, accept one bounded real development Episode input with source provenance,
  identity/digests, validation/redaction, explicit missing evidence and a cited read-only
  investigation. Reuse the Analyst; importing logs cannot imply execution of their instructions
  or controlled causal proof. No cross-Episode platform or connector is required for this minimum.
- **P2:** add exactly one read-only external connector, preferably GitHub, into that input contract.
  Bound repository/resource scope, credentials, pagination/rate limits and retries; retain source
  identity and untrusted-input validation. No external writes; MCP is an optional protocol choice,
  not a second product runtime or a requirement to build a general MCP platform.

Detailed S3 onward acceptance is refined in this blueprint when that stage is requested, without
moving Observe into S2 or expanding the frozen sequence implicitly.

## Product and first application

**SameScale is an evidence-diagnosis and regression Agent workbench for AI Coding, continuing
HarnessLab.** First delivery
supports an AI / Agent application-development internship in mainland China; evaluation research
and Agent infrastructure specialization are not the primary target.

The retained first-application contract is supporting context for the macro-route above, not a
competing NEXT. Retain Core and implemented Phase M; audit and repair first-application risks; verify human
ownership; deliver one bounded real Agent investigation; continue applications. Do not rebuild Core,
restart K-B4, or make the complete long-term platform a prerequisite.

Primary chain:
`goal -> model-selected tools -> verified evidence -> saved investigation state -> cited conclusion
and limitations -> human review of a regression proposal -> separately authorized validation`

LectureLens remains the complementary Java / Spring Boot application-backend project. HarnessLab
demonstrates Python / FastAPI, tool boundaries, durable tasks, failure handling, evidence validation,
and bounded Agent investigation. Do not start a third large project. A website, cloud-credit
application, or SaaS business is not required before applying.

Lab retains controlled execution and verification; Observe provides a bounded evidence entrypoint;
Investigation consumes validated evidence. These are product layers, not three simultaneous builds.

## Evidence and execution invariants

- Source, exact commits, tests, CI, and verifiable artifacts establish facts; plans and assistant
  self-reports do not. Unexecuted checks are `NOT_RUN`; unsupported acceptance is `NOT_VERIFIED`.
  Record actual/expected behavior, evidence, and corrective work when a contract differs.
- Preserve frozen Matrix results, profiles, scores, contracts, source identities, and limitations.
  Corrections use traceable successor notes/artifacts, never replacement of original evidence.
- Accepted V6 evidence does not establish general rankings or overall causality. Direct/Codex
  comparison is limited; medium/high lacks five comparable repetitions per eligible task; accepted
  controlled causal claims are zero. Three BadCases represent two failure features, not three
  proven root causes. Unsupported root-cause fields remain unknown.
- Deterministic L0 outranks human gold L1, which outranks LLM Judge L2. Separate observation,
  correlation, hypothesis, and controlled attribution; keep Official and Custom evidence separate.
- Unknown cost, missing trace, unreported tokens, and uncollected timings stay unknown, not zero.
  Cancellation request, terminal status, process termination, and cost settlement are distinct.
- The host validates and executes tool requests. External text is untrusted evidence. Read-only
  tools cannot provide shell, arbitrary SQL/filesystem, generic code, or experiment execution.
- Retain credential isolation, path bounds, digest verification, hidden-verifier isolation,
  idempotency, leases, transition guards, and resource limits. Docker is not VM-level isolation.
- Use the authorized server; preserve existing work; isolate tests from historical/business data.
  No destructive cleanup or frozen Matrix rerun to obtain green results.
- Upgrading the development assistant does not change frozen subject models or campaign contracts.

## Phase L: technical quality and human ownership

L.0 identifies the actual workspace, branch, HEAD, dirty state, applicable instructions, locked
dependencies, test entrypoints, active processes, and protected evidence. Old paths and NEXT entries
do not require restarting completed work.

L.1 audits source, frontend, migrations, tests, CI, scripts, dependencies, configuration, and
documentation. Mark coverage as in-depth, sampled, or unchecked. Focus on execution/cancellation,
recovery, budgets, evidence, Provider/Analyst boundaries, input trust, API scope, terminal UI states,
migration compatibility, and test validity. Search hits alone are not an audit.

Findings include severity, confidence, location/commit, trigger, impact, counterevidence, minimal
fix, tests, and compatibility/evidence risks. Distinguish defects, delivery gaps, unverified risks,
and style. Historical findings are leads to recheck, not proof of current defects.

L.2 makes bounded repairs: establish behavior, reproduce a failure, fix minimally, and check related
contracts. Remove abstractions only with demonstrated redundancy or no consumers. Do not delete by
line-count targets, weaken assertions, mass-upgrade dependencies, or erase unknown values.

L.3 checks the failure case, affected modules, necessary integration, and applicable final gates.
Use keyless tests and isolated resources. A distinct review pass considers counterexamples;
same-model review is not statistical independence. Keep historical bytes/digests stable where
compatible; document corrected behavior with an explicit contract or correction record.

L.4 is **human ownership**, accepted separately from technical completion. The user must explain
the execution/evidence/Agent chains, participate in at least one test and core repair, explain a
rejected alternative, and adapt a test or locate code under a new boundary condition.

Use three small learning checkpoints: A, predict the behavior contract; B, participate in a failing
assertion and choose an approach; C, explain the change and apply it to a new case. Record concrete
human contributions and AI assistance. Documents, approvals, and memorization do not replace this.
Use one concept and a small code excerpt per step.

Phase L exits when first-application high-risk issues are fixed or explicitly isolated, regressions
are evidenced, one human-participated repair passes explanation and transfer, and remaining debt
is understood. There is no requirement for a perfect repository.

## Real Agent delivery

### Read-only investigation

Reuse LangGraph, the existing Provider boundary, and six tools: `query_runs`, `compare_cells`,
`inspect_trace`, `inspect_failure`, `get_task_contract`, and `get_ablation`. Keep Fake for deterministic
tests; real mode is explicit and never silently falls back to Fake.

The model selects actions using the question and returned evidence. Validate structured arguments,
return values, scope, facts/citations, timeouts, failures, and abstention. Global starting ceilings
are 8 decisions and 12 tools, with lower frozen session limits allowed. Record real-run request,
token, time, and cost bounds before spending. Longer trajectories are not evidence of quality.

### Recovery and minimal review

Persist goal, scope, evidence references, completed actions, remaining limits, and pause position
using existing PostgreSQL and the investigation graph. Recovery cannot reset budgets or silently
repeat completed/ambiguous actions. Do not claim distributed exactly-once processing.

The implementation uses application-managed PostgreSQL session journals around LangGraph nodes,
not a native LangGraph PostgreSQL Checkpointer. Verify the mechanism through recovery behavior;
do not introduce another workflow system solely to change its label.

The minimal side effect is saving a versioned regression proposal or safe snapshot reference after
review. Host code binds approval to user/operator scope, exact content/digest, snapshot, and valid
state. Changed content invalidates approval; repeated confirmation cannot duplicate plans.
An unverified reviewer label is not authenticated identity and must be disclosed as such.

Actual regression execution is a separate scope with visible counts, costs, risks, authorization,
and isolated execution. Saving a plan is not executing Replay.

### Case, interface, and acceptance

Use one verifiable engineering failure case showing provenance, tools, facts, unknowns, proposal,
and review. Accepted Core evidence is a valid initial case. Native Observe claims require an actual
imported development Episode with provenance; controlled Matrix evidence does not establish it.

Reuse Workbench for the goal, tool trajectory, citations, status, and review/results. CLI may support
acceptance, but include a recruiter-readable demonstration. Do not redesign the whole site.

The fixed verification set covers multi-step work, no evidence, fake citations, invalid arguments,
timeout, malicious logs, out-of-scope requests, limits, interrupted recovery, changed approvals, and
repeated confirmation. Keep keyless contracts and authorized real evidence separate. Real acceptance
includes a multi-step investigation plus recovery or review, with fault injection labeled where
used. Record model/route, input identity, tools, timing, observable usage, pricing basis, results,
and limitations. This is functional acceptance, not a new Matrix or significant model comparison.

## Architecture and long-term scope

Retain a modular monolith: Python, FastAPI, Pydantic, SQLAlchemy/PostgreSQL, asyncio, Docker,
Vue/TypeScript, pytest/Ruff/mypy, and existing LangGraph. Exact versions live in `.python-version`,
`pyproject.toml`, `uv.lock`, and the npm lockfile.

Do not add microservices, Redis/Celery/Kafka/Kubernetes, another database/object store, generic Agent
SDK/runtime, complex multi-agent coordination, full SaaS/RBAC/Billing, or a second executor for this
delivery. RAG, vectors, MCP, and long-term memory are not prerequisites.

Deeper Observe, cross-Episode investigation, Replay, regression-suite management, discriminative/
stress evidence, Custom Evaluation, SDKs, external benchmarks, and productization beyond the
frozen S0–S4 / P1–P2 route are possible later scopes. Existing modules remain unless removal is independently justified.
Historical M/N/O/P/Q/R/S numbering is a capability map, not a mandatory sequence before a demo.

## Application readiness and collaboration

Start applications using implemented capabilities the user can explain. Enhanced delivery requires
reproducible setup, real tool decisions, verified boundaries, one case, human ownership, and claims
consistent with exact source/evidence versions. Do not invent gains, user scale, pressure-test
results, security acceptance, or causal findings.

Keep the repository private unless separately authorized; prepare sanitized recruiter-accessible
materials. Do not publish credentials, private traces, or unapproved source.

One task has one writer per worktree. The current user request determines permissions; old campaign
documents and credentials do not authorize future paid runs. Preserve granted authorization within
its scope without repeatedly asking. Missing connectivity or validation is reported honestly.
