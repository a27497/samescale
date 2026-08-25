from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping
from typing import Any

import httpx
from pydantic import ValidationError

from harnesslab.contracts.common import Protocol
from harnesslab.contracts.provider import ThinkingMode, ThinkingTransport
from harnesslab.model_lane.models import (
    ProviderAdapter,
    ProviderFailureCategory,
    ProviderInvocationError,
    ProviderRequest,
    ProviderResult,
    ProviderTimeoutPhase,
    ProviderUsage,
)

MAX_PROVIDER_RESPONSE_BYTES = 2_000_000


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
        url = f"{request.profile.base_url}{request.profile.route}"
        payload = self._payload(request)
        headers = self._headers(credential)
        started = time.perf_counter()

        async def send(client: httpx.AsyncClient) -> tuple[httpx.Response, bytes, int]:
            async with client.stream(
                "POST",
                url,
                headers=headers,
                json=payload,
                timeout=request.profile.request_timeout_seconds,
                follow_redirects=False,
            ) as response:
                header_latency_ms = int((time.perf_counter() - started) * 1000)
                self._raise_for_status(response, header_latency_ms)
                chunks: list[bytes] = []
                total = 0
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

        try:
            if self._client is None:
                async with httpx.AsyncClient(
                    timeout=request.profile.request_timeout_seconds
                ) as client:
                    response, content, latency_ms = await send(client)
            else:
                response, content, latency_ms = await send(self._client)
        except httpx.TimeoutException as exc:
            raise ProviderInvocationError(
                ProviderFailureCategory.TIMEOUT,
                "provider request timed out",
                latency_ms=int((time.perf_counter() - started) * 1000),
                timeout_phase=_timeout_phase(exc),
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
        if status == "incomplete":
            raise ProviderInvocationError(
                ProviderFailureCategory.INCOMPLETE_RESPONSE,
                "provider response is incomplete",
            )
        if status != "completed":
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
        if not public_parts and not refused:
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
            endpoint=f"{request.profile.base_url}{request.profile.route}",
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
            stop_reason=None,
            response_status=status,
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
        if profile.reasoning.effort is not None:
            payload["output_config"] = {"effort": profile.reasoning.effort}
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
        if stop_reason in {"max_tokens", "model_context_window_exceeded"}:
            raise ProviderInvocationError(
                ProviderFailureCategory.INCOMPLETE_RESPONSE,
                "provider response reached a configured or context token limit",
            )
        refused = stop_reason == "refusal"
        if stop_reason not in {"end_turn", "stop_sequence", "refusal"}:
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
            endpoint=f"{request.profile.base_url}{request.profile.route}",
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
            response_status="completed",
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
        if finish_reason == "length":
            raise ProviderInvocationError(
                ProviderFailureCategory.INCOMPLETE_RESPONSE,
                "provider response reached the configured token limit",
            )
        if not refused and finish_reason != "stop":
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
            endpoint=f"{request.profile.base_url}{request.profile.route}",
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
            response_status="completed",
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
