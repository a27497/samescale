# MiniShop 工程收口验收 — 2026-10-18（Asia/Shanghai）

范围：首次真实结果复核/公开案例、私有 1.2.0 独立资格、README 和官网展示。
主分支基于未合并 PR #30 的准确 head `68fd2f1d4bef57b44c25e50f6fddbe6174c40b45`，
官网独立 worktree 基于 main `a79801a`。两个原工作区及其他 worktree 保留，未改 PR #29/#30。

| 检查 | 实际结果 |
| --- | --- |
| [新私有资格](minishop-verifier-1.2.0-20261018.md) | 17 次独立合成运行符合预期；baseline×3 FAIL，oracle×3 PASS，双合法策略及全部缺陷控制检出；新 TaskStore 资格可规划 |
| 原件完整性 | 合并本轮及历史清单，3,585 个条目（3,583 文件 + 两个原 worktree diff）逐项相同；含 32 文件快照、原 R、旧版本/资格、收据/标记/导出/Replay/原报告 |
| 静态边界 | 其他检查体/套件设置 AST 不变；真实 MiniShop 摘要未加入新注册表；核心、依赖、预算未改 |
| 公开投影 | 历史 24/26、两个 AssertionError 与原件相符；投影 SHA 和来源关联核对通过；原报告副本字节相同 |
| 泄漏检查 | 允许文件清单 + 手工阅读；私有源码标记、常见 token/key/私钥模式零匹配；无原始 export/隐藏源码/Oracle 入 Git |
| 相关测试 | `tests/test_custom_task_qualification.py` + `tests/test_ci_routing.py`：29 PASS |
| 既有网络隔离回归 | `scripts/ci_s3.sh`：245 PASS，两次旧代表证据 Replay 的五个输出相同，外部/模型/Provider 调用 0；未执行 subject 或 Verifier |
| 官网锁定安装与构建 | `npm ci`、`npm run build` PASS（既有 tsc，不宣称完整 Vue 模板类型验证） |
| 官网浏览器 | 系统 Chrome，320/390/768/1440px 共 66/66 检查 PASS；无溢出、控制台/运行时/失败请求，链接焦点与触摸高度通过；390/1440px 截图逐屏目视复核 |
| 真实 MiniShop 执行 | **0 次**；无原自测、verify-workspace、真实快照资格或外部 Agent 调用 |

首次独立报告的 26 项不是本轮测试计数；245 项回归使用既有代表证据，也不是 MiniShop 新分数。
官网浏览器检查不覆盖 MiniShop 应用。静态规范复核：新 Vue 组件语义标题、真实链接、焦点可见、
状态文字/颜色、响应式与触摸目标均通过，无新增动效/表单/依赖。

## 完整失败记录

1. 准备复制旧只读私有包后写入触发 PermissionError，物理执行 0；保留副本后修正新副本权限。
2. 离线回归首次借用旧环境，缺 `jsonschema` 导致收集失败（FAIL_CLOSED，不能记 PASS）。
   在独立 worktree 按当前 lockfile 安装新 `.venv` 后，使用新输出目录重跑取得 245 PASS。
3. 浏览器默认 Chromium 未安装，启动失败；使用已安装系统 Chrome 完成全部检查，未升级依赖。
4. 元素整块截图使固定页头出现在长图中部；保留该截图，补充真实 viewport 上/中/下截图验读。
   正常 viewport 无同类遮挡，此为采集方式限制，没有修改页面来隐藏问题。

所有准备失败、试次原始收据、校准源码、回归日志、浏览器脚本/截图及冻结清单保留在
Git 外本轮私有 state 目录 `samescale-minishop-closeout-20261018`。公开只提供结果和摘要。
未运行：全库后端/前端测试、真实设备、非 Chromium 浏览器、屏幕阅读器、MiniShop 新验收。
没有业务数据库使用或生产服务更改；资格在各自可销毁容器/临时数据库，官网独立 loopback 预览。

后续只提交两个独立 Draft PR 并核对其准确远端 SHA/CI；CI 与本地结果分开汇报。
完成后 STOP，等待审查，不合并、不部署、不追加真实验收。
