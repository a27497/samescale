from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path

import httpx
import pytest

from harnesslab.contracts.common import Protocol
from harnesslab.contracts.model import ModelProfile, ReasoningProfile
from harnesslab.model_lane.models import (
    ProviderFailureCategory,
    ProviderIncompleteReason,
    ProviderInvocationError,
    ProviderJSONSchema,
    ProviderReadTimeoutStage,
    ProviderRequest,
    ProviderTimeoutPhase,
)
from harnesslab.model_lane.profiles import load_model_profile
from harnesslab.model_lane.providers import (
    AnthropicMessagesAdapter,
    OpenAICompatibleChatAdapter,
    OpenAIResponsesAdapter,
)

FAKE_KEY = "gate-d-fake-key-not-a-real-credential"


def profile(
    protocol: Protocol,
    *,
    effort: str | None = "medium",
    max_output_tokens: int | None = 4000,
    temperature: float | None = 0.25,
) -> ModelProfile:
    routes = {
        Protocol.RESPONSES: ("https://api.openai.test/v1", "/responses"),
        Protocol.MESSAGES: ("https://api.anthropic.test", "/v1/messages"),
        Protocol.CHAT_COMPLETIONS: ("https://compatible.test/v1", "/chat/completions"),
    }
    base_url, route = routes[protocol]
    return ModelProfile(
        requested_model="requested-model",
        provider="test-provider",
        base_url=base_url,
        route=route,
        protocol=protocol,
        reasoning=ReasoningProfile(
            effort=effort,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        ),
        credential_reference="TEST_PROVIDER_API_KEY",
    )


def provider_request(
    protocol: Protocol,
    *,
    effort: str | None = "medium",
    temperature: float | None = 0.25,
    max_output_tokens: int | None = 4000,
) -> ProviderRequest:
    return ProviderRequest(
        profile=profile(
            protocol,
            effort=effort,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        ),
        instructions="Return strict JSON only.",
        input="Solve the visible task.",
    )


async def client_for(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.parametrize("provider", ["deepseek-official", "openai", "test-provider"])
async def test_responses_structured_output_provider_contract(provider: str) -> None:
    schema = ProviderJSONSchema(
        value={
            "type": "object",
            "properties": {"answer": {"type": "string"}},
            "required": ["answer"],
            "additionalProperties": False,
        }
    )
    invocation = provider_request(Protocol.RESPONSES)
    invocation = invocation.model_copy(
        update={
            "profile": invocation.profile.model_copy(update={"provider": provider}),
            "output_json_schema": schema,
        }
    )
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        expected: dict[str, object] = {
            "type": "json_schema",
            "name": "structured_output",
            "schema": schema.value,
        }
        if provider != "deepseek-official":
            expected["strict"] = True
        assert json.loads(request.content) == {
            "model": "requested-model",
            "instructions": "Return strict JSON only.",
            "input": "Solve the visible task.",
            "store": False,
            "tools": [],
            "max_output_tokens": 4000,
            "temperature": 0.25,
            "reasoning": {"effort": "medium"},
            "text": {"format": expected},
        }
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": '{"answer":"ok"}'}],
                    }
                ],
            },
        )

    async with await client_for(handler) as client:
        await OpenAIResponsesAdapter(
            client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
        ).invoke(invocation)
    assert calls == 1


@pytest.mark.asyncio
async def test_openai_responses_adapter_contract_and_private_reasoning_exclusion() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.openai.test/v1/responses"
        assert request.headers["authorization"] == f"Bearer {FAKE_KEY}"
        payload = json.loads(request.content)
        assert payload == {
            "model": "requested-model",
            "instructions": "Return strict JSON only.",
            "input": "Solve the visible task.",
            "store": False,
            "tools": [],
            "max_output_tokens": 4000,
            "temperature": 0.25,
            "reasoning": {"effort": "medium"},
        }
        return httpx.Response(
            200,
            json={
                "id": "resp-safe-id",
                "status": "completed",
                "model": "observed-openai-model",
                "output": [
                    {"type": "reasoning", "content": "PRIVATE_OPENAI_REASONING"},
                    {
                        "type": "message",
                        "content": [
                            {"type": "output_text", "text": '{"schema_version":1,'},
                            {"type": "output_text", "text": '"operations":[]}'},
                        ],
                    },
                ],
                "usage": {
                    "input_tokens": 11,
                    "output_tokens": 7,
                    "total_tokens": 18,
                    "output_tokens_details": {"reasoning_tokens": 3},
                },
            },
        )

    async with await client_for(handler) as client:
        result = await OpenAIResponsesAdapter(
            client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
        ).invoke(provider_request(Protocol.RESPONSES))

    serialized = result.model_dump_json()
    assert result.public_output_text == '{"schema_version":1,"operations":[]}'
    assert result.requested_model == "requested-model"
    assert result.observed_model == "observed-openai-model"
    assert result.endpoint_identity == (
        "test-provider|responses|https://api.openai.test/v1/responses"
    )
    assert result.request_id == "resp-safe-id"
    assert result.usage.reasoning_tokens == 3
    assert result.attempt_count == 1
    assert "PRIVATE_OPENAI_REASONING" not in serialized
    assert FAKE_KEY not in serialized


@pytest.mark.asyncio
async def test_openai_responses_max_output_incomplete_is_a_safe_provider_result() -> None:
    attempts = 0
    body = {
        "id": "resp-budget-id",
        "status": "incomplete",
        "incomplete_details": {"reason": "max_output_tokens"},
        "model": "observed-budget-model",
        "output": [
            {"type": "reasoning", "summary": "PRIVATE_BUDGET_REASONING"},
            {
                "type": "message",
                "content": [{"type": "output_text", "text": '{"schema_version":1'}],
            },
        ],
        "usage": {
            "input_tokens": 11,
            "output_tokens": 4000,
            "total_tokens": 4011,
            "output_tokens_details": {"reasoning_tokens": 37},
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(200, json=body)

    async with await client_for(handler) as client:
        result = await OpenAIResponsesAdapter(
            client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
        ).invoke(provider_request(Protocol.RESPONSES))

    serialized = result.model_dump_json()
    assert result.incomplete_reason is ProviderIncompleteReason.MAX_OUTPUT_TOKENS
    assert result.stop_reason == "max_output_tokens"
    assert result.response_status == "incomplete"
    assert result.observed_model == "observed-budget-model"
    assert result.usage.output_tokens == 4000
    assert result.usage.reasoning_tokens == 37
    assert result.attempt_count == attempts == 1
    assert "PRIVATE_BUDGET_REASONING" not in serialized


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw_reason", "expected"),
    (
        ("content_filter", ProviderIncompleteReason.CONTENT_FILTER),
        ("future_provider_reason", ProviderIncompleteReason.UNKNOWN),
        (None, ProviderIncompleteReason.UNKNOWN),
    ),
)
async def test_openai_responses_non_budget_incomplete_remains_provider_failure(
    raw_reason: str | None, expected: ProviderIncompleteReason
) -> None:
    attempts = 0
    details = {} if raw_reason is None else {"reason": raw_reason}

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(
            200,
            json={
                "status": "incomplete",
                "incomplete_details": details,
                "output": [],
            },
        )

    async with await client_for(handler) as client:
        with pytest.raises(ProviderInvocationError) as caught:
            await OpenAIResponsesAdapter(
                client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
            ).invoke(provider_request(Protocol.RESPONSES))

    assert caught.value.category is ProviderFailureCategory.INCOMPLETE_RESPONSE
    assert caught.value.incomplete_reason is expected
    assert caught.value.response_status == "incomplete"
    assert attempts == 1
    assert raw_reason is None or raw_reason not in str(caught.value)


@pytest.mark.asyncio
async def test_openai_responses_supports_max_reasoning_effort() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["reasoning"] == {"effort": "max"}
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "{}"}],
                    }
                ],
            },
        )

    async with await client_for(handler) as client:
        result = await OpenAIResponsesAdapter(
            client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
        ).invoke(provider_request(Protocol.RESPONSES, effort="max"))

    assert not result.refused


@pytest.mark.asyncio
async def test_openai_responses_refusal_is_successful_public_result() -> None:
    body = {
        "id": "resp-refusal-id",
        "status": "completed",
        "model": "observed-refusing-model",
        "output": [
            {"type": "reasoning", "summary": "PRIVATE_REFUSAL_REASONING"},
            {
                "type": "message",
                "content": [
                    {"type": "refusal", "refusal": "PUBLIC_OPENAI_REFUSAL"},
                ],
            },
        ],
        "usage": {
            "input_tokens": 9,
            "output_tokens": 4,
            "total_tokens": 13,
            "output_tokens_details": {"reasoning_tokens": 2},
        },
    }
    async with await client_for(lambda request: httpx.Response(200, json=body)) as client:
        result = await OpenAIResponsesAdapter(
            client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
        ).invoke(provider_request(Protocol.RESPONSES))

    serialized = result.model_dump_json()
    assert result.refused
    assert result.public_output_text == "PUBLIC_OPENAI_REFUSAL"
    assert result.request_id == "resp-refusal-id"
    assert result.observed_model == "observed-refusing-model"
    assert result.usage.total_tokens == 13
    assert result.usage.reasoning_tokens == 2
    assert result.response_status == "completed"
    assert result.latency_ms >= 0
    assert "PRIVATE_REFUSAL_REASONING" not in serialized


@pytest.mark.asyncio
async def test_anthropic_messages_adapter_contract_and_thinking_exclusion() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://api.anthropic.test/v1/messages"
        assert request.headers["x-api-key"] == FAKE_KEY
        assert request.headers["anthropic-version"] == "2023-06-01"
        payload = json.loads(request.content)
        assert payload["system"] == "Return strict JSON only."
        assert payload["messages"] == [{"role": "user", "content": "Solve the visible task."}]
        assert payload["max_tokens"] == 4000
        assert payload["output_config"] == {"effort": "medium"}
        assert "thinking" not in payload
        assert "providerOptions" not in payload
        assert "tools" not in payload
        return httpx.Response(
            200,
            headers={"request-id": "anthropic-request-id"},
            json={
                "id": "msg-safe-id",
                "model": "observed-claude-model",
                "content": [
                    {"type": "thinking", "thinking": "PRIVATE_ANTHROPIC_THINKING"},
                    {"type": "text", "text": '{"schema_version":1,"operations":[]}'},
                ],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 12, "output_tokens": 8},
            },
        )

    async with await client_for(handler) as client:
        result = await AnthropicMessagesAdapter(
            client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
        ).invoke(provider_request(Protocol.MESSAGES))

    serialized = result.model_dump_json()
    assert result.observed_model == "observed-claude-model"
    assert result.endpoint_identity == (
        "test-provider|messages|https://api.anthropic.test/v1/messages"
    )
    assert result.request_id == "msg-safe-id"
    assert result.stop_reason == "end_turn"
    assert result.usage.total_tokens == 20
    assert "PRIVATE_ANTHROPIC_THINKING" not in serialized
    assert FAKE_KEY not in serialized


@pytest.mark.asyncio
async def test_anthropic_messages_emits_bailian_strict_json_schema_format() -> None:
    schema = ProviderJSONSchema(
        value={
            "type": "object",
            "properties": {
                "schema_version": {"type": "integer", "const": 1},
                "label": {"type": "string", "enum": ["PASS", "FAIL", "UNKNOWN"]},
                "reason": {"type": "string", "maxLength": 200},
            },
            "required": ["schema_version", "label", "reason"],
            "additionalProperties": False,
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["output_config"] == {
            "format": {"type": "json_schema", "schema": schema.value}
        }
        assert "thinking" not in payload
        assert "providerOptions" not in payload
        assert "temperature" not in payload
        return httpx.Response(
            200,
            json={
                "id": "bailian-json-schema",
                "model": "glm-5.2",
                "content": [
                    {
                        "type": "text",
                        "text": '{"schema_version":1,"label":"PASS","reason":"ok"}',
                    }
                ],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 12, "output_tokens": 8},
            },
        )

    request = provider_request(
        Protocol.MESSAGES, effort=None, temperature=None, max_output_tokens=256
    ).model_copy(update={"output_json_schema": schema})
    async with await client_for(handler) as client:
        result = await AnthropicMessagesAdapter(
            client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
        ).invoke(request)

    assert result.observed_model == "glm-5.2"


@pytest.mark.asyncio
async def test_anthropic_refusal_is_successful_public_result() -> None:
    body = {
        "id": "msg-refusal-id",
        "model": "observed-refusing-claude",
        "content": [
            {"type": "thinking", "thinking": "PRIVATE_REFUSAL_THINKING"},
            {"type": "text", "text": "PUBLIC_ANTHROPIC_REFUSAL"},
        ],
        "stop_reason": "refusal",
        "usage": {"input_tokens": 8, "output_tokens": 3},
    }
    async with await client_for(lambda request: httpx.Response(200, json=body)) as client:
        result = await AnthropicMessagesAdapter(
            client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
        ).invoke(provider_request(Protocol.MESSAGES))

    serialized = result.model_dump_json()
    assert result.refused
    assert result.public_output_text == "PUBLIC_ANTHROPIC_REFUSAL"
    assert result.request_id == "msg-refusal-id"
    assert result.observed_model == "observed-refusing-claude"
    assert result.stop_reason == "refusal"
    assert result.usage.total_tokens == 11
    assert result.response_status == "completed"
    assert result.latency_ms >= 0
    assert "PRIVATE_REFUSAL_THINKING" not in serialized


@pytest.mark.asyncio
async def test_openai_compatible_chat_completions_core_contract() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://compatible.test/v1/chat/completions"
        assert request.headers["authorization"] == f"Bearer {FAKE_KEY}"
        payload = json.loads(request.content)
        assert payload == {
            "model": "requested-model",
            "messages": [
                {"role": "system", "content": "Return strict JSON only."},
                {"role": "user", "content": "Solve the visible task."},
            ],
            "max_tokens": 4000,
            "temperature": 0.25,
        }
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-safe-id",
                "model": "observed-compatible-model",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": '{"schema_version":1,"operations":[]}',
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
            },
        )

    async with await client_for(handler) as client:
        result = await OpenAICompatibleChatAdapter(
            client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
        ).invoke(provider_request(Protocol.CHAT_COMPLETIONS, effort=None))

    assert result.public_output_text == '{"schema_version":1,"operations":[]}'
    assert result.observed_model == "observed-compatible-model"
    assert result.endpoint_identity == (
        "test-provider|chat_completions|https://compatible.test/v1/chat/completions"
    )
    assert result.request_id == "chatcmpl-safe-id"
    assert result.stop_reason == "stop"
    assert result.usage.total_tokens == 15


@pytest.mark.asyncio
async def test_openai_compatible_chat_supports_request_scoped_strict_schema_and_reasoning() -> None:
    schema = ProviderJSONSchema(
        value={
            "type": "object",
            "properties": {"schema_version": {"type": "integer", "const": 1}},
            "required": ["schema_version"],
            "additionalProperties": False,
        }
    )

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert payload["reasoning_effort"] == "high"
        assert payload["response_format"] == {
            "type": "json_schema",
            "json_schema": {
                "name": "judge_output",
                "strict": True,
                "schema": schema.value,
            },
        }
        return httpx.Response(
            200,
            json={
                "id": "chatcmpl-strict-id",
                "model": "observed-strict-model",
                "choices": [
                    {
                        "message": {"content": '{"schema_version":1}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                    "total_tokens": 15,
                    "completion_tokens_details": {"reasoning_tokens": 3},
                },
            },
        )

    request = provider_request(
        Protocol.CHAT_COMPLETIONS,
        effort="high",
        temperature=None,
        max_output_tokens=256,
    ).model_copy(update={"output_json_schema": schema})
    async with await client_for(handler) as client:
        result = await OpenAICompatibleChatAdapter(
            client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
        ).invoke(request)

    assert result.usage.reasoning_tokens == 3


@pytest.mark.asyncio
async def test_generic_chat_refusal_is_successful_public_result() -> None:
    body = {
        "id": "chat-refusal-id",
        "model": "observed-compatible-refusal-model",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "refusal": "PUBLIC_CHAT_REFUSAL",
                    "reasoning": "PRIVATE_CHAT_REASONING",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 7, "completion_tokens": 2, "total_tokens": 9},
    }
    async with await client_for(lambda request: httpx.Response(200, json=body)) as client:
        result = await OpenAICompatibleChatAdapter(
            client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
        ).invoke(provider_request(Protocol.CHAT_COMPLETIONS, effort=None))

    serialized = result.model_dump_json()
    assert result.refused
    assert result.public_output_text == "PUBLIC_CHAT_REFUSAL"
    assert result.request_id == "chat-refusal-id"
    assert result.observed_model == "observed-compatible-refusal-model"
    assert result.stop_reason == "stop"
    assert result.usage.total_tokens == 9
    assert result.response_status == "completed"
    assert result.latency_ms >= 0
    assert "PRIVATE_CHAT_REASONING" not in serialized


@pytest.mark.asyncio
async def test_missing_credential_fails_before_http_request() -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json={})

    async with await client_for(handler) as client:
        with pytest.raises(ProviderInvocationError) as caught:
            await OpenAIResponsesAdapter(client=client, environment={}).invoke(
                provider_request(Protocol.RESPONSES)
            )

    assert caught.value.category is ProviderFailureCategory.CONFIGURATION
    assert not called


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        pytest.param(302, ProviderFailureCategory.HTTP_ERROR, id="redirect-302"),
        pytest.param(401, ProviderFailureCategory.AUTHENTICATION, id="auth-401"),
        pytest.param(429, ProviderFailureCategory.RATE_LIMIT, id="rate-limit-429"),
        pytest.param(503, ProviderFailureCategory.HTTP_ERROR, id="server-503"),
    ],
)
async def test_http_provider_failures_are_distinct_and_not_retried(
    status_code: int, expected: ProviderFailureCategory
) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(
            status_code,
            headers={"x-request-id": "safe-failure-request-id"},
            json={"error": "unsafe body is ignored"},
        )

    async with await client_for(handler) as client:
        with pytest.raises(ProviderInvocationError) as caught:
            await OpenAIResponsesAdapter(
                client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
            ).invoke(provider_request(Protocol.RESPONSES))

    assert caught.value.category is expected
    assert caught.value.status_code == status_code
    assert caught.value.request_id == "safe-failure-request-id"
    assert caught.value.latency_ms is not None
    assert attempts == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("exception_type", "expected_phase"),
    [
        pytest.param(httpx.ConnectTimeout, ProviderTimeoutPhase.CONNECT, id="connect"),
        pytest.param(httpx.ReadTimeout, ProviderTimeoutPhase.READ, id="read"),
        pytest.param(httpx.WriteTimeout, ProviderTimeoutPhase.WRITE, id="write"),
        pytest.param(httpx.PoolTimeout, ProviderTimeoutPhase.POOL, id="pool"),
        pytest.param(httpx.TimeoutException, ProviderTimeoutPhase.UNKNOWN, id="unknown"),
    ],
)
async def test_http_timeout_subtypes_are_preserved_without_retry(
    exception_type: type[httpx.TimeoutException], expected_phase: ProviderTimeoutPhase
) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        raise exception_type(f"unsafe timeout detail {FAKE_KEY}", request=request)

    async with await client_for(handler) as client:
        with pytest.raises(ProviderInvocationError) as caught:
            await OpenAIResponsesAdapter(
                client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
            ).invoke(provider_request(Protocol.RESPONSES))

    assert caught.value.category is ProviderFailureCategory.TIMEOUT
    assert caught.value.timeout_phase is expected_phase
    assert caught.value.read_timeout_stage is (
        ProviderReadTimeoutStage.WAITING_FOR_RESPONSE_HEADERS
        if expected_phase is ProviderTimeoutPhase.READ
        else None
    )
    assert caught.value.latency_ms is not None
    assert caught.value.latency_ms >= 0
    assert attempts == 1


class ReadTimeoutResponseStream(httpx.AsyncByteStream):
    def __init__(self, chunks: tuple[bytes, ...]) -> None:
        self.chunks = chunks

    async def __aiter__(self) -> AsyncIterator[bytes]:
        for chunk in self.chunks:
            yield chunk
        raise httpx.ReadTimeout(
            f"unsafe body timeout detail {FAKE_KEY}",
            request=httpx.Request("POST", "https://unsafe-provider-url.invalid/v1/responses"),
        )


@pytest.mark.asyncio
async def test_read_timeout_before_response_headers_has_safe_stage() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout(f"unsafe pre-header timeout detail {FAKE_KEY}", request=request)

    async with await client_for(handler) as client:
        with pytest.raises(ProviderInvocationError) as caught:
            await OpenAIResponsesAdapter(
                client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
            ).invoke(provider_request(Protocol.RESPONSES))

    error = caught.value
    assert error.category is ProviderFailureCategory.TIMEOUT
    assert error.timeout_phase is ProviderTimeoutPhase.READ
    assert error.read_timeout_stage is ProviderReadTimeoutStage.WAITING_FOR_RESPONSE_HEADERS
    assert error.response_header_latency_ms is None
    assert error.response_body_bytes_received is None
    assert error.status_code is None
    assert error.request_id is None


@pytest.mark.asyncio
async def test_read_timeout_after_headers_before_body_has_safe_stage() -> None:
    async with await client_for(
        lambda request: httpx.Response(
            200,
            headers={"x-request-id": "safe-body-timeout-id"},
            stream=ReadTimeoutResponseStream(()),
        )
    ) as client:
        with pytest.raises(ProviderInvocationError) as caught:
            await OpenAIResponsesAdapter(
                client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
            ).invoke(provider_request(Protocol.RESPONSES))

    error = caught.value
    assert error.category is ProviderFailureCategory.TIMEOUT
    assert error.timeout_phase is ProviderTimeoutPhase.READ
    assert error.read_timeout_stage is ProviderReadTimeoutStage.READING_RESPONSE_BODY
    assert error.response_header_latency_ms is not None
    assert error.response_header_latency_ms >= 0
    assert error.response_body_bytes_received == 0
    assert error.status_code == 200
    assert error.request_id == "safe-body-timeout-id"


@pytest.mark.asyncio
async def test_read_timeout_after_partial_body_counts_bytes_without_content() -> None:
    partial = b"PRIVATE_PARTIAL_PROVIDER_BODY"
    async with await client_for(
        lambda request: httpx.Response(
            200,
            stream=ReadTimeoutResponseStream((partial,)),
        )
    ) as client:
        with pytest.raises(ProviderInvocationError) as caught:
            await OpenAIResponsesAdapter(
                client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
            ).invoke(provider_request(Protocol.RESPONSES))

    error = caught.value
    assert error.read_timeout_stage is ProviderReadTimeoutStage.READING_RESPONSE_BODY
    assert error.response_body_bytes_received == len(partial)
    serialized = json.dumps(error.__dict__, sort_keys=True, default=str)
    assert partial.decode() not in serialized
    assert FAKE_KEY not in serialized
    assert "unsafe-provider-url.invalid" not in serialized
    assert "authorization" not in serialized.casefold()


@pytest.mark.asyncio
async def test_body_read_timeout_request_id_remains_bounded() -> None:
    async with await client_for(
        lambda request: httpx.Response(
            200,
            headers={
                "request-id": "x" * 301,
                "x-request-id": "safe-bounded-request-id",
            },
            stream=ReadTimeoutResponseStream(()),
        )
    ) as client:
        with pytest.raises(ProviderInvocationError) as caught:
            await OpenAIResponsesAdapter(
                client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
            ).invoke(provider_request(Protocol.RESPONSES))

    assert caught.value.request_id == "safe-bounded-request-id"


@pytest.mark.asyncio
async def test_timeout_malformed_and_incomplete_are_distinct() -> None:
    timeout_attempts = 0

    def timeout_handler(request: httpx.Request) -> httpx.Response:
        nonlocal timeout_attempts
        timeout_attempts += 1
        raise httpx.ReadTimeout("synthetic timeout", request=request)

    async with await client_for(timeout_handler) as client:
        with pytest.raises(ProviderInvocationError) as timeout:
            await OpenAIResponsesAdapter(
                client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
            ).invoke(provider_request(Protocol.RESPONSES))
    assert timeout.value.category is ProviderFailureCategory.TIMEOUT
    assert timeout.value.timeout_phase is ProviderTimeoutPhase.READ
    assert timeout_attempts == 1

    async with await client_for(lambda request: httpx.Response(200, content=b"not-json")) as client:
        with pytest.raises(ProviderInvocationError) as malformed:
            await OpenAIResponsesAdapter(
                client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
            ).invoke(provider_request(Protocol.RESPONSES))
    assert malformed.value.category is ProviderFailureCategory.MALFORMED_RESPONSE

    async with await client_for(
        lambda request: httpx.Response(200, json={"status": "incomplete", "output": []})
    ) as client:
        with pytest.raises(ProviderInvocationError) as incomplete:
            await OpenAIResponsesAdapter(
                client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
            ).invoke(provider_request(Protocol.RESPONSES))
    assert incomplete.value.category is ProviderFailureCategory.INCOMPLETE_RESPONSE

    async with await client_for(
        lambda request: httpx.Response(200, json={"status": "failed", "output": []})
    ) as client:
        with pytest.raises(ProviderInvocationError) as provider_error:
            await OpenAIResponsesAdapter(
                client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
            ).invoke(provider_request(Protocol.RESPONSES))
    assert provider_error.value.category is ProviderFailureCategory.PROVIDER_ERROR


@pytest.mark.asyncio
async def test_schema_invalid_provider_result_is_normalized_as_malformed() -> None:
    body = {
        "id": "x" * 301,
        "status": "completed",
        "output": [{"type": "message", "content": [{"type": "output_text", "text": "{}"}]}],
    }
    async with await client_for(lambda request: httpx.Response(200, json=body)) as client:
        with pytest.raises(ProviderInvocationError) as caught:
            await OpenAIResponsesAdapter(
                client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
            ).invoke(provider_request(Protocol.RESPONSES))
    assert caught.value.category is ProviderFailureCategory.MALFORMED_RESPONSE


@pytest.mark.asyncio
async def test_non_utf8_provider_text_is_normalized_as_malformed() -> None:
    encoded_body = (
        b'{"status":"completed","output":[{"type":"message","content":'
        b'[{"type":"output_text","text":"\\ud800"}]}]}'
    )
    async with await client_for(
        lambda request: httpx.Response(200, content=encoded_body)
    ) as client:
        with pytest.raises(ProviderInvocationError) as caught:
            await OpenAIResponsesAdapter(
                client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
            ).invoke(provider_request(Protocol.RESPONSES))
    assert caught.value.category is ProviderFailureCategory.MALFORMED_RESPONSE


@pytest.mark.asyncio
async def test_injected_client_uses_profile_timeout() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.extensions["timeout"] == {
            "connect": 60.0,
            "read": 60.0,
            "write": 60.0,
            "pool": 60.0,
        }
        return httpx.Response(
            200,
            json={
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "{}"}],
                    }
                ],
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler), timeout=None) as client:
        await OpenAIResponsesAdapter(
            client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
        ).invoke(provider_request(Protocol.RESPONSES))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("adapter_type", "protocol", "body"),
    [
        pytest.param(
            OpenAIResponsesAdapter,
            Protocol.RESPONSES,
            {
                "id": "response-without-model",
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "{}"}],
                    }
                ],
            },
            id="responses",
        ),
        pytest.param(
            AnthropicMessagesAdapter,
            Protocol.MESSAGES,
            {
                "id": "message-without-model",
                "content": [{"type": "text", "text": "{}"}],
                "stop_reason": "end_turn",
            },
            id="messages",
        ),
        pytest.param(
            OpenAICompatibleChatAdapter,
            Protocol.CHAT_COMPLETIONS,
            {
                "id": "chat-without-model",
                "choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}],
            },
            id="chat-completions",
        ),
    ],
)
async def test_unset_temperature_is_omitted_and_observed_model_is_optional(
    adapter_type: (
        type[OpenAIResponsesAdapter]
        | type[AnthropicMessagesAdapter]
        | type[OpenAICompatibleChatAdapter]
    ),
    protocol: Protocol,
    body: dict[str, object],
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert "temperature" not in payload
        assert "reasoning" not in payload
        assert "output_config" not in payload
        assert "thinking" not in payload
        assert "providerOptions" not in payload
        return httpx.Response(200, json=body)

    async with await client_for(handler) as client:
        result = await adapter_type(
            client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
        ).invoke(provider_request(protocol, effort=None, temperature=None))

    assert result.observed_model is None


def test_provider_request_omits_absent_structured_output_from_serialization() -> None:
    request = provider_request(Protocol.MESSAGES, effort=None, temperature=None)
    assert "output_json_schema" not in request.model_dump(mode="json")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("adapter_type", "protocol", "forbidden_key"),
    [
        pytest.param(
            OpenAIResponsesAdapter,
            Protocol.RESPONSES,
            "max_output_tokens",
            id="responses",
        ),
        pytest.param(
            OpenAICompatibleChatAdapter,
            Protocol.CHAT_COMPLETIONS,
            "max_tokens",
            id="chat-completions",
        ),
    ],
)
async def test_unset_optional_generation_controls_are_not_invented(
    adapter_type: type[OpenAIResponsesAdapter] | type[OpenAICompatibleChatAdapter],
    protocol: Protocol,
    forbidden_key: str,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        assert forbidden_key not in payload
        assert "temperature" not in payload
        assert "reasoning" not in payload
        if protocol is Protocol.RESPONSES:
            body = {
                "status": "completed",
                "output": [
                    {
                        "type": "message",
                        "content": [{"type": "output_text", "text": "{}"}],
                    }
                ],
            }
        else:
            body = {"choices": [{"message": {"content": "{}"}, "finish_reason": "stop"}]}
        return httpx.Response(200, json=body)

    async with await client_for(handler) as client:
        await adapter_type(client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}).invoke(
            provider_request(
                protocol,
                effort=None,
                temperature=None,
                max_output_tokens=None,
            )
        )


@pytest.mark.asyncio
async def test_anthropic_requires_explicit_max_tokens() -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200)

    async with await client_for(handler) as client:
        with pytest.raises(ProviderInvocationError) as caught:
            await AnthropicMessagesAdapter(
                client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
            ).invoke(
                provider_request(
                    Protocol.MESSAGES,
                    effort=None,
                    temperature=None,
                    max_output_tokens=None,
                )
            )
    assert caught.value.category is ProviderFailureCategory.CONFIGURATION
    assert not called


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("adapter_type", "protocol", "body", "expected"),
    [
        pytest.param(
            AnthropicMessagesAdapter,
            Protocol.MESSAGES,
            {
                "content": [{"type": "text", "text": "{}"}],
                "stop_reason": "tool_use",
            },
            ProviderFailureCategory.PROVIDER_ERROR,
            id="messages-tool-use",
        ),
        pytest.param(
            AnthropicMessagesAdapter,
            Protocol.MESSAGES,
            {
                "content": [{"type": "text", "text": "{}"}],
                "stop_reason": "pause_turn",
            },
            ProviderFailureCategory.PROVIDER_ERROR,
            id="messages-pause-turn",
        ),
        pytest.param(
            OpenAICompatibleChatAdapter,
            Protocol.CHAT_COMPLETIONS,
            {"choices": [{"message": {"content": "{}"}, "finish_reason": "tool_calls"}]},
            ProviderFailureCategory.PROVIDER_ERROR,
            id="chat-tool-calls",
        ),
        pytest.param(
            OpenAICompatibleChatAdapter,
            Protocol.CHAT_COMPLETIONS,
            {"choices": [{"message": {"content": "{}"}, "finish_reason": "content_filter"}]},
            ProviderFailureCategory.PROVIDER_ERROR,
            id="chat-content-filter",
        ),
    ],
)
async def test_nonterminal_provider_stop_reasons_do_not_complete(
    adapter_type: type[AnthropicMessagesAdapter] | type[OpenAICompatibleChatAdapter],
    protocol: Protocol,
    body: dict[str, object],
    expected: ProviderFailureCategory,
) -> None:
    async with await client_for(lambda request: httpx.Response(200, json=body)) as client:
        with pytest.raises(ProviderInvocationError) as caught:
            await adapter_type(
                client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
            ).invoke(provider_request(protocol, effort=None))
    assert caught.value.category is expected


@pytest.mark.asyncio
async def test_anthropic_empty_terminal_response_reaches_subject_output_boundary() -> None:
    body = {
        "id": "empty-message",
        "content": [],
        "stop_reason": "end_turn",
        "usage": {"input_tokens": 2, "output_tokens": 0},
    }
    async with await client_for(lambda request: httpx.Response(200, json=body)) as client:
        result = await AnthropicMessagesAdapter(
            client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
        ).invoke(provider_request(Protocol.MESSAGES))
    assert result.public_output_text == ""
    assert result.stop_reason == "end_turn"


@pytest.mark.asyncio
async def test_redirect_is_not_followed_even_when_injected_client_enables_it() -> None:
    attempts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        attempts.append(str(request.url))
        if len(attempts) == 1:
            return httpx.Response(
                302,
                headers={
                    "location": "https://attacker.invalid/collect",
                    "request-id": "redirect-request-id",
                },
            )
        raise AssertionError("redirect target must never be requested")

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), follow_redirects=True
    ) as client:
        with pytest.raises(ProviderInvocationError) as caught:
            await AnthropicMessagesAdapter(
                client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
            ).invoke(provider_request(Protocol.MESSAGES))

    assert caught.value.category is ProviderFailureCategory.HTTP_ERROR
    assert caught.value.status_code == 302
    assert caught.value.request_id == "redirect-request-id"
    assert attempts == ["https://api.anthropic.test/v1/messages"]


@pytest.mark.asyncio
async def test_oversized_provider_response_is_rejected_before_json_parsing() -> None:
    oversized = b"{" + b"x" * 2_000_001
    async with await client_for(
        lambda request: httpx.Response(
            200,
            content=oversized,
            headers={"x-request-id": "oversized-request-id"},
        )
    ) as client:
        with pytest.raises(ProviderInvocationError) as caught:
            await OpenAIResponsesAdapter(
                client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
            ).invoke(provider_request(Protocol.RESPONSES))

    assert caught.value.category is ProviderFailureCategory.MALFORMED_RESPONSE
    assert caught.value.request_id == "oversized-request-id"
    assert caught.value.latency_ms is not None


class DelayedResponseStream(httpx.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        await asyncio.sleep(0.02)
        yield (
            b'{"status":"completed","output":[{"type":"message","content":'
            b'[{"type":"output_text","text":"{}"}]}]}'
        )


@pytest.mark.asyncio
async def test_provider_latency_includes_response_body_consumption() -> None:
    async with await client_for(
        lambda request: httpx.Response(200, stream=DelayedResponseStream())
    ) as client:
        result = await OpenAIResponsesAdapter(
            client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
        ).invoke(provider_request(Protocol.RESPONSES))
    assert result.latency_ms >= 10


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("adapter_type", "protocol"),
    [
        pytest.param(OpenAIResponsesAdapter, Protocol.RESPONSES, id="responses"),
        pytest.param(AnthropicMessagesAdapter, Protocol.MESSAGES, id="messages"),
    ],
)
async def test_unsupported_official_effort_fails_before_http(
    adapter_type: type[OpenAIResponsesAdapter] | type[AnthropicMessagesAdapter],
    protocol: Protocol,
) -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200)

    async with await client_for(handler) as client:
        with pytest.raises(ProviderInvocationError) as caught:
            await adapter_type(
                client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
            ).invoke(provider_request(protocol, effort="potato"))
    assert caught.value.category is ProviderFailureCategory.CONFIGURATION
    assert not called


@pytest.mark.asyncio
async def test_generic_effort_is_forwarded_without_transformation() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert json.loads(request.content)["reasoning_effort"] == "high"
        return httpx.Response(
            200,
            json={
                "model": "observed-model",
                "choices": [
                    {"message": {"content": "{}"}, "finish_reason": "stop"},
                ],
            },
        )

    async with await client_for(handler) as client:
        result = await OpenAICompatibleChatAdapter(
            client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
        ).invoke(provider_request(Protocol.CHAT_COMPLETIONS, effort="high"))
    assert result.observed_model == "observed-model"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("adapter_type", "protocol", "body", "expected_stop_reason"),
    [
        pytest.param(
            AnthropicMessagesAdapter,
            Protocol.MESSAGES,
            {
                "id": "messages-truncated-id",
                "model": "observed-model",
                "content": [{"type": "text", "text": "partial"}],
                "stop_reason": "max_tokens",
                "usage": {"input_tokens": 3, "output_tokens": 4000},
            },
            "max_tokens",
            id="messages-max-tokens",
        ),
        pytest.param(
            OpenAICompatibleChatAdapter,
            Protocol.CHAT_COMPLETIONS,
            {
                "id": "chat-truncated-id",
                "model": "observed-model",
                "choices": [{"message": {"content": "partial"}, "finish_reason": "length"}],
                "usage": {
                    "prompt_tokens": 3,
                    "completion_tokens": 4000,
                    "total_tokens": 4003,
                },
            },
            "length",
            id="chat-length",
        ),
    ],
)
async def test_output_budget_stop_reasons_preserve_public_result(
    adapter_type: type[AnthropicMessagesAdapter] | type[OpenAICompatibleChatAdapter],
    protocol: Protocol,
    body: dict[str, object],
    expected_stop_reason: str,
) -> None:
    async with await client_for(lambda request: httpx.Response(200, json=body)) as client:
        result = await adapter_type(
            client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
        ).invoke(provider_request(protocol, effort=None))
    assert result.public_output_text == "partial"
    assert result.observed_model == "observed-model"
    assert result.stop_reason == expected_stop_reason
    assert result.response_status == "truncated"
    assert result.usage.input_tokens == 3
    assert result.usage.output_tokens == 4000


@pytest.mark.asyncio
async def test_messages_context_window_exceeded_remains_incomplete_provider_failure() -> None:
    body = {
        "content": [{"type": "text", "text": "partial"}],
        "stop_reason": "model_context_window_exceeded",
    }
    async with await client_for(lambda request: httpx.Response(200, json=body)) as client:
        with pytest.raises(ProviderInvocationError) as caught:
            await AnthropicMessagesAdapter(
                client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
            ).invoke(provider_request(Protocol.MESSAGES, effort=None))
    assert caught.value.category is ProviderFailureCategory.INCOMPLETE_RESPONSE


@pytest.mark.parametrize(
    "filename",
    [
        pytest.param("openai-responses.example.yaml", id="responses"),
        pytest.param("anthropic-messages.example.yaml", id="messages"),
        pytest.param("openai-compatible.example.yaml", id="chat-completions"),
    ],
)
def test_example_profiles_contain_only_credential_references(filename: str) -> None:
    path = Path(__file__).resolve().parents[1] / "profiles" / filename
    content = path.read_text(encoding="utf-8")
    loaded = load_model_profile(path)

    assert loaded.credential_reference is not None
    assert loaded.credential_reference in content
    assert "api_key:" not in content.lower()
    assert "authorization:" not in content.lower()
    assert "x-api-key:" not in content.lower()
