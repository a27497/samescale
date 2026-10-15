# MiniShop：DeepSeek Harness → SameScale（方案 C）

本交付只准备任务资格与本地代码快照配置。未运行 DeepSeek Harness、Agent、付费模型或
真实开发实验；没有合并、部署或开启 REAL_CODEX。任务的 oracle 验收不能充当 Agent 成绩。
SameScale 仅使用最终代码快照：`code-only-v1`、`source_kind=unverified`，不填写 Harness
身份，不伪造运行记录、自报、用量或失败原因。后续运行与独立 Workspace 验收需要单独授权。

## 技术栈与公开任务契约

Python 3.12 标准库 WSGI、服务端 HTML/CSS、JSON 商品目录与内存状态。无数据库服务、
Flask、Node、npm install、浏览器依赖或外部资产。`app.create_app()` 返回 WSGI callable；
import 不启动服务，人工启动可使用 `wsgiref`。金额为整数人民币分，应用重启重置状态。

任务 instruction 与受保护的 `contract.md` 必须同时向受测 Harness 提供以下五项要求：

1. `GET /` 展示 pen（Pen，199 分，5 件）、notebook（Notebook & Notes，599 分，3 件）、
   mug（Mug，1299 分，2 件）的名称、价格和库存。
2. `POST /cart/items` 接收 `product_id`、`quantity`，设置数量，0 删除；成功 303 跳转
   `/cart`。`GET /cart` 展示明细及总额。cookie 会话隔离购物车，同实例共享库存。
3. 缺字段、非整数、负数返回 400；未知商品 404；超过库存 409。拒绝后状态保持原样。
4. `POST /orders` 成功返回 201、唯一非空订单号、明细快照和服务端重算的总额，扣库存并
   清空购物车。忽略客户端价格/总额。空车或库存不足 409，失败不能部分扣减。
5. UTF-8 HTML 提供添加、设置/删除、下单表单，转义动态内容，CSS 为本地资源。

公开 contract 还明确用于确定性检查的 HTML `data-product-id`、`data-unit-price`、
`data-stock`、`data-quantity`、`data-subtotal`、`data-total`、`data-order-id` 属性。
这些接口是公开要求，隐藏检查不要求特定内部实现。无登录、支付、管理后台或持久化范围。

## Git 外的任务包与隔离

遵循 [Task Packages](TASK_FORMAT.md) 和 [Local Planning](LOCAL_PLANNING.md)，将以下
包放在操作员批准的独立 `task-snapshots` 根目录，不能进入 Official `tasks/`：

```text
task-snapshots/minishop-standard-library/1.0.0/
  task.yaml
  instruction.md
  custom-eval.yaml
  workspace/
    app.py
    views.py
    catalog.json
    contract.md
    README.md
    static/style.css
    tests/test_smoke.py
  verifier/
    verify.py
    worker.py
  oracle/
    app.py
    views.py
```

manifest 声明 H lane、Python verifier、30 秒上限、deny network，并保护 `contract.md`。
初始 workspace 可导入并响应，占位业务产生正常断言失败；缺依赖/语法错误不能代替 baseline-fail。
Oracle 仅覆盖独立的新 workspace。受测 Harness 只收到 instruction 和初始 workspace；
verifier、oracle、策略、TaskStore、资格和运行收据必须放在其可访问根目录之外。

固定已缓存镜像：

```text
sha256:bfc964b68812bc467a9d722ab811b4a28333a8aed2b99a1e4254fc42f0edac30
```

使用现有 `PinnedVerifierSandbox`，`--pull never`、network none、非 root、只读根文件系统与
`/workspace`、`/verifier`，128 MB/0.5 CPU/64 PID，只有 `/tmp` 可临时写入。
`verification.py` 实际采用 `min(manifest timeout, 30)`。WSGI 隐藏测试在内存调用，不监听端口。
每项使用新应用实例；会话隔离和“跨会话库存”各在同一实例操作两个会话。禁用 bytecode 写入。

23 项隐藏检查覆盖目录值/名称转义/charset、空车、添加/覆盖/删除/多商品总额、会话隔离、
五类输入拒绝、空车下单拒绝、订单明细/价格篡改/库存清空/唯一编号、跨会话库存、表单跳转、
本地 CSS、新实例初始状态。拒绝用例同时核对状态未改变。
Verifier stdout 只输出严格 JSON：非空唯一名称 checks，`passed=all(checks)`，总分为通过比例。
业务失败正常 exit 0；异常、超时、空检查和非法输出均不能作为有效资格结果。

## 已完成的 CUSTOM 技术资格（2026-10-16，Asia/Shanghai）

本次固定任务包，分别真实执行了一次 baseline 与一次 baseline+oracle，无自动重试：

| 项目 | 观察结果 |
| --- | --- |
| task_reference | `minishop-standard-library@1.0.0` |
| task_digest | `sha256:3d59931e2876f84cf37d58c7d8aaeec9293b4113a272555d76ef3429a684d0cc` |
| baseline | 正常 SUBJECT_RESULT；3/23 通过、20 项失败 |
| oracle | 正常 SUBJECT_RESULT；23/23 通过 |
| baseline sandbox 耗时 / 整次调用耗时 | 15.210 秒 / 15.735 秒 |
| oracle sandbox 耗时 / 整次调用耗时 | 16.037 秒 / 16.276 秒 |
| 镜像内 Python | 3.12.11，GCC 12.2.0 |
| TaskStore inspect | `eligible_for_planning=true`，无拒绝原因 |
| 文件规模 | 完整包 14 文件、22,296 字节；初始/覆盖后 workspace 均 7 文件 |

耗时高于阶段 1 的低于 5 秒设计目标，但本次均小于 30 秒；不保证其他主机相同耗时。
任务包、报告、manifest、lifecycle、隔离观察、完整 qualification/validation 与策略均保留
在 Git 外专用目录。实际体积与摘要以该目录的 `step-a-receipt.json` 和逐文件清单为准。
这些记录没有提交到本 PR，隐藏 verifier/oracle 源码没有公开。

资格记录按以下观察生成，而非复制测试夹具中的合成资格：

- `TaskValidationResult` 精确绑定任务、verifier、baseline workspace 与 oracle overlay 后
  workspace；两侧均 exit 0、正常 SUBJECT_RESULT、checks 非空，baseline 有失败，oracle 全过。
- CUSTOM、UNASSIGNED 的 `TaskQualification` 包含 PACKAGE_VALID、BASELINE_FAILS、
  ORACLE_PASSES、WORKSPACE_ISOLATION、HIDDEN_ASSETS_ISOLATED；行为证据绑定真实 manifest，
  隔离证据绑定两个独立 workspace、只读挂载、摘要前后一致和完成的清理 lifecycle。
- qualification/validation 为外部 0600 文件；task-policy 为 0600，源快照与独立 managed store
  分离。通过 `LocalTaskPolicy` 本地目录入口导入，再重新 `inspect_task` 确认准入。

没有 Official tier、来源真实性、重复运行健康、DeepSeek 能力或 Harness 因果结论。
`custom-eval validate --execute-verifier` 使用宿主机子进程，其结果本身不证明上述 Docker 隔离。

## 本地初始化脚本

使用锁定 uv 0.12.5/Python 3.12.14，在自己的 checkout 根目录运行。
仅指定人工审查过的专用最终 workspace；不要指定 home 根、Downloads、开发登录目录、
任务包根或其他人的工作区。不要读取 `samescale-deploy_credentials*.csv`。
以下为命令模板；不能把 oracle workspace 冒充真实 Harness 交付。

```bash
export SS_REVIEWED=/absolute/reviewed/minishop-final
export SS_STATE=/absolute/new/private-minishop-state
export SS_TASK_REFERENCE=minishop-standard-library@1.0.0
export SS_TASK_DIGEST=sha256:3d59931e2876f84cf37d58c7d8aaeec9293b4113a272555d76ef3429a684d0cc
export SS_VERIFIER_IMAGE=sha256:bfc964b68812bc467a9d722ab811b4a28333a8aed2b99a1e4254fc42f0edac30

uv run --locked python scripts/samescale_local_init.py preflight "$SS_REVIEWED" \
  --state-root "$SS_STATE" --task-reference "$SS_TASK_REFERENCE" \
  --task-digest "$SS_TASK_DIGEST" --verifier-image-id "$SS_VERIFIER_IMAGE"

uv run --locked python scripts/samescale_local_init.py init "$SS_REVIEWED" \
  --state-root "$SS_STATE" --task-reference "$SS_TASK_REFERENCE" \
  --task-digest "$SS_TASK_DIGEST" --verifier-image-id "$SS_VERIFIER_IMAGE"

uv run --locked python scripts/samescale_local_init.py print-serve --state-root "$SS_STATE"
```

`preflight` 只读，汇总所有可安全检查的拒绝项及原因，返回 2 表示拒绝，0 表示结构可用。
危险根目录不遍历；`.git`、`.env*`、`node_modules`、`.codex`、`.claude` 等条目不读取或递归，
但继续检查其他允许条目。拒绝链接/硬链接/特殊文件、非法文件名、凭据模式、非 UTF-8/二进制、
空 workspace、超过 500 文件或 4,000,000 字节。自动模式检查不能代替人工隐私审查。
`/mnt` 默认拒绝；若明确使用 `--allow-mnt`，输出并在收据保留权限语义警告。
本脚本需要 Linux/POSIX 的 dir_fd/O_NOFOLLOW；不保证 Windows 原生兼容。

`init` 要求全新、与 source/仓库分离的 state 目录，创建所有目录为 0700、文件为 0600。
调用 `service.content_digest` 复查源目录，复制后再次核对快照及原源摘要；一致才写策略。
失败清理仅限本次新建 state；既有目录和策略拒绝覆盖，没有 force 选项。
输出仅代码策略、排除规则收据 `exclusions.json` 和保留完整目录的 workspace 副本。
成功收据中的 `excluded_paths=[]` 表示没有静默剔除内容；被禁条目导致整次拒绝。
口令只在首次成功的终端 JSON 中显示一次，不写磁盘、不自动保存在 shell/browser。
请当场保存到自己的安全凭据管理器；不要重定向整个 init stdout 到日志或提交输出。

`print-serve` 只打印 Bash 启动命令，口令由交互式隐藏输入提供；不包含口令值、不启动服务。
私有 host API 仍需[Quickstart](EXTERNAL_EVIDENCE_QUICKSTART.md)中的独立已迁移 PostgreSQL、
已有前端构建和 artifact roots。还需自行设置步骤 A 的 `HARNESSLAB_LOCAL_TASK_POLICY`。
不要复用历史/演示数据库，不启动现有部署或修改 Compose。脚本不执行迁移、导入或 Verifier。
导入仍需操作员在页面审阅并同意；真正独立验收应另行授权。

初始化接受的是操作员给定 task reference/digest，不伪造资格，也不执行 TaskStore 准入。
`READY`/`INITIALIZED` 仅表示结构配置成功，不表示任务通过。实际验收继续使用既有 TaskStore
和 `verify-workspace` 门禁；无结果保持 NOT_VERIFIED，code-only 保持 NO_RUN_RECORD/NOT_ATTESTED。

## 本地与 CI 验证

新增测试覆盖正常 code-only 导入、只读 preflight、空目录/容量限制、UTF-8/二进制/凭据、
非法及私有名称拒绝且不遍历、链接/特殊文件、汇总拒绝、写入前后摘要漂移、重复 init、
全层级目录权限、一次性口令和无口令启动输出。所有输入为明确合成测试目录。

旧格式 export 和 Replay 的独立 pin 在添加脚本前从未修改的 main@889f301 冻结：

```text
export: sha256:abbcc4afc6b9f61875b8a6900588f917c23f43a917822027d91c79c929d6f4c0
replay: sha256:a9e055c405d1364437df5a7174674fdbae6d4893e27273d52ec396a7465c5766
```

测试比对完整字节摘要和两次 Replay 字节相等，且旧存储字节保持不变；不重跑历史 Agent/Verifier。
本 PR 仅新增脚本、测试和本文。既有 CI 使用固定 core selectors，不自动纳入新测试模块；
新测试在本地完整 pytest 中执行，远端 core CI 和本地全量结果必须分别报告。
