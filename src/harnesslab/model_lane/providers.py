from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from typing import Any

import httpx
from pydantic import ValidationError

from harnesslab.contracts.common import Protocol
from harnesslab.contracts.provider import ThinkingMode, ThinkingTransport
from harnesslab.model_lane.models import (
    ProviderAdapter,
    ProviderFailureCategory,
    ProviderIncompleteReason,
    ProviderInvocationError,
    ProviderReadTimeoutStage,
    ProviderRequest,
    ProviderResult,
    ProviderTimeoutPhase,
    ProviderTransportPhase,
    ProviderTransportPhaseTrace,
    ProviderTransportTrace,
    ProviderUsage,
)

MAX_PROVIDER_RESPONSE_BYTES = 2_000_000
MAX_PROVIDER_TRANSPORT_TRACE_EVENTS = 16


class CampaignHTTPClientPool(AbstractAsyncContextManager["CampaignHTTPClientPool"]):
    """Campaign-owned clients isolated by exact route and credential reference."""

    def __init__(self, *, max_connections_per_route: int = 2) -> None:
        if not 1 <= max_connections_per_route <= 8:
            raise ValueError("max connections per route must be between 1 and 8")
        self.max_connections_per_route = max_connections_per_route
        self._clients: dict[tuple[str, str], httpx.AsyncClient] = {}
        self._closed = False

    def client_for(self, route_identity: str, credential_reference: str) -> httpx.AsyncClient:
        if self._closed:
            raise RuntimeError("campaign HTTP pool is closed")
        if not route_identity or not credential_reference:
            raise ValueError("route and credential references must be non-empty")
        key = (route_identity, credential_reference)
        client = self._clients.get(key)
        if client is None:
            limits = httpx.Limits(
                max_connections=self.max_connections_per_route,
                max_keepalive_connections=self.max_connections_per_route,
            )
            client = httpx.AsyncClient(
                follow_redirects=False,
                limits=limits,
                timeout=None,
                trust_env=False,
            )
            self._clients[key] = client
        return client

    @property
    def route_count(self) -> int:
        return len(self._clients)

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> None:
        self._closed = True
        clients = tuple(self._clients.values())
        self._clients.clear()
        for client in clients:
            await client.aclose()


_TRANSPORT_EVENT_PHASES = {
    "connection.connect_tcp": ProviderTransportPhase.CONNECT_TCP,
    "connection.start_tls": ProviderTransportPhase.START_TLS,
    "http11.send_request_headers": ProviderTransportPhase.SEND_REQUEST_HEADERS,
    "http2.send_request_headers": ProviderTransportPhase.SEND_REQUEST_HEADERS,
    "http11.send_request_body": ProviderTransportPhase.SEND_REQUEST_BODY,
    "http2.send_request_body": ProviderTransportPhase.SEND_REQUEST_BODY,
    "http11.receive_response_headers": ProviderTransportPhase.RECEIVE_RESPONSE_HEADERS,
    "http2.receive_response_headers": ProviderTransportPhase.RECEIVE_RESPONSE_HEADERS,
}


class _ProviderTransportTraceCollector:
    """Collect only stable httpcore event names and request-relative timing."""

    def __init__(self, started: float) -> None:
        self._started = started
        self._records: dict[ProviderTransportPhase, tuple[int, int | None]] = {}
        self._event_count = 0
        self._failed = False

    async def __call__(self, name: str, _raw_info: object) -> None:
        # The raw info payload is intentionally ignored in full. It can contain
        # transport objects and is not part of HarnessLab's stable evidence contract.
        try:
            self._record_event(name)
        except Exception:
            self._failed = True
            self._records.clear()

    def _record_event(self, name: str) -> None:
        if self._failed:
            return
        self._event_count += 1
        if self._event_count > MAX_PROVIDER_TRANSPORT_TRACE_EVENTS:
            self._failed = True
            self._records.clear()
            return
        event, separator, state = name.rpartition(".")
        if not separator or state not in {"started", "complete", "failed"}:
            return
        phase = _TRANSPORT_EVENT_PHASES.get(event)
        if phase is None:
            return
        elapsed_ms = int((time.perf_counter() - self._started) * 1000)
        previous = self._records.get(phase)
        if state == "started":
            if previous is None:
                self._records[phase] = (elapsed_ms, None)
            return
        if state == "complete" and previous is not None and previous[1] is None:
            self._records[phase] = (previous[0], elapsed_ms)

    def snapshot(self) -> ProviderTransportTrace | None:
        if self._failed:
            return None
        try:
            return ProviderTransportTrace(
                phases=tuple(
                    ProviderTransportPhaseTrace(
                        phase=phase,
                        started_ms=started_ms,
                        completed_ms=completed_ms,
                    )
                    for phase, (started_ms, completed_ms) in self._records.items()
                )
            )
        except (ValidationError, ValueError):
            return None


def _timeout_phase(exc: httpx.TimeoutException) -> ProviderTimeoutPhase:
    if isinstance(exc, httpx.ConnectTimeout):
        return ProviderTimeoutPhase.CONNECT
    if isinstance(exc, httpx.ReadTimeout):
        return ProviderTimeoutPhase.READ
    if isinstance(exc, httpx.WriteTimeout):
        return ProviderTimeoutPhase.WRITE
    if isinstance(exc, httpx.PoolTimeout):
        return ProviderTimeoutPhase.POOL
    return ProviderTimeoutPhase.UNKNOWN


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ProviderInvocationError(
            ProviderFailureCategory.MALFORMED_RESPONSE,
            f"provider returned invalid {label}",
        )
    return value


def _optional_nonnegative(value: object, label: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ProviderInvocationError(
            ProviderFailureCategory.MALFORMED_RESPONSE,
            f"provider returned invalid {label}",
        )
    return value


def _safe_bounded_text(value: object, *, limit: int) -> str | None:
    if not isinstance(value, str) or len(value) > limit:
        return None
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return None
    return value


def _response_request_id(response: httpx.Response) -> str | None:
    for name in ("request-id", "x-request-id"):
        value = _safe_bounded_text(response.headers.get(name), limit=300)
        if value is not None:
            return value
    return None


def _body_response_status(body: dict[str, Any]) -> str | None:
    for field in ("status", "stop_reason"):
        value = _safe_bounded_text(body.get(field), limit=200)
        if value is not None:
            return value
    choices = body.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        return _safe_bounded_text(choices[0].get("finish_reason"), limit=200)
    return None


class _HTTPProviderAdapter:
    protocol: Protocol

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        environment: Mapping[str, str] | None = None,
    ) -> None:
        self._client = client
        self._environment = environment if environment is not None else os.environ

    async def invoke(self, request: ProviderRequest) -> ProviderResult:
        if request.profile.protocol is not self.protocol:
            raise ProviderInvocationError(
                ProviderFailureCategory.CONFIGURATION,
                f"adapter requires {self.protocol.value} protocol",
            )
        reference = request.profile.credential_reference
        if reference is None:
            raise ProviderInvocationError(
                ProviderFailureCategory.CONFIGURATION,
                "credential reference is not configured",
            )
        credential = self._environment.get(reference)
        if credential is None or not credential.strip():
            raise ProviderInvocationError(
                ProviderFailureCategory.CONFIGURATION,
                f"credential environment variable {reference} is not configured",
            )
        try:
            runtime_base_url = request.profile.resolve_base_url(self._environment)
        except ValueError as exc:
            raise ProviderInvocationError(
                ProviderFailureCategory.CONFIGURATION,
                "provider runtime URL is not configured",
            ) from exc
        url = f"{runtime_base_url}{request.profile.route}"
        payload = self._payload(request)
        headers = self._headers(credential)
        started = time.perf_counter()
        transport_trace = _ProviderTransportTraceCollector(started)

        async def send(client: httpx.AsyncClient) -> tuple[httpx.Response, bytes, int]:
            response: httpx.Response | None = None
            header_latency_ms: int | None = None
            total = 0
            try:
                async with client.stream(
                    "POST",
                    url,
                    headers=headers,
                    json=payload,
                    timeout=request.profile.request_timeout_seconds,
                    follow_redirects=False,
                    extensions={"trace": transport_trace},
                ) as response:
                    header_latency_ms = int((time.perf_counter() - started) * 1000)
                    self._raise_for_status(response, header_latency_ms)
                    chunks: list[bytes] = []
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > MAX_PROVIDER_RESPONSE_BYTES:
                            raise ProviderInvocationError(
                                ProviderFailureCategory.MALFORMED_RESPONSE,
                                "provider response exceeds the byte limit",
                                request_id=_response_request_id(response),
                                latency_ms=int((time.perf_counter() - started) * 1000),
                            )
                        chunks.append(chunk)
                    latency_ms = int((time.perf_counter() - started) * 1000)
                    return response, b"".join(chunks), latency_ms
            except httpx.ReadTimeout as exc:
                if response is None:
                    raise ProviderInvocationError(
                        ProviderFailureCategory.TIMEOUT,
                        "provider request timed out",
                        latency_ms=int((time.perf_counter() - started) * 1000),
                        timeout_phase=ProviderTimeoutPhase.READ,
                        read_timeout_stage=(ProviderReadTimeoutStage.WAITING_FOR_RESPONSE_HEADERS),
                        transport_trace=transport_trace.snapshot(),
                    ) from exc
                assert header_latency_ms is not None
                raise ProviderInvocationError(
                    ProviderFailureCategory.TIMEOUT,
                    "provider request timed out",
                    status_code=response.status_code,
                    request_id=_response_request_id(response),
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    timeout_phase=ProviderTimeoutPhase.READ,
                    read_timeout_stage=ProviderReadTimeoutStage.READING_RESPONSE_BODY,
                    response_header_latency_ms=header_latency_ms,
                    response_body_bytes_received=total,
                    transport_trace=transport_trace.snapshot(),
                ) from exc

        try:
            if self._client is None:
                async with httpx.AsyncClient(
                    timeout=request.profile.request_timeout_seconds
                ) as client:
                    response, content, latency_ms = await send(client)
            else:
                response, content, latency_ms = await send(self._client)
        except httpx.TimeoutException as exc:
            timeout_phase = _timeout_phase(exc)
            raise ProviderInvocationError(
                ProviderFailureCategory.TIMEOUT,
                "provider request timed out",
                latency_ms=int((time.perf_counter() - started) * 1000),
                timeout_phase=timeout_phase,
                read_timeout_stage=(
                    ProviderReadTimeoutStage.WAITING_FOR_RESPONSE_HEADERS
                    if timeout_phase is ProviderTimeoutPhase.READ
                    else None
                ),
                transport_trace=transport_trace.snapshot(),
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderInvocationError(
                ProviderFailureCategory.HTTP_ERROR,
                "provider HTTP request failed",
                latency_ms=int((time.perf_counter() - started) * 1000),
            ) from exc
        try:
            body = json.loads(content)
        except (ValueError, UnicodeDecodeError, RecursionError) as exc:
            raise ProviderInvocationError(
                ProviderFailureCategory.MALFORMED_RESPONSE,
                "provider returned non-JSON content",
                request_id=_response_request_id(response),
                latency_ms=latency_ms,
            ) from exc
        safe_body = body if isinstance(body, dict) else {}
        try:
            normalized_body = _object(body, "response body")
            return self._parse(normalized_body, request, latency_ms, response)
        except ProviderInvocationError as exc:
            exc.request_id = exc.request_id or _safe_bounded_text(safe_body.get("id"), limit=300)
            exc.request_id = exc.request_id or _response_request_id(response)
            exc.response_status = exc.response_status or _body_response_status(safe_body)
            exc.latency_ms = exc.latency_ms if exc.latency_ms is not None else latency_ms
            raise
        except (ValidationError, TypeError, ValueError) as exc:
            raise ProviderInvocationError(
                ProviderFailureCategory.MALFORMED_RESPONSE,
                "provider response failed normalized validation",
                request_id=(
                    _safe_bounded_text(safe_body.get("id"), limit=300)
                    or _response_request_id(response)
                ),
                response_status=_body_response_status(safe_body),
                latency_ms=latency_ms,
            ) from exc

    def _raise_for_status(self, response: httpx.Response, latency_ms: int) -> None:
        if 200 <= response.status_code < 300:
            return
        if response.status_code in {401, 403}:
            category = ProviderFailureCategory.AUTHENTICATION
        elif response.status_code == 429:
            category = ProviderFailureCategory.RATE_LIMIT
        else:
            category = ProviderFailureCategory.HTTP_ERROR
        raise ProviderInvocationError(
            category,
            f"provider HTTP status {response.status_code}",
            status_code=response.status_code,
            request_id=_response_request_id(response),
            latency_ms=latency_ms,
        )

    def _payload(self, request: ProviderRequest) -> dict[str, object]:
        raise NotImplementedError

    def _headers(self, credential: str) -> dict[str, str]:
        raise NotImplementedError

    def _parse(
        self,
        body: dict[str, Any],
        request: ProviderRequest,
        latency_ms: int,
        response: httpx.Response,
    ) -> ProviderResult:
        raise NotImplementedError


class OpenAIResponsesAdapter(_HTTPProviderAdapter):
    protocol = Protocol.RESPONSES

    def _headers(self, credential: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {credential}", "Content-Type": "application/json"}

    def _payload(self, request: ProviderRequest) -> dict[str, object]:
        profile = request.profile
        if profile.reasoning.effort not in {
            None,
            "none",
            "minimal",
            "low",
            "medium",
            "high",
            "xhigh",
            "max",
        }:
            raise ProviderInvocationError(
                ProviderFailureCategory.CONFIGURATION,
                "unsupported OpenAI Responses reasoning effort",
            )
        payload: dict[str, object] = {
            "model": profile.requested_model,
            "instructions": request.instructions,
            "input": request.input,
            "store": False,
            "tools": [],
        }
        if profile.reasoning.max_output_tokens is not None:
            payload["max_output_tokens"] = profile.reasoning.max_output_tokens
        if profile.reasoning.temperature is not None:
            payload["temperature"] = profile.reasoning.temperature
        if profile.reasoning.effort is not None:
            payload["reasoning"] = {"effort": profile.reasoning.effort}
        return payload

    def _parse(
        self,
        body: dict[str, Any],
        request: ProviderRequest,
        latency_ms: int,
        response: httpx.Response,
    ) -> ProviderResult:
        status = body.get("status")
        incomplete_reason: ProviderIncompleteReason | None = None
        if status == "incomplete":
            details = body.get("incomplete_details")
            raw_reason = details.get("reason") if isinstance(details, dict) else None
            safe_reason = raw_reason if isinstance(raw_reason, str) else None
            incomplete_reason = (
                {
                    "max_output_tokens": ProviderIncompleteReason.MAX_OUTPUT_TOKENS,
                    "content_filter": ProviderIncompleteReason.CONTENT_FILTER,
                    "provider_interrupted": ProviderIncompleteReason.PROVIDER_INTERRUPTED,
                }.get(safe_reason, ProviderIncompleteReason.UNKNOWN)
                if safe_reason is not None
                else ProviderIncompleteReason.UNKNOWN
            )
        if status == "incomplete" and (
            incomplete_reason is not ProviderIncompleteReason.MAX_OUTPUT_TOKENS
        ):
            raise ProviderInvocationError(
                ProviderFailureCategory.INCOMPLETE_RESPONSE,
                "provider response is incomplete",
                response_status="incomplete",
                incomplete_reason=incomplete_reason,
            )
        if status not in {"completed", "incomplete"}:
            raise ProviderInvocationError(
                ProviderFailureCategory.PROVIDER_ERROR,
                "provider response did not complete",
            )
        output = body.get("output")
        if not isinstance(output, list):
            raise ProviderInvocationError(
                ProviderFailureCategory.MALFORMED_RESPONSE, "provider output must be a list"
            )
        public_parts: list[str] = []
        refused = False
        for item in output:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "refusal" and isinstance(item.get("refusal"), str):
                public_parts.append(item["refusal"])
                refused = True
                continue
            if item.get("type") != "message":
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for block in content:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "output_text" and isinstance(block.get("text"), str):
                    public_parts.append(block["text"])
                elif block.get("type") == "refusal" and isinstance(block.get("refusal"), str):
                    public_parts.append(block["refusal"])
                    refused = True
        if not public_parts and not refused and status == "completed":
            raise ProviderInvocationError(
                ProviderFailureCategory.MALFORMED_RESPONSE,
                "provider response contains no public output or refusal text",
            )
        usage_raw = body.get("usage")
        usage = _object(usage_raw, "usage") if usage_raw is not None else {}
        details_raw = usage.get("output_tokens_details")
        details = _object(details_raw, "output token details") if details_raw is not None else {}
        return ProviderResult(
            requested_model=request.profile.requested_model,
            observed_model=body.get("model") if isinstance(body.get("model"), str) else None,
            provider=request.profile.provider,
            endpoint_identity=request.profile.provider_route_identity,
            protocol=self.protocol,
            request_id=body.get("id") if isinstance(body.get("id"), str) else None,
            public_output_text="".join(public_parts),
            refused=refused,
            usage=ProviderUsage(
                input_tokens=_optional_nonnegative(usage.get("input_tokens"), "input tokens"),
                output_tokens=_optional_nonnegative(usage.get("output_tokens"), "output tokens"),
                total_tokens=_optional_nonnegative(usage.get("total_tokens"), "total tokens"),
                reasoning_tokens=_optional_nonnegative(
                    details.get("reasoning_tokens"), "reasoning tokens"
                ),
            ),
            stop_reason=(
                ProviderIncompleteReason.MAX_OUTPUT_TOKENS.value
                if incomplete_reason is ProviderIncompleteReason.MAX_OUTPUT_TOKENS
                else None
            ),
            response_status=status,
            incomplete_reason=incomplete_reason,
            latency_ms=latency_ms,
        )


class AnthropicMessagesAdapter(_HTTPProviderAdapter):
    protocol = Protocol.MESSAGES

    def _headers(self, credential: str) -> dict[str, str]:
        return {
            "x-api-key": credential,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

    def _payload(self, request: ProviderRequest) -> dict[str, object]:
        profile = request.profile
        if profile.reasoning.effort not in {None, "low", "medium", "high", "xhigh", "max"}:
            raise ProviderInvocationError(
                ProviderFailureCategory.CONFIGURATION,
                "unsupported Anthropic Messages effort",
            )
        if profile.reasoning.max_output_tokens is None:
            raise ProviderInvocationError(
                ProviderFailureCategory.CONFIGURATION,
                "Anthropic Messages requires max_output_tokens",
            )
        payload: dict[str, object] = {
            "model": profile.requested_model,
            "system": request.instructions,
            "messages": [{"role": "user", "content": request.input}],
            "max_tokens": profile.reasoning.max_output_tokens,
        }
        if profile.reasoning.temperature is not None:
            payload["temperature"] = profile.reasoning.temperature
        output_config: dict[str, object] = {}
        if profile.reasoning.effort is not None:
            output_config["effort"] = profile.reasoning.effort
        if request.output_json_schema is not None:
            output_config["format"] = {
                "type": "json_schema",
                "schema": request.output_json_schema.value,
            }
        if output_config:
            payload["output_config"] = output_config
        return payload

    def _parse(
        self,
        body: dict[str, Any],
        request: ProviderRequest,
        latency_ms: int,
        response: httpx.Response,
    ) -> ProviderResult:
        content = body.get("content")
        if not isinstance(content, list):
            raise ProviderInvocationError(
                ProviderFailureCategory.MALFORMED_RESPONSE, "provider content must be a list"
            )
        texts = [
            block["text"]
            for block in content
            if isinstance(block, dict)
            and block.get("type") == "text"
            and isinstance(block.get("text"), str)
        ]
        stop_reason = body.get("stop_reason")
        if stop_reason == "model_context_window_exceeded":
            raise ProviderInvocationError(
                ProviderFailureCategory.INCOMPLETE_RESPONSE,
                "provider response exceeded the model context window",
            )
        refused = stop_reason == "refusal"
        if stop_reason not in {"end_turn", "stop_sequence", "refusal", "max_tokens"}:
            raise ProviderInvocationError(
                ProviderFailureCategory.PROVIDER_ERROR,
                "provider response did not end with terminal public text",
            )
        usage_raw = body.get("usage")
        usage = _object(usage_raw, "usage") if usage_raw is not None else {}
        request_id = body.get("id") if isinstance(body.get("id"), str) else None
        if request_id is None:
            request_id = response.headers.get("request-id")
        input_tokens = _optional_nonnegative(usage.get("input_tokens"), "input tokens")
        output_tokens = _optional_nonnegative(usage.get("output_tokens"), "output tokens")
        return ProviderResult(
            requested_model=request.profile.requested_model,
            observed_model=body.get("model") if isinstance(body.get("model"), str) else None,
            provider=request.profile.provider,
            endpoint_identity=request.profile.provider_route_identity,
            protocol=self.protocol,
            request_id=request_id,
            public_output_text="".join(texts),
            refused=refused,
            usage=ProviderUsage(
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=(
                    input_tokens + output_tokens
                    if input_tokens is not None and output_tokens is not None
                    else None
                ),
            ),
            stop_reason=stop_reason,
            response_status="truncated" if stop_reason == "max_tokens" else "completed",
            latency_ms=latency_ms,
        )


class OpenAICompatibleChatAdapter(_HTTPProviderAdapter):
    protocol = Protocol.CHAT_COMPLETIONS

    def _headers(self, credential: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {credential}", "Content-Type": "application/json"}

    def _payload(self, request: ProviderRequest) -> dict[str, object]:
        profile = request.profile
        if profile.reasoning.effort is not None:
            raise ProviderInvocationError(
                ProviderFailureCategory.CONFIGURATION,
                "generic Chat Completions does not define reasoning effort semantics",
            )
        payload: dict[str, object] = {
            "model": profile.requested_model,
            "messages": [
                {"role": "system", "content": request.instructions},
                {"role": "user", "content": request.input},
            ],
        }
        if profile.reasoning.max_output_tokens is not None:
            payload["max_tokens"] = profile.reasoning.max_output_tokens
        if profile.reasoning.temperature is not None:
            payload["temperature"] = profile.reasoning.temperature
        if profile.thinking_transport is ThinkingTransport.DEEPSEEK_THINKING_OBJECT:
            assert profile.thinking_mode is not None
            payload["thinking"] = {"type": profile.thinking_mode.value}
        elif profile.thinking_transport is ThinkingTransport.BAILIAN_ENABLE_THINKING:
            payload["enable_thinking"] = profile.thinking_mode is ThinkingMode.ENABLED
        return payload

    def _parse(
        self,
        body: dict[str, Any],
        request: ProviderRequest,
        latency_ms: int,
        response: httpx.Response,
    ) -> ProviderResult:
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ProviderInvocationError(
                ProviderFailureCategory.MALFORMED_RESPONSE,
                "provider response must contain a first choice",
            )
        choice = choices[0]
        message = _object(choice.get("message"), "choice message")
        content = message.get("content")
        refusal = message.get("refusal")
        if refusal is not None and not isinstance(refusal, str):
            raise ProviderInvocationError(
                ProviderFailureCategory.MALFORMED_RESPONSE,
                "choice message refusal must be public text",
            )
        refused = isinstance(refusal, str)
        if not refused and not isinstance(content, str):
            raise ProviderInvocationError(
                ProviderFailureCategory.MALFORMED_RESPONSE,
                "choice message content must be public text",
            )
        finish_reason = choice.get("finish_reason")
        if not refused and finish_reason not in {"stop", "length"}:
            raise ProviderInvocationError(
                ProviderFailureCategory.PROVIDER_ERROR,
                "provider response did not end with terminal public text",
            )
        usage_raw = body.get("usage")
        usage = _object(usage_raw, "usage") if usage_raw is not None else {}
        request_id = body.get("id") if isinstance(body.get("id"), str) else None
        if request_id is None:
            request_id = response.headers.get("x-request-id")
        return ProviderResult(
            requested_model=request.profile.requested_model,
            observed_model=body.get("model") if isinstance(body.get("model"), str) else None,
            provider=request.profile.provider,
            endpoint_identity=request.profile.provider_route_identity,
            protocol=self.protocol,
            request_id=request_id,
            public_output_text=refusal if refused else content,
            refused=refused,
            usage=ProviderUsage(
                input_tokens=_optional_nonnegative(usage.get("prompt_tokens"), "prompt tokens"),
                output_tokens=_optional_nonnegative(
                    usage.get("completion_tokens"), "completion tokens"
                ),
                total_tokens=_optional_nonnegative(usage.get("total_tokens"), "total tokens"),
            ),
            stop_reason=finish_reason,
            response_status="truncated" if finish_reason == "length" else "completed",
            latency_ms=latency_ms,
        )


def adapter_for_profile(
    request: ProviderRequest,
    *,
    client: httpx.AsyncClient | None = None,
    environment: Mapping[str, str] | None = None,
) -> ProviderAdapter:
    adapters: dict[Protocol, type[_HTTPProviderAdapter]] = {
        Protocol.RESPONSES: OpenAIResponsesAdapter,
        Protocol.MESSAGES: AnthropicMessagesAdapter,
        Protocol.CHAT_COMPLETIONS: OpenAICompatibleChatAdapter,
    }
    adapter_type = adapters.get(request.profile.protocol)
    if adapter_type is None:
        raise ProviderInvocationError(
            ProviderFailureCategory.CONFIGURATION,
            f"unsupported provider protocol {request.profile.protocol.value}",
        )
    return adapter_type(client=client, environment=environment)
