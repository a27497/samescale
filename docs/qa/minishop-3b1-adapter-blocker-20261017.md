# MiniShop 3b-1：适配传入阻塞记录（2026-10-17，Asia/Shanghai）

本轮 **BLOCKED / NOT_COMPLETED**。依据用户“若认为必须改 Verifier，停止并报告”
的限制，在静态检查发现适配传入缺口后停止。没有生成或冻结被测声明、新任务版本、
新 task_digest 或 qualification_identity，没有复用 1.0.0 资格冒充本轮资格。
本 Draft PR 只保存阻塞记录；不构成 3b-1 验收通过，也不授权 3b-2。

## 基线、快照和只读完整性

基线为 fetch 后最新 main `38d9f029563b0a157ac5a0a2426f013bb8ea4654`，
即已合并 [PR #28](https://github.com/a27497/samescale/pull/28) 的 merge commit。
工作分支 `codex/minishop-3b1-adapter-20261017`，独立 worktree；原有 UI 脏工作区不动。

用户补充允许按相同 content_digest 使用既有存储副本。实际只读核验对象：

- store：`/home/dev/.local/state/samescale-code-snapshot-20261016/browser-store`
- identity：`2fd1898f67aadfee85fdf40f924cccf68d64759443d125715bacec6e91d7ec68`
- content_digest：`sha256:2665fbe6ae797a8c075cb92894610fded920f0ebcbf63fadb39ef567661eb143`
- 文件数 32，源字节 237,995；现有 `code_snapshots.service.read` 的完整只读校验 **PASS**，包含每个文件 SHA-256、清单、内容摘要和存储身份校验。
- snapshot.json 整体 SHA-256 前后相同：`sha256:846222ebfc7a626bfe979ae580d49677f2a2368da7bdfbc5ef4c3047c38927a0`。

与 Windows 实测时的 identity
`58c9ef0ce39b4f5d245cbc325adde1e5fc33b28cd0c16f413b05d8ccd04182f0`
不同，原因是确认签名不同，content_digest 相同。没有重新导入、确认、还原、修改或删除
这个既有 store/snapshot。该差异不作来源真实性认证。
初次只读检查脚本误把 `included` 列表当成计数，断言中止；按实际 schema 使用列表长度
后完整校验通过。没有源文件内容审阅或被测代码执行。

**实际打开的被测源码/README/说明文件及行范围：空清单。**
只对存储封装做不执行的完整性校验，读取文件路径/摘要清单；未将被测文件解码为文本审阅。
未读取业务实现、tests/、docs/SELF_REPORT.md 或 scripts/ 的语义内容。
完整性校验按既有读取契约对全部存储字节计算摘要，不等于源码审阅。

## 静态阻塞证据

固定快照清单没有根目录 `interface.json`。1.0.0 hidden Verifier 在任何服务启动前
只读取被测 workspace 根下该文件，并据此构造启动和接口观察；它不读取 task manifest
metadata。此行为由私有固定 Verifier 静态确认，未执行被测快照，也未复制其隐藏源码到 Git。

现有公开链路同时表明：

- [verification.py](../../src/harnesslab/external_evidence/verification.py) 第 113–135 行仅复制导入 workspace、核对其 digest/protected 文件，然后传给 sandbox；没有声明注入。
- [sandbox/runner.py](../../src/harnesslab/sandbox/runner.py) 第 388–440 行固定校验并复制 verifier 树，只挂载 workspace 与 verifier，命令仅传入 workspace 路径。
- [task package](../../src/harnesslab/tasks/package.py) 第 262–286 行的 baseline materialize 不会覆盖导入 workspace；不能把 baseline 中的 interface.json 自动视为被测声明。

因此仅在新任务 metadata 中增加声明及摘要无法使它被现有 Verifier 消费。
往还原/导入目录加文件会改变固定快照；在执行复制阶段注入需要改受保护的
verification/sandbox 链路；改 Verifier 去读取新位置会改变 verifier_digest。
上述路径均越过本轮零改动约束，未实施。没有通过改镜像、包装入口或额外命令绕过。
在这些限制下，不能诚实声称新任务已适用于该固定快照。

若直接运行当前链路，静态预期是缺失 interface.json 导致整体基础设施/适配失败；
这不是一次实测，不是业务 FAIL，也没有被测收据。必须先由用户另行决定并授权
适配传入机制的范围；本记录不预先选择实现方案或扩大 3b 授权。

## C17 / C22 等无法观察时的实际处理

1.0.0 Verifier 的单项包装器只将 AssertionError、KeyError、TypeError、IndexError
转换为该项 false。商品存储关联候选不唯一时抛 RuntimeError，越过单项包装器，
由最外层作为基础设施错误退出 2，且不输出最终 JSON 检查报告；即使内部此前已有若干项结果，
也不形成完整业务向量。这一关联可能在 C02/C03 或测试库存准备阶段就失败，早于 C17。

C17 在商品关联后，对其他表执行受控故障注入；若断言不成立，产生单项 false。
SQLite 操作错误等未捕获异常则使整次基础设施失败。C22 仅迁移 SQLite 后重新启动；
订单/库存语义断言不成立产生单项 false，复制/恢复 SQLite 的操作错误、服务启动失败等
则使整次基础设施失败。C22 不要求通过表名关联订单存储。

现有 verification.py 对执行错误保留 NOT_VERIFIED / VERIFIER_INFRASTRUCTURE_FAILURE，
不能把缺失观察算作 VERIFIED_FAIL。若今后单独获准执行并出现接口或环境错误，
A–F 报告 D 节应列 ADAPTER_OR_ENVIRONMENT_FAILURE，并永久保留原收据与尝试；
不能改声明重跑后覆盖原结果。这里仅记录静态行为，**没有本轮 C17/C22 被测观测值**。

## 身份与资格状态

| 项目 | 本轮结果 |
| --- | --- |
| R | 保留 `sha256:31c93f958b80472ada981cc30f210d41d313bc23a7d27acc2ad4fd15f3070bdc` |
| 1.0.0 task_digest 重新计算 | `sha256:95f1b9baa8baee78753f53ec3882598d741f1c0efc8ffbdfc47831c8f0ffdadc`，与旧摘要一致 |
| verifier_digest 重新计算 | `sha256:cf3803e8cbad714e53ed1745d8336c3f5a2a0d3627e9445fa4d9e6805214bf30`，与 1.0.0 一致 |
| image | 既有 `sha256:e8e919870821cd896510b4f29e073b37ac7a5b711f7edeea508606a2defb84a3` 可用，未重建 |
| 被测声明及 SHA-256 | NOT_WRITTEN / NOT_FROZEN |
| 新 task_digest / qualification_identity | NOT_CREATED |
| 新 baseline×3 / oracle×3 / 三缺陷控制 / 兼容对照 | NOT_RUN；没有本轮向量或 ≤25 秒资格声明 |
| 被测 Verifier 物理尝试 / 收据 | NOT_RUN / NOT_CREATED，尝试数 0 |
| 3b-2 / 新收据导出与 Replay | NOT_RUN，等待单独书面确认及阻塞解决 |

[1.0.0 原资格](minishop-fastapi-sqlite-1.0.0.md)保持原有历史范围，未挪用或改写。
私有预检记录位于 `/home/dev/.local/state/samescale-minishop-3b1-20261017/preflight-proof.json`。

## 本轮代码检查与停止记录

uv 0.12.5，既有锁不变。`uv run --locked ruff check .` **PASS**；
`uv run --locked ruff format --check .` **PASS（914 files）**；
`uv run --locked mypy src tests scripts` **PASS（472 source files）**。

全量 pytest 在新建一次性 PostgreSQL 18 数据库上、迁移到 head、清理环境/隔离 HOME、
子进程 umask 022 下启动；发现强制停止条件后发送 SIGINT，未重试。
**退出码 2 / INTERRUPTED**；pytest 页脚 **281 passed，1 warning，60.32 秒**，
整次含启动 63.329357 秒。完整 collected 数未在页脚报告，记 NOT_REPORTED；
已报告 failed/errors/skipped/deselected 均为 0，但剩余测试不算通过。
中断 JUnit 含 282 个 testcase 节点，含中断中的未完成节点，不能用“无 failure 子节点”
计为 282 PASS；私有脚本初算 282 的 summary 与实际页脚差异保留并明确不采信。
原始日志/JUnit/command 均保留在私有 state 根 `regression/`。
冻结 evidence 前后 **439 文件相同**。

收集前 `--ignore` 整文件排除：

```text
tests/test_codex_current_setup.py
tests/test_codex_harness.py
tests/test_multi_harness.py
tests/test_phase_f_claude_startup.py
tests/test_phase_f_deepseek_startup.py
tests/test_runtime_config_hygiene.py
tests/test_verifier_lifecycle_handoff.py
tests/test_cli.py
tests/test_subscription_protocol_docker.py
```

另外审查了其他 backend/subprocess 路径：Fake bindings、被 mock 的 CLI 调用、
本地 Python/Git/OpenSSL 和普通 task sandbox 不启动真实 Agent CLI；未发现需新增整文件
排除的同类测试。本轮未运行 Agent CLI、模型、Provider 或 Judge。未删改或跳过既有断言。

本地 Offline Regression 在停止条件发现后 **NOT_RUN**；本 Draft PR 的远端 Fast CI /
Offline Regression 仅验证文档分支，精确 head 链接及结果在最终交接提供，不建立新任务资格。
仅本报告、CURRENT_MILESTONE 和 blueprint 授权/阻塞状态进入 Git。
受保护 src、tests、scripts、固定任务和 Verifier 字节零改动，未创建被测 policy/record/receipt。
**停止，等待用户对阻塞的书面处置；不合并、不部署、不执行 3b-2。**
