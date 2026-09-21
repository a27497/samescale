# Phase S2 — Trace Diff + Offline Replay：COMPLETE

2026-09-21。两个 S1 正式真实 run 均已离线 replay，cross-run diff 可确定性复验，
missing/tampered/inconsistent evidence 均 fail closed。**本阶段 external / Provider / model /
Claude / Judge 调用全部为 0**。未执行 subject、trace 中的命令或 verifier。

S1 保持 [PARTIAL REAL BENCHMARK / BLOCKED](../s1-partial-closeout-20260921/README.md)：
1 Official Codex verified pass、1 Claude timeout / NOT_VERIFIED、14 NOT_RUN。S2 完成不补齐 S1，
不改变原配置或 600 秒 timeout，不支持能力排名、完整 configuration 结论或 Harness 因果归因。
未进入 S3，未 commit/push/deploy。

## 可复验的实测差异

| 维度 | Official Codex | Claude Code |
| --- | --- | --- |
| 冻结配置 | CLI 0.153.4 / gpt-6-astra / high / Official ChatGPT | CLI 2.1.241 / qwen3.8-max / 原 Alibaba Bailian Messages provider |
| 正式 run | 7462d2841b6f44648c43ee384baf8e6f | 9f0c915c881c417786fc6bff73b175d3 |
| native / normalized events | 33，逐事件一致 | 6857，逐事件一致 |
| 工具序列 | 11 command executions + 2 file edits；启动/完成去重后 13 次 | 4 Bash + 6 Read，10 次结果均记录 completed |
| 文件访问与编辑 | shell 中的路径提及单独记录；2 个显式 edit；workspace 实际增加 1 文件、修改 1 文件 | 6 个明确 Read；其余 shell 路径提及不当作访问证明；workspace 无变化 |
| subject 自检 | `python tools/frontend_check.py`，记录 exit 0 | 没有记录执行 validation command；读取检查脚本不等于执行 |
| 独立 verifier | 已保存报告 20/20 verified_pass | NOT_RUN，task NOT_VERIFIED |
| subject / 端到端观测 | 193000 / 220490 ms | 601055 / 606046 ms |
| usage | input 188342；cached input 25216；cache write input 0；output 5230；reasoning output 714 | UNKNOWN；thinking metadata 数量不能代替 token usage |
| output budget | 5230 / 声明 6000，WITHIN_DECLARED_BUDGET | UNKNOWN；预算与 task success 分开 |
| completion / failure | 原生 `turn.completed`，独立 verifier 决定通过 | 无原生终态；timed_out=true；execution_budget_exhausted；exit 0 不代表通过 |
| secret / cleanup | 原 secret audit PASS；cleanup PASS | 原 secret audit PASS；原 cleanup FAIL 和后续 post-stop PASS 分开保留 |

Codex 两个变更文件为 `frontend/src/stores/taskEvents.ts` 和新增的
`frontend/src/stores/taskEvents.recovery.test.ts`。三条探索 shell 命令记录了非零退出状态，
后续仍完成编辑、自检与独立 verifier；不把这些普通命令失败改写为基础设施失败。

Claude 最后一个工具结果在 ordinal 92；其后记录 6762 个 thinking-token metadata events。
这些事实支持“该次执行在记录的读取/检查交互后，直到时限仍未记录完成或文件变更”。
**不能据此证明模型仍在有效推进、卡在某个函数、某一步耗时多少，或 provider/模型/Harness
中的哪一层导致 timeout**。没有逐事件时间戳、私密推理正文或已验证根因。
`FULL_STREAM` 是原 collector 标签，不等于原生会话已完整结束。

两侧 task、起始 workspace、verifier digest 相同；model、provider、CLI 和各自冻结的 prompt-template
身份不同，不能做单变量因果解释。cost、provider request count 保持 UNKNOWN；不据此比较普遍效率。

## 交付与信任边界

- [Machine-readable trace diff](trace-diff.json)：工具序列、文件访问/编辑、validation、duration/usage、
  changed files、completion/failure 和解释限制。事件通过 ordinal、JSON pointer 与 trace digest 定位。
- [Readable diagnosis](diagnosis.md)：逐次工具序列表；[Codex replay](codex.json) 与
  [Claude replay](claude.json)分别保留重建 outcome、verifier state 和控制状态。
- [Representative immutable bundles](representative-bundles.zip)：两条原始 run 的 manifest、
  sanitized native/normalized trace、完整 workspace、已有 verifier 输出/快照、receipt、result、
  secret audit、cleanup；另带 digest 相同的起始 workspace。无隐藏 oracle 可执行资产、凭据或私密推理正文。
- [Packaging provenance](packaging-provenance.json)：从原两个正式 cell 索引校验 315 + 109 个原件文件。
  baseline 来自 Claude 未变更 workspace，并分别匹配两侧冻结 input digest。bundle 是逐字节复制原件，
  不是从 summary 伪造的 run；新目录和清单不取代原 S1 run/campaign identities。
- [Replay reader](../../../src/harnesslab/analyst/offline_replay.py) 与
  [CLI](../../../scripts/replay_s2.py)：先校验外部指定的 inputs digest、bundle manifest digest、
  完整文件集合和各文件摘要，再核验 run/workspace/verifier tree、native→normalized trace 重建、
  changes 与 manifest/receipt/projection/verifier 一致性。零 verifier checks、缺终态伪装成功、
  usage/cleanup 矛盾均拒绝；两侧全部通过后才创建 comparison 输出。
- Claude sanitized trace 未保留 tool IDs，因此结果只按“唯一 pending tool 的记录顺序”关联；
  遇到并发歧义直接拒绝。Codex 按 item ID 关联，保留其交错的开始/完成顺序。
- digest 必须由调用者在 bundle 外保存。攻击者同时替换原件和所有 trust anchors 不在摘要校验的
  认证能力之内。该 reader 支持本次 S1 的冻结格式，不宣称任意 Harness trace 都可 replay。

Replay 是对已保存事实的重建与校验；不会重演模型行为，也不会再次证明 verifier 当前执行仍通过。
命令文本仅作数据读取，subject workspace 与 verifier 中的代码都不执行。
CLI 安装 CPython audit hook 拒绝 socket 和子进程操作；它是本工具的离线保护，非任意恶意程序的 OS sandbox。

## 离线复现

需要已有仓库锁定的 Python 依赖；以下 `uv --offline` 不下载依赖。先核对本报告外部保存的 archive
trust anchor，再解压到新目录。整个解压目录可搬移，无需原 `/home/dev/artifacts` 路径。

```bash
sha256sum docs/evidence/s2-offline-replay-20260921/representative-bundles.zip
# 必须为 ee7748478fa7366d17454d1c5936a33466c580c2a3baf9ccdc5c302705345abd
python3 -m zipfile -e docs/evidence/s2-offline-replay-20260921/representative-bundles.zip /tmp/s2-bundles-new
uv run --locked --offline python scripts/replay_s2.py \
  --inputs /tmp/s2-bundles-new/inputs.json \
  --sha256 sha256:d77d964fe60158da4e22ee7e60df0cfb54178a99c957298d861d977f925d0395 \
  --output /tmp/s2-replay-new
```

输出目录必须不存在且位于输入 bundle 外；不覆盖历史结果。失败返回 exit 2 / FAIL_CLOSED，
不导出半个有效 comparison。[两次独立 CLI 复验](reproducibility.json)的五个输出文件逐字节相同；
[implementation pins](implementation-sha256.json)绑定 reader、normalizer、tests 与锁定依赖声明。

## 验证与停止点

[44 regression tests](../../../tests/test_s2_offline_replay.py) **PASS**，
[Ruff](ruff.txt)、[format](format.txt)、[mypy](mypy.txt) **PASS**；
[完整命令和退出码](checks.json)、[pytest 输出](pytest.txt)保留。测试直接使用本目录的真实 bundles，
解压副本后测试，不依赖原外部 artifacts 路径，不修改真实原件。
覆盖：两个真实 replay、diff 确定性、缺失/篡改、额外文件、symlink、替换 trust anchor、重复 JSON key、
非有限 JSON 数值、路径逃逸、零 checks、verifier 失败与超时矛盾、baseline/native/normalized/terminal/
usage/changed files/secret/cleanup 不一致、不同 task 或重复 run、失败不释放部分结果、输出不得写入 bundle，
以及 socket/子进程保护。initial-checks 记录先前 43 项本地检查；最终 44 项是追加输入保护后的结果，不累加。

[Representative integrity drill](integrity-drill.json)在临时副本中证明三种情况均 FAIL_CLOSED：
missing native、tampered workspace、重新计算外层摘要但 task success 矛盾。演练副本已移除。
[保全及 secret audit](preservation-and-secret-audit.json)确认 S1 原导出 318 文件、partial closeout
5 个索引文件保持原字节；513 个 archive members 的高置信凭据模式检查无发现，私密 reasoning 正文未保留。
未读取新的 credential sources；原 secret audit 的 PASS 继续通过 digest 绑定。
[Offline boundary receipt](offline-boundary.json)记录 external calls=0，无 subject/verifier 新执行。

[Final status](final-status.json)：**S2 COMPLETE，停止于本 Phase；S3 未开始。**
外部中间产物与完整复现输出保留于 `/home/dev/artifacts/samescale-s2-offline-20260921/`；
本 report、archive 和导出 JSON 已足以独立复现本次离线读证据流程。
