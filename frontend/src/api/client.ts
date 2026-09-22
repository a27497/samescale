import axios from 'axios'

import type {
  CoreReadiness,
  BadCaseExport,
  DiagnosisReport,
  ExperimentDetail,
  ExperimentListResponse,
  ExperimentStatus,
  JudgeCalibrationDetail,
  JudgeCalibrationSummary,
  MatrixResponse,
  ModelComparisonCloseout,
  RegressionResponse,
  RegressionIntent,
  RunDetail,
  RunListResponse,
  TraceResponse,
} from '@/types/workbench'
import type {
  CapabilityAssessment,
  ExperimentBuilderRequest,
  ExperimentPreflight,
  ExperimentSnapshot,
  ExperimentSnapshotSummary,
  HarnessDefinition,
  MethodologyRegistryItem,
  ModelDefinition,
  ProviderDefinition,
  ProviderModelProfile,
  RegistrySettings,
  TaskRegistryItem,
} from '@/types/registry'

export const apiClient = axios.create({
  baseURL: '/api/workbench',
  timeout: 15_000,
  headers: { Accept: 'application/json' },
})

export const workbenchApi = {
  listExperiments: async (params: Record<string, string | number | undefined> = {}) =>
    (await apiClient.get<ExperimentListResponse>('/experiments', { params })).data,
  getExperiment: async (id: string) =>
    (await apiClient.get<ExperimentDetail>(`/experiments/${encodeURIComponent(id)}`)).data,
  getMatrix: async (id: string) =>
    (await apiClient.get<MatrixResponse>(`/experiments/${encodeURIComponent(id)}/matrix`)).data,
  getModelComparisonAnalysis: async (id: string) =>
    (
      await apiClient.get<ModelComparisonCloseout>(
        `/experiments/${encodeURIComponent(id)}/model-comparison-analysis`,
      )
    ).data,
  getRuns: async (id: string, params: Record<string, string | number | undefined> = {}) =>
    (await apiClient.get<RunListResponse>(`/experiments/${encodeURIComponent(id)}/runs`, { params }))
      .data,
  getStatus: async (id: string) =>
    (await apiClient.get<ExperimentStatus>(`/experiments/${encodeURIComponent(id)}/status`)).data,
  getRun: async (id: string) =>
    (await apiClient.get<RunDetail>(`/runs/${encodeURIComponent(id)}`)).data,
  getTrace: async (id: string) =>
    (await apiClient.get<TraceResponse>(`/runs/${encodeURIComponent(id)}/trace`)).data,
  getDiagnosis: async (id: string) =>
    (
      await apiClient.get<DiagnosisReport>(
        `/experiments/${encodeURIComponent(id)}/diagnosis`,
      )
    ).data,
  exportBadCases: async (id: string, clusterIds: string[] = []) =>
    (
      await apiClient.post<BadCaseExport>(
        `/experiments/${encodeURIComponent(id)}/diagnosis/badcases`,
        { cluster_ids: clusterIds, include_synthetic_qualification: false },
      )
    ).data,
  listCalibrations: async () =>
    (
      await apiClient.get<{
        items: JudgeCalibrationSummary[]
        total: number
        limit: number
        offset: number
      }>('/judgelab/calibrations')
    ).data,
  getCalibration: async (id: string) =>
    (
      await apiClient.get<JudgeCalibrationDetail>(
        `/judgelab/calibrations/${encodeURIComponent(id)}`,
      )
    ).data,
  compare: async (
    baselineId: string,
    candidateId: string,
    intent: RegressionIntent,
    cellMapping: Record<string, string> = {},
  ) =>
    (
      await apiClient.post<RegressionResponse>('/regression/compare', {
        baseline_experiment_id: baselineId,
        candidate_experiment_id: candidateId,
        intent,
        cell_mapping: cellMapping,
      })
    ).data,
  readiness: async () => (await apiClient.get<CoreReadiness>('/core-readiness')).data,
}

export const registryApiClient = axios.create({
  baseURL: '/api',
  timeout: 30_000,
  headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
})

export const registryApi = {
  providers: async () =>
    (await registryApiClient.get<{ items: ProviderDefinition[] }>('/registry/providers')).data,
  models: async () =>
    (
      await registryApiClient.get<{
        models: ModelDefinition[]
        provider_profiles: ProviderModelProfile[]
      }>('/registry/models')
    ).data,
  harnesses: async () =>
    (await registryApiClient.get<{ items: HarnessDefinition[] }>('/registry/harnesses')).data,
  capabilities: async () =>
    (await registryApiClient.get<{ items: CapabilityAssessment[] }>('/registry/capabilities')).data,
  settings: async () => (await registryApiClient.get<RegistrySettings>('/registry/settings')).data,
  tasks: async () =>
    (await registryApiClient.get<{ items: TaskRegistryItem[] }>('/registry/tasks')).data,
  methodologies: async () =>
    (
      await registryApiClient.get<{ items: MethodologyRegistryItem[] }>(
        '/registry/methodologies',
      )
    ).data,
  preflight: async (request: ExperimentBuilderRequest) =>
    (await registryApiClient.post<ExperimentPreflight>('/experiments/preflight', request, { timeout: 120_000 })).data,
  snapshots: async (offset = 0) =>
    (await registryApiClient.get<{ items: ExperimentSnapshotSummary[]; total: number; limit: number; offset: number }>('/experiments/snapshots', { params: { offset, limit: 25 } })).data,
  getSnapshot: async (id: string) =>
    (await registryApiClient.get<ExperimentSnapshot>(`/experiments/snapshots/${encodeURIComponent(id)}`)).data,
  snapshot: async (request: ExperimentBuilderRequest) =>
    (await registryApiClient.post<ExperimentSnapshot>('/experiments/snapshot', request, { timeout: 120_000 })).data,
}
