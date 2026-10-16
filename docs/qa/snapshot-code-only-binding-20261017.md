# CodeSnapshot → code-only-v1 → 原独立 Verifier — 2026-10-17（Asia/Shanghai）

fetch 后 main 仍为 `69e915315c0a53b5d5b3f05f19085bda240d5fab`。
独立分支 `codex/snapshot-code-only-binding-20261017`；保留原脏工作树及所有原始记录。
本轮仅新分支提交/普通推送和 Draft PR；不合并、不部署、不启动 Agent CLI 或真实模型。

## 实现与验收边界

- CLI `harnesslab code-snapshots restore` 重用完整 `read()` 验证，第二次读取绑定同一内容地址，
  拒绝两次读取之间的快照替换。只还原纳入内容，保留排除清单的元数据。
- 目标必须尚不存在，父目录已存在且私有。所有路径组件通过 fd 和 `O_NOFOLLOW`；
  创建文件使用 `O_EXCL`，读回逐字节比对，通过 `renameat2(RENAME_NOREPLACE)` 原子发布。
  不支持该原语时拒绝；无覆盖式 fallback。并发同一目标一方成功、一方拒绝，无 loser 暂存残留。
- 拒绝 store、仓库、已配置 TaskStore 源/managed/准入记录、执行/Verifier runtime/artifact、
  已批准 source workspace/path 的重叠；拒绝既有非空/空目标、链接目标/父路径、不安全父目录。
- 必填任务引用/摘要、source_id、还原确认；source_id 不得覆盖已批准来源。结果始终待人工审核，
  `source_kind=unverified`、`NOT_ATTESTED / NOT_VERIFIED`、`execution_authorized=false`。
  不写 policy，不做自动 ingest，不推断任务适配性，不执行或 import 上传源码，没有新 HTTP 写路由。
- 新测试追加到已列入 Fast CI 核心的 `tests/test_code_snapshots.py`；原函数/类 AST 与断言全部保持，
  原 CI 清单及前29项指纹保持不变。没有为方便登记新文件而放宽原清单断言。
- `external_evidence/*`（包括 Verifier/模型/收据/导出）、原 Replay、沙箱实现、REAL_CODEX 和冻结
  evidence/依赖锁均与 main 零 diff。CLI 入口只新增 import 和 add_typer，原函数 AST 全部相同。

[受保护路径与离线回归收据](snapshot-code-only-binding-20261017/compatibility.json)。

## 本地检查

uv 0.12.5 / Python 3.12.14。只用清洁测试环境与本轮新建的专用 PostgreSQL18 容器
`samescale-snapshot-bind-test-20261017` / `snapshot_bind_test`，迁移至 head。

| 检查 | 观察 |
| --- | --- |
| `uv run --locked ruff check .` | PASS |
| `uv run --locked ruff format --check .` | 911 文件 PASS |
| `uv run --locked mypy src tests scripts` | 472 文件 PASS |
| ZIP + CI focused | 159 PASS；ZIP134（原97 + 新37），原断言不变 |
| 全量 pytest | collected2174 / passed2174 / failed0 / skipped0 / deselected0；1529.68秒，1条原有重复 ZIP 名 warning；首次运行前整文件排除下列8项 |
| `bash scripts/ci_s3.sh .../offline` | 237 PASS；独立断网 namespace、双 Replay 与五项 golden 不变，外部/Provider/模型/Agent/Verifier调用0 |

[本地验证计数与日志哈希](snapshot-code-only-binding-20261017/verification.json)。

新增检查包含：CLI 明确同意/摘要/逐文件 pin/不写 policy/被排除字节不落地；篡改、序列化、
权限、快照 symlink 和读取间替换；目标/父链接、各种保护根、已存在目录、并发原子发布；
写入/发布失败及父路径替换清理；缺少映射/无效 pin/重复 source_id；显式批准后 ingest 得到
新记录且旧记录和导出逐字节不变；原 verify_workspace 的 PASS、FAIL、基础设施失败、零检查
拒绝及同一收据复用。四种 Verifier 合约为明确标注的合成后端，不计作真实物理验收。
还原/导入测试同时封锁进程、HTTP transports、Agent/Provider/模型边界；只在显式 ingest
步骤启用原 project，在合成 Verifier 合约里直接调用原 verify_workspace，旧 ZIP 守卫不变。

## 真实 WSGI 参考样本（非 Agent 产物）

操作员单独允许固定脚本把已资格记录绑定的 oracle 工作区作为不透明字节处理；不查看答案源码，
不读取隐藏测试内容到助手上下文，不复制这些资产到 subject 或 Git。使用已保存的资格工作区
`/home/dev/samescale-minishop-20261016/artifacts/` 两个已冻结 workspace，各7文件。
固定镜像与原 TaskStore admission 可用，因此两侧都实际跑了一次现有隔离 Verifier。

任务 `minishop-standard-library@1.0.0`，task_digest
`sha256:3d59931e2876f84cf37d58c7d8aaeec9293b4113a272555d76ef3429a684d0cc`；资格
`sha256:9112ebdac6d058b375dec513b3ca496612ca154bb4b07a7031d15e3398c0113a`；镜像
`sha256:bfc964b68812bc467a9d722ab811b4a28333a8aed2b99a1e4254fc42f0edac30`。

| 样本 | 独立结果 | checks | 物理尝试 | 第二次调用 |
| --- | --- | --- | --- | --- |
| WSGI oracle 参考实现 | VERIFIED_PASS | 23/23 | 1 | 同一收据，无重跑 |
| WSGI baseline | VERIFIED_FAIL | 3/23 | 1 | 同一收据，无重跑 |

- oracle：snapshot `c54b7fa4350ce99de606514c1595f382beba54a74917d0430233958f358d48ce`；record `1de7ab180c0ff1d955680692b970332b2cf9ddd959c6d12da6bd92142424d6be`；receipt `sha256:6fd4705457db4e20a5a73ad5248f09d0ccbc47938208e44c8653cf84907df383`。
- baseline：snapshot `85a37dff1edb55f824e44b1fc217f0b2fb1f49d172ab968085c05220b6c9283d`；record `9689f3739c14e0284111dfbb6238c829f838eee4db721bd1400a402eb7eb2513`；receipt `sha256:7e5ba8496980c18fd1f8b00c8f621eac462e936d66360370798208e3a5cc2bc6`。

两侧均经：独立 ZIP 快照确认 → 实际还原 CLI → 驱动程序执行**另行人工授权的来源批准**
→ 原 ingest → 原 verify_workspace → 导出/离线 Replay；还原本身没有审批或写入 policy。
还原源码树摘要和逐文件字节与资格记录绑定的 workspace 一致；第二次调用收据文件字节相同。
后一个导入前后，前一记录/收据/导出所有字节保持；原输入摘要前后一致。
[实际收据与元数据](snapshot-code-only-binding-20261017/real-acceptance.json)。
原始私有产物、还原 workspace、policy 和逐个收据留在 Git 外
`/home/dev/.local/state/samescale-snapshot-bind-20261017-v2/`，脚本与测试日志在
`/tmp/samescale-snapshot-bind-20261017/`。没有把参考实现当作模型/Agent 的真实交付。

## 首次 pytest 前的真实 CLI 排除

整文件 `--ignore`，无测试断言删除/放宽；以下文件中的纯单元检查也未运行，不能算通过：

- `tests/test_codex_current_setup.py`
- `tests/test_codex_harness.py`
- `tests/test_multi_harness.py`
- `tests/test_phase_f_claude_startup.py`
- `tests/test_phase_f_deepseek_startup.py`
- `tests/test_runtime_config_hygiene.py`
- `tests/test_verifier_lifecycle_handoff.py`
- `tests/test_cli.py`

[完整排除清单](snapshot-code-only-binding-20261017/pytest-exclusions.json)。
没有运行这些文件中的 Codex/Claude/DeepSeek doctor、启动、沙箱/relay、本地假 Provider handoff。

## 诊断与 NOT_RUN

首次 focused 有5个新串联用例失败：旧 ZIP fixture 明确禁止 project/verify；修正新用例的阶段
入口后通过，原 fixture/断言未改。新增合成报告补齐原有 schema/score，不改变 Verifier。
数据库刚启动未就绪时迁移失败；初次 broad invocation 已主动中止，保留 startup 日志，
不计为全量通过；数据库就绪并完成迁移后才重新运行。真实验收首轮准备把目标取名为私密
路径组件，被正确拒绝，未产生任何物理 Verifier 尝试；准备历史保留，改普通目录名后新一代
两侧各跑一次，没有自动/手动重试任何已经消费的物理尝试。

NOT_RUN：上述8个真实 CLI 文件；新的 Windows/WSL CLI 还原实测；不支持 renameat2 的真实
文件系统（拒绝路径用离线故障注入覆盖）；崩溃/SIGKILL 恢复；真实基础设施失败/零检查样本
（这两项只做合成合约）。FastAPI MiniShop58c9ef0 没有适配可信任务，未绑定、未验收，
保持 NOT_VERIFIED。无 paid/Agent/Judge/model 调用；没有部署、合并或推进其他阶段。

## 发布与停止点

改动文件清单：

- `src/harnesslab/code_snapshots/restore.py`
- `src/harnesslab/code_snapshots/cli.py`
- `src/harnesslab/cli.py`
- `tests/test_code_snapshots.py`
- `docs/CODE_SNAPSHOTS.md`
- `PUBLIC_PRODUCT_CONTRACT.md`
- `CURRENT_MILESTONE.md`
- `docs/PROJECT_BLUEPRINT.md`
- `docs/qa/snapshot-code-only-binding-20261017.md`
- `docs/qa/snapshot-code-only-binding-20261017/compatibility.json`
- `docs/qa/snapshot-code-only-binding-20261017/pytest-exclusions.json`
- `docs/qa/snapshot-code-only-binding-20261017/real-acceptance.json`
- `docs/qa/snapshot-code-only-binding-20261017/verification.json`

只提交/普通推送本分支和 Draft PR。准确 head 与 Fast/Offline CI 链接/结果以发布交付消息
核对，不以旧提交绿色代替本提交；完成后停止等待人工审查。
