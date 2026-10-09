import { defineStore } from 'pinia'

import { workbenchApi } from '@/api/client'
import { loadOutcomeCounts, type OutcomeCounts } from '@/utils/experimentResults'
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
  outcomeCounts: Record<string, OutcomeCounts>
  listGeneration: number
  total: number
  moreLoading: boolean
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
  detailGeneration: number
  pollingGeneration: number
  refreshingGeneration: number | null
  pollingHandle: ReturnType<typeof setInterval> | null
}

export const useExperimentStore = defineStore('experiments', {
  state: (): ExperimentState => ({
    outcomeCounts: {},
    listGeneration: 0,
    total: 0,
    moreLoading: false,
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
    detailGeneration: 0,
    pollingGeneration: 0,
    refreshingGeneration: null,
  }),
  actions: {
    async readOutcomeCounts(items: ExperimentSummary[], generation: number) {
      // Bound the additional count reads; a late list response cannot replace current counts.
      const pending = [...items]
      await Promise.all(Array.from({ length: Math.min(3, pending.length) }, async () => {
        while (pending.length && generation === this.listGeneration) {
          const item = pending.shift()!
          const counts = await loadOutcomeCounts(item)
          if (generation === this.listGeneration) this.outcomeCounts[item.experiment_id] = counts
        }
      }))
    },
    async fetchList() {
      const request = ++this.listGeneration
      this.loading = true; this.moreLoading = false; this.error = null; this.outcomeCounts = {}
      try {
        const response = await workbenchApi.listExperiments({ search: this.search || undefined, status: this.statusFilter || undefined })
        if (request !== this.listGeneration) return
        this.items = response.items; this.total = response.total
        await this.readOutcomeCounts(response.items, request)
      } catch { if (request === this.listGeneration) this.error = 'Experiment evidence could not be loaded.' }
      finally { if (request === this.listGeneration) this.loading = false }
    },
    async loadMore() {
      if (this.moreLoading || this.loading || this.items.length >= this.total) return
      const request = this.listGeneration
      this.moreLoading = true; this.error = null
      try {
        const response = await workbenchApi.listExperiments({ search: this.search || undefined, status: this.statusFilter || undefined, offset: this.items.length })
        if (request !== this.listGeneration) return
        this.items.push(...response.items.filter(item => !this.items.some(existing => existing.experiment_id === item.experiment_id)))
        this.total = response.total
        await this.readOutcomeCounts(response.items, request)
      } catch { if (request === this.listGeneration) this.error = 'Experiment evidence could not be loaded.' }
      finally { if (request === this.listGeneration) this.moreLoading = false }
    },
    async fetchExperiment(id: string, generation?: number): Promise<boolean> {
      const request = ++this.detailGeneration
      const isCurrent = () => request === this.detailGeneration && (generation === undefined || generation === this.pollingGeneration)
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
      } catch (error) {
        if (!isCurrent()) return false
        this.selected = null
        this.matrix = null
        this.runs = []
        this.modelComparison = null
        const code = (error as { response?: { data?: { error?: { code?: string } } } })?.response?.data?.error?.code
        this.error = code === 'ARTIFACT_INTEGRITY_ERROR'
          ? `${id.startsWith('phase-i-matrix-') ? 'HISTORICAL EVIDENCE' : 'EVIDENCE'} — ARTIFACT INTEGRITY FAILED. The original record remains preserved; replacement evidence was not used.`
          : 'Persisted experiment evidence could not be verified.'
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
