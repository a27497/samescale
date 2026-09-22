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
  listGeneration: number
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
    listGeneration: 0,
    search: '',
    statusFilter: '',
    selectedMetric: 'success_rate',
    pollingHandle: null,
    pollingGeneration: 0,
    refreshingGeneration: null,
  }),
  actions: {
    async fetchList() {
      const generation = ++this.listGeneration
      this.loading = true
      this.error = null
      try {
        const response = await workbenchApi.listExperiments({
          search: this.search || undefined,
          status: this.statusFilter || undefined,
        })
        if (generation !== this.listGeneration) return
        this.items = response.items
      } catch {
        if (generation !== this.listGeneration) return
        this.items = []
        this.error = '无法读取实验列表。请确认本地数据库与 API 已启动，再刷新。'
      } finally {
        if (generation === this.listGeneration) this.loading = false
      }
    },
    async fetchExperiment(id: string, generation?: number): Promise<boolean> {
      const isCurrent = () => generation === undefined || generation === this.pollingGeneration
      if (!isCurrent()) return false
      if (this.selected?.experiment_id !== id) { this.selected = null; this.matrix = null; this.runs = []; this.modelComparison = null; this.durableStatus = null }
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
        this.selected = null; this.matrix = null; this.runs = []; this.durableStatus = null
        this.error = '无法读取或校验实验证据，请重试。'
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
        if (generation === this.pollingGeneration) this.error = '无法读取运行状态，请重新加载。'
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
