# SameScale · 求职冻结材料

主线：**真实 coding task → 两个 AI Coding configurations → result → Trace Diff → diagnosis → Offline Replay → CI regression**。
[Recruiter Demo 与讲解稿](RECRUITER_DEMO.md)是第一入口；[S4 final report](evidence/s4-job-search-freeze-20260921/README.md)记录验收与冻结边界。

## 简历可用的工程事实

项目名：**SameScale — AI Coding Evidence Diagnosis & Configuration Decision Workbench**。
技术栈沿用 Python / FastAPI / PostgreSQL / LangGraph / Vue；本 Recruiter Demo 为离线 HTML 投影，
不需要启动完整服务。以下为项目事实，个人描述仅保留自己实际负责、能够解释的部分；项目采用 AI 辅助开发，
不要改写为未经确认的“全部独立手写”或虚构个人贡献比例。

- 实现 AI 编程运行的证据读取与 Trace Diff，关联 native/normalized trace、workspace changes、独立 verifier 和 failure taxonomy，区分模型自报完成、工具退出与任务验收。
- 将两次真实历史 coding attempts 封装为可搬移、摘要绑定的离线 replay；对文件缺失、篡改和跨记录矛盾 fail closed，保留原始失败与 unknown 状态。
- 接入 GitHub Actions 离线回归，本地与 CI 使用统一入口；65 项 S2/S3 回归与实际 pushed SHA 验证通过，检测 evidence、parser/schema、变更归属和失败分类回归。
- 交付无需账号或模型密钥的只读 Recruiter Demo，以公开字段投影呈现任务、结果、诊断、replay 与 CI 证据，不暴露原始命令、私有工作区或凭据引用。
- 冻结 D1 两配置、两任务、五次 trial 的 20 个 slot；在预声明硬停止规则下执行 2 次、其余 18 次标记 `NOT_RUN`，得出范围限定的 `INSUFFICIENT EVIDENCE`，不把缺失试次补猜成成功率。
- 复用自然超时的 `A/candidate/1`：把 5 个保存文件与后续独立离线 verifier 的 71/75 报告连接，定位 A3/A4 保存工作区缺陷；原 Episode `NOT_VERIFIED`，Model/Harness 根因 `NOT_ESTABLISHED`。冻结只读回放并接入 CI 回归。
- D2 本地 Offline CI 同入口为 **126 项 PASS**、同一自然失败只读回放两次且输出摘要一致；最终 GitHub exact-head 状态以 CURRENT_MILESTONE 的记录为准。

数字限定：20/20 是**一次 Codex recorded run 的 verifier checks**；65 是**S2/S3 工程回归 tests**；
2/16 是**正式 benchmark cells 的执行覆盖**。不能将三者相加、当成模型成功率或推广成能力提升。
S1 **PARTIAL REAL BENCHMARK / BLOCKED**；S2/S3/S4 **COMPLETE**。不宣称完成多模型全矩阵、模型排名、
Harness 因果收益、通用 timeout 修复、线上部署、holdout 泛化或个人面试准备度已通过。
D1 **COMPLETE / INSUFFICIENT EVIDENCE** 指决策证据边界已收口；20-run campaign 未执行完，
Consistency / Median Latency / Steps per Verified Success 为 `NOT_VERIFIED`，成本 `NOT_AVAILABLE`。

## 60 秒介绍

“SameScale 利用开发者自己的真实编程证据诊断失败，并判断是否有足够证据更换配置。
在冻结的两项任务、两种配置与 20 个 trial slot 中，仅 2 次运行被执行；一次由独立 verifier 通过，
另一次到时限且未验证，所以配置决策是 INSUFFICIENT EVIDENCE。
另一个历史真实失败留下了 5 个文件：原 Episode 未验证，后续独立离线审计对保存工作区得到 71/75，
定位了字幕语言处理缺陷，但不能证明 Model 或 Harness 是根因。
证据可两次只读回放，并进入无外部网络的 CI 回归。开发使用了 AI 辅助，
我会按实际参与范围解释设计、实现和验证。”

## 面试追问与回答依据

| 问题 | 回答要点与证据 |
| --- | --- |
| 为什么不是“Codex 赢了 Claude”？ | Claude Code 是运行时，此次请求 qwen3.8-max；模型/provider/CLI/template 同时不同。仅两个 attempts，其余 14 NOT_RUN；无完整比较或因果资格。 |
| D1 为何 COMPLETE 却只有 2/20？ | 完成的是 20 个 slot 的状态记账与有边界的配置决策。冻结停止规则阻止 18 次后续 dispatch；结论只能是 INSUFFICIENT EVIDENCE，不能报告一致性或五次中位数。 |
| D2 的 71/75 是原 Episode 成绩吗？ | 不是。原 Episode 在 timeout 时 NOT_VERIFIED，verifier NOT_RUN；后续独立离线审计在同一保存工作区发现 A3/A4 缺陷，71/75 只属于该审计。 |
| 为什么 Claude exit 0 仍未验证？ | task success 由 independent verifier 决定。没有原生完成、timeout=true、verifier NOT_RUN，因此保留 NOT_VERIFIED；不是 verified business fail。见 S2 claude.json。 |
| 怎么判断文件真的改了？ | 比较摘要绑定的 baseline/output workspace，重建 changed paths，再与 manifest/projection 对照。shell 路径提及只作弱观察，不能代替 Read/Edit 或实际 diff。 |
| Trace Diff 如何避免工具数翻倍？ | Codex 通过 item identity 关联 start/result，Claude 按唯一 pending tool 顺序关联，歧义拒绝。13/10 是工具活动数，不是 native event 数或 token 数。 |
| 确认 timeout 根因了吗？ | 没有。保存了读取后无变更/无完成直到时限的事实，failure taxonomy 是 execution_budget_exhausted。无逐事件时间戳，thinking metadata 不是有效推进或根因证明。 |
| replay 能复现模型答案吗？ | 不能。重建已保存的 outcome、trace、workspace diff 和 verifier 状态；不执行 subject、captured command 或 verifier。确定性属于证据读取，不属于模型生成。 |
| SHA-256 就能证明真实性吗？ | 只能在受信任的外部 anchor 下检测变更。攻击者替换原件及所有 anchors 时，摘要本身不能认证来源。保留 Git 版本、原件身份和独立验收来源。 |
| CI 如何避免付费或凭据依赖？ | Linux network namespace 仅有 down loopback、无外部路由；清空环境、临时 HOME。S2 CLI 额外拒绝 socket/子进程；无需模型 key。依赖安装/GitHub 日志传输在隔离边界外。 |
| 为什么导出单文件？ | 使用已有 S2/S3 证据路径和已有离线 HTML 模式；固定分享面，无后台会话、API 或实时模型依赖。完整产品 UI 仍保留，求职讲解不依赖未冻结的 dirty UI。 |
| 遇到过什么实际 CI 问题？ | 首轮离线回归已通过，但 artifact storage quota 导致上传失败。保留失败，改为 SHA-bound Actions log/summary，并回读真实 SHA 的结果；没有删除历史 artifacts。 |
| 哪些是你的贡献？ | 按实际参与说明需求拆解、证据合同、实现、测试和排障；展示 commit diff 与验收记录，明确 AI 辅助部分。工具生成的代码和报告不能单独证明个人掌握程度。 |

证据权威遵循 deterministic L0 > human gold L1 > LLM Judge L2；本案例的 task success 依据独立确定性 verifier，
不是 Judge 自评。本求职冻结没有新增任何 Provider/model/Claude/Judge 调用。

## 技术讲解路径

1. [S2 reader](../src/harnesslab/analyst/offline_replay.py)：输入 trust anchor → inventory → cross-record checks → trace/workspace reconstruction。
2. [S3 entry](../scripts/ci_s3.sh) 与 [runner](../scripts/verify_s3_regression.py)：OS 隔离、重复 replay、golden checks、非零/不跳过关键 tests。
3. [S4 exporter](../scripts/export_recruiter_demo.py)：先核对完整私有输入，再选择公开字段；HTML 文本转义，CSP 禁止脚本/外部资源。
4. [S3 CI acceptance](evidence/s3-ci-regression-20260921/README.md)：本地结果、GitHub SHA-bound receipt、历史失败；[S4 acceptance](evidence/s4-job-search-freeze-20260921/README.md)：分享边界与浏览器验收。

**求职冻结。STOP。** 这里不启动新 benchmark、新功能、后续阶段或部署。
