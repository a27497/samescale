# 网页 ZIP 源码快照验证 — 2026-10-16（Asia/Shanghai）

基线经 fetch 和再次远端检查为 main `ffcf0876d4ec9e0ce4aa843bc7b87fbf847ad292`。
独立 worktree `/home/dev/.worktrees/samescale-code-snapshot-zip-20261016`，分支
`codex/code-snapshot-zip-20261016`。原有脏工作区和旧数据库未改动。仅 Draft PR，不合并、不部署。

## 两个真实附件

| 样本 | ZIP 字节 | 源文件 / 条目 | 纳入 | 排除 | 整包拒绝 | 结果 |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| MiniShop_source_only.zip | 81,554 | 32 / 32 | 32 | 0 | 0 | 确认保存；逐文件与源码树摘要均独立核对 |
| MiniShop.zip | 13,839,456 | 2,282 / 2,611 | 0 | 0 | 1 | HTTP 413 / ZIP_UPLOAD_LIMIT；未创建快照 |

精简版源码 237,995 字节。原始归档 SHA256：
`sha256:b81d13eb30ddc217a33236447b382f3ae98e4376932a8a93be8e0e7a392082b6`。
源码 content_digest：
`sha256:2665fbe6ae797a8c075cb92894610fded920f0ebcbf63fadb39ef567661eb143`。
详情实测为 `NOT_ATTESTED / NO_RUN_RECORD / NOT_VERIFIED`，明确未绑定任务和后续可信任务条件。

原始版归档 SHA256：
`sha256:f67a40d7a76accde120a959e87b07c3a8e171730a6babb06ab83d178cada4076`。
独立 ZIP 元数据统计解压字节 38,048,630。归档本身超过 8,000,000 上传上限，
服务端在消费请求体前拒绝；没有进入内容扫描，没有排除或静默保存子集。
这里的文件数/条目数来自独立元数据计数，不声称服务端完成内容审查。

浏览器实测环境为 Linux GCP + headless Google Chrome 153.0.8010.52，直接连接真实
loopback API 和生产构建。经过输入操作员凭据、选择真实 ZIP、查看完整预检、确认按钮
在勾选前禁用、勾选保存、访问详情、刷新并重新输入凭据读取，再选择原始版看到整包拒绝。
原始版拒绝前后存储目录内容相同。无浏览器脚本异常；页面继承现有字体和白色 panel。

[精简版浏览器记录](code-snapshot-zip-20261016/source-browser.json)、
[原始版浏览器记录](code-snapshot-zip-20261016/original-browser.json)、
[独立逐文件清单](code-snapshot-zip-20261016/minishop-independent-manifest.json)。
独立计算脚本仅使用标准库 ZIP 读取和 hashlib，不调用产品 content_digest 或执行附件内容；
浏览器额外从保存的 Base64 解码内容，用 Node crypto 再核对逐文件摘要和源码树摘要。
原 ZIP 和源码内容不提交 Git，实测产物留在
`/home/dev/.local/state/samescale-code-snapshot-20261016`。

## 本地检查

uv 实际版本 0.12.5，Python 3.12.14，Node 24.18.1，Java 21。

- `uv run --locked ruff check .`：PASS。
- `uv run --locked ruff format --check .`：906 文件 PASS。
- `uv run --locked mypy src tests scripts`：470 文件 PASS。
- `uv run --locked pytest -q tests/test_code_snapshots.py`：88 collected / 88 passed / 0 failed / 0 skipped / 0 deselected。
- 历史 ExternalRecord / P1 / generic、local-init 和 CI inventory 最终检查：141 collected / 141 passed / 0 failed / 0 skipped / 0 deselected。
- Release、CI inventory 和新 ZIP 契约联合检查：125 collected / 125 passed / 0 failed / 0 skipped / 0 deselected。
- `npm run test`：22 文件、278 测试 PASS。
- `npm run build`：PASS；包含 `vue-tsc --noEmit`。另执行的 `npm run type-check` 也 PASS。
- `bash scripts/ci_s3.sh /home/dev/.local/state/samescale-code-snapshot-20261016/offline-publication`：191 collected / 191 passed / 0 failed / 0 skipped / 0 deselected，独立网络 namespace，双 Replay 与原五项 golden 摘要逐字节一致；外部/Provider/模型/Judge/Agent/Verifier 调用 0。

[Offline 本地收据](code-snapshot-zip-20261016/offline-local.json)。
新测试同时用 process/HTTP transport 和具名 Agent/Provider/Verifier 边界的拒绝哨兵，
导入、读取和确认均无法调用它们。兼容测试核对导入前后原记录身份、导出字节、Replay、
非空 synthetic NOT_VERIFIED 独立收据和记录目录全部字节；不将 synthetic 收据说成实际验收。
现有真实历史 hook 兼容测试和 frozen-evidence guard 继续保留。

完整 pytest 最终回归仍在独立 disposable PostgreSQL 数据库中运行。使用精确 deselect，
无整个模块忽略，保留原有 pure argv/绑定测试；下列 9 个 selectors 对应 10 个实际 CLI 用例
不执行，也不计入通过数。之前的进行中全量运行因最终守卫修正和精确排除登记而中止，
保留日志但不作为完整通过证据。最终命令与计数在回归结束后登记。

```bash
uv run --locked pytest -q \
  --deselect=tests/test_phase_f_claude_startup.py::test_pinned_claude_recognizes_hidden_max_turns_flag_keylessly \
  --deselect=tests/test_phase_f_claude_startup.py::test_pinned_claude_bare_tool_profile_mismatch_is_reproduced \
  --deselect=tests/test_phase_f_claude_startup.py::test_pinned_claude_original_empty_mcp_shape_reproduces_startup_failure \
  --deselect=tests/test_phase_f_claude_startup.py::test_pinned_claude_non_bare_profile_denies_ambient_project_config \
  --deselect=tests/test_phase_f_deepseek_startup.py::test_pinned_deepseek_profile_completes_against_keyless_local_transport \
  --deselect=tests/test_codex_current_setup.py::test_current_docker_strict_config_and_sandbox_without_provider \
  --deselect=tests/test_codex_harness.py::test_codex_runtime_doctor_verifies_pinned_version_and_flags \
  --deselect=tests/test_multi_harness.py::test_phase_f_runtime_doctors_verify_pins_flags_and_toolchains \
  --deselect=tests/test_cli.py::test_harness_codex_doctor_reports_pinned_runtime \
  --junitxml=/home/dev/.local/state/samescale-code-snapshot-20261016/full-final.xml
```

进程仅传入 PATH、LANG、测试环境和新数据库 URL，未传入模型凭据。数据库为本次新建
容器 `samescale-code-snapshot-test-20261016` 中新建的 `snapshot_final_test`，迁移到 head；
没有覆盖已有业务、历史或 demo 数据。最终 [实际排除节点清单](code-snapshot-zip-20261016/pytest-exclusions.json)。

## 负面契约覆盖

`tests/test_code_snapshots.py` 覆盖 ../、绝对、盘符/反斜杠、NUL、私密目录及 .env*，
重复/大小写/NFC/文件目录冲突，symlink/Unix 与 DOS 特殊属性、加密、嵌套归档、损坏、
CRC/本地头/完整 deflate 流伪造、上传/扫描/最终文件数与解压大小限额、zip bomb 比例、
非 UTF-8/二进制（含可 UTF-8 解码的二进制）、被排除文件中的凭据，无/错误口令、
错误/无 Origin、跨站 sec-fetch-site、非 loopback Host、公开 Demo 拒绝、其他路由非 JSON
拒绝及查询参数不能覆盖 JSON 守卫，超大/错误 Content-Length、无长度超限、断开和超时，
无明确确认、归档/清单/签名/工具不匹配、并发幂等且 inode 不重写、原子提交异常后的暂存
清理、受保护根重叠拒绝、快照篡改拒读，以及上传阶段禁止全部执行边界。

2,282 条目的可排除子集另有明确标为 synthetic 的扫描包络测试；它不替代真实原始版。

## NOT_RUN 与停止范围

- Windows 浏览器 + WSL2 后端完整流程：NOT_RUN，当前执行主机是 Linux GCP。Linux 浏览器结果不替代此项。
- 原始版内容扫描/子集确认保存：NOT_RUN（预期在上传限额先拒绝）；整包上传拒绝与不写入已实测。
- 精确排除的 10 个真实 Agent CLI 启动/探测用例：NOT_RUN，不计入通过数。
- 任务绑定、独立验收、Agent、付费模型、合并、部署：本轮范围外，未执行。

Draft PR 和准确 head 的 Fast CI / Offline Regression 链接在发布后补充。
