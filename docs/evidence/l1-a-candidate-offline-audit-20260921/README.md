# A Candidate：超时后独立离线审计（2026-09-21）

**保存工作区存在可复现的 A3/A4 功能缺陷；A7 因两页共享语言缺陷整体未通过。**
本记录是 post-timeout offline audit，证明保存代码的行为，不是原 Episode 的正式成绩。
原真实 attempt 仍为 **NOT_VERIFIED**，其 verifier **NOT_RUN / 0 checks**；未回填结果、重试或恢复。
71/75 只表示检查结果，不是工程完成百分比，也不是 Candidate 正式运行成绩。

## 原运行与离线审计分层

| 证据层 | 可确认事实 | 不能外推 |
| --- | --- | --- |
| [原真实 attempt](../l1-a-candidate-real-20260921/README.md) | Subject 上限 600 秒，实际 601.037 秒；保存 5 个修改；verifier 未运行；usage UNKNOWN；request ID / HTTP status 未记录 | 模型、中转、Provider 根因；正式验收通过或失败成绩 |
| 冻结 verifier 的独立离线运行 | public 25/25；type-check/build 通过；总检查 71/75、业务断言 68/72；A3 有 4 个失败 | 覆盖全部 BCP47；原 Episode 得到 71/75 |
| 独立补充组件验收 | 12/22 通过，10 个失败；两页 `en-x-demo` 等 private-use 输入变成 `und` | 原冻结 verifier 已包含这些测试；Current 也跑过这些新增测试 |

任务 `lecturelens-embedded-subtitle-language-metadata@1.0.1`，原 slot `A/candidate/1`。
[原冻结请求](../l1-a-candidate-closeout-20260921/execution-request.json) identity
`sha256:e6f94974c63b8ecfaca982c9c230d3a0a859089b56e1310e0baa9519b962b61e`。
authorization `3ce7b6074a1e4a5396ade94519c44824`、execution `a4869bcecb1148debd84bed5f7259d20`
均已消费，不得复用。离线审计不产生新的真实 attempt 或执行许可。

审计从冻结任务副本叠加 5 个保存文件，所得 99 个文件与原 output snapshot 字节一致；
固定镜像、断网容器内验收，Candidate 代码未改，240 个原始 evidence/task 文件复核未变。
详见原样复制的 [审计记录](source-audit-README.md)、[结果](result.json)、
[保护核对](preservation.json) 与 [来源绑定](provenance.json)。
本次稳定化仅复制记录和核对摘要，没有重新执行 public/type/build/verifier/Subject/Provider/model/Judge。

## 功能失败与环境失败

- **Candidate A3 缺陷**：两页均保留 `sl-rozaj-rozaj` 和 `en-u-ca-gregory-u-nu-latn`，
  没有将重复 variant / extension 降为 `und`。DOM 值使测试中的规范化抛出 RangeError；
  这是已收集的 4 个业务断言失败，不是测试启动或依赖失败。
- **Candidate A4 缺陷**：两页对 `en-x-demo`、`de-DE-x-goethe`、`en-US-x-a`、`x-demo`、
  `en-US-u-ca-gregory-x-demo` 都返回 `und`。补充断言挂载真实 Vue 页面与播放器、mock API，
  检查 DOM `srclang` 与保留字幕内容，属于独立验收复现。
- **首次审计基础设施故障**：容器用户不能写入新审计输出目录，
  [原 traceback](verifier-infrastructure-first.stderr) 单独保存。
  首次补充启动还遇到审计父目录 0700 无法遍历；该项来自原审计记录，未留下独立原始 stderr 文件。
  只调整新建临时目录权限后完成重跑；未修改 Candidate 代码或依赖版本。

冻结 verifier 的 [75 项报告](verifier-evidence/report.json)、
[72 个业务断言](verifier-evidence/business-vitest.json)、
[公开测试](verifier-evidence/public-vitest.json) 和 [各阶段退出结果](verifier-evidence/stages.json)
与 [补充测试结果](supplemental-evidence/supplemental-vitest.json) 分开保存。
verifier 进程 exit 0 仅表示成功生成报告，报告 `passed=false` 才是本次离线验收结论。
补充 [测试源码快照](supplemental-contract.test.ts.txt) 和 [执行脚本快照](run-supplement.py.txt)
使用文本后缀保留原始字节，不注入仓库测试发现流程，不改变冻结 verifier。

A1、A2 核心别名/地区/文字用例、A5、A6 在已测范围通过。
切换、刷新、失败、晚到响应和旧字幕/可见语言清理已有两页组件验收支持。
A3/A4 失败；A7 的一致性与生命周期子项通过，但共享语言缺陷使整体未通过。
真实浏览器媒体播放、全部 BCP47 输入和所有异步时序仍未覆盖。
“工程上接近完成”是范围受限的工程判断，不等于验收通过，也不保证延长时间就能成功。

## 比较与诊断边界

[派生诊断](diagnosis.json) 分别记录历史 A Current 和本次 Candidate 的来源与状态。
A Current 历史记录为 RECORDED_PASS、75 项检查；本次 Candidate 是超时 NOT_VERIFIED，
其保存工作区在后续离线审计发现缺陷。可以陈述这些不同层次的事实。
不能将 75/75 与 71/75 当成同条件完整配对成绩，不能声称 Prompt 优化成败、模型能力优劣、
效率/稳定性排名，或 Candidate 必然会通过/失败于另一次真实 attempt。
Current 的 output 7875 超过声明 6000，且未做本次补充验收；比较仍为 INCONCLUSIVE，L1 未完成。

本案例新增的诊断闭环是：保留超时原件 → 按身份重建保存工作区 → 区分环境故障与功能缺陷
→ 用独立补充验收暴露冻结测试覆盖缺口 → 将结果关联但不回填原 Episode。
这不增加自动修复、自动恢复或新的产品执行能力。

## 只读复核

```sh
python3 docs/evidence/l1-a-candidate-offline-audit-20260921/verify_snapshot.py
```

此脚本仅使用标准库读取仓库内快照，核对摘要、计数、失败用例、99 文件映射和原 Episode 边界；
不读外部开发机路径、不启动容器、不调用模型、不重跑验收。
完整外部副本由 `source-audit-sha256.json` 绑定；`sha256.json` 绑定本目录。
哈希一致性不是来源身份认证；没有完整任务和固定镜像时不能声称重新执行了验收。
