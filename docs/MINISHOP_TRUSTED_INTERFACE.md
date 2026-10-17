# MiniShop：可信接口声明与首次物理验收边界

这是 `minishop-fastapi-sqlite@1.1.2` 的私有任务交付说明。原
[1.0.0 的 26 项业务契约](MINISHOP_FASTAPI_SQLITE.md)及其资格记录保持原样。
本轮是交付后审计准备，不是 DeepSeek 的验收成绩、盲测或模型排名。

## 任务侧适配

旧 Verifier 从被测根目录读 `interface.json`，真实快照没有该文件。新版本仅修改
私有任务自己的 Verifier：按完整 workspace 内容摘要，从只读 `/verifier` 中的受审
registry 取形状声明；不回退到工作区声明，也不向源码注入文件。未知摘要、声明格式错误、
缺失入口、启动异常、无法观察的 SQLite 布局和不完整生命周期均不能产生有效业务结果。
registry 只包含启动、路由、字段和数据库路径，没有金额/库存答案、分数或豁免规则。

真实快照的声明固定 `working_directory=MiniShop`、`run:app`、`MINISHOP_DB_PATH`，
测试数据库位于临时工作副本的 `MiniShop/data/shop.sqlite3`。每次重启重新复制冻结输入，
只迁移 SQLite；不运行交付方自测、PowerShell、开发脚本或 SELF_REPORT。
入口和字段只经静态源码形状审查，没有导入被测模块来推断声明。

新 Verifier 的 `suite`、逐项异常分类 `check`、`at`、`quote` 和 `main` 与旧版本 AST
完全一致。原 26 项业务断言、业务失败与基础设施错误的分类均保留。缺失业务响应字段
仍按既有检查语义处理；不能把任意业务失败都重新称为接口错误。声明/启动/存储观察异常
发生于适配或基础设施阶段时，整次没有可用的业务验收结果。

使用现有 PinnedVerifierSandbox，无核心修改。新私有 Verifier 在启动应用子进程前启用
Linux Landlock（x86_64/aarch64；内核或 Docker 策略不支持则关闭式失败）。子进程只能
读取运行时库、基本系统文件和本次临时目录，不能读取 `/verifier`、原 `/workspace`
或 `/proc`；限制由后代继承。非 root、network none、根及两个 bind mount 只读、
128 MB / 0.5 CPU / 64 PID、30 秒上限均不改变。Landlock 是额外的文件读取边界，
不是任意恶意程序、所有内核攻击或侧信道的完整安全证明。

新镜像保持 Python 3.12.14 固定基础 digest，任务独立运行依赖精确版本及 hash 锁定，
包括交付源码声明的 FastAPI 0.143.2 / Uvicorn standard 0.54.0；不安装或执行其测试依赖。
仓库 `uv.lock`、Sandbox、`external_evidence/verification.py`、REAL_CODEX 门禁完全不改。

## 资格、接入与保管

新资格要求 baseline 三次有效业务 FAIL、oracle 三次 26/26 PASS、各组逐项向量一致；
独立保留价格/提前提交/重扣库存三个单点控制和两个正确兼容样本。一个兼容样本使用与真实
声明完全相同的结构；另一个保留包装字段、低初始库存、并发暂拒等兼容条件，并实际验证
子进程直接及经符号链接读取隐藏文件均被拒绝。每次完整生命周期要求不超过 25 秒。
实际结果、身份和准备失败历史见[验收准备报告](qa/minishop-trusted-interface-20261017.md)。

参考样本实际经过 ZIP CodeSnapshot → CLI 恢复 → 明确来源批准 → code-only-v1 →
已有独立 Verifier。PASS/FAIL、接口拒绝、超时、已消耗尝试、损坏输入分别保留；
重复请求只复用收据。原 ExternalRecord 的 NOT_VERIFIED 不回填；独立结果另存并可离线导出/
Replay。零检查、重复检查、矛盾分数、损坏 JSON、截断、清理失败或缺失 lifecycle 都不能 PASS。
新增公开测试只使用 synthetic 边界，不含隐藏业务检查。

完整任务、隐藏源、接口 registry、独立 oracle、资格 workspaces、原始执行产物和操作脚本
仅留在 Git 外：任务根 `/home/dev/.local/share/samescale/task-snapshots/minishop-fastapi-sqlite/1.1.2`，
审计根 `/home/dev/.local/state/samescale-minishop-trusted-interface-20261017`。
目录 0700、文件 0600（冻结包文件 0400）；Sandbox 的临时可读权限只作用于执行副本。
PR 只包含公开方法、摘要/计数和 synthetic 回归。克隆仓库或 CI 不会获得私有任务或运行它。

## 首次真实执行的授权

真实 32 文件快照只恢复、校验和静态预检，可建立无执行能力的 code-only 记录。
运行前仍需用户明确授权准确 snapshot/content/task/verifier/qualification/image/record 身份，
允许 **一次** 独立物理 Verifier，在隔离 Linux 中启动保存的 MiniShop、执行 26 项检查并保存
独立收据。允许失败结果，基础设施异常维持 NOT_VERIFIED；不自动重试，不修复或改写原源码。
精确身份和可直接批准的授权文字见[报告](qa/minishop-trusted-interface-20261017.md)。

当前保存的数据式 policy 不配置 verifier image/runtime/artifact；完整执行 policy 作为未激活
候选文件保留。用户授权后才能显式选用候选并调用现有 `verify-workspace` CLI。
这不是 Agent/模型调用、合并、部署或修改 PR #29 的授权。
浏览器购物车/结算、视觉/响应式、文档清楚程度、原开发历史、Windows/WSL2 和全空间故障/
并发仍未覆盖；26/26 也不代表原需求所有条款已验证。
