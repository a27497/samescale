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
    ProviderInvocationError,
    ProviderRequest,
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
    assert result.endpoint == "https://api.openai.test/v1/responses"
    assert result.request_id == "resp-safe-id"
    assert result.usage.reasoning_tokens == 3
    assert result.attempt_count == 1
    assert "PRIVATE_OPENAI_REASONING" not in serialized
    assert FAKE_KEY not in serialized


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
    assert result.endpoint == "https://api.anthropic.test/v1/messages"
    assert result.request_id == "msg-safe-id"
    assert result.stop_reason == "end_turn"
    assert result.usage.total_tokens == 20
    assert "PRIVATE_ANTHROPIC_THINKING" not in serialized
    assert FAKE_KEY not in serialized


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
    assert result.endpoint == "https://compatible.test/v1/chat/completions"
    assert result.request_id == "chatcmpl-safe-id"
    assert result.stop_reason == "stop"
    assert result.usage.total_tokens == 15


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
        return httpx.Response(200, json=body)

    async with await client_for(handler) as client:
        result = await adapter_type(
            client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
        ).invoke(provider_request(protocol, effort=None, temperature=None))

    assert result.observed_model is None


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
async def test_generic_effort_is_rejected_instead_of_silently_transformed() -> None:
    async with await client_for(lambda request: httpx.Response(500)) as client:
        with pytest.raises(ProviderInvocationError) as caught:
            await OpenAICompatibleChatAdapter(
                client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
            ).invoke(provider_request(Protocol.CHAT_COMPLETIONS, effort="high"))
    assert caught.value.category is ProviderFailureCategory.CONFIGURATION


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("adapter_type", "protocol", "body"),
    [
        pytest.param(
            AnthropicMessagesAdapter,
            Protocol.MESSAGES,
            {
                "content": [{"type": "text", "text": "partial"}],
                "stop_reason": "max_tokens",
            },
            id="messages-max-tokens",
        ),
        pytest.param(
            OpenAICompatibleChatAdapter,
            Protocol.CHAT_COMPLETIONS,
            {"choices": [{"message": {"content": "partial"}, "finish_reason": "length"}]},
            id="chat-length",
        ),
    ],
)
async def test_truncated_provider_stop_reasons_are_incomplete(
    adapter_type: type[AnthropicMessagesAdapter] | type[OpenAICompatibleChatAdapter],
    protocol: Protocol,
    body: dict[str, object],
) -> None:
    async with await client_for(lambda request: httpx.Response(200, json=body)) as client:
        with pytest.raises(ProviderInvocationError) as caught:
            await adapter_type(
                client=client, environment={"TEST_PROVIDER_API_KEY": FAKE_KEY}
            ).invoke(provider_request(protocol, effort=None))
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
