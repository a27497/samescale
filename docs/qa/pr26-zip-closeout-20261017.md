# PR #26 ZIP 合并前收尾 — 2026-10-17（Asia/Shanghai）

基线 `833cdc398d2f47c6f8573246b59833729f379a30`，仅在
`codex/code-snapshot-zip-20261016` 工作树内修改。提交和普通推送至 Draft PR #26，
授权边界为不合并、不部署、不调用模型或 Agent、不读取真实凭据。首轮测试的真实 CLI 探测偏差见下文。

## 交付范围

- UI、源码快照文档及公开契约均明确提示：请上传仅含源码的 ZIP；依赖目录中的文件可能触发凭据规则导致整包拒绝。
- P1-1 未实现：现有 `test_credentials_reject_even_excludable_files` 明确断言 `.venv` 和 `dist`
  内凭据命中也整包拒绝；遵守本轮不放宽、删除或跳过已有断言的约束。`SECRET`、`PRIVATE_PARTS` 不变。
- P1-2 已实现安全分阶段汇总，最多 50 条，并返回上限和截断标志。元数据阶段每条目报告首项失败；
  此阶段有拒绝则不读取内容。内容阶段同时收集凭据及嵌套归档原因，损坏/解压异常时保留此前原因并停止。
  不声称穷尽未读取内容的问题；修正后需重新预检。确认同样扫描，拒绝时零文件写入。
- 上传/扫描/最终快照限额和签名成功路径不变。被排除内容仍不返回、不持久化。
  `external_evidence/*`、Verifier、Replay/export、REAL_CODEX 和冻结证据不变。

## 本地验收

uv 0.12.5 / Python 3.12.14 / Node 24.18.1。

| 检查 | 结果 |
| --- | --- |
| `uv run --locked ruff check .` | PASS |
| `uv run --locked ruff format --check .` | 908 文件 PASS |
| `uv run --locked mypy src tests scripts` | 470 文件 PASS；新增测试列表类型标注修正后通过 |
| `uv run --locked pytest -q tests/test_code_snapshots.py` | 97 PASS；原88不改，追加9个用例 |
| `npm run test` | 22 文件 / 280 测试 PASS；追加2个用例 |
| `npm run build` | PASS（含 vue-tsc） |
| `npm run type-check` | 独立 vue-tsc PASS |
| 原断言核对 | Python 原模块 AST 前缀一致；前端原文件字节前缀一致 |
| 文档链接 | 最终137个相对链接 PASS |
| 全量 pytest 节点覆盖 | 2258 collected；2244 合格 PASS / 0 failed / 0 skipped；14 最终排除。两段1956+288完整且不交叠；非单次不中断全量运行 |
| `bash scripts/ci_s3.sh /tmp/samescale-pr26-closeout-20261017/offline` | 200 PASS；独立网络 namespace；双 Replay 和五项 golden 摘要不变；外部调用0 |

追加契约覆盖：多文件/同文件凭据及嵌套归档汇总；元数据多原因且禁止内容读取；
50/51/80 条在元数据和内容两个阶段的边界；拒绝预检与确认零文件写入；不回显合成凭据值；
后续损坏保留前项拒绝；UI 上传前警示、多原因及截断提示且无确认入口。

全量使用本轮专用容器 `samescale-pr26-closeout-test-20261017` 的新库 `pr26_closeout_test`，
迁移至 head。测试进程只获得 PATH/HOME/LANG、测试环境和该临时库 URL，没有转发模型凭据。
不接触已有数据库。日志/原始 JUnit 留在 Git 外 `/tmp/samescale-pr26-closeout-20261017/`。

## 精确排除与 NOT_RUN

最终未忽略任何测试模块，精确排除以下14个真实 Agent CLI 用例，不计入通过数。原清单10项漏掉了4项；纠正后保留全部既有断言：

- `tests/test_cli.py::test_harness_codex_doctor_reports_pinned_runtime`
- `tests/test_codex_current_setup.py::test_current_docker_strict_config_and_sandbox_without_provider`
- `tests/test_codex_harness.py::test_codex_runtime_doctor_verifies_pinned_version_and_flags`
- `tests/test_multi_harness.py::test_phase_f_runtime_doctors_verify_pins_flags_and_toolchains[claude]`
- `tests/test_multi_harness.py::test_phase_f_runtime_doctors_verify_pins_flags_and_toolchains[deepseek]`
- `tests/test_phase_f_claude_startup.py::test_pinned_claude_recognizes_hidden_max_turns_flag_keylessly`
- `tests/test_phase_f_claude_startup.py::test_pinned_claude_bare_tool_profile_mismatch_is_reproduced`
- `tests/test_phase_f_claude_startup.py::test_pinned_claude_original_empty_mcp_shape_reproduces_startup_failure`
- `tests/test_phase_f_claude_startup.py::test_pinned_claude_non_bare_profile_denies_ambient_project_config`
- `tests/test_phase_f_deepseek_startup.py::test_pinned_deepseek_profile_completes_against_keyless_local_transport`

- `tests/test_runtime_config_hygiene.py::test_pinned_codex_split_sandbox_executes_with_outer_filesystem_and_seccomp_network`
- `tests/test_runtime_config_hygiene.py::test_pinned_codex_uses_generated_isolated_relay_profile_without_websockets`
- `tests/test_verifier_lifecycle_handoff.py::test_claude_keyless_provider_uses_exact_live_workspace_verifier_handoff`
- `tests/test_verifier_lifecycle_handoff.py::test_claude_keyless_live_handoff_survives_recent_runtime_and_egress_teardown`

首轮沿用旧清单时，两个 `test_runtime_config_hygiene` 的真实 Codex CLI 探测已执行；它们
使用合成凭据、隔离沙箱和本地拒绝代理，没有真实模型/Provider 调用或真实凭据读取。
不能声称本轮真实 CLI 零启动。这两项从最终通过数中剔除；其余12项为 NOT_RUN，
包括尚未执行的两个 Claude CLI + 本地假服务 handoff 用例。

发现遗漏后主动 SIGINT：首轮1958 PASS、10 deselected、退出码2（主动中断，不是全量成功）。
独立重新收集2258个节点，将首轮 JUnit 中的1956个合格通过项、最终14个排除项与剩余288项
按精确节点身份做不交叠分区，补跑288项最终全部 PASS，耗时403.06秒。命令参数超过操作系统 argv 限额的一次补跑启动
在创建 pytest 前失败（0 tests run），随后改为从 JSON 节点清单通过 `pytest.main` 传参。
未额外跳过应跑断言；最终覆盖计数已按分区和两份 JUnit 的实际通过节点核对。
[机器可读计数、14项排除与原始日志摘要](pr26-zip-closeout-20261017.json)。

Windows 浏览器 + WSL2 完整流程、真实模型/Provider/Judge 及新原始 ZIP 的浏览器重验：NOT_RUN。
本轮文案和拒绝展示通过 Vue 组件测试验证，无新增浏览器实测声明。任务绑定、独立验收、合并和部署未执行。
P1-1 的新接受行为及 `CREDENTIAL_PATTERN_IN_EXCLUDED` 未实现，不能记作通过。

## 远端与停止点

准确新 head 与 Fast CI / Offline Regression 结果在推送后交付消息核对；旧 head 的绿色记录不代替本轮结果。
完成 CI 核对后停止，保持 Draft，等待人工审查。

## 本轮改动文件

- `CURRENT_MILESTONE.md`
- `PUBLIC_PRODUCT_CONTRACT.md`
- `docs/CODE_SNAPSHOTS.md`
- `docs/PROJECT_BLUEPRINT.md`
- `docs/qa/pr26-zip-closeout-20261017.md`
- `docs/qa/pr26-zip-closeout-20261017.json`
- `frontend/src/api/codeSnapshots.ts`
- `frontend/src/components/CodeSnapshotPanel.vue`
- `frontend/tests/code-snapshots.spec.ts`
- `src/harnesslab/code_snapshots/service.py`
- `tests/test_code_snapshots.py`
