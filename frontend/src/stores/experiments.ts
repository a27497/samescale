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
  pollingGeneration: number
  refreshingGeneration: number | null
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
    pollingGeneration: 0,
    refreshingGeneration: null,
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
    async fetchExperiment(id: string, generation?: number): Promise<boolean> {
      const isCurrent = () => generation === undefined || generation === this.pollingGeneration
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
        if (!isCurrent()) return false
        this.selected = selected
        this.matrix = matrix
        this.modelComparison = modelComparison
        this.runs = runs.items
        return true
      } catch {
        if (!isCurrent()) return false
        this.modelComparison = null
        this.error = 'Persisted experiment evidence could not be verified.'
        return false
      } finally {
        if (isCurrent()) this.loading = false
      }
    },
    async refreshStatus(id: string, generation?: number) {
      generation ??= this.pollingGeneration
      if (generation !== this.pollingGeneration || this.refreshingGeneration === generation) return
      this.refreshingGeneration = generation
      try {
        const status = await workbenchApi.getStatus(id)
        if (generation !== this.pollingGeneration) return
        this.durableStatus = status
        if (status.terminal) {
          const refreshed = await this.fetchExperiment(id, generation)
          if (refreshed && generation === this.pollingGeneration) this.stopPolling()
        } else {
          this.error = null
        }
      } catch {
        if (generation === this.pollingGeneration) this.error = 'Experiment status could not be loaded.'
      } finally {
        if (this.refreshingGeneration === generation) this.refreshingGeneration = null
      }
    },
    startPolling(id: string, intervalMs = 3_000) {
      this.stopPolling()
      this.durableStatus = null
      const generation = this.pollingGeneration
      this.pollingHandle = setInterval(() => void this.refreshStatus(id, generation), intervalMs)
      void this.refreshStatus(id, generation)
    },
    stopPolling() {
      if (this.refreshingGeneration === this.pollingGeneration) this.loading = false
      if (this.pollingHandle !== null) clearInterval(this.pollingHandle)
      this.pollingHandle = null
      this.pollingGeneration += 1
    },
  },
})
