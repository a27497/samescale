# Grok 第二轮复评后的 P0 定向收口 — 2026-10-09

直接继承 `codex/product-ui-closeout-v1-20261009` 两轮未提交成果；HEAD 仍为
`314fe71c4fc6d08c31b8a7b490435deaa1917be4`。白色 / Cobalt、字号及主要信息架构保留。
本轮只修改前端、对应测试和验收文档；网关修正只在工作区外的隔离副本验证。
未提交、push、merge 或部署，等待人工视觉确认后 **STOP**。

## 每项 P0 的处理状态

| 项目 | 状态 | 实现及验证边界 |
| --- | --- | --- |
| 1. 状态语义 | 已修复 | Run、Experiment、Trace 事件及 Verifier 执行使用明确上下文；FILE_CHANGE 的 `completed` 为“事件已结束”。执行结束保持中性色，不推断任务通过。独立任务验收仍读取保存的 verdict。减少重复任务徽标；事件状态、原文及 exit code 可展开 / 复制。 |
| 2. Experiments 统计 | 已修复 | “已收集任务结果 / 计划”与通过、未通过、基础设施失败分开。列表 / 概览共享统计逻辑；已有 `getRuns(outcome=…, limit=1).total` 是跨分页权威总数，必须与 `completed_capability_count` 的和相符。请求失败、计数非法、来源身份 / outcome 不一致或完整性失败时通过 / 未通过显示“未报告”，不从通过率或当前页猜测。真实基线 6/6，3 通过、3 未通过、0 基础设施失败；候选 6/6，6、0、0。 |
| 3. 不可比原始值 | 已修复 | NOT_COMPARABLE / PARTIALLY_COMPARABLE 默认收起“原始描述值与来源（不作优劣或改进判断）”。0.50 / 1.00、原始 direction 与完整 JSON 保留可查。可比条件门禁未放宽；注入 IMPROVED 的不可比响应也不会宣传改进。 |
| 4. 未知 Run | 隔离修正通过，未发布 | HTML `/runs/<安全标识>` 可以进入应用；API 白名单 116 个 method/path 元组完全相同。未知 API 仍是 403，界面明确“拒绝读取，无法确认是否存在”。内部产品真实 404 独立核对；单元与浏览器响应夹具验证 404 文案。没有把权限拒绝改成普通 404，也未放行未知 Run API。 |
| 5. DevTools 六条错误 | 已调查，原始六条未能逐条对应 | 已分别捕获旧隔离预览和实际 HTTPS 的 console / network 日志、触发 URL 与来源。正常主路径无错误；已修复 Run 读取失败后仍多请求 Trace 的项目问题，公共实验列表不再给出新建计划入口。Grok 未提供原始六条文本，不能宣称六个 Bug 已全部修复。权限拒绝仍真实可见。 |
| 6. 预填截断 | 已修复 | 下拉框加载中显示“已预填实验（名称读取中）”；名称不可得时“名称未报告”，不从 ID 尾部猜名称或候选角色。实验列表失败时继续按精确 ID 读取详情；选择值、URL、引用仍为原始身份。 |

同时移除状态徽标多余 tabindex、中英重复 aria-label 及遮挡原文的浮层；原始状态在显式技术详情和完整证据 JSON 中保留。
核心侧栏不再动态插入 Run 项，固定链接高度，1366 / 1440px 导航坐标一致。Run 证据仍由调查链接直接访问。
真实返回保留原始 Run ID、查询参数、深层展开及滚动位置。八列实验表调整列宽，基础设施列完整可见。

## 先核对的数据契约

依据当前源代码而非英文名称推断：

- `src/harnesslab/api/workbench_service.py` 的 `_run_counts` / `_summary`：能力结果为 `capability_pass + capability_fail`，基础设施为 `infra_failure`；两者分开。
- 同文件 `list_runs`：过滤后的数据库 `COUNT` 构成 `total`，与 `limit` / 分页读取无关；前端请求既有 outcome 过滤，没有新增 API。
- `src/harnesslab/diagnosis/projection_service.py` / `src/harnesslab/harness_lane/trace.py`：Trace 事件携带自己的 status / exit code，事件 completed 不等于整次运行状态。
- Run 生命周期、独立验收 verdict、Verifier sandbox 执行状态各自读取对应保存字段；零退出码或 succeeded 进程不代替任务验收。
- Regression 原始描述值、方向和 comparability 保留原响应；有效配对门禁未变，缺失来源不补造。

## 验收结果

| 检查 | 最终结果 | 记录 |
| --- | --- | --- |
| 前端 Vitest | **179/179，15 文件 PASS** | [测试日志](tests-final.log)，增加 20 项定向回归；既有语义测试保留，原码断言改用真实 `data-status` / 技术详情，检查不再依赖已删除的隐藏读屏重复文本 |
| Vue 类型检查与隔离构建 | **PASS** | [构建日志](build-final.log)，`npm run build -- --outDir /home/dev/.local/state/samescale-product-p0-20261009/final-dist` 包含 `vue-tsc --noEmit`；不写现有服务 frontend/dist |
| Chromium 主流程 | **156/156 PASS** | [主记录](browser-results.json)：Chromium 153.0.8010.12，1366 / 1440×960；Demo → Run → Diagnosis → Regression、实验列表 / 概览 / 运行、来源与原文、复制 / 下载、预填加载 / 列表 503、真正 403 与受控 404、可比三态、精确身份与返回；正常路径错误 0 |
| 列宽 / 深层返回 | **10/10 PASS** | [补充记录](browser-extra.json)：八列完整宽度、基础设施列可见、表头低于 80px；展开技术详情后返回，两宽度的 1765px 滚动位置及展开恢复 |
| Analyst 共享回归 | **54/54 PASS** | [记录](analyst-check.json)：两宽度下首页、历史 Real、Offline Fake；旧本地、实际旧 HTTPS、新隔离候选均加载、无溢出且无错误；没有修改旧 HTTPS |
| 隔离网关 / 只读门禁 | **110/110 PASS** | [记录](public-gates.json)：此文件是本轮 **loopback HTTP 隔离副本** 检查，不宣称新公网验收；56 个最终构建文件逐字节核验，保存只读 API、离线计算、拒绝写入 / 私有 API / 非允许标识 / 路径穿越；API 白名单完全未变 |
| 工作区、服务、证据保护 | **PASS** | [保护记录](protection.json)：原 UI-2 1494 文件、dirty status / diff；前两轮 QA；6 个既有容器 ID / 启动时间；旧网关配置、旧 local / HTTPS 构建；数据库 23 表 / 17 行及 Demo / Run / Trace 响应均相同 |

最终 index SHA256：`cca6587dc2cf2f662477fe230db366205dde9c8564d8101663fa82520527e8ae`。
[完整构建及测试源文件哈希](build-manifest.json) 绑定实际浏览器构建。原始 ID、SHA、引用、下载未改写；
现有 FIXTURE_OFFLINE 的 Demo / manifest、12 个运行和 frozen evidence 保持不变。没有 Provider / Agent 执行。

## 实际 console / network 调查

[原始逐路径日志](baseline-errors.json) 同时包含 15931 和实际
`https://twelve-terrorist-campbell-alias.trycloudflare.com`，不是把 localhost 成功当公网检查。
七条主路径 × 两视口 × 两环境均为 0 错误。以下异常为额外明确触发的路径：

| 触发路径 | 环境 / 具体请求 | 观察与处置 |
| --- | --- | --- |
| `/runs/grok-unknown-run` | 原本地：Run GET 403、Trace GET 403，各伴随 `Failed to load resource … 403` | 原页面把不同错误合并提示并重复请求。新产品在 Run 失败后不再请求 Trace，403 保留准确权限语义。 |
| 同上 | 旧 HTTPS：HTML 文档 GET 403 / PUBLIC_DEMO_READ_ONLY | 网关页面白名单导致直接 JSON；隔离副本安全 HTML 路由修正，旧公网未变。 |
| `/connections` | 原本地 local-configuration/status GET 403；旧 HTTPS 另有 registry/harnesses、providers、models GET 403 | 私有配置 / registry 在安全网关外被拒绝，各伴随浏览器资源错误。没有 JS runtime exception，不放宽权限以消除红字；高级配置不属于完整调查主路径。 |
| `/settings` | 旧 HTTPS registry/settings GET 403 | 私有设置的拒绝，保留安全边界。 |
| `/experiments/new` | 旧 HTTPS HTML GET 403 | 非允许的新建路径；公共只读实验列表现在隐藏该入口，私有环境原操作仍保留。 |

网络错误与浏览器同一请求的 console 资源消息分别记录，不能按条数算多个 Bug。
新隔离预览未知 Run 仍产生必要的 API 403；主流程 0 错误指正常已开放路径，不包括故意触发的拒绝和 404 / 503 夹具。
产品内部未知 Run [直接只读后端结果](backend-404.json) 为 404 / NOT_FOUND；该后端内部探测没有扩大网关权限。

## 前后截图及视觉结论

[本地 44 张原始截图对照图库](/home/dev/.codex/visualizations/2026/10/09/samescale-product-p0/index.html)
与 [截图清单](screenshot-inventory.json) 包括两视口的五个核心页面、实验列表 / 概览 / 运行、
FILE_CHANGE、预填加载与未知 Run。左侧来自第二轮旧构建，右侧为 P0 候选。
历史 Real 另有同视口对照；未知 Run 对照明确标注“旧 HTTPS / 新隔离 HTTP”，不混称发布效果。

实际查看前后原图，确认不可比数值不再占据默认报告区；统计区别可读，列表最后一列可见；
FILE_CHANGE 不再错误解释为运行结束，Trace 原文没有状态浮层遮挡；侧栏位置固定，预填过程没有 ID 尾部片段。
Run 和 FILE_CHANGE 截图采用匹配的滚动状态；局部 Trace 使用 viewport 截图避免 Chromium full-page 固定侧栏拼接假象。

## 隔离环境、关闭与限制

人工确认入口：[P0 Demo](http://127.0.0.1:15941/demo)。只绑定 loopback，不新建 HTTPS / 云资源。
沿真实产品前端浏览 Analyst、Demo、Experiments、Run、Diagnosis、Regression；仅允许已保存的公开 FIXTURE_OFFLINE 数据和原有有界只读计算。
完整技术详情可展开、复制、导航与下载。未扩大私有接口、凭据、oracle 或运行权限。
隔离网关源码 [唯一差异](gateway-isolated.patch) 在工作区外；HTML 安全 Run 路径规则在 API 拒绝逻辑之后生效。
上游仍是原隔离只读网关；不修改原公网入口、白名单、Nginx、正式域名、防火墙或数据库。

只关闭本轮预览：`bash /home/dev/.local/state/samescale-product-p0-20261009/stop.sh`。
该脚本只移除 `samescale-product-p0-preview` 及其本轮 bridge；原只读 QA 网络是 external，不会删除，旧服务 / HTTPS 不受影响。
旧 `15931` 与旧 HTTPS 仍是第二轮构建，未发布本轮 P0，公网网关修正等待单独确认。

剩余限制：Grok 原始六条日志未收到；高级私有配置仍会被拒绝；本轮未测试新 P0 公网 TLS，未新增隧道；
没有手机、非 Chromium、完整读屏认证、真实执行或缺失历史产物修复。原运行列表既有 100 记录读取边界未改。
本轮未补造未知字段 / 根因 / 来源认证。正式展示就绪需要人工视觉确认与另行发布授权。

## 验证过程中的修正

初次主浏览器 **154/156**：Diagnosis 运行 DTO 不含 repeat_index，测试以“第 3 次”寻找同一 Run 不正确；
改为核对原始 Run ID / 查询，最终 156/156。代码身份未替换。
视觉检查发现实验表仍用旧六列宽度，新增列被挤出；修正为八列宽度，补充表格内部宽度和最后列可见检查，
防止仅看页面无横向溢出漏报。
深层返回初次 **8/10**：Playwright 点击会先把顶端链接滚入视口再离开，历史正确保存为 0；
改为在底部激活同一原生链接、不自动预滚动，最终返回准确恢复 1765px，未改业务来迎合测试。
初次门禁 **109/110**：Python HTTP handler 将 leading `//api/health` 规范化为已允许的 health，
与旧网关行为一致；修正测试预期，没有扩展私有接口。
初次类型 / 旧测试依赖失败经纠正；最后 179 个测试及类型 / 构建全部通过。
这些初始记录保留，不以失败计数推断对应个数的产品 Bug。
