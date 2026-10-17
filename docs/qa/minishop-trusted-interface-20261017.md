# MiniShop 可信接口适配、资格与首次执行准备 — 2026-10-17（Asia/Shanghai）

从 `main@38d9f029563b0a157ac5a0a2426f013bb8ea4654` 创建独立分支 `codex/minishop-trusted-interface-20261017`。PR #29 和原脏工作区保持不动。完整私有实现/原始产物留在批准的 Git 外目录；这里只公开方法、身份、计数与逐项布尔结果。真实 DeepSeek 物理验收仍未授权，结果为 **NOT_VERIFIED / 0 attempts**。

## 固定身份

| 项目 | 值 |
| --- | --- |
| Task / Verifier version | `minishop-fastapi-sqlite@1.1.2 / 1.1.2` |
| Task digest | `sha256:78e8c1945d0df60610923c1989960142f322419ee42f47354b00302ee0639b35` |
| Verifier digest | `sha256:b8ee081681a71fc198dfe00cd84cf29f9441913cf718109f33e74825dbf9edf9` |
| Qualification | `sha256:16c02a254dc7b296776f193cb89032ee67d8cfda5a48e1d4df9bc229cc08cd7e` |
| Image | `sha256:5ad60dee2fb2d11aa75f8ec7cb08bf4fb491a9463dd13261fb589e8d6e64b297` |
| Runtime lock | `sha256:75d9318e6ef390ba9f1fe1009ec7bcd395b8aa1ec02e0faa8790f211f8386585` |
| Requirement R | `sha256:31c93f958b80472ada981cc30f210d41d313bc23a7d27acc2ad4fd15f3070bdc` |
| Interface registry | `sha256:a06e5d7da92b8b73615a13688143e4f409c37e91c02e340c083fbe12992f7092` |
| Subject shape declaration (canonical JSON) | `sha256:72f12eaa8ec62106f8bcc7def0b6685a6b2a40ab82c3b1360c5a5a7e127065ef` |
| Subject snapshot | `2fd1898f67aadfee85fdf40f924cccf68d64759443d125715bacec6e91d7ec68` |
| Subject content | `sha256:2665fbe6ae797a8c075cb92894610fded920f0ebcbf63fadb39ef567661eb143` |
| Serialized original snapshot | `sha256:846222ebfc7a626bfe979ae580d49677f2a2368da7bdfbc5ef4c3047c38927a0` |
| Prepared ExternalRecord | `5fe073a6d1999fabf61945917bd297ac784addf1809f078e75817764df0f7086` |
| Pending execution policy | `sha256:ac1f5e48eb919fd393bf6c0cb1a8d196081df12c859a7b503669b6b139f216e8` |

## 修复与不变项

新任务以完整 workspace 摘要选择可信 Verifier 侧声明，不读取工作区 `interface.json`。声明只描述形状，固定 `MiniShop/`、`run:app`、`MINISHOP_DB_PATH` 与临时 SQLite，源码不注入、不修改。`suite`、逐项异常分类、字段读取、main 等 AST 与旧 1.0.0 相同；C01–C26 判定标准未改。详见[方法及安全边界](../MINISHOP_TRUSTED_INTERFACE.md)。

独立新镜像使用相同 digest 固定 Python 3.12.14 基础，20 个运行依赖精确版本/hash 锁定，匹配交付声明的 FastAPI 0.143.2 / Uvicorn standard 0.54.0；仓库依赖不升级。新增任务侧 Landlock 限制应用及其后代读取隐藏 Verifier，实际兼容样本验证直接路径、符号链接及 `/proc` 访问拒绝。原 PinnedVerifierSandbox 的 network none、非 root、只读挂载、资源和时间门禁保留，核心 verification/Sandbox/REAL_CODEX 无 diff。

TaskStore 再检查 `eligible_for_planning=true`、reason_codes 为空。技术资格为 CUSTOM/UNASSIGNED，不建立 Official、盲测、源真实性或模型能力结论。

## 资格与有限控制

| 运行 | 分类 | 通过/总数 | 完整生命周期秒 |
| --- | --- | ---: | ---: |
| ready-baseline-1 | SUBJECT_RESULT / FAIL | 6/26 | 10.360177 |
| ready-baseline-2 | SUBJECT_RESULT / FAIL | 6/26 | 9.499034 |
| ready-baseline-3 | SUBJECT_RESULT / FAIL | 6/26 | 9.018184 |
| ready-oracle-1 | SUBJECT_RESULT / PASS | 26/26 | 10.842395 |
| ready-oracle-2 | SUBJECT_RESULT / PASS | 26/26 | 10.805768 |
| ready-oracle-3 | SUBJECT_RESULT / PASS | 26/26 | 10.730879 |
| ready-control-price | SUBJECT_RESULT / FAIL | 25/26 | 10.961122 |
| ready-control-partial | SUBJECT_RESULT / FAIL | 25/26 | 10.879324 |
| ready-control-retry | SUBJECT_RESULT / FAIL | 24/26 | 10.925307 |
| ready-compat-metadata | SUBJECT_RESULT / PASS | 26/26 | 14.277387 |
| ready-compat-subject-shape | SUBJECT_RESULT / PASS | 26/26 | 14.018084 |

baseline 与 oracle 各三次的逐项向量分别一致。三个控制均只替换独立 oracle 中一个唯一代码位置：客户端金额命中 C05，提前提交命中 C17，重试扣库存命中 C18/C20。两个正确兼容样本分别验证与真实声明完全相同的字段/目录/启动结构，以及包装元数据、初始库存、并发暂拒和隐藏读取拒绝。全部 11 次最终观察检查非空、无截断、清理成功、输入/输出 workspace 摘要一致，完整生命周期均小于 25 秒。名称和逐项向量保存在[公开 JSON](minishop-trusted-interface-20261017.json)，原始运行和完整资格文档仅在私有审计根。

准备的 15 次物理观察全部保留，不混入最终 11 次资格/控制：1.1.0 三次；1.1.1 十次（静态 reader 曾生成 `.pyc`，因此两个包身份分开记录）；1.1.2 两次基础设施失败。发现并修正了探针引用不存在文件、共享 runtime 的递归权限恢复干扰另一执行、冻结目录权限阻止 staging 清理等准备问题。最终使用独立运行目录、禁用字节码写入、私有目录 0700/冻结文件 0400；包摘要在资格、准入、静态预检及集成前后相同。没有放宽业务断言或把任何基础设施错误计成 FAIL/PASS，也没有删除、覆盖失败运行或自动挑选重复。

## CodeSnapshot 实际接入

| 已批准参考场景 | 结果 | 物理次数 |
| --- | --- | ---: |
| baseline | VERIFIED_FAIL 6/26 | 1 |
| shape | VERIFIED_PASS 26/26 | 1 |
| isolation | VERIFIED_PASS 26/26 | 1 |
| interface | NOT_VERIFIED 0/0 | 1 |
| timeout | NOT_VERIFIED 0/0 | 1 |
| interrupted | NOT_VERIFIED | 0 |
| corrupt | NOT_VERIFIED | 0 |

前三个样本实际经过 ZIP preview/confirm → CodeSnapshot → CLI 恢复 → 来源批准 → code-only-v1 → 已有独立 Verifier，并导出/Replay 独立结果；原记录始终 NOT_VERIFIED，来源为 synthetic。接口未知与受控 1 秒超时为 0 checks/NOT_VERIFIED，旧 30 秒正式上限没有改变；已消耗/损坏输入在新物理启动前拒绝。每个正式接入场景最多一次物理尝试，已有结果重复调用只复用收据。共 5 次 MiniShop 接入 Verifier，另两个场景 0 次；直接任务资格/准备 26 次，合计 31 次本轮 MiniShop Verifier（不含通用回归夹具）。

集成准备曾在无会话 token 的快照签名步骤、以及 `oracle` 受保护路径名处阻断，均在对应物理启动前；修正为本进程临时 token 和批准的中性参考目录后继续。已成功的三个场景直接保留结果，未重跑。原始准备日志保留在私有审计根。

真实快照只做现有读取完整性校验、逐字节恢复、静态 AST/字段/入口检查和数据式来源批准/ingest；没有导入、启动、跑自测或运行 Verifier。32 文件 / 237,995 字节完全一致，原序列化文件摘要 `846222eb…` 不变；原始 R、旧任务 1.0.0 和其已有 Verifier/全部历史收据/Replay 与保存的 2,016 文件清单逐项相同。另有 439 个仓库 frozen 文件由回归前后 inventory 验证不变。

## 本地验证与限制

新增 8 个 synthetic 损坏证据回归覆盖非法 JSON、重复检查、矛盾分数/总判定、stdout/stderr 截断、清理失败和缺失 lifecycle；每种均 NOT_VERIFIED，且不能借重复调用重跑。原有 zero-check、timeout、来源批准、存储/权限、身份和历史 export/Replay 测试保留。私有适配 10 个 unittest 方法及其 schema/path/未知绑定/额外答案字段子用例 PASS。

相关 14 文件共 425 项：首次 415 PASS / 10 FAIL；10 项均为 `no_harnesslab_containers()` 全局断言与本轮独立资格容器重叠，初始日志保留。10 项在所有任务执行完成后串行复查 **10/10 PASS**，合并不重叠的最终覆盖为 **425 项全部 PASS**；详见 JSON verification 字段及 CURRENT_MILESTONE。没有改断言，也没有把首次失败说成通过。离线 network namespace 回归 **245 PASS**、两轮 Replay / 五个 golden 输出不变，模型/Provider/Judge/外部调用 0；Ruff lint/format **914 文件 PASS**、mypy **472 文件 PASS**，129 个文档相对链接全部有效、最终 diff 检查 PASS；原有 47 个测试函数/类 AST 不变，9 个私有标记模式在交付文件中 0 命中。

本轮不重复全库 pytest，不修改前端、不运行前端检查；Windows/WSL2 NOT_RUN。浏览器购物车/结算、视觉响应式、文档清晰度、原开发事实、全部并发调度及所有故障点仍 NOT_COVERED。当前静态兼容通过不证明真实 MiniShop 启动成功或业务通过。CI 不含任何私有任务资产，不重演本次资格；对应最终提交的远程 CI 状态单独在发布交接核对。

## 精确授权门槛（尚未执行）

> 授权仅对上述 snapshot/content 及已准备 ExternalRecord `5fe073a6d1999fabf61945917bd297ac784addf1809f078e75817764df0f7086`，使用表中 `minishop-fastapi-sqlite@1.1.2` 的确切 task/verifier/qualification/image/shape/registry 摘要，进行一次独立 L0 物理 Verifier。在隔离 Linux 中启动保存的 MiniShop，执行原 26 项契约并保存独立收据；不调用 Coding Agent/模型，不改原源码，不自动重试。业务 FAIL 原样保留；基础设施错误、超时或零检查保持 NOT_VERIFIED。

完整候选 policy 位于审计根 `PENDING_AUTHORIZATION-subject-execution-policy.json`，摘要如上；TaskStore policy、只读包、镜像和原记录均已准备。保存的数据式 policy 未配置镜像/runtime/artifact，候选未激活，记录无 `.verifier-started` 或 `verification.json`。原 code-only 记录/源真实性仍 NOT_ATTESTED / NO_RUN_RECORD；首次验收只产生独立工作区结果，不追认原运行。

**STOP：等待这一准确范围的首次真实物理验收授权。** 本轮仅提交/推送新分支与 Draft PR，不合并、不部署、不改 PR #29。
