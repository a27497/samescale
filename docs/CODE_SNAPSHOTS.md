# 网页 ZIP 源码快照（code-snapshot-v1）

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
源码树摘要、限制和确认绑定，篡改后拒绝读取。

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

## 暂存与测试

上传/预检只使用受限内存，不创建待确认目录。确认在 flock 下以临时目录和 `os.rename`
原子发布，已有快照不重写。临时目录是 store 的随机兄弟目录；在写入前检查与仓库、
记录/快照 store、全部批准来源 workspace、配置的 TaskStore/来源、执行及 Verifier 根、
显式 Custom TaskStore 分离。正常结束、拒绝和异常时由 TemporaryDirectory 清理。

新增 adversarial fixtures 只用于拒绝/排除契约，不代表真实 MiniShop 通过。它们与
`tests/test_local_init_script.py` 一起注册到 Fast CI 核心清单、固定分片和 self-hosted 清单；
保留原 29 selectors 的独立 fingerprint，并在 inventory 契约里追加精确登记。
新增 ZIP 测试还进入 Offline Regression。实测记录见
[2026-10-16 验证报告](qa/code-snapshot-zip-20261016.md)。
