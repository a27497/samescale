# Repair the environment-configured API client

Fix the configuration, factory, and client modules as one contract. Configuration must validate
`API_BASE_URL`, `RETRY_LIMIT` (integer 0–5), and `ENABLED` (`true` or `false`), while removing
trailing slashes from the base URL. The factory must use the supplied environment.

`getUser` must URL-encode IDs and call the injected transport. Retry thrown transport errors and
5xx responses up to the configured retry limit, but never retry 4xx responses. Disabled clients
must reject before calling the transport. Preserve the exported interfaces and do not modify
`contract.md` or `test/public.test.ts`. No package install or network access is required.
