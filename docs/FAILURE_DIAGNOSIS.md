# LLM 失败诊断

诊断是操作员 CLI 中独立、可选的辅助说明。只有已有独立 Verifier 收据为
`VERIFIED_FAIL`、收集过检查且存在失败检查时才接受输入。Verifier 保持唯一验收权威；
诊断类别不是验收失败类型、置信度不是校准概率，诊断成功、失败和不可用都不改变验收。
网页没有新增诊断展示或自动模型调用。

## 职责与输入边界

`failure_diagnosis` 只接收不可变的验收事实快照和操作员审阅的公开摘录。
收据通过文件 SHA256 固定，检查引用必须绑定实际失败编号；模型仅收到四种公开材料：
任务描述、最终代码 diff、Verifier 已公开的失败观察和 Agent 最终自报。
不向模型发送完整收据、Episode、TaskStore、oracle、隐藏测试源码、已知标准答案或报告根因。
不能把未经处理的 traceback 当成公开输入：其中打印的断言和源码仍是隐藏材料。

公开材料由操作员负责审阅与来源核对。`public_only_reviewed=true` 是审阅声明，不是自动证明；
模型可能受到证据里的提示注入影响。严格 JSON/schema 校验、引用绑定和无工具执行只限制
结构与权限，不能证明解释正确，也不能自动识别自由文本中的全部秘密。

`scripts/prepare_failure_diagnosis_cases.py` 只读取固定两个案例已有的任务、交付 diff、
最终消息、验收收据、上游检查状态和失败输出。它只保留明确的异常名称、失败检查标识与
已渲染的输出差异，丢弃源码、断言、上下文和堆栈位置；仍需人工审阅后使用。
上游输出是整次运行的聚合观察，不能据其顺序推断每个收据编号对应哪个上游断言。
脚本将聚合观察标注在实际失败编号的摘录中，不读取隐藏文件或上游修复。

## 结构与降级

Pydantic 生成 JSON schema，`jsonschema` 的 Draft 2020-12 校验器验证模型输出后，
再校验类型与语义。固定类别：**边界条件遗漏、输出格式不符、逻辑或算法问题、运行时异常、
构建或依赖问题、超时、原因未知**。每份解释必须包含：

- 以上枚举之一、非空诊断说明、0–1 置信度。
- 属于输入摘录的证据引用，至少一条来自失败检查；diff 摘录可以同时引用。
- `notice="诊断仅供参考，不影响验收"`、`affects_acceptance=false`；额外字段拒绝。

未授权模型调用时默认规则分类。模型异常、超时、超长/非法输出、schema 拒绝、引用越界、
工具事件都返回降级产物，不向外抛出模型异常或保存异常原文。规则仅检查公开失败文字：
超时 → 超时；导入异常 → 构建或依赖问题；断言或 FAILED → 逻辑或算法问题；其余 →
原因未知、诊断不可用。规则置信度固定为 0，并记录固定的降级原因，不能当成具体根因。
输入损坏、非 FAIL 收据、写入路径重叠等操作员输入错误会拒绝执行。

## 外部 Codex CLI 后端

`DiagnosisBackend` 可替换，默认规则与测试 fake 不发真实请求。真实后端使用用户既有
ChatGPT 登录文件的只读引用，**不使用 API Key，不读取或转发 ANTHROPIC_AUTH_TOKEN**。
单独授权订阅诊断与产品 REAL_CODEX 执行权限无关；REAL_CODEX 门禁不修改、不绕过。

支持固定 Linux x64 Codex CLI **0.162.1**，二进制 SHA256
`628e35487d888a28f0427fc37501da529dd3d81fcbad7a2c3421c1e8670d92e1`。
版本或摘要不同会降级，不静默使用其他 CLI。
`codex exec --json --sandbox read-only --ephemeral --ignore-user-config --ignore-rules`
使用独立临时 HOME、固定输出 schema 和无工具模型目录：shell 禁用，
`apply_patch_tool_type=null`、扩展工具为空；关闭固定版本全部175个布尔 feature、
规划、交互问答及 web search。只关闭 `apply_patch_freeform` 不能移除修改工具。
配置不载入用户 MCP、插件、技能或规则；非致命 CLI `error` 通知不视为工具，
但必须收到最终消息和完整结束事件。任何真正的工具项或未知项都拒绝。
CLI 私有推理及通知正文不留存，只保留诊断 JSON、可得 token 数和事件类型计数。

Docker 根文件系统只读、空工作目录只读、移除 capabilities、禁止提权，限制 CPU、内存和 PID。
仅挂载 schema/模型目录、固定 CLI vendor 与登录引用，均只读；不挂载仓库、原证据或隐藏材料。
复用既有固定 egress proxy，只允许 `chatgpt.com:443`；实际内部/出口网络拓扑须通过既有
检查。凭据在容器私有 tmpfs 中复制给 CLI，容器结束即删除，不读取或归档凭据内容。
子进程只接收明确列出的非密钥环境变量。超时会杀进程并删除自己创建的容器及网络。
每次授权调用不自动重试；修正实现后重试须保存前次产物并记录总调用次数。

官方参考：[非交互模式](https://learn.chatgpt.com/docs/non-interactive-mode)、
[配置参考](https://learn.chatgpt.com/docs/config-file/config-reference)。工具关闭规则还依据
[固定版本工具注册源码](https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/core/src/tools/spec_plan.rs)
与[事件协议](https://github.com/openai/codex/blob/rust-v0.162.1/codex-rs/exec/src/exec_events.rs)。

## 使用与离线复核

先导入已有证据，单独授权 Verifier 并获得 FAIL 收据。另行制作公开摘录 JSON：
`public_only_reviewed=true`，`excerpts` 为包含 `id/kind/reference/text` 的数组。
kind 从四种输入类型选取，失败检查 reference 写 `check:编号`，其他 reference 指具体原证据位置。
任务、diff 与失败检查必需，自报缺失时不补造。先默认规则执行：

```bash
uv run --locked harnesslab failure-diagnosis run \
  --receipt /private/evidence/verification.json --receipt-sha256 RECEIPT_SHA256 \
  --public-packet /private/reviewed/public-packet.json --output /private/diagnoses/new-run
```

需模型时，在相同命令中额外指定：

```bash
  --confirm-subscription-diagnosis --model gpt-6.1-sol \
  --vendor /private/codex/vendor/x86_64-unknown-linux-musl \
  --credential-reference /private/codex/auth.json --timeout-seconds 120
```

预先准备既有 `harnesslab-egress-proxy:1.0.0` 镜像及固定 Python 基础镜像。
版本/vendor 由操作员提供，诊断不会安装 CLI、拉取镜像或调用原 Agent/Verifier。
输出必须位于 Git 与输入存储之外的新目录；拒绝覆盖已有目录。
`diagnosis.json` 是独立产物；同次生成 `export.json`，并输出可信 SHA256。
输出中验收事实仅是绑定输入的快照，不是新验收收据。

```bash
uv run --locked harnesslab failure-diagnosis replay \
  --export /private/diagnoses/new-run/export.json --artifact-sha256 ARTIFACT_SHA256
uv run --locked pytest -q tests/test_failure_diagnosis.py
uv run --locked pytest -q tests/test_external_evidence_docker.py -k codex-hooks
```

最后一个隔离测试需要 README 指定的既有 Docker 测试镜像，运行的是无密钥模拟任务。
离线回放检查产物摘要、schema、引用和模式一致性，不加载模型后端、不重新诊断、
不修改验收，也不证明诊断正确。导出包含公开摘录，仍应按私有证据保存；没有自动上传。

费用记录如实写 **ChatGPT 订阅额度，无单独计费**，不是“免费”。记录模型、CLI 版本、
物理调用数、CLI 原生可得的 token 字段；不可得写 null/不可得，不估算美元或 token。
CLI 调用次数不能等同于内部请求次数；通知和断线重试可能增加内部请求。

## 本次真实观察（摘要）

UTC 2026-10-14，gpt-6.1-sol/low，CLI 0.162.1，两个预先指定的 FAIL 案例。
总4次 CLI 调用：首轮2次因事件解析兼容问题降级，修正通知项分类后各追加1次；所有尝试保留。
最终 SymPy 诊断“逻辑或算法问题”、置信度0.58：指出名称解析可能变化，**没有识别出**
报告中已知的 Unicode 数字遗漏，不能声称根因一致。最终 Sphinx 诊断“输出格式不符”、
置信度0.88：明确指出签名末尾多出的反斜杠，与报告失败表现一致；其具体形成路径仍是推测。
不是成功率评测，也没有根据诊断补跑验收或改变任何原始结果。

| 案例 | 最终调用耗时（含启动与清理） | input / cached / output / reasoning tokens | 最终产物 SHA256 |
| --- | --- | --- | --- |
| SymPy-20916 | 18.653秒 | 1535 / 0 / 336 / 34 | `d96c8f2e4d769a6b0ac9e3fd382813b3f59f8fd510fd5981406abcab93ce0087` |
| Sphinx-7748 | 18.503秒 | 2623 / 0 / 346 / 25 | `2eb6f856e3494dc3782390bff06eedd495c2bd54fd3a23e8a31805a988fe91eb` |

两次最终调用的 cache_write_input_tokens 都为0；首轮 token 数不可得，不能给出4次总 token 数。
模型名是 CLI 请求配置，服务端实际路由未单独证明；重新调用可能给出不同解释，
只有保存产物的离线校验保证字节与结构一致，不能保证根因正确。
首轮耗时分别18.258秒、16.756秒。费用均为订阅额度、无单独计费。
原始诊断 JSON、公开输入、调用元数据、离线导出与初次降级保存在 Git 外
`/home/dev/.local/state/samescale-eval/llm-failure-diagnosis-20261014/`，最终目录为 `results-v2/`。
原收据、运行记录、交付 diff 和原导出的 SHA256 前后均一致。
独立归档为该目录旁的 `llm-failure-diagnosis-20261014.tar.gz`，15464字节，SHA256
`4264722a9907825cb868d50ef1823a6f3c4ab35654d8099362d000c67a070610`；只包含公开输入与
诊断、绑定元数据和导出，不包含登录文件、隐藏材料或模型私有推理。
已知原因对照来自[既有评测报告](evidence/swe-full-20261014/README.md)，未作为模型输入。
