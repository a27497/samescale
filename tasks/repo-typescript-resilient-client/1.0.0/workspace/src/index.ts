import { ApiClient, type Transport } from "./client.ts";
import { loadConfig, type ClientEnvironment } from "./config.ts";

export function createClient(environment: ClientEnvironment, transport: Transport): ApiClient {
  void environment;
  return new ApiClient(loadConfig({}), transport);
}

export { loadConfig } from "./config.ts";
