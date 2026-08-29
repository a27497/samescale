import type { ClientConfig } from "./config.ts";

export interface TransportResponse {
  status: number;
  body: unknown;
}

export type Transport = (url: string) => Promise<TransportResponse>;

export class ApiClient {
  private readonly config: ClientConfig;
  private readonly transport: Transport;

  constructor(config: ClientConfig, transport: Transport) {
    this.config = config;
    this.transport = transport;
  }

  async getUser(id: string): Promise<TransportResponse> {
    const url = `${this.config.baseUrl}/users/${id}`;
    let response: TransportResponse = { status: 500, body: null };
    for (let attempt = 0; attempt <= this.config.retryLimit; attempt += 1) {
      response = await this.transport(url);
      if (response.status < 500) return response;
    }
    return response;
  }
}
