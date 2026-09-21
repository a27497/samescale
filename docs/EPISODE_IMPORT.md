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
命令可以由操作员的外层脚本在产物关闭后调用，但本次没有安装或启用任何自动 Hook。
不要在仍写入的产物目录上导入；导入前后的内容检查可发现普通并发变化，不构成恶意文件系统的安全边界。
