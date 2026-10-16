# 网页 ZIP 源码快照（code-snapshot-v1）

**请上传仅含源码的 ZIP；依赖目录中的文件可能触发凭据规则导致整包拒绝。**
打包前移除 `.venv / venv / node_modules`、缓存与构建产物；不要上传整个开发环境。

在 `/external-runs` 输入本地操作员凭据，选择声明的工具和 ZIP，点击安全预检。
预检展示原始归档摘要、纳入文件、逐文件摘要、排除原因和目录条目。用户审阅后勾选
“仅保存这个源码子集”，才能确认保存。详情链接为 `/code-snapshots/<identity>`。

来源工具只是声明。详情固定为 `NOT_ATTESTED / NO_RUN_RECORD / NOT_VERIFIED`。
快照没有任务、运行记录或验收收据；后续需要另行审查和绑定可信任务及独立验收条件。
本轮没有绑定或执行入口，不能将快照身份交给 ExternalRecord 的验收命令来获得通过。

## 独立对象和存储

快照使用现有操作员/证据策略，不要求批准来源或 TaskStore 任务。操作员可配置独立
0700 store 和 0600 策略，策略结构为 `{"store":"/ABSOLUTE/PRIVATE/STORE","sources":[]}`，
设置 `HARNESSLAB_EXTERNAL_EVIDENCE_POLICY` 和至少 32 字符的
`HARNESSLAB_LOCAL_CONFIGURATION_TOKEN`，使用私有 loopback host API。
已有安全策略也可以沿用；其既有 source、记录和身份无需改写。

源码快照存放在 store 的独立 `.code-snapshots-v1/<identity>/snapshot.json` 子目录。
内容以 Base64 包含在这个只写一次的 0400 文件内，条目名不会成为任何解压或写入路径。
身份绑定全部内容、声明、归档/清单摘要及确认记录。详情读取会复核身份、逐文件摘要、
源码树摘要、限制和确认绑定，连仅改变 JSON 空白的字节篡改也拒绝读取。

现有记录列表忽略点号命名空间，`read_record` 和 Verifier 仍查找原有根下的身份目录；
不会发现快照。ExternalRecord、ApprovedSource、code-only-v1、记录身份、Replay、导出、
verification.py 和 REAL_CODEX 门禁均保持原样。无数据库迁移，没有 Agent、Verifier、
Provider 或模型调用，也不执行或 import 上传内容。

## 请求和确认

只有 `POST /api/code-snapshots/archive` 显式接受 `application/zip`，不使用 multipart。
默认 `local_operator(Request)` 保持封闭的 JSON 守卫；共享检查函数只能由新路由在
服务端显式传入 ZIP 类型，无法通过查询参数改写既有路由的类型要求。
Host、Origin、sec-fetch-site、Bearer 和公开 Demo 限制全部保留。

- `?action=preview&declared_tool=unknown`：返回 `REVIEW_REQUIRED` 或 `REJECTED`。
- 声明可选 `unknown / deepseek-harness-desktop / codex / claude-code / other`。
- 预检不写磁盘。服务器返回完整清单、`manifest_sha256` 和操作员密钥的 HMAC 签名。
- `?action=confirm`：浏览器重新发送同一 File 的 ZIP 字节，携带
  `X-Snapshot-Consent: SAVE_REVIEWED_SOURCE_SUBSET`、`X-Snapshot-Archive-Sha256`、
  `X-Snapshot-Manifest-Sha256` 和 `X-Snapshot-Review`。服务端重算全部清单并核对签名。
- 接口拒绝未知或重复查询参数；不接受服务器文件系统路径。
- `GET /api/code-snapshots/<identity>`：只读完整性检查后的详情，不返回源码内容。

确认记录保存归档摘要、清单摘要、签名和明确的子集同意。HMAC 证明确认对应服务器审阅
结果，不是工具来源认证。重复同一确认是幂等的；声明或操作员密钥变化产生不同的确认。
归档原始字节不持久保存；仅保存原始 ZIP 的 SHA256 和审阅后的源码子集。

## 三种限额

| 范围 | 上限 |
| --- | --- |
| 压缩包上传 | 8,000,000 字节；检查 Content-Length 和实际流；上传超时 30 秒 |
| 扫描 | 10,000 条目（含目录及将被排除的文件）、32,000,000 解压字节 |
| 单条目和压缩比 | 8,000,000 解压字节、单条目与全包均 ≤ 200 倍 |
| 最终源码快照 | 500 个纳入文件、4,000,000 纳入字节 |
| 持久容器 | 含 Base64 内容和全部清单的 JSON ≤ 8,000,000 字节；超限在任何写入前拒绝 |

超限整包拒绝，不能自动丢弃文件来凑限额。缺少 Content-Length 的流也受实际上传上限
约束；声明与实收不符、断开、超时或损坏归档均拒绝。扫描支持 STORED/DEFLATED，验证
本地头、完整压缩流、实际大小、CRC 和数据描述符，不只信任 ZIP 声明的大小。

## 排除与硬拒绝

所有文件先检查路径、属性和凭据，再进行排除分类。即使位于依赖/缓存目录，也不能
跳过凭据检查。沿用原 `SECRET`、`PRIVATE_PARTS`、`safe_name` 和 `safe_content`，不放宽规则。

可以排除并逐项留存路径、字节数、摘要及原因：`.venv / venv / node_modules` 依赖目录；
`__pycache__ / .pytest_cache / .mypy_cache / .ruff_cache / .cache / cache` 缓存；
`dist / build` 构建产物；`artifacts` 生成产物；非 UTF-8、含非文本控制字节或已知二进制格式。
排除原因代码为 `DEPENDENCY_DIRECTORY / CACHE_DIRECTORY / BUILD_OUTPUT /
GENERATED_ARTIFACT / BINARY_OR_NON_UTF8`。目录条目单列，不伪装为源码文件。

整包硬拒绝：路径穿越、绝对/盘符/反斜杠路径、不安全或私密文件名（含 `.env*`、`.git`）、
symlink/特殊属性、加密条目、重复/大小写/NFC/文件目录前缀冲突、凭据命中、嵌套 ZIP/JAR/WHL、
不支持的压缩方法、损坏归档和任何资源超限。失败只返回固定原因，不返回匹配到的凭据值。

整包拒绝按安全检查阶段汇总，最多返回 50 条（`rejection_limit`）；超出时
`rejections_truncated=true`。每个条目报告该阶段遇到的失败；内容阶段可同时报告凭据和
嵌套归档。路径/元数据阶段有拒绝时不读取内容；损坏或解压异常时停止继续读取，保留
此前原因。因此列表不保证穷尽未读取内容的问题，修正后应重新预检。拒绝时不签署清单、
不返回内容或部分源码快照，确认同样重新扫描并在任何写入前拒绝。

## 暂存与测试

上传/预检只使用受限内存，不创建待确认目录。确认在 flock 下以临时目录和 `os.rename`
原子发布，已有快照不重写。沿用既有记录 writer 的全局锁并在写入前保留共享
store 的 20,000 文件 / 128,000,000 字节总包络，容量不足拒绝保存，保护旧记录读取。临时目录是 store 的随机兄弟目录；在写入前检查与仓库、
记录/快照 store、全部批准来源 workspace、配置的 TaskStore/来源、执行及 Verifier 根、
显式 Custom TaskStore 分离。正常结束、拒绝和异常时由 TemporaryDirectory 清理。

新增 adversarial fixtures 只用于拒绝/排除契约，不代表真实 MiniShop 通过。它们与
`tests/test_local_init_script.py` 一起注册到 Fast CI 核心清单、固定分片和 self-hosted 清单；
保留原 29 selectors 的独立 fingerprint，并在 inventory 契约里追加精确登记。
新增 ZIP 测试还进入 Offline Regression。实测记录见
[2026-10-16 验证报告](qa/code-snapshot-zip-20261016.md)。

## CLI 还原到待批准 code-only-v1 来源

`harnesslab code-snapshots restore` 在 Linux/WSL 将一个已有、完整性校验通过的快照还原为
新目录，输出可人工审核的 `source_fragment`。不自动编辑 policy、ingest、绑定运行或执行
Verifier；来源固定 `unverified`，结果仍为 `NOT_ATTESTED / NOT_VERIFIED`。

先配置已有私有证据策略 `HARNESSLAB_EXTERNAL_EVIDENCE_POLICY`。目标必须为绝对、规范、
尚不存在的路径（包括已有空目录也拒绝），父目录须已存在、归当前用户所有且组/其他用户不可写。
目标不得与证据 store、仓库、TaskStore 源/managed store/准入记录、Verifier runtime/artifact、
已批准 source workspace/path 或其他已配置执行存储重叠。父路径任一符号链接均拒绝。

```bash
umask 077
mkdir -m 700 /absolute/private-restores
uv run --locked harnesslab code-snapshots restore SNAPSHOT_ID \
  --destination /absolute/private-restores/new-workspace \
  --source-id reviewed-final-code \
  --task-reference "$REVIEWED_TASK_REFERENCE" \
  --task-digest "$REVIEWED_TASK_DIGEST" \
  --confirm-source-restore > /absolute/private-restores/restore-review.json
```

任务引用与摘要是操作员的显式断言，并非从 ZIP 文件名、生成工具或代码内容推断。
还原阶段不检查任务资格，也不证明该任务适合这份代码。输出包含纳入文件的路径/大小/sha256、
源码树摘要和原排除清单；没有被排除内容。逐文件重新读回比对后，使用 fd 相对路径与
`O_NOFOLLOW / O_EXCL` 写入独立暂存目录，通过 Linux `renameat2(RENAME_NOREPLACE)` 原子发布。
不支持该原语的内核/文件系统拒绝，没有覆盖式降级。并发同一目标只允许一个发布者，其余拒绝；
写入、校验或发布失败清理本次暂存，不清理或覆盖原有目标。突然断电/进程 SIGKILL 后的残留
不属于正常异常清理保证，需人工检查；不要把还原目录视为不可变证据。

人工核对任务适配性、来源片段、逐文件摘要及排除项，再把 `source_fragment` **手动**追加到
policy 的 `sources`，保留旧来源及其 pin。之后使用现有接口和显式同意：

```bash
curl --fail-with-body http://127.0.0.1:8000/api/external-evidence/records \
  -H 'Origin: http://127.0.0.1:8000' -H 'Content-Type: application/json' \
  -H "Authorization: Bearer $HARNESSLAB_LOCAL_CONFIGURATION_TOKEN" \
  --data '{"source_id":"reviewed-final-code","consent":"IMPORT_APPROVED_SAVED_EVIDENCE"}'
# 读取返回的新 ExternalRecord identity；随后另行显式授权已有独立 Verifier：
uv run --locked harnesslab external-evidence verify-workspace RECORD_ID \
  --confirm-independent-verifier
```

物理验收仍要求原有 TaskStore 资格、确切 task_digest、固定镜像和隔离 runtime/artifact。
一次物理尝试、无自动重试、默认基础设施失败、30秒上限、network none、零检查/矛盾证据不得
PASS，以及原收据/导出/Replay/ExternalRecord 身份算法都不改变。二次调用复用已有收据，
并不重跑。任何 task pin 或还原目录变化都需要重新审核，不能修改旧证据来取得通过。

**FastAPI MiniShop 快照 `58c9ef0ce39b4f5d245cbc325adde1e5fc33b28cd0c16f413b05d8ccd04182f0`
没有可信任务。不得将它映射到 `minishop-standard-library@1.0.0` 的 WSGI 契约后宣称验收。**
CLI 不做语义适配认证；没有适配且已资格认证的任务时保持 NOT_VERIFIED。
