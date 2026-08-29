import { loadConfig } from "../src/index.ts";

const config = loadConfig({ API_BASE_URL: "https://service.test/", RETRY_LIMIT: "1" });
if (config.retryLimit !== 1) throw new Error("retry limit was not read");
