import axios from 'axios'

export interface SnapshotEntry { path: string; bytes: number; sha256: string; reason?: string }
export interface SnapshotManifest {
  archive_sha256: string; archive_bytes: number; declared_tool: string
  included: SnapshotEntry[]; excluded: SnapshotEntry[]; directories: string[]; content_digest: string
}
export type SnapshotReview =
  | { status: 'REVIEW_REQUIRED'; manifest: SnapshotManifest; manifest_sha256: string; review_signature: string }
  | { status: 'REJECTED'; rejections: { reason: string; entry: number | null; path: string | null }[] }
export interface CodeSnapshot {
  identity: string; kind: 'code-snapshot-v1'; source_authenticity: 'NOT_ATTESTED'
  run_record: 'NO_RUN_RECORD'; verification: 'NOT_VERIFIED'; manifest: SnapshotManifest
  confirmation: { consent: string; archive_sha256: string; manifest_sha256: string; excluded_subset_acknowledged: true }
}
const client = axios.create({ baseURL: '/api/code-snapshots', timeout: 60000 })
const headers = (token: string) => ({ Authorization: `Bearer ${token}`, 'Content-Type': 'application/zip' })
export const codeSnapshotsApi = {
  preview: async (file: File, tool: string, token: string) => (await client.post<SnapshotReview>('/archive', file, { headers: headers(token), params: { action: 'preview', declared_tool: tool } })).data,
  confirm: async (file: File, tool: string, review: Extract<SnapshotReview, { status: 'REVIEW_REQUIRED' }>, token: string) => (await client.post<CodeSnapshot>('/archive', file, {
    params: { action: 'confirm', declared_tool: tool }, headers: {
      ...headers(token), 'X-Snapshot-Consent': 'SAVE_REVIEWED_SOURCE_SUBSET',
      'X-Snapshot-Archive-Sha256': review.manifest.archive_sha256,
      'X-Snapshot-Manifest-Sha256': review.manifest_sha256, 'X-Snapshot-Review': review.review_signature,
    },
  })).data,
  detail: async (identity: string, token: string) => (await client.get<CodeSnapshot>(`/${encodeURIComponent(identity)}`, { headers: { Authorization: `Bearer ${token}` } })).data,
}
