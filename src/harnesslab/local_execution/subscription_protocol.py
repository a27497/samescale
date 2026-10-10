"""Offline HTTP/SSE protocol double, run ONLY in a network-none controller container.

This module deliberately has no live transport, credential loader, auth-file reader,
refresh, account login, purchase, or outbound socket operation. The private canary
models a credential owned by the controller, never by Codex or its tools.
"""

from __future__ import annotations

import json
import os
import secrets
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any

MAX_REQUEST_BYTES = 1_000_000


class OfflineSubscriptionController:
    def __init__(self, policy: dict[str, Any], journal: Path) -> None:
        self.model = policy["model"]
        self.max_requests = policy["max_requests"]
        self.scenario = policy["scenario"]
        self.deadline = time.monotonic() + policy["wall_time_seconds"]
        self.journal = journal
        self._private_credential = "offline-controller-canary-" + secrets.token_hex(24)
        self.state: dict[str, Any] = {
            "schema_version": 1,
            "source": "PROTOCOL_STUB_NO_MODEL",
            "run_id": policy["run_id"],
            "authorization_digest": policy["authorization_digest"],
            "requests_consumed": 0,
            "requests_received": 0,
            "turns_consumed": 0,
            "requests_denied": 0,
            "automatic_retries": 0,
            "real_model_requests": 0,
            "token_usage": None,
            "quota": "SYNTHETIC_EXHAUSTED"
            if self.scenario == "quota_exhausted"
            else "SYNTHETIC_AVAILABLE",
            "state": "READY",
        }
        # A lost physical attempt can never recreate/reset its controller budget.
        fd = os.open(journal, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(fd)
        self._save()
        self._siwc: Any = None
        self._siwc_error: str | None = None
        if policy.get("siwc_stub"):
            if __package__:
                from .siwc_contract import OfflineOAuthIssuer, OfflineSiwcSession, SiwcDenied
            else:
                from siwc_contract import (  # type: ignore[no-redef,import-not-found]
                    OfflineOAuthIssuer,
                    OfflineSiwcSession,
                    SiwcDenied,
                )

            issuer = OfflineOAuthIssuer()
            self._siwc = OfflineSiwcSession(policy["siwc_host_id"], issuer)
            pending = self._siwc.begin()
            callback = issuer.authorize(pending)
            now = int(time.time())
            grant = issuer.exchange(callback, pending, now)
            if self.scenario == "siwc_scope_missing":
                grant.scope = "openid profile email"
            if self.scenario == "siwc_wrong_client":
                callback["client_id"] = "oaiapp_offline_wrong"
            try:
                self._siwc.complete(callback, now, grant=grant)
                self._siwc.pin(now, seconds=policy["wall_time_seconds"])
            except SiwcDenied as exc:
                self._siwc_error = str(exc)
            self.state["schema_version"] = 2
            self.state["siwc"] = self._siwc.safe_receipt()
            self._save()

    def _save(self) -> None:
        with self.journal.open("w") as stream:
            json.dump(self.state, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        # This receipt contains only public counters and bounded state codes.
        self.journal.chmod(0o644)

    def _deny(self, code: str) -> tuple[int, dict[str, str]]:
        if self._siwc is not None:
            self._siwc.stop()
        self.state["requests_denied"] += 1
        self.state["state"] = code
        self._save()
        return 403, {"error": code}

    def response(self, request: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        self.state["requests_received"] += 1
        self._save()
        if time.monotonic() >= self.deadline:
            return self._deny("TIMEOUT")
        if self.state["state"] not in {"READY", "ACTIVE"}:
            return self._deny("CONTROLLER_CLOSED")
        if request.get("model") != self.model or request.get("stream") is not True:
            return self._deny("ROUTE_OR_PROTOCOL_DENIED")
        if self._siwc is not None:
            if self._siwc_error:
                return self._deny("SIWC_AUTH_DENIED")
            if __package__:
                from .siwc_contract import SiwcDenied, prepare_responses
            else:
                from siwc_contract import (  # type: ignore[no-redef]
                    SiwcDenied,
                    prepare_responses,
                )
            try:
                request = prepare_responses(request, self.model)
                self._siwc.headers_for_double(int(time.time()))
            except SiwcDenied as exc:
                return self._deny(str(exc))
        if self.scenario == "auth_expired":
            return self._deny("AUTH_EXPIRED")
        if self.scenario == "quota_exhausted":
            return self._deny("QUOTA_EXHAUSTED_NO_CREDIT_FALLBACK")
        if self.state["requests_consumed"] >= self.max_requests:
            return self._deny("REQUEST_LIMIT")
        self.state["requests_consumed"] += 1
        self.state["turns_consumed"] = 1
        self.state["state"] = "ACTIVE"
        # Durable debit before transport. Failure cannot refund or trigger retry.
        self._save()
        if self.scenario in {"siwc_stream_failed", "siwc_stream_incomplete"}:
            status = "failed" if self.scenario == "siwc_stream_failed" else "incomplete"
            self.state["state"] = "SIWC_STREAM_NOT_COMPLETED"
            self._siwc.stop()
            self._save()
            return 200, {
                "id": "offline-failed-response",
                "object": "response",
                "status": status,
                "output": [],
                "error": {
                    "code": "subscription_sharing_usage_unavailable",
                    "message": "Offline stream stopped.",
                },
            }
        if self.scenario == "upstream_failure":
            return self._deny("UPSTREAM_FAILED_NO_RETRY")
        if self.scenario == "hang":
            time.sleep(max(0, self.deadline - time.monotonic()))
            return self._deny("TIMEOUT")
        if self.state["requests_consumed"] == 1:
            item = self._tool_item(request)
            if item is None:
                return self._deny("UNSUPPORTED_PROTOCOL_TOOLS")
        else:
            self.state["state"] = "COMPLETED"
            self._save()
            item = {
                "id": "offline-message",
                "type": "message",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": "Offline protocol fixture finished."}],
            }
        # The only credential-bearing operation lives here. The double consumes it
        # internally and provides no raw response/header/exception reflection.
        credential = (
            self._siwc.headers_for_double(int(time.time()))
            if self._siwc is not None
            else self._private_credential
        )
        result = self._offline_transport(item, credential)
        if self._siwc is not None:
            try:
                self._siwc.reject_credential_reflection(result[1])
            except ValueError:
                return self._deny("SIWC_CREDENTIAL_REFLECTION_DENIED")
        return result

    def _tool_item(self, request: dict[str, Any]) -> dict[str, Any] | None:
        tools: dict[str, str] = {}
        declared = list(request.get("tools", []))
        for item in request.get("input", []):
            if item.get("type") == "additional_tools":
                declared.extend(item.get("tools", []))
        for tool in declared:
            if tool.get("type") == "namespace":
                for nested in tool.get("tools", []):
                    tools[nested.get("name", "")] = nested.get("type", "")
            else:
                tools[tool.get("name", "")] = tool.get("type", "")
        patch = (
            "*** Begin Patch\n*** Delete File: /workspace/calculator.py\n"
            "*** Add File: /workspace/calculator.py\n"
            "+def clamp(value, lower, upper):\n"
            "+    return max(lower, min(value, upper))\n*** End Patch"
        )
        if "exec_command" in tools or "exec" in tools:
            probe = "\n".join(
                [
                    "import os,pathlib,socket,errno",
                    "p=pathlib.Path",
                    "assert not any(p(x).exists() for x in "
                    "('/control','/receipts','/verifier','/oracle','/home/dev','/var/run/docker.sock'))",
                    "assert not any(any(x in k for x in "
                    "('KEY','TOKEN','SECRET','PASSWORD')) for k in os.environ)",
                    "assert b'offline-'+b'controller-'+b'canary-' not in "
                    "p('/proc/1/environ').read_bytes()",
                    "try: socket.socket(socket.AF_INET,socket.SOCK_STREAM)",
                    "except OSError as e: assert e.errno == errno.EPERM",
                    "else: raise AssertionError('Subject tool network was permitted')",
                    "p('/workspace/calculator.py').write_text('def clamp(value, lower, upper):\\n"
                    "    return max(lower, min(value, upper))\\n')",
                    "print('SUBJECT_CREDENTIAL_AND_NETWORK_ISOLATION_PASS')",
                ]
            )
            import shlex

            if "exec" in tools:
                return {
                    "id": "offline-tool",
                    "type": "custom_tool_call",
                    "call_id": "offline-call",
                    "name": "exec",
                    "namespace": "functions",
                    "input": "text(await tools.exec_command("
                    + json.dumps({"cmd": "python3 -c " + shlex.quote(probe), "yield_time_ms": 1000})
                    + "));",
                }
            return {
                "id": "offline-tool",
                "type": "function_call",
                "call_id": "offline-call",
                "name": "exec_command",
                "arguments": json.dumps(
                    {"cmd": "python3 -c " + shlex.quote(probe), "yield_time_ms": 1000}
                ),
            }
        if "apply_patch" in tools:
            custom = tools["apply_patch"] == "custom"
            return {
                "id": "offline-tool",
                "type": "custom_tool_call" if custom else "function_call",
                "call_id": "offline-call",
                "name": "apply_patch",
                **({"input": patch} if custom else {"arguments": json.dumps({"patch": patch})}),
            }
        return None

    @staticmethod
    def _offline_transport(
        item: dict[str, Any], credential: str | dict[str, str]
    ) -> tuple[int, dict[str, Any]]:
        if isinstance(credential, dict):
            assert credential["Authorization"].startswith("Bearer offline-siwc-access-")
            assert credential["originator"] == "SameScale"
        else:
            assert credential.startswith("offline-controller-canary-")
        return 200, {
            "id": "offline-response",
            "object": "response",
            "status": "completed",
            "output": [item],
            "usage": None,
        }


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        # Never log headers, bodies, errors, paths, prompts or credentials.
        pass

    def do_GET(self) -> None:
        self.send_response(200 if self.path == "/health" else 403)
        self.end_headers()

    def do_POST(self) -> None:
        controller: OfflineSubscriptionController = self.server.controller  # type: ignore[attr-defined]
        received_before = controller.state["requests_received"]
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if (
                self.path != "/v1/responses"
                or not 0 < length <= MAX_REQUEST_BYTES
                or any(
                    self.headers.get(h) is not None
                    for h in ("Authorization", "Proxy-Authorization", "Cookie", "X-Api-Key")
                )
            ):
                controller.state["requests_received"] += 1
                status, result = controller._deny("REQUEST_ENVELOPE_DENIED")
            else:
                request = json.loads(self.rfile.read(length))
                if not isinstance(request, dict):
                    raise TypeError("MALFORMED_REQUEST")
                status, result = controller.response(request)
        except (ValueError, TypeError, AttributeError):
            # An exception after response() debited ingress is still one HTTP request.
            if controller.state["requests_received"] == received_before:
                controller.state["requests_received"] += 1
            status, result = controller._deny("MALFORMED_REQUEST")
        if status != 200:
            body = json.dumps(result).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        events: list[dict[str, Any]]
        if result["status"] != "completed":
            events = [{"type": "response." + result["status"], "response": result}]
        else:
            item = result["output"][0]
            events = [
                {
                    "type": "response.created",
                    "response": {**result, "output": [], "status": "in_progress"},
                },
                {"type": "response.output_item.added", "output_index": 0, "item": item},
                {"type": "response.output_item.done", "output_index": 0, "item": item},
                {"type": "response.completed", "response": result},
            ]
        body = "".join("data: " + json.dumps(event) + "\n\n" for event in events).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    policy = json.loads(Path("/control/policy.json").read_text())
    controller = OfflineSubscriptionController(policy, Path("/receipts/controller.json"))
    server = HTTPServer(("127.0.0.1", 8765), _Handler)
    server.controller = controller  # type: ignore[attr-defined]
    server.serve_forever()


if __name__ == "__main__":
    main()
