# 通用运行证据输入（最小版本）

SameScale 是「AI Coding 任务验收与证据工作台」。必需输入为最终代码 Workspace 和独立的
任务验收条件；运行记录仅增强解释覆盖度。本轮保留人工批准的私有策略入口，不新增上传
服务或扫描器。先由操作员主动提供、审查并固定文件，UI 再按工具选择已批准输入。
[隔离启动、权限和摘要命令](EXTERNAL_EVIDENCE_QUICKSTART.md)。

## 输入与批准绑定

策略仍是所有者私有 0600 文件，存储独立 0700。所有输入共用原操作员/loopback/同源权限、
显式 `IMPORT_APPROVED_SAVED_EVIDENCE` 同意、固定摘要和敏感模式检查。摘要证明字节一致，
不证明来源真实、会话与 Workspace 配对或素材可公开。模式检查不能代替人工隐私/IP 审查。
不接触 `~/.codex` / `~/.claude` / Cursor 会话目录，不读取认证或隐藏验收目录。

每个 `ApprovedSource` 固定 `source_id`、`source_kind`、`workspace`、`workspace_digest`、
`task_reference` 与 `task_digest`。任务引用/摘要必须来自独立审查的验收任务包；不能由日志
提供运行命令。新格式要求任务映射，但映射不等于 TaskStore 行为准入，也不等于验收通过。
只支持非空 UTF-8 最终 Workspace（500 文件 / 4 MB）；本轮没有 baseline+diff 应用器。
没有可靠基线时文件差异为 `BASELINE_MISSING`，不会将日志里的编辑事件当成实际 diff。

| 格式 | 运行记录与工具 | 覆盖度 |
| --- | --- | --- |
| `stream-json-v1` | 目录仅含 `events.jsonl`；`harness.name=codex` | `SUPPLIED_EXEC_JSONL_ONLY` |
| `stream-json-v1` | 目录仅含 `events.jsonl`；`harness.name=claude-code` | `SUPPLIED_STREAM_JSON_ONLY` |
| `auto-v1` | 同上，仅按提供的 Codex / Claude 信封识别，歧义/混合拒绝 | 同相应转换器 |
| `code-only-v1` | 无 `path` / `digest` / `harness` | `NO_RUN_RECORD`（无运行记录） |
| `hook-v1` | Codex Hook；兼容 `native-hook-v1` | `PAIRED_HOOKS_ONLY` 或 `INCOMPLETE_HOOKS` |
| `h-lane-v1` | Codex H-Lane；兼容 `codex-h-lane-v1` | `RECORDED_H_LANE` |
| `verified-hook-v1` | 原严格绑定 Hook bundle | `PAIRED_HOOKS_ONLY` |

旧 `codex-jsonl-v1` 是 Codex stream 转换器的兼容别名。四种原格式及旧
`external-codex-evidence-v1` 记录继续读取，不重写旧记录身份、验收收据或冻结证据。

`harness.version` 为经审查的版本或 `null`，不能猜测。`extensions` 只由转换器生成安全的
格式/转换器标识；禁止通过批准配置注入任意原始工具字段。当前内部模型不绑定 ATIF 或 OTel。
原始事件在内存转换为现有 `NormalizedTrace` 后，共用投影/存储/导出路径；自由文本、思考、
提示、输出、原始会话 ID 和命令正文不持久化。命令只保留摘要，安全相对文件路径仅作观察。
流限制为 4 MB / 4096 行，单行 1 MB、嵌套 64 层；只接受一个显式普通文件，无链接/硬链接。
JSON 重复键、非有限值、错误信封、过大输入、凭据形状和受保护路径拒绝，拒绝时不生成记录。

## 仅代码改动的策略条目

以下是配置结构占位符，必须替换成独立审查的实际值；它不是产品内示例任务。

```json
{
  "source_id": "reviewed-code-only-001",
  "format": "code-only-v1",
  "source_kind": "unverified",
  "workspace": "/absolute/reviewed/final-workspace",
  "workspace_digest": "sha256:EXTERNALLY_RETAINED_WORKSPACE_PIN",
  "task_reference": "EXACT_ADMITTED_TASK_REFERENCE",
  "task_digest": "sha256:EXTERNALLY_RETAINED_TASK_PIN"
}
```

无需运行日志 pin；现有 Workspace 摘要命令仍适用。先选择“仅代码改动”，再选批准的
Workspace 和条件绑定，明确同意导入。无运行记录时原运行状态为“未报告”，不推断 Agent
未执行，不制造原 Episode。导入后仍是 `NOT_VERIFIED`；需要新验收时使用原有单独授权 CLI：

```bash
uv run --locked harnesslab external-evidence verify-workspace RECORD_ID --confirm-independent-verifier
```

该命令要求精确 TaskStore qualification / baseline-fail / oracle-pass、独立固定 Verifier 镜像
以及隔离 runtime/artifact 目录；这是操作员另行授权的验收，不是导入按钮自动执行。
无日志不阻止验收，成功/失败/超时均绑定 Workspace 与任务摘要。0 项检查、损坏或失败清理
不能通过；一次尝试后不自动重试。原记录和来源声明不被新收据覆盖。

## 观察与限制

Claude 转换器复用 `multi_harness` stream 解析；campaign 的固定工具 profile 不适用于
外部保存日志，不作为导入验收结论。`result.success` / Agent 的“完成”均不能证明任务通过。
缺结尾的合法片段可导入为 PARTIAL；未映射事件保持 UNKNOWN。工具调用关联、过程退出码、
实际模型/路由/用量/成本/时间序在本轮仍可能缺失，覆盖度不会标为全量。
Cursor、DeepSeek 类 harness 及其他工具本轮可提供最终 Workspace 的仅代码输入；它们的
原生日志转换器尚未实现。非 UTF-8 / 二进制、大仓库、任意 diff、远程/多人上传、在线 Agent、
模型调用、后台调度验收和通用 DLP/来源认证均不在范围内。所有来源保持 `NOT_ATTESTED`，
`NOT_VERIFIED` / `NOT_RUN` / `CORRUPT` 含义不变；离线 replay PASS 仅证明导出一致性。
