import type { ClientConfig } from "./config.ts";
export interface TransportResponse { status: number; body: unknown; }
export type Transport = (url: string) => Promise<TransportResponse>;
export class ApiClient {
  private readonly config: ClientConfig;
  private readonly transport: Transport;
  constructor(config: ClientConfig, transport: Transport) { this.config = config; this.transport = transport; }
  async getUser(id: string): Promise<TransportResponse> {
    if (!this.config.enabled) throw new Error("disabled");
    const url = `${this.config.baseUrl}/users/${encodeURIComponent(id)}`;
    let lastError: unknown;
    for (let attempt = 0; attempt <= this.config.retryLimit; attempt += 1) {
      try { const response = await this.transport(url); if (response.status < 500 || attempt === this.config.retryLimit) return response; }
      catch (error) { lastError = error; if (attempt === this.config.retryLimit) throw error; }
    }
    throw lastError;
  }
}
