export interface ClientEnvironment { API_BASE_URL?: string; RETRY_LIMIT?: string; ENABLED?: string; }
export interface ClientConfig { baseUrl: string; retryLimit: number; enabled: boolean; }
export function loadConfig(environment: ClientEnvironment): ClientConfig {
  const baseUrl = (environment.API_BASE_URL ?? "https://api.example.test").replace(/\/+$/, "");
  if (!/^https?:\/\/[^/]+/.test(baseUrl)) throw new TypeError("invalid URL");
  const retry = environment.RETRY_LIMIT ?? "2";
  if (!/^[0-5]$/.test(retry)) throw new TypeError("invalid retry");
  const enabled = environment.ENABLED ?? "true";
  if (!/^(true|false)$/.test(enabled)) throw new TypeError("invalid enabled");
  return { baseUrl, retryLimit: Number(retry), enabled: enabled === "true" };
}
