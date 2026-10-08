# Visual v1 最终审核修复 — 2026-10-08

当前候选版本上的最小修复已完成，本地技术验收通过。**STOP，等待最终人工视觉确认。**

[独立生产预览](http://127.0.0.1:5195/demo)，运行于 loopback 5195；构建仅输出 `/tmp/samescale-visual-v1-final-review/dist`。原默认 frontend/dist 与已有服务未被替换。原 [Visual v1 验收记录](visual-v1-20261008.md) 保留上一候选的观察范围。

## 修改

- `StatusBadge.vue`：`failed_subject` 改为“主体运行失败 / Subject run failed”，保留原始 code、颜色和生命周期含义；高级页面的默认英文标签同步纠正。独立 Verifier 标签与自报标签保持分离。
- `RunDetailView.vue`：诊断按钮仅按 `verifier_passed` 三态选文案。true：“查看实验诊断 / View experiment diagnosis”；false：“查看失败诊断 / View failure diagnosis”；null：“查看诊断记录 / View diagnosis records”。目标实验、候选和运行 query 原样保留。
- `PublicDemoView.vue`：补充证据每次重读先清空上一轮结果，四项请求独立成功／失败更新，失败项无旧数据或替代记录；其他已新读成功项不等待失败项。已失败阶段立即显示不可用，未完成阶段显示加载；重试禁重入、按钮在读取中禁用，过期／卸载后的响应不写入当前界面。
- `visual-v1.spec.ts`：新增 **18 项**针对性测试。覆盖双语生命周期／旧英文标签、Verifier 通过／失败／未验证与成功自报的独立语义、三态按钮和深链接、正常异常恢复、Run／Trace／Diagnosis／Comparison 每项“先成功→重试失败→再次恢复”，以及其他新读成功阶段仍可读。

CSS、App Shell 和其余三页源文件保持当前候选原样；正常状态布局、主题与原始证据文案未调整。仅另外更新本报告、Current Milestone 和 Blueprint 的本轮范围及结果。

## 验证

| 检查 | 结果 |
| --- | --- |
| 全量前端回归 | **134/134 PASS，12 文件**；[日志](/home/dev/.codex/visualizations/2026/10/08/samescale-visual-v1-final-review/tests-final.log) |
| TypeScript + 隔离生产构建 | **PASS**；[日志](/home/dev/.codex/visualizations/2026/10/08/samescale-visual-v1-final-review/build-final.log) |
| 实际保存证据的 Chromium 生产预览检查 | **44/44 PASS，运行错误 0**；[记录](/home/dev/.codex/visualizations/2026/10/08/samescale-visual-v1-final-review/browser-qa.json) |
| 1440px，Run Detail / Demo，中英文 | 4 张正常全页截图，全部无横向溢出，尺寸与上一候选一致；另存 2 张受控异常截图 |
| Git diff 空白、文档本地链接、保护性核验 | PASS；[核验记录](/home/dev/.codex/visualizations/2026/10/08/samescale-visual-v1-final-review/integrity.json) |

运行命令：`npm --prefix frontend test`；`npm --prefix frontend run build -- --outDir /tmp/samescale-visual-v1-final-review/dist`。浏览器脚本 [browser-qa.cjs](/home/dev/.codex/visualizations/2026/10/08/samescale-visual-v1-final-review/browser-qa.cjs) 仅放行 GET/HEAD 与既有只读 compare POST；受控错误仅为浏览器 HTTP 409 响应，没有改变服务端数据。

浏览器实测两种语言下的实际 Run 生命周期／独立失败／按钮、正常 Demo 保存摘要与不可比结果；先注入 Diagnosis 错误，使成功 Trace 可进入补充重试，再延迟并拒绝 Trace。旧 Agent 自报在重读开始即消失，Diagnosis 可先恢复；Trace 失败后，Verifier 和候选对比仍保留各自刚读成功的实际证据；最后解除错误重试恢复真实 Trace 和导出。独立 Verifier 的通过、失败、未验证三态以针对性单元测试验证；正常浏览器截图使用真实保存的失败样例，不改造为通过／未验证证据。

首次新增测试的标签选择器及测试 href 类型检查已修正，初次日志保留；浏览器首次恢复检查只等 Trace 返回便检查仍在加载的导出按钮，已改为等待全部补充读取结束，初次记录保留。最终检查全部通过。

## 1440px 中英文截图

| 页面 | zh-CN | en-US |
| --- | --- | --- |
| Run Detail 正常真实证据 | [中文](/home/dev/.codex/visualizations/2026/10/08/samescale-visual-v1-final-review/run-zh-CN-1440.png) | [English](/home/dev/.codex/visualizations/2026/10/08/samescale-visual-v1-final-review/run-en-US-1440.png) |
| Public Demo 正常真实证据 | [中文](/home/dev/.codex/visualizations/2026/10/08/samescale-visual-v1-final-review/demo-zh-CN-1440.png) | [English](/home/dev/.codex/visualizations/2026/10/08/samescale-visual-v1-final-review/demo-en-US-1440.png) |
| Demo 先成功后失败（受控 Trace HTTP 409） | [中文异常](/home/dev/.codex/visualizations/2026/10/08/samescale-visual-v1-final-review/demo-retry-trace-error-controlled-zh-CN-1440.png) | [English error](/home/dev/.codex/visualizations/2026/10/08/samescale-visual-v1-final-review/demo-retry-trace-error-controlled-en-US-1440.png) |

正常截图来源仍为 `public-demo-20260930-9569db12e23a`，`FIXTURE_OFFLINE`，同一保存 manifest / Run / Trace / Diagnosis；不是实时 Agent／Provider。中文中原始英文摘要与 API 文本保留原样。

## 保护、Git 与剩余风险

[保护核验](/home/dev/.codex/visualizations/2026/10/08/samescale-visual-v1-final-review/integrity.json) 对比本轮开始的原 UI-2 与当前候选文件清单：原 UI-2 全部 **1494 个文件**与 dirty diff 保持不变；当前候选本轮仅改 3 个前端组件／页面、1 个测试文件、3 个范围／验收文档。其余现有候选修改均保留。已保存 Demo / Run / Trace / Diagnosis 与之前的来源投影逐项相同，完整性门禁仍 ready，冻结仓库证据未修改。未改后端、API、schema、依赖、权限或 Demo 数据。

分支仍为 `codex/samescale-visual-v1-20261008`，HEAD `ec14e936a79e88446347dd010f68bd6bde55aaec`，未暂存、提交、推送、合并或部署，未执行真实 Agent/Provider。[最终 Git 状态](/home/dev/.codex/visualizations/2026/10/08/samescale-visual-v1-final-review/git-final.txt)。

没有已知技术阻塞；最终人工视觉确认尚未完成。非 Chromium、真实执行／私有持久化、远端 CI 未运行，本次只报告上述本地验收范围。正常 1440px 截图已人工工具查看，未见标签截断或布局变化；其他桌面宽度沿用上一轮布局证据，未为本次重新截取。

**STOP，等待最终人工视觉确认。**
