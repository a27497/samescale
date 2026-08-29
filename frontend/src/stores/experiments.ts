import { defineStore } from 'pinia'

import { workbenchApi } from '@/api/client'
import type {
  ExperimentDetail,
  ExperimentStatus,
  ExperimentSummary,
  MatrixMetricKey,
  MatrixResponse,
  ModelComparisonCloseout,
  RunSummary,
} from '@/types/workbench'

interface ExperimentState {
  items: ExperimentSummary[]
  selected: ExperimentDetail | null
  matrix: MatrixResponse | null
  modelComparison: ModelComparisonCloseout | null
  runs: RunSummary[]
  durableStatus: ExperimentStatus | null
  loading: boolean
  error: string | null
  search: string
  statusFilter: string
  selectedMetric: MatrixMetricKey
  pollingHandle: ReturnType<typeof setInterval> | null
}

export const useExperimentStore = defineStore('experiments', {
  state: (): ExperimentState => ({
    items: [],
    selected: null,
    matrix: null,
    modelComparison: null,
    runs: [],
    durableStatus: null,
    loading: false,
    error: null,
    search: '',
    statusFilter: '',
    selectedMetric: 'success_rate',
    pollingHandle: null,
  }),
  actions: {
    async fetchList() {
      this.loading = true
      this.error = null
      try {
        const response = await workbenchApi.listExperiments({
          search: this.search || undefined,
          status: this.statusFilter || undefined,
        })
        this.items = response.items
      } catch {
        this.error = 'Experiment evidence could not be loaded.'
      } finally {
        this.loading = false
      }
    },
    async fetchExperiment(id: string) {
      this.loading = true
      this.error = null
      try {
        const selected = await workbenchApi.getExperiment(id)
        const [matrix, runs, modelComparison] = await Promise.all([
          workbenchApi.getMatrix(id),
          workbenchApi.getRuns(id, { limit: 100 }),
          selected.comparison_intent === 'MODEL_COMPARISON'
            ? workbenchApi.getModelComparisonAnalysis(id)
            : Promise.resolve(null),
        ])
        this.selected = selected
        this.matrix = matrix
        this.modelComparison = modelComparison
        this.runs = runs.items
      } catch {
        this.modelComparison = null
        this.error = 'Persisted experiment evidence could not be verified.'
      } finally {
        this.loading = false
      }
    },
    async refreshStatus(id: string) {
      this.durableStatus = await workbenchApi.getStatus(id)
      if (this.durableStatus.terminal) this.stopPolling()
    },
    startPolling(id: string, intervalMs = 3_000) {
      this.stopPolling()
      void this.refreshStatus(id)
      this.pollingHandle = setInterval(() => void this.refreshStatus(id), intervalMs)
    },
    stopPolling() {
      if (this.pollingHandle !== null) clearInterval(this.pollingHandle)
      this.pollingHandle = null
    },
  },
})
