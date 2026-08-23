import axios from 'axios'

import type {
  CoreReadiness,
  ExperimentDetail,
  ExperimentListResponse,
  ExperimentStatus,
  JudgeCalibrationDetail,
  JudgeCalibrationSummary,
  MatrixResponse,
  RegressionResponse,
  RunDetail,
  RunListResponse,
  TraceResponse,
} from '@/types/workbench'

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
  getRuns: async (id: string, params: Record<string, string | number | undefined> = {}) =>
    (await apiClient.get<RunListResponse>(`/experiments/${encodeURIComponent(id)}/runs`, { params }))
      .data,
  getStatus: async (id: string) =>
    (await apiClient.get<ExperimentStatus>(`/experiments/${encodeURIComponent(id)}/status`)).data,
  getRun: async (id: string) =>
    (await apiClient.get<RunDetail>(`/runs/${encodeURIComponent(id)}`)).data,
  getTrace: async (id: string) =>
    (await apiClient.get<TraceResponse>(`/runs/${encodeURIComponent(id)}/trace`)).data,
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
  compare: async (baselineId: string, candidateId: string, cellMapping: Record<string, string> = {}) =>
    (
      await apiClient.post<RegressionResponse>('/regression/compare', {
        baseline_experiment_id: baselineId,
        candidate_experiment_id: candidateId,
        cell_mapping: cellMapping,
      })
    ).data,
  readiness: async () => (await apiClient.get<CoreReadiness>('/core-readiness')).data,
}
