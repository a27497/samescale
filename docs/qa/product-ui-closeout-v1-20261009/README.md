# SameScale 第一轮产品 UI/UX 收口 · 本地验收

基线：`314fe71c4fc6d08c31b8a7b490435deaa1917be4`。独立工作区
`/home/dev/.worktrees/samescale-ui-closeout-v1-20261009`，分支
`codex/product-ui-closeout-v1-20261009`。远端 main 通过只读查询核对为此基线；本地旧跟踪
引用不做更新。所有修改未提交，等待人工视觉确认；未推送、合并或正式部署。

[打开前后截图对照](/home/dev/.codex/visualizations/2026/10/09/samescale-ui-closeout-v1/review.html)
· [本地隔离预览](http://127.0.0.1:15921/demo)

## 改动与证据边界

| 页面 | 改动 | 仍可查的原始信息 |
| --- | --- | --- |
| Analyst | 提高正文可读性；来源标签统一；Historical Real 不再使用 Fake 专属提示 | 报告原文、metadata、摘要绑定与引用目录 |
| Demo | 保留五步导览，压缩重复说明；不可比时明确暂不判断方向 | Manifest、运行身份、声明、验收摘要、完整来源限制 |
| Run Detail | 保留双栏；运行状态单独标注；失败提示依据保存结果，不猜测 Agent 文本语义 | Agent 原文、验收摘要、Trace 事件、身份、用量和安全 JSON |
| Diagnosis | 任务结论与 Verifier 进程分别标注；工作区、事件和调用计数改为易读描述 | 原始事实、假设、聚类维度、process/score、引用和原文 JSON |
| Regression | 中文可比性约束；不可比／部分可比不呈现更优方向；重要数值放大 | 共同任务及全量原始值、配对值、后端方向与差值记录 |
| Experiments | 列表筛选、详情四个章节、表头、空态／错误态和状态中文化；表格与图表间距修正 | 原实验／模型／任务名称、IDs、摘要、机器状态和数值 |

中文正文以 15px、表格以 14px 为主，技术身份最低 12px；状态以中文标签显示，机器码
通过 native title、键盘聚焦（显示 code）、辅助技术标签及原始证据入口追溯。未知码原样
保留。`completed`／`succeeded` 表示运行／进程结束，保持中性色；任务通过仍依赖任务结果。

`FILE_CHANGE` 是 Trace 事件；最终工作区模式来自任务前后保存内容的对照。`DIGEST_ONLY`
不显示“零条修改路径”，避免将未提供路径误写成零修改。未报告分数／用量不转成零或通过。

中文解释仅用于核对过的 code/enum 和完全匹配的后端固定指导语。自由文本不做猜测翻译。
历史 Real 报告、原始事实、Agent 消息和独立验收摘要均未改写。摘要一致性不认证来源。

## 验证结果

| 检查 | 实际结果 |
| --- | --- |
| `npm run test --prefix frontend` | 142/142 PASS，13 文件 |
| `npm run type-check --prefix frontend` | PASS；最终 build 也再次执行 Vue 类型检查 |
| `npm run build --prefix frontend -- --outDir /home/dev/.local/state/samescale-ui-closeout-v1-20261009/after-dist` | PASS，构建目录独立于运行服务 |
| 真实 Chromium `153.0.8010.52` 主矩阵 | 163/163 PASS，1366px / 1440px |
| 最终表宽／数值字号／详情对齐／矩阵间距复查 | 16/16 PASS，1366px / 1440px |
| Git diff 范围、空白检查 | PASS；后端、依赖与冻结证据目录无差异 |
| 原 UI-2 保护 | 1494 文件内容、dirty 状态和完整 diff 相同 |
| 既有隔离 QA DB | 23 表 / 17 行，与 before snapshot 相同 |
| 源 API 对照 | Demo、Run、Trace、Diagnosis、Historical Real 的 baseline/candidate 响应相同 |

主矩阵覆盖五个核心页面、Experiments 列表和详情四标签、历史 Real／离线 Fake 报告的
两个桌面宽度；补充七页英文 smoke、机器码键盘读取、引用定位与返回、JSON 下载、公开
产物入口，以及浏览器内明确标记的不可比／部分可比 direction=IMPROVED、任务通过／
未验证响应注入。注入只用于界面验证，没有改动后端或保存证据。

正常路径记录 0 runtime / console / HTTP / external-request 错误；主矩阵各页无横向页面溢出，
未发现低于 12px 的可见 DOM 文字。图表轴／标注明确设为 12px 并做截图检查；不把 canvas
文字算入 DOM 字号扫描。最终列表表头不会逐字换行，主要对比数值为 14px。

[主矩阵记录](browser-results.json) · [最终定向复查](browser-followup.json) ·
[长报告截图核对](capture-normalization.json) · [工作区保护记录](protection.json) ·
[前端源码与测试摘要](source-hashes.json)。

截图使用既有临时 QA 的 `public-demo-20261009-b13ae8d9b801`，清单为
`sha256:cd96bbc1274fe1dea7815ca85d619d27fec4559a1255d46cc458af7d5318a0af`。
此实例与生产 Demo 是不同的已有证据范围；本轮未创建或替换 Demo 身份。该离线样例实际
展示 task fail、Verifier process succeeded、最终工作区无修改以及 NOT_COMPARABLE 0/6；
其原始全量通过率 0.50 / 1.00 保留，不得据此判定候选更优。

首次前端运行 121/134，失败项为旧英文／文案／按钮样式断言；更新断言时仍保留语义与
安全投影检查，并新增 8 项有界契约测试。中间 139/140 为一条旧边界文案断言，已修正。
最终 142/142 通过。首次 browser harness 使用了不在工具沙箱中的 URL 全局对象，未完成；
改用已有可用解析方式后主矩阵通过。定向复查首次因隔离预览进程已退出而未完成，
确认专用端口空闲后重新启动本轮预览，再完成 16/16。原运行服务未重启或覆盖。
首次长报告截图处于自动滚动后的 fixed/sticky 位置；最终前后长报告均从 scrollY=0 拍摄，
保留真实焦点状态。初始日志保留在本轮本地 state 中，没有把未完成检查计作通过。

## 同视口截图

截图为原始 Chromium PNG，18 张基线、24 张候选。下表链接 1440px；对照页同时提供
1366px。详情概览／矩阵／统计另有两种宽度的候选截图。正常截图不使用响应注入。

| 页面 | 改版前 | 改版后 |
| --- | --- | --- |
| Analyst | [截图](/home/dev/.codex/visualizations/2026/10/09/samescale-ui-closeout-v1/before-analyst-1440.png) | [截图](/home/dev/.codex/visualizations/2026/10/09/samescale-ui-closeout-v1/after-analyst-1440.png) |
| Demo | [截图](/home/dev/.codex/visualizations/2026/10/09/samescale-ui-closeout-v1/before-demo-1440.png) | [截图](/home/dev/.codex/visualizations/2026/10/09/samescale-ui-closeout-v1/after-demo-1440.png) |
| Run Detail | [截图](/home/dev/.codex/visualizations/2026/10/09/samescale-ui-closeout-v1/before-run-1440.png) | [截图](/home/dev/.codex/visualizations/2026/10/09/samescale-ui-closeout-v1/after-run-1440.png) |
| Diagnosis | [截图](/home/dev/.codex/visualizations/2026/10/09/samescale-ui-closeout-v1/before-diagnosis-1440.png) | [截图](/home/dev/.codex/visualizations/2026/10/09/samescale-ui-closeout-v1/after-diagnosis-1440.png) |
| Regression | [截图](/home/dev/.codex/visualizations/2026/10/09/samescale-ui-closeout-v1/before-regression-1440.png) | [截图](/home/dev/.codex/visualizations/2026/10/09/samescale-ui-closeout-v1/after-regression-1440.png) |
| Experiments 列表 | [截图](/home/dev/.codex/visualizations/2026/10/09/samescale-ui-closeout-v1/before-experiments-1440.png) | [截图](/home/dev/.codex/visualizations/2026/10/09/samescale-ui-closeout-v1/after-experiments-1440.png) |
| Experiments 运行详情 | [截图](/home/dev/.codex/visualizations/2026/10/09/samescale-ui-closeout-v1/before-experiment-1440.png) | [截图](/home/dev/.codex/visualizations/2026/10/09/samescale-ui-closeout-v1/after-experiment-1440.png) |
| Historical Real | [截图](/home/dev/.codex/visualizations/2026/10/09/samescale-ui-closeout-v1/before-historical-1440.png) | [截图](/home/dev/.codex/visualizations/2026/10/09/samescale-ui-closeout-v1/after-historical-1440.png) |
| Offline Fake | [截图](/home/dev/.codex/visualizations/2026/10/09/samescale-ui-closeout-v1/before-offline-1440.png) | [截图](/home/dev/.codex/visualizations/2026/10/09/samescale-ui-closeout-v1/after-offline-1440.png) |

## 未修复与未覆盖

- 原历史 QA 产物仍未恢复，原始完整性失败身份保持不变；这是本轮不修改的证据问题。
- 来源未核验、观察模型／资源约束／用量等缺失项保持未知；UI 不补造数据或修改可比结论。
- 英文证据原文、工具字段、原始任务／模型名称和未知机器码保留。未进行自由文本整篇翻译。
- 未覆盖移动端、非 Chromium、系统字体差异、完整屏幕阅读器认证及真实用户理解度。
- Demo 详情使用 GENERAL 既有报告；复杂 MODEL_COMPARISON 的统计布局通过前端已有
  数据契约测试覆盖，未在浏览器中跑新的此类真实实验。
- 私有会话持久化、真实 Agent／Provider 执行、生产网络和远端 CI 不属于本轮验收。

技术验收完成，人工视觉验收仍待确认。本轮 STOP，不由此启动发布、合并、部署或新阶段。
