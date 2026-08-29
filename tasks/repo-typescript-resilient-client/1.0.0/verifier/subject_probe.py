from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


def failure(reason: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "passed": False,
        "score": 0.0,
        "checks": [
            {"name": "subject-build-or-run", "passed": False, "score": 0.0, "detail": reason}
        ],
        "summary": "TypeScript repository contract could not execute",
    }


def run(workspace: Path) -> dict[str, object]:
    index = workspace / "src/index.ts"
    config = workspace / "src/config.ts"
    if not index.is_file() or not config.is_file():
        return failure("SUBJECT_SOURCE_MISSING")
    source = f"""
import {{ createClient }} from {json.dumps(index.resolve().as_uri())};
import {{ loadConfig }} from {json.dumps(config.resolve().as_uri())};

const results = [];
const configValue = loadConfig({{ API_BASE_URL: "https://service.test///", RETRY_LIMIT: "2", ENABLED: "false" }});
results.push(configValue.baseUrl === "https://service.test" && configValue.retryLimit === 2 && configValue.enabled === false);

const urls = [];
const encoded = createClient({{ API_BASE_URL: "https://service.test/", RETRY_LIMIT: "0", ENABLED: "true" }}, async url => {{ urls.push(url); return {{ status: 200, body: "ok" }}; }});
await encoded.getUser("a/b c");
results.push(urls.length === 1 && urls[0] === "https://service.test/users/a%2Fb%20c");

let serverCalls = 0;
const server = createClient({{ API_BASE_URL: "https://service.test", RETRY_LIMIT: "2" }}, async () => {{ serverCalls += 1; return {{ status: serverCalls < 3 ? 503 : 200, body: null }}; }});
const serverResult = await server.getUser("x");
results.push(serverCalls === 3 && serverResult.status === 200);

let clientCalls = 0;
const clientError = createClient({{ API_BASE_URL: "https://service.test", RETRY_LIMIT: "3" }}, async () => {{ clientCalls += 1; return {{ status: 404, body: null }}; }});
results.push((await clientError.getUser("x")).status === 404 && clientCalls === 1);

let disabledCalls = 0;
const disabled = createClient({{ API_BASE_URL: "https://service.test", RETRY_LIMIT: "1", ENABLED: "false" }}, async () => {{ disabledCalls += 1; return {{ status: 200, body: null }}; }});
let disabledRejected = false;
try {{ await disabled.getUser("x"); }} catch {{ disabledRejected = true; }}
results.push(disabledRejected && disabledCalls === 0);

let thrownCalls = 0;
const thrown = createClient({{ API_BASE_URL: "https://service.test", RETRY_LIMIT: "1" }}, async () => {{ thrownCalls += 1; if (thrownCalls === 1) throw new Error("temporary"); return {{ status: 200, body: null }}; }});
results.push((await thrown.getUser("x")).status === 200 && thrownCalls === 2);

let invalid = 0;
for (const environment of [{{ RETRY_LIMIT: "6" }}, {{ RETRY_LIMIT: "1.5" }}, {{ ENABLED: "yes" }}, {{ API_BASE_URL: "file:///tmp/x" }}]) {{ try {{ loadConfig(environment); }} catch (error) {{ if (error instanceof TypeError) invalid += 1; }} }}
results.push(invalid === 4);
console.log(JSON.stringify(results));
"""
    with tempfile.TemporaryDirectory(prefix="client-contract-") as temporary:
        harness = Path(temporary) / "hidden-verifier.mjs"
        harness.write_text(source, encoding="utf-8")
        completed = subprocess.run(
            ["node", "--no-warnings", str(harness)],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    if completed.returncode != 0:
        return failure("SUBJECT_RUNTIME_FAILURE")
    try:
        values = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return failure("SUBJECT_OUTPUT_FAILURE")
    names = (
        "validated-config",
        "encoded-url",
        "retry-5xx",
        "no-retry-4xx",
        "disabled-no-transport",
        "retry-transport-error",
        "reject-invalid-config",
    )
    if not isinstance(values, list) or len(values) != len(names):
        return failure("SUBJECT_OUTPUT_FAILURE")
    checks = [
        {"name": name, "passed": value is True, "score": 1.0 if value is True else 0.0}
        for name, value in zip(names, values, strict=True)
    ]
    return {
        "schema_version": 1,
        "passed": all(item["passed"] for item in checks),
        "score": sum(item["score"] for item in checks) / len(checks),
        "checks": checks,
        "summary": "TypeScript configuration/factory/transport contract",
    }
