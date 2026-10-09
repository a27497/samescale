# Workbench Brand v1 同步验收 — 2026-10-09

本轮基于产品最新主线 `98b8f7d605794d4db1939a46be0c25ce877a25e7`，在独立 worktree `/home/dev/.worktrees/samescale-brand-v1`、分支 `codex/workbench-brand-v1-20261009` 完成品牌同步。原 `/home/dev/projects/samescale` 的未提交 UI-2 工作没有被纳入或修改。完成提交和推送供审核；不合并、不部署。

## 改动与来源

权威来源为官网仓库 `a27497/samescale-site` 已发布提交 `73063c5a6f311de61970862d16311cb0e2ada814`。从该提交直接读取 14 个正式资产，未重新绘制，也没有导入字体或探索稿。

| 来源路径（官网 `public/`） | 产品用途 |
| --- | --- |
| `brand/samescale-lockup-cobalt.svg` | 侧栏 E3-F + W1 转曲字标；所有字形仍为正式 SVG 路径 |
| `brand/samescale-symbol-24px-cobalt.svg` | 实际侧栏 Logo 的 24px 图标，覆盖字标原主图标位置，保留专用切割缝隙 |
| `brand/samescale-lockup-cobalt-on-dark.svg` | 同步正式深色背景字标资产；当前产品仍为原有浅色主题 |
| `brand/samescale-symbol-{16,24,32}px-cobalt.svg` 及对应 `-dark.svg` | 同步正式专用尺寸；24px 在产品使用，全部尺寸已验证解码、品牌颜色和透明缝隙 |
| `brand/samescale-symbol-cobalt.svg` 与 `-dark.svg` | 同步正式主 SVG，在 56px 验证；本轮 UI 未引入新的大图标或 33–55px 品牌图标 |
| `favicon.svg`、`favicon.ico`、`favicon-32x32.png`、`apple-touch-icon.png` | 替换旧 Favicon，提供 SVG/PNG/ICO 与 Apple 图标引用 |

每个文件的来源、目标和 SHA-256 见 [资产来源记录](assets.json)。所有 14 个文件均与官网指定提交字节一致，SVG XML 有效、路径非空，无文本字体依赖或脚本。真实浏览器已加载全部资源。

`frontend/src/components/WorkbenchBrand.vue` 保留正式字形与可访问的 SameScale 名称，显式声明图像尺寸，不加载网络字体。共享 App 只替换 Logo 模板及组件导入；原 Logo 链接仍到 `/analyst`，导航结构、路由和交互函数不变。

`frontend/src/styles.css` 将主按钮、导航选中和焦点适配为 `#4263D5`；保留 `#5579ED` 深色背景品牌 token。页面布局、业务色、图表、证据内容及页面级样式不变。PASS/FAIL/NOT_VERIFIED 的状态组件无修改；五条 good/bad/warn/neutral/failure 色规则与主线一致。

`frontend/index.html` 使用当前 AI Coding Evaluation & Diagnosis Workbench 产品元数据，并添加 application-name、匹配现有白色页面背景的 theme-color 和图标回退。路由级动态标题及中英文切换保持原行为。

## 检查结果

- `npm ci` 使用既有 lockfile，未新增或升级依赖。
- `npm run test --prefix frontend`：**134/134 PASS，12 文件**，包括原有三态独立验收、Demo integrity 与重试回归。
- `npm run build --prefix frontend -- --outDir /tmp/samescale-workbench-brand-v1/brand-dist --emptyOutDir`：**vue-tsc + Vite 构建 PASS**。
- 静态检查使用官网项目中固定版本的 web-design-guidelines，新增组件的名称、图像尺寸、可见焦点、图标语义与元数据无新增问题。
- Chromium 真实生产构建：主线与候选双预览，五个主要页面覆盖 **320/390/768/1440px**，两种语言覆盖五页。正文几何、文本哈希、导航目的地、业务状态颜色一致，所有宽度无横向溢出，正式 24px 字标与图标正常加载且不挤压导航。
- 首轮浏览器矩阵 **196/198**，console/page/request/HTTP 错误均为 **0**。两个失败为验收脚本问题：关闭的 details 子链接虽有 client rects，但不是有效焦点；设置页断言未等待路由切换完成。
- 在主线与候选上修正检查方法，导航定向复验 **20/20 PASS**，覆盖 320/390/768px 双向焦点循环、导航打开/关闭、Demo 跳转以及桌面设置页。原两个失败均被明确复验替代；没有改动产品导航代码。保留首轮记录，不将其改写为 198/198。
- SVG Favicon 浅色与深色媒体渲染分别为 Cobalt / `#5579ED`；16/24/32px 像素缝隙透明，56px 使用主 SVG。所有 14 个资源 HTTP 200。
- 人工检查下列八张截图，字标清晰、页面保留现有结构，失败/未知/不可比状态仍独立表达。
- 原工作区 **17 个未提交文件及完整 diff**、**639 个后端/冻结证据等受保护文件**均未变；实际 Demo 身份与 manifest 完全一致，完整性门禁仍 ready。官网工作区干净；未生成或替换服务默认 `frontend/dist`。

[总验收记录](acceptance.json) · [首轮浏览器记录](browser-initial.json) · [导航复验](navigation-followup.json) · [保护核验](integrity.json)

## 截图

| 页面/宽度 | 实际截图 |
| --- | --- |
| 移动导航 320px | [320px](home-320-navigation.png) |
| 移动导航 390px | [390px](home-390-navigation.png) |
| 移动导航 768px | [768px](home-768-navigation.png) |
| 调查首页 1440px | [Home](home-1440.png) |
| 运行证据 1440px | [Run Detail](run-1440.png) |
| 失败诊断 1440px | [Diagnosis](diagnosis-1440.png) |
| 候选对比 1440px | [Regression](regression-1440.png) |
| 只读公开演示 1440px | [Public Demo](demo-1440.png) |

## 复验与边界

构建/预览均隔离在 `/tmp/samescale-workbench-brand-v1`。5190 为原主线构建，5191 为品牌候选构建，API 代理既有本地 8000 服务；预览拒绝写请求，唯一允许的 POST 为只读的已保存证据比较。浏览器也限制同源与上述只读请求，不允许模型/Agent/Provider 执行。预览启动脚本 [preview.mjs](preview.mjs) 使用已有 Vite 和隔离的 baseline-dist / brand-dist；脚本 [browser-acceptance.js](browser-acceptance.js) 和 [navigation-followup.js](navigation-followup.js) 可通过项目 playwright-cli 执行；前者保留同一覆盖矩阵并已校正两个断言。

未覆盖 Safari/Firefox、真实移动设备、原生浏览器 Favicon 缓存、Apple 安装、完整读屏和私有会话持久化；深色仅验证正式资产，不宣称产品新增深色主题。此次未运行后端完整测试或新的真实模型调用，未改动核心业务逻辑、冻结 Demo、历史证据或摘要。

`npm ci` 报告既有依赖 **6 项 high-severity advisories**；本轮没有扩展为依赖修复。远端 Actions 结果须按推送 SHA 单独报告，本地测试与浏览器通过不等同于 CI PASS。

下一步：审核品牌同步分支；不合并 main、不部署。STOP。
