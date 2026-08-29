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
  const rawUrl = environment.API_BASE_URL ?? "https://api.example.test";
  const baseUrl = rawUrl.replace(/\/+$/, "");
  if (!/^https?:\/\/[^/]+/.test(baseUrl)) throw new TypeError("API_BASE_URL must be an HTTP URL");
  const rawRetry = environment.RETRY_LIMIT ?? "2";
  if (!/^[0-5]$/.test(rawRetry)) throw new TypeError("RETRY_LIMIT must be an integer from 0 to 5");
  const rawEnabled = environment.ENABLED ?? "true";
  if (rawEnabled !== "true" && rawEnabled !== "false") throw new TypeError("ENABLED must be true or false");
  return { baseUrl, retryLimit: Number(rawRetry), enabled: rawEnabled === "true" };
}
