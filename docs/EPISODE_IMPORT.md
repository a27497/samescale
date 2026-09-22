# 已结束 Codex 运行包 → Episode

`harnesslab episode import-codex` 读取现有 SameScale Codex H-Lane 产物，建立一个内容寻址的
CUSTOM Episode 元数据记录。不启动模型、数据库、Hook 或验收器，也不导入 Official 成绩表。

支持的输入必须包含 `manifest.json`、`native/codex.sanitized.jsonl`、`trace/normalized.json`。
有已记录独立验收的运行，还必须带最终 `workspace/` 与完整 `verifier/` 目录。
无验收的失败运行允许缺少 workspace，但显示 MISSING / NOT_VERIFIED。
不接受任意原始 `codex exec --json`、Codex 桌面对话日志或 LectureLens Study Agent 的业务 trace。

```bash
harnesslab episode import-codex /absolute/completed-h-lane-run \
  --source-kind historical --store harnesslab-runtime/episodes

harnesslab episode inspect harnesslab-runtime/episodes/<episode-sha256>.json
```

`--source-kind` 为 `historical`、`synthetic` 或默认 `unverified`。这是操作员提供的来源标签，
校验摘要不构成生产者认证；`source_authenticity` 始终为 NOT_ATTESTED。
相同来源内容和标签导入幂等，改变内容产生新身份，不覆盖旧记录；inspect 会拒绝已改动记录。
源目录和目标目录不能重叠，目标不能位于仓库 Official `tasks/` 或 `release/` 中。

导入器核对 profile 指纹、trace 摘要/顺序/数量、工作区摘要和 verifier 的任务身份、工作区、
stdout/stderr 与实际验收报告。摘要漂移、缺失关键证据、链接/特殊文件、重复 JSON key 或
矛盾的验收结果均拒绝导入；输入上限为 10000 个文件、128 MB，单个 JSON 上限 4 MB。
带验收附件的来源必须为 verified_pass / verified_fail；基础设施失败不能携带可接受的验收结论。
verifier 超时、取消或 stdout 截断时，即使保存的 JSON 可解析且声称通过，也拒绝导入。

| 保存的信息 | 含义和限制 |
| --- | --- |
| task/profile/prompt/workspace/trace 摘要 | 可关联原产物；不复制原源码、模型消息、推理、命令或命令输出 |
| setup_identity | 本次运行的完整 profile、渲染后 prompt 与预算的组合摘要；包含任务提示，不作为跨任务配置等价证明 |
| requested/observed model | 原 manifest 中的请求和报告值；不能验证中转实际运行的上游模型 |
| duration_ms、tokens | 原 manifest 已记录值；耗时不是纯推理时间，缺少值不估算 |
| cost_usd | 此格式没有可信账单，始终为 null |
| event_counts、failed_commands | 事件类型计数及已结束非零退出命令数；不是任务失败率或原因判断 |
| changed_file_count | 原 manifest 记录的修改数量；导入器未重建 before/after diff |
| RECORDED_PASS / RECORDED_FAIL | 原独立 verifier 报告与附件一致；本轮没有重新执行验证 |
| NOT_VERIFIED | 没有完整独立验收；不能用 Agent 自述替代 |

`comparison_eligible`、`execution_authorized` 均为 false。导入后仍需任务来源治理与可比性评估，
才能用于后续比较；不能据单个 Episode 推荐模型或配置。
该 H-Lane 命令可以由操作员的外层脚本在产物关闭后调用，本身不安装或启用自动 Hook。
不要在仍写入的产物目录上导入；导入前后的内容检查可发现普通并发变化，不构成恶意文件系统的安全边界。

## Native Hook 最小被动接收

源码接收器 `scripts/receive_agent_hook.py --source codex|claude --spool /absolute/private-spool`
只接收原生 Hook 的 stdin；无启动 Agent、读取 transcript、shell 执行、网络或环境变量采集入口。
配置由本地操作员管理，不自动安装。每个 spool 仅支持一个来源、单会话、单 turn。
对 Codex 注册 `SessionStart`、`PreToolUse`、`PostToolUse`、`Stop`；Claude 另注册
`PostToolUseFailure`。使用绝对 Python/script 路径及仓库 `src` 的 PYTHONPATH，设置有界 timeout。
Hook 返回空 JSON，不改权限、不注入上下文、不要求 Agent 继续。生产者自身的日志策略独立于
SameScale；本轮 Codex 使用 `--ephemeral`、history none、禁用日志及不保存 stdout/stderr。

落盘白名单仅含来源枚举、生命周期枚举、哈希 session/call ID、工具类别、明确退出码/失败事件。
原始 Prompt、命令、参数、输出、消息、hidden reasoning、transcript 路径及未知字段全部丢弃。
仅识别明确支持的状态结构；未知状态是 null，不能推断为成功或失败。私有 spool 必须位于
可信本地文件系统，不能当作敌对同 UID 文件系统或远程生产者认证边界。

```bash
harnesslab episode import-hooks /absolute/private-spool \
  --store /absolute/episodes --source-kind unverified
harnesslab episode freeze-hooks /absolute/private-spool \
  --store /absolute/episodes --output /absolute/regression-case.json
PYTHONPATH=src:. .venv/bin/python scripts/replay_hook.py \
  --case /absolute/regression-case.json --sha256 sha256:TRUSTED_DIGEST \
  --output /absolute/new-replay.json
```

接收采用持久化去重、进程锁与 fsync，冲突/无效输入写 content-free `REJECTED` 标记。
重复事件幂等；乱序按生命周期和调用配对规范化，**不声称恢复真实墙钟顺序**。
接收进程重启无需内存状态；中断写入、缺少启动/停止/配对事件、混入其他会话或矛盾内容均
fail-closed。import 与 freeze 在调用方确认会话关闭后执行；不是运行中实时完成状态管理。
摘要仅证明完整性，`source_authenticity=NOT_ATTESTED`、`comparison_eligible=false`。

复用 Episode namespace 与 content identity、既有 NormalizedTrace、S2 pinned-reader / audit
guard、S3 offline gate；新的 CUSTOM hook 数据不会伪装成 H-Lane 或写入 Official frozen BadCases。
不带 verification 时，Bad Case 仅归因到已观察工具失败；根因为 null，最终任务验收为 NOT_VERIFIED。
Replay 重算并核对 trace/归因，**不执行 Agent、命令或 verifier**。

首次仅 Hook 验收为 **PARTIAL**：真实 Codex 的 10 条回调与导入有证据，
但缺少 Bash 退出码，该旧会话冻结被拒绝。后续独立验收的闭环见下文及
[Phase 0 来源记录](evidence/phase0-candidate-20260922/README.md)。
Claude 因协议 blocker 的 STOP 规则未启动，不能写作 Claude 环境故障。合成回归中的
Bad Case/freeze/replay PASS 不能替代这项真实验收。

### 独立工作区验收与 verified Bad Case

Codex 0.153.4 的 Bash Hook stdout 不包含进程状态；接收器不再从文本头解析 exit code。
原 Hook Episode 与 Trace 不变，另用既有 `DockerSandbox.run_hidden_verifier_workspace` 在只读、
无网络、无凭据容器内验收最终源码。Verifier 不执行原 captured commands 或 subject 自带测试脚本。
当前收口只支持有原会话最终源码摘要绑定的受控 CUSTOM fixture，不宣称通用工作区摄入服务。

验证 bundle 使用 S2 的 pinned inventory reader，包含原 Hook receipts、原 Episode/Trace、
原 capture 摘要和最终源码绑定、TaskPackage、独立 verifier 源码、真实 sandbox manifest、
完整 stdout/stderr report 与 lifecycle。产物摘要、只读挂载、workspace/task/verifier 绑定和 report
内部结果必须全部一致；缺失、变更、超时、截断、零 checks 或矛盾结果均拒绝。

```bash
harnesslab episode freeze-hooks /absolute/verification/hooks \
  --store /absolute/episodes --output /absolute/regression-case.json \
  --verification /absolute/verification \
  --verification-sha256 sha256:TRUSTED_BUNDLE_DIGEST
PYTHONPATH=src:. .venv/bin/python scripts/replay_hook.py \
  --case /absolute/regression-case.json --sha256 sha256:TRUSTED_CASE_DIGEST \
  --output /absolute/new-replay.json
```

Verifier PASS 不能生成 verified Bad Case。FAIL 则保留 `L0_INDEPENDENT_VERIFIER`、失败 check 和
工作区摘要；不改写 Hook 的 null exit code，不以任务契约失败证明 Agent 指令遵循失败或模型根因。
旧 Episode 继续是仅 Hook 的 NOT_VERIFIED，新的验证附件才承载 VERIFIED_FAIL/PASS。
原 BLOCKED 记录保持原状；[独立 verifier 收口证据](evidence/phase0-candidate-20260922/README.md)
记录实际新结果。Replay 只核对已记录结果，不重新运行任何验收代码。
