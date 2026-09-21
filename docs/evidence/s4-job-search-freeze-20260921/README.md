# Phase S4 — Recruiter Demo + Job-search Freeze：COMPLETE

2026-09-21。**求职冻结 COMPLETE / STOP**。[Final status](final-status.json)。

**S1 PARTIAL REAL BENCHMARK / BLOCKED；S2 / S3 / S4 COMPLETE。**
实现验收 SHA `5bdc03f8addce7532fdfc053c383cb66895e3b3b` 已推送当前 feature branch。
本地统一离线 gate **73 tests PASS**；同一实际 SHA 的
[Offline Regression](https://github.com/a27497/samescale/actions/runs/35645815474) 与
[Fast CI](https://github.com/a27497/samescale/actions/runs/35645815456) 均 **PASS**。
[GitHub receipt](github-receipt.json) 与本地结果完全一致；[JUnit](github-pytest.xml) 回读 73 cases。
[Fast metadata](github-fast-run.json) 与 [core summary](github-fast-summary.txt) 分开保留，不累加重叠测试。
冻结后的文档收口提交不改变实现与分享包；[freeze manifest](freeze-manifest.json) 绑定已验收的文件。

Provider/model/Claude/Judge 新调用 **0**；无 PR、merge main、deploy 或新 benchmark。
**STOP：不规划 S5，不继续开发新功能。**

- [Recruiter Demo](../../recruiter/demo/index.html)：单文件、只读、无外部资源，按七步展示完整证据链。
- [讲解稿](../../RECRUITER_DEMO.md)：4 分钟主路径、3/5 分钟变体与操作者复验命令。
- [面试/简历事实](../../JOB_SEARCH_FREEZE.md)：带限定的工程事实、60 秒介绍、11 个面试追问。
- 复用 S2 reader、S3 frozen anchors 和已保存的 CI receipt；新增公开字段投影，未增加运行时/API/UI 框架。
- [8 tests](pytest.txt) PASS；[browser acceptance](browser-acceptance.json)：1360×900、390×844，
  各 7 anchors、3 details、刷新、键盘 skip link、无全局横向溢出、0 HTTP requests、0 page errors。
  [桌面预览](preview.png)、[完整桌面](desktop.png)、[手机](mobile.png)；已检查浏览器实际渲染截图。
- [browser check source](browser-check.cjs) 使用已有 Puppeteer/Chromium 工具；不是产品运行依赖。
  可通过 PUPPETEER_MODULE 与 CHROMIUM_EXECUTABLE 指定本地安装；产品 HTML 不需要这些工具。
- 3–5 分钟是演示稿预算；未做外部招聘者理解度实测，不将其标记为用户研究通过。

分享包仅 `docs/recruiter/demo/`，包含 index.html、public-evidence.json、SHA256SUMS。
原始命令、trace、workspaces、内部 endpoint、credential references 不被序列化到分享文件。
source hash 可以支持完整性核对，不单独认证同时被替换的 source/anchor。未公开仓库、未部署网站。

S1 保持 PARTIAL REAL BENCHMARK / BLOCKED，2/16 cells，14 NOT_RUN；Codex recorded 20/20 pass，
Claude timeout / NOT_VERIFIED、verifier NOT_RUN，根因未知。S2/S3 已完成；不支持能力排名或完整 benchmark。
本次新增 Provider/model/Claude/Judge calls=0；无 subject/captured command/verifier 执行。
S4 收口后 STOP，不规划 S5，不继续开发功能。

## 独立提交树验收

从 Git index 独立导出并安装锁定依赖，未加载原工作区 dirty 模块。
[统一入口](local-regression.json) **73 tests PASS**（65 S2/S3 + 8 S4），
[pytest](combined-pytest.txt)、[JUnit](combined-pytest.xml)、[Ruff](ruff.txt)、
[format](format.txt)、[mypy](mypy.txt) PASS。此数字不与重复执行的测试数量累加。
Demo 中的 65 是保存的 S3 CI 验收快照，不冒充本次 73 项或实时 GitHub 状态。
[保全检查](preservation.json)：3258 个起始文件中，3257 原内容不变；唯一行为改动为
既有 CI runner 追加 S4 tests/mandatory families，四个已有文档只追加 S4 区块。历史 evidence 原件未改。
