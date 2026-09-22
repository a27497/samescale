import { t } from './i18n'
// Display labels only. API values and original evidence remain unchanged.
const labels: Record<string, string> = {
  COMPLETED: '已完成', FAILED: '失败', PAUSED: '已暂停', RUNNING: '运行中', STOPPED: '已停止',
  completed: '已完成', failed: '失败', cancelled: '已取消', queued: '排队中', running: '运行中',
  COMPARABLE: '可比较', NOT_COMPARABLE: '不可比较', PARTIALLY_COMPARABLE: '部分可比较',
  READY: '就绪', READY_WITH_WARNINGS: '就绪 · 有提示', NOT_READY: '未就绪', BLOCKED: '已阻断',
  NOT_RUN: '未运行', NOT_VERIFIED: '未验证', NOT_REPORTED: '未报告', NOT_AVAILABLE: '不可用',
  REPORTED: '已报告', AVAILABLE: '可用', UNAVAILABLE: '不可用', QUOTA_EXHAUSTED: '额度耗尽', UNKNOWN: '未知', MISSING: '缺失', SET: '已配置',
  ENABLED: '配置已启用', DISABLED: '配置已停用', SUPPORTED: '支持', PARTIALLY_SUPPORTED: '部分支持',
  UNSUPPORTED: '不支持', PASS: '通过', FAIL: '失败', WARNING: '提示',
  QUICK: '快速', INFORMAL: '非正式', FORMAL: '正式', FORMAL_EXHAUSTIVE: '正式穷举',
  QUALIFIED_FOR_SUITE: '当前套件合格', NOT_QUALIFIED: '不合格',
  FULL_STREAM: '完整事件流', FINAL_OUTPUT_ONLY: '仅最终输出', SMOKE: '冒烟检查',
  READ_ONLY: '只读', capability_pass: '能力通过', capability_fail: '能力失败', infra_failure: '基础设施失败',
  VERIFIED_FACT: '已验证事实', TRACE_CORRELATION: '轨迹相关性', UNVERIFIED_HYPOTHESIS: '待验证假设',
  'DURABLE TERMINAL': '已保存终态', 'POLLING POSTGRES': '更新已保存状态',
  'REAL_JUDGE_SMOKE=NOT_RUN': '真实评审冒烟：未运行',
}
export const statusLabel = (value: string) => t(labels[value] ?? value)
