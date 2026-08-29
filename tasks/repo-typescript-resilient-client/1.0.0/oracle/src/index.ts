import { ApiClient, type Transport } from "./client.ts";
import { loadConfig, type ClientEnvironment } from "./config.ts";

export function createClient(environment: ClientEnvironment, transport: Transport): ApiClient {
  return new ApiClient(loadConfig(environment), transport);
}

export { loadConfig } from "./config.ts";
