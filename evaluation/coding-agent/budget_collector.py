"""Private OTLP sink: persist response token counts only; discard all prompt/tool bodies."""

import gzip
import hashlib
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

STATE = Path("/meter")
CONFIG = {}
SEEN = set()
TOTAL = 0


def project(body):
    for resource in body.get("resourceLogs", body.get("resource_logs", [])):
        for scope in resource.get("scopeLogs", resource.get("scope_logs", [])):
            for record in scope.get("logRecords", scope.get("log_records", [])):
                attrs = {a["key"]: a.get("value", {}) for a in record.get("attributes", [])}

                def value(key, fields=attrs):
                    item = fields.get(key, {})
                    return item.get("stringValue", item.get("intValue", item.get("doubleValue")))

                if (
                    value("event.name") != "codex.sse_event"
                    or (value("event.kind") or value("kind")) != "response.completed"
                ):
                    continue
                if value("input_token_count") is None:
                    continue
                output = {
                    k: int(value(source) or 0)
                    for k, source in [
                        ("input_tokens", "input_token_count"),
                        ("cached_input_tokens", "cached_token_count"),
                        ("cache_write_input_tokens", "cache_write_token_count"),
                        ("output_tokens", "output_token_count"),
                    ]
                }
                output["time_unix_nano"] = str(
                    record.get("timeUnixNano", record.get("time_unix_nano"))
                )
                output["conversation_id"] = str(value("conversation.id"))
                output["event_timestamp"] = str(value("event.timestamp"))
                yield output


def charge(usage):
    uncached = (
        usage["input_tokens"] - usage["cached_input_tokens"] - usage["cache_write_input_tokens"]
    )
    if uncached < 0 or any(v < 0 for k, v in usage.items() if k.endswith("tokens")):
        raise ValueError("invalid usage; stop rather than infer zero")
    factor = 2 if usage["input_tokens"] > 272000 else 1
    output_factor = 1.5 if factor == 2 else 1
    return (
        factor
        * (
            uncached * 2
            + usage["cached_input_tokens"] * 0.1
            + usage["cache_write_input_tokens"] * 2.5
        )
        + usage["output_tokens"] * 10 * output_factor
    ) / 1e6


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_POST(self):
        global TOTAL
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if self.path != "/v1/logs" or length > 4_000_000:
                raise ValueError("invalid OTLP envelope")
            data = self.rfile.read(length)
            if self.headers.get("Content-Encoding") == "gzip":
                data = gzip.decompress(data)
            for usage in project(json.loads(data)):
                identity = hashlib.sha256(json.dumps(usage, sort_keys=True).encode()).hexdigest()
                if identity in SEEN:
                    continue
                SEEN.add(identity)
                usage["api_equivalent_usd"] = charge(usage)
                TOTAL += usage["api_equivalent_usd"]
                usage["campaign_api_equivalent_usd"] = TOTAL
                with (STATE / "usage.jsonl").open("a") as stream:
                    stream.write(json.dumps(usage, sort_keys=True) + "\n")
                    stream.flush()
                if CONFIG["limit_usd"] <= TOTAL:
                    (STATE / "STOP_BUDGET").touch(exist_ok=True)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"{}")
        except Exception as exc:
            # Only a bounded exception type, never the unfiltered incoming event.
            (STATE / "STOP_METER_ERROR").write_text(type(exc).__name__)
            self.send_response(400)
            self.end_headers()


if __name__ == "__main__":
    CONFIG = json.loads((STATE / "config.json").read_text())
    TOTAL = CONFIG["initial_api_equivalent_usd"]
    HTTPServer(("0.0.0.0", 4318), Handler).serve_forever()
