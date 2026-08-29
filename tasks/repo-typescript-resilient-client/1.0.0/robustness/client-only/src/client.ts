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
    let response: TransportResponse = { status: 500, body: null };
    for (let attempt = 0; attempt <= this.config.retryLimit; attempt += 1) {
      try { response = await this.transport(url); } catch (error) { if (attempt === this.config.retryLimit) throw error; continue; }
      if (response.status < 500 || attempt === this.config.retryLimit) return response;
    }
    return response;
  }
}
