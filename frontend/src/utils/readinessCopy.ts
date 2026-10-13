// Exact presentation translations of saved readiness guidance. Unknown source text stays in details.
export function readinessEvidence(text: string): string {
  const exact: Record<string, string> = {
    'Frozen profiles bound to the accepted V6 ExperimentPlan': '冻结模型配置已绑定到已验收的 V6 实验计划。',
    'Accepted V6: 7 cells and 630 slots; DeepSeek Harness E1 is outside Core scope and REAL_DEEPSEEK_SMOKE remains DEFERRED_NOT_VERIFIED': '已验收 V6 包含 7 个配置组合、630 个运行单元。DeepSeek Harness E1 不在核心范围内，其真实烟测已延期且尚未验证。',
    'REAL_MATRIX_EVIDENCE=VERIFIED': '真实矩阵证据已核验。',
    'Frozen release snapshot: REAL_JUDGE_SMOKE=VERIFIED': '冻结发布快照保存了已核验的真实 Judge 烟测证据；它不代表当前工作区已运行校准。',
    '82/90 complete, all PARTIALLY_COMPARABLE; formal eligibility false; no Harness uplift.': '90 对中有 82 对完成，均为部分可比；未达到正式比较条件，不能声明 Harness 增益。',
    'Integrity VERIFIED; 83/90 complete, 42 COMPARABLE, 41 NOT_COMPARABLE; formal eligibility false; causal reasoning-effort claims forbidden.': '完整性已核验；90 对中有 83 对完成，其中 42 对可比、41 对不可比。未达到正式比较条件，不能对推理强度作因果归因。',
    'Approved bounded Analyst source and Gate J evidence mapping': '已批准范围受限的调查来源与对应验收证据。',
    'Core document set is checked from repository source': '已根据仓库源码检查核心文档集。',
    'Three verifier-backed V6 BadCases frozen with checked source bindings; final release remains gated': '已冻结 3 个有独立验收支持的 V6 失败案例，并检查来源绑定；最终发布仍需满足其余条件。',
    'Strict release contract loaded; CORE_RELEASE_READY=FALSE': '发布约定已读取，最终发布条件尚未满足。请检查下方待解决项。',
    'Final exact-head CI binding is not yet in release evidence': '发布证据尚未绑定最终提交的远端 CI 结果。需补充与准确提交对应的 CI 记录。',
    'Tag creation is refused until final release verification passes': '最终发布核验通过前不能创建版本标签。先完成发布证据检查。',
  }
  if (Object.hasOwn(exact, text)) return exact[text]
  const corpus = /^(\d+) digest-bound task identities; Core requirement is (\d+)-(\d+)$/.exec(text)
  if (corpus) return `已登记 ${corpus[1]} 个绑定摘要的任务；核心要求为 ${corpus[2]} 至 ${corpus[3]} 个。`
  const calibration = /^(\d+) integrity-validated completed calibrations of (\d+) completed records$/.exec(text)
  if (calibration) return `${calibration[2]} 个已结束校准记录中，${calibration[1]} 个通过完整性检查。暂无合格记录时，请先检查或接入校准报告。`
  return '此项尚无对应的中文证据摘要。可展开查看原始记录；以所列状态和来源为准。'
}
