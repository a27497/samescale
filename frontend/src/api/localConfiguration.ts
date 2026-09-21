import axios from 'axios'
import type { ProviderModelProfile } from '@/types/registry'

export interface LocalModelWrite {
  name: string
  template_profile_id: string
  request_timeout_seconds: number
  enabled: boolean
  expected_revision: number
  purpose?: 'SUBJECT' | 'ANALYST' | 'JUDGE'
  max_output_tokens?: number | null
  reasoning_effort?: string | null
  temperature?: number | null
  connection_id?: string | null
  connection_revision?: number | null
}
export interface CredentialMetadata {
  credential_id: string; revision: number; name: string; enabled: boolean; reference: string; present: boolean
}
export interface ConnectionMetadata {
  connection_id: string; revision: number; name: string; enabled: boolean
  template_provider_id: string; protocol: string; credential_id: string | null; credential_revision: number | null
  environment_reference: string | null; credential_reference: string; endpoint_reference: string; endpoint_fingerprint: string
  endpoint_present: boolean; credential_present: boolean; ready_for_planning: boolean; health_status: 'NOT_VERIFIED'
}
export interface CredentialWrite {
  name: string; expected_revision: number; enabled: boolean; value?: string
}
export interface ConnectionWrite {
  name: string; expected_revision: number; enabled: boolean; template_provider_id: string; protocol: string
  base_url?: string; credential_id: string | null; credential_revision: number | null; environment_reference: string | null
}
export interface LocalModelConfiguration extends Omit<LocalModelWrite, 'expected_revision'> {
  configuration_id: string
  revision: number
  profile: ProviderModelProfile
  template_digest: string
  origin: 'LOCAL'
}
export interface ConfigurationOptions {
  model_controls: { profile_id: string; max_output_tokens: number; reasoning_efforts: string[]; temperature_supported: boolean }[]
  harness_templates: { profile_id: string; harness_id: string; version: string; profile_reference: string; reasoning_effort: string | null; tool_surface: string[]; supported_provider_profile_ids: string[] }[]
}
export interface LocalHarnessWrite {
  name: string; expected_revision: number; enabled: boolean; template_profile_id: string; provider_profile_ids: string[]
}
export interface LocalHarnessConfiguration {
  configuration_id: string; revision: number; name: string; enabled: boolean; template_profile_id: string; template_digest: string; harness_id: string
  profile: { profile_id: string; supported_provider_profile_ids: string[]; harness_config_identity: string }
}
// Operator tokens are passed per request and never installed in shared defaults or storage.
const client = axios.create({ baseURL: '/api/local-configuration', timeout: 15000 })
const headers = (token: string) => ({ Authorization: `Bearer ${token}` })
export const localConfigurationApi = {
  options: async (token: string) => (await client.get<ConfigurationOptions>('/options', { headers: headers(token) })).data,
  harnesses: async (token: string) => (await client.get<{ items: LocalHarnessConfiguration[] }>('/harnesses', { headers: headers(token) })).data,
  saveHarness: async (id: string, payload: LocalHarnessWrite, token: string) => (await client.put<LocalHarnessConfiguration>(`/harnesses/${encodeURIComponent(id)}`, payload, { headers: headers(token) })).data,

  status: async () => (await client.get<{ enabled: boolean }>('/status')).data,
  list: async (token: string) => (await client.get<{ items: LocalModelConfiguration[] }>('/models', { headers: headers(token) })).data,
  save: async (id: string, payload: LocalModelWrite, token: string) => (await client.put<LocalModelConfiguration>(`/models/${encodeURIComponent(id)}`, payload, { headers: headers(token) })).data,
  credentials: async (token: string) => (await client.get<{ items: CredentialMetadata[] }>('/credentials', { headers: headers(token) })).data,
  connections: async (token: string) => (await client.get<{ items: ConnectionMetadata[] }>('/connections', { headers: headers(token) })).data,
  saveCredential: async (id: string, payload: CredentialWrite, token: string) => (await client.put<CredentialMetadata>(`/credentials/${encodeURIComponent(id)}`, payload, { headers: headers(token) })).data,
  saveConnection: async (id: string, payload: ConnectionWrite, token: string) => (await client.put<ConnectionMetadata>(`/connections/${encodeURIComponent(id)}`, payload, { headers: headers(token) })).data,
  checkConnection: async (id: string, token: string) => (await client.post<{ connection: ConnectionMetadata; connection_health: 'NOT_VERIFIED'; network_requests: number; provider_requests: number }>(`/connections/${encodeURIComponent(id)}/check`, {}, { headers: headers(token) })).data,
}
