// UI explanations only. Compatibility decisions remain in the server Registry.
import type { HarnessDefinition } from '@/types/registry'
import { t } from './i18n'

export const runtimeName = (runtime: HarnessDefinition) => runtime.harness_id === 'direct-model'
  ? t('直接调用') : runtime.display_name
export const runtimeGroup = (runtime: HarnessDefinition) => runtime.harness_id === 'direct-model'
  ? '直接调用' : '编程 Agent'
export const runtimeProfileGroups = (runtimes: HarnessDefinition[]) => ['编程 Agent', '直接调用'].map(label => ({
  label,
  profiles: runtimes.filter(runtime => runtimeGroup(runtime) === label).flatMap(runtime => runtime.profiles),
})).filter(group => group.profiles.length)

const reasons: Record<string, string> = {
  PROTOCOL_UNSUPPORTED_BY_HARNESS: '此执行方式不支持该协议。',
  PROVIDER_MODEL_PROFILE_UNSUPPORTED_BY_HARNESS: '此执行方式未声明支持该模型服务配置。',
  PROVIDER_OR_PROFILE_DISABLED: '服务或模型配置已停用。',
  AUTOMATION_NOT_ALLOWED: '当前配置不允许自动调用。',
  MODEL_PURPOSE_NOT_SUBJECT: '此配置用途不是被测模型，不能用于评测单元。',
  HARNESS_CONFIGURATION_DISABLED: '此运行配置已停用。',
  TRACE_COVERAGE_LIMITED: '轨迹覆盖有限，无法查看完整执行过程。',
  OBSERVED_MODEL_NOT_EXPOSED: '运行接口不提供实际模型身份。',
  CONFIGURED_MODEL_ID_REQUIRED: '尚未配置模型 ID。',
  RUNTIME_ENDPOINT_REFERENCE_MISSING: '尚未配置服务地址引用。',
  RUNTIME_ENDPOINT_INVALID: '服务地址不符合配置要求。',
  RUNTIME_ENDPOINT_WORKSPACE_MISMATCH: '协议地址不属于同一工作区。',
}
export const registryReason = (code: string) => reasons[code] ?? '服务端报告了此限制，详见原因代码。'
