# L1 诊断补充：A Candidate 超时后的保存工作区

本次 SameScale 案例把“执行未完成”与“保存代码有什么缺陷”分开回答。
[稳定证据与逐项结果](evidence/l1-a-candidate-offline-audit-20260921/README.md)
关联原 attempt、冻结 verifier 的独立运行及补充验收，保留三层身份。

原真实 attempt 在 Subject 上限 600 秒后结束，实际约 601.037 秒；保存 5 个文件，
verifier 未运行，Episode 始终 NOT_VERIFIED。token usage UNKNOWN，request ID / HTTP status 未记录，
模型、中转或 Provider 根因均未建立；一次性 authorization/execution ID 已消费，不得重试或恢复。

后续独立离线审计的 public checks 25/25、type-check/build 通过；冻结 verifier 为 71/75，
其中业务断言 68/72。A3 在两页保留重复 variant/extension 的无效标签；A4 的 `en-x-demo`
等 private-use 标签在独立补充组件验收中被复现为 `und`。A7 因共享语言缺陷整体未通过。
补充验收 12/22 通过；切换、刷新、失败、晚到响应和旧字幕清理的已测行为通过。
首次审计的目录权限故障有独立记录，修复临时环境后才取得完整结果；它不属于 Candidate 功能缺陷。

因此，审计证明的是**保存工作区存在可复现缺陷**。71/75 是检查计数，不能写成工程完成百分比，
不能回填为原 Episode 的正式成绩。“工程上接近完成”不等于验收通过，也不预言另一次执行结果。

历史 A Current 有 75/75 的已记录通过；本次 Candidate 是超时 NOT_VERIFIED，离线保存工作区验收失败。
这些事实可以并列展示，但不能据此作同条件完整配对排名、Prompt 改进成败或模型质量/效率/稳定性判断。
Current 未运行本次补充验收；原比较仍 INCONCLUSIVE，L1 仍未完成。

SameScale 新增的证据是：能保留原失败、重建同一保存工作区、定位具体失败断言，并识别冻结 verifier
未覆盖的 private-use 边界；派生诊断与原 Episode 相互关联而不相互覆盖。未新增运行或自动修复能力。

当前停止点与后续范围由 [CURRENT_MILESTONE](../CURRENT_MILESTONE.md) 维护。
