export interface ClientEnvironment {
  API_BASE_URL?: string;
  RETRY_LIMIT?: string;
  ENABLED?: string;
}

export interface ClientConfig {
  baseUrl: string;
  retryLimit: number;
  enabled: boolean;
}

export function loadConfig(environment: ClientEnvironment): ClientConfig {
  return {
    baseUrl: environment.API_BASE_URL ?? "https://api.example.test/",
    retryLimit: Number(environment.RETRY_LIMIT ?? "2"),
    enabled: Boolean(environment.ENABLED ?? "true"),
  };
}
