# SameScale · 3–5 分钟 Recruiter Demo

打开 [冻结 Demo](recruiter/demo/index.html)，或把这个 HTML 单文件发给查看者后用浏览器打开。
无需登录、模型密钥、服务、数据库、Docker 或网络；页面没有外部字体、脚本或自动请求。
GitHub 的文件预览不会运行 HTML，需下载后打开。未部署网站，不要求招聘者获得私有仓库权限。

分享范围为 `docs/recruiter/demo/` 中的 HTML、public-evidence.json 与 SHA256SUMS。
原始 bundle、工作区、trace、凭据、内部 endpoint 和完整仓库不属于分享包。
JSON 是经过字段筛选的公开投影；SHA256SUMS 用于检查文件是否发生变化，不构成来源认证。

## 4 分钟演示脚本

| 时间 | 页面动作 | 可以直接讲的内容 |
| --- | --- | --- |
| 0:00–0:30 | 打开 Task | “SameScale 把 AI 编程运行变成可复核的工程证据。这里是一道真实仓库任务：浏览器 SSE 断流后自动恢复进度，同时防止旧连接覆盖新任务。” |
| 0:30–1:00 | 点 Configurations | “冻结同一个任务、起始 workspace 与 independent verifier。两次正式运行分别用了 Official Codex / gpt-6-astra 和 Claude Code / qwen3.8-max。Claude Code 是运行时名称。模型、provider、CLI、模板不同，所以不是单变量实验。” |
| 1:00–1:35 | 点 Result | “Codex 保存的独立验收是 20/20 verified_pass。Claude 到时限后停止，NOT_VERIFIED，verifier NOT_RUN。exit code 0 不能替代 task success。16 cells 只跑了 2 个；这不是能力排名或完整 benchmark。” |
| 1:35–2:15 | 点 Trace Diff，展开两侧序列 | “Codex 有 13 次工具活动和两个实际文件变更；Claude 有 10 次工具交互，6 次明确 Read，但没有文件变更或 validation command。shell 提到文件不等于读到了文件；事件 ordinal 也不是耗时。” |
| 2:15–2:50 | 点 Diagnosis | “可以确认保存了哪些动作、是否修改、是否验收。不能证明 timeout 来自模型、provider 或 Harness。failure taxonomy 记录 execution_budget_exhausted，根因保持 NOT_ESTABLISHED。原失败与后续 cleanup 分别保留。” |
| 2:50–3:25 | 点 Offline Replay，展开来源 | “用相同 S2 reader 从完整 bundle 重建这些事实；检查摘要、文件集合、native/normalized trace、workspace diff 与 verifier 状态。缺失、篡改、矛盾都拒绝。Replay 不会再次运行模型或 verifier。” |
| 3:25–4:00 | 点 CI | “本地和 GitHub 运行同一个无外部网络入口。65 项离线回归以及实际 pushed SHA 的 CI 记录已保存，五个输出逐字节一致。工程价值是完整性、可诊断性和回归约束；S1 仍 partial/blocked，S2/S3/S4 已完成并冻结。” |

三分钟版本：不展开工具序列和来源，保留 NOT_VERIFIED、partial 与非因果边界。
五分钟版本：展开两侧工具序列与源码摘要，回答一次“为什么 replay 不等于重新执行”的追问。
不把等待完整 CI 放进演示时长；CI 显示的是已验收记录，页面不会实时查询 GitHub。
此时长为讲解预算，不是招聘者理解度实测。

## 操作者复验（演示前执行）

先安装仓库锁定依赖：`uv sync --locked`。随后以下命令均不调用模型：

```bash
# 必须使用一个不存在的新输出目录；校验后才导出公开投影
uv run --locked --offline python -m scripts.export_recruiter_demo \
  --output /tmp/samescale-recruiter-new
# 浏览器直接打开 /tmp/samescale-recruiter-new/index.html

# S3 的既有同一入口；Linux、sudo/unshare/setpriv 与已安装依赖是前提
bash scripts/ci_s3.sh /tmp/samescale-regression-new
```

依赖安装是单独的联网准备步骤。HTML 文件打开不需要安装依赖。
导出器会复用完整 S2 bundle replay，与冻结 golden 比对，再核对已保存的 S3 SHA-bound CI receipt。
若导出失败，先查输入摘要与记录一致性；不要改写 golden 或重新调用模型来“修绿”。
需要 inspect 完整 trace 时由操作者在私有仓库内使用 S2 CLI；不要把原始 bundle 作为 recruiter 分享包。

[面试与简历事实](JOB_SEARCH_FREEZE.md) · [S4 final report](evidence/s4-job-search-freeze-20260921/README.md)
