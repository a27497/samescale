from __future__ import annotations

import asyncio
import json
import ssl
import subprocess
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from harnesslab.contracts.common import Protocol
from harnesslab.contracts.model import ModelProfile, ReasoningProfile
from harnesslab.model_lane.models import (
    MAX_PROVIDER_TRANSPORT_PHASES,
    ProviderFailureCategory,
    ProviderInvocationError,
    ProviderReadTimeoutStage,
    ProviderRequest,
    ProviderTransportPhase,
    ProviderTransportPhaseTrace,
    ProviderTransportTrace,
)
from harnesslab.model_lane.providers import (
    MAX_PROVIDER_TRANSPORT_TRACE_EVENTS,
    OpenAIResponsesAdapter,
    _ProviderTransportTraceCollector,
)

FAKE_KEY = "gate-d-transport-fake-key"
RAW_INFO_SENTINEL = "RAW-HTTPCORE-INFO-MUST-NEVER-PERSIST"


def _request(base_url: str, timeout: float = 0.05) -> ProviderRequest:
    return ProviderRequest(
        profile=ModelProfile(
            requested_model="requested-model",
            provider="local-test-provider",
            base_url=base_url,
            route="/responses",
            protocol=Protocol.RESPONSES,
            reasoning=ReasoningProfile(effort="low", max_output_tokens=20),
            request_timeout_seconds=timeout,
            credential_reference="TEST_PROVIDER_API_KEY",
        ),
        instructions="Return strict JSON only.",
        input="Use the visible fixture.",
    )


def _certificate(tmp_path: Path) -> tuple[Path, Path]:
    certificate = tmp_path / "localhost.crt"
    private_key = tmp_path / "localhost.key"
    completed = subprocess.run(
        (
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(private_key),
            "-out",
            str(certificate),
            "-subj",
            "/CN=127.0.0.1",
            "-days",
            "1",
        ),
        check=True,
        capture_output=True,
    )
    assert RAW_INFO_SENTINEL.encode() not in completed.stdout + completed.stderr
    return certificate, private_key


@asynccontextmanager
async def _delayed_tls_server(tmp_path: Path) -> AsyncIterator[str]:
    certificate, private_key = _certificate(tmp_path)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certificate, private_key)

    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            headers = await reader.readuntil(b"\r\n\r\n")
            content_length = 0
            for line in headers.split(b"\r\n"):
                if line.lower().startswith(b"content-length:"):
                    content_length = int(line.split(b":", 1)[1].strip())
            if content_length:
                await reader.readexactly(content_length)
            await asyncio.sleep(0.2)
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(handle, "127.0.0.1", 0, ssl=context)
    port = server.sockets[0].getsockname()[1]
    try:
        yield f"https://127.0.0.1:{port}"
    finally:
        server.close()
        await server.wait_closed()


class _ExplosiveRawInfo:
    def __init__(self) -> None:
        object.__setattr__(self, "_sentinel", RAW_INFO_SENTINEL)

    def __getattribute__(self, name: str) -> object:
        raise AssertionError(f"raw info was inspected: {name}")


@pytest.mark.asyncio
async def test_transport_trace_ignores_raw_info_and_persists_only_normalized_fields() -> None:
    collector = _ProviderTransportTraceCollector(0.0)
    await collector("connection.connect_tcp.started", _ExplosiveRawInfo())
    serialized = collector.snapshot().model_dump_json()  # type: ignore[union-attr]
    assert RAW_INFO_SENTINEL not in serialized
    assert set(json.loads(serialized)) == {"schema_version", "source", "source_version", "phases"}


@pytest.mark.asyncio
async def test_transport_phase_mapping_timing_and_http1_http2(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    moments = iter((10.001, 10.002, 10.003, 10.004, 10.005, 10.006, 10.007, 10.008))
    monkeypatch.setattr("harnesslab.model_lane.providers.time.perf_counter", lambda: next(moments))
    collector = _ProviderTransportTraceCollector(10.0)
    names = (
        "connection.connect_tcp.started",
        "connection.connect_tcp.complete",
        "connection.start_tls.started",
        "connection.start_tls.complete",
        "http11.send_request_headers.started",
        "http11.send_request_headers.complete",
        "http2.send_request_body.started",
        "http2.send_request_body.complete",
    )
    for name in names:
        await collector(name, _ExplosiveRawInfo())
    trace = collector.snapshot()
    assert trace is not None
    assert tuple(item.phase for item in trace.phases) == (
        ProviderTransportPhase.CONNECT_TCP,
        ProviderTransportPhase.START_TLS,
        ProviderTransportPhase.SEND_REQUEST_HEADERS,
        ProviderTransportPhase.SEND_REQUEST_BODY,
    )
    assert all(item.completed_ms is not None for item in trace.phases)
    assert tuple(item.started_ms for item in trace.phases) == tuple(
        sorted(item.started_ms for item in trace.phases)
    )


@pytest.mark.asyncio
async def test_real_httpx_httpcore_timeout_captures_completed_prior_phases_and_open_headers(
    tmp_path: Path,
) -> None:
    async with (
        _delayed_tls_server(tmp_path) as base_url,
        httpx.AsyncClient(verify=False, trust_env=False) as client,
    ):
        with pytest.raises(ProviderInvocationError) as caught:
            await OpenAIResponsesAdapter(
                client=client,
                environment={"TEST_PROVIDER_API_KEY": FAKE_KEY},
            ).invoke(_request(base_url))

    error = caught.value
    assert error.category is ProviderFailureCategory.TIMEOUT
    assert error.read_timeout_stage is ProviderReadTimeoutStage.WAITING_FOR_RESPONSE_HEADERS
    assert error.transport_trace is not None
    phases = {item.phase: item for item in error.transport_trace.phases}
    assert phases[ProviderTransportPhase.CONNECT_TCP].completed_ms is not None
    assert phases[ProviderTransportPhase.START_TLS].completed_ms is not None
    assert phases[ProviderTransportPhase.SEND_REQUEST_HEADERS].completed_ms is not None
    assert phases[ProviderTransportPhase.SEND_REQUEST_BODY].completed_ms is not None
    assert phases[ProviderTransportPhase.RECEIVE_RESPONSE_HEADERS].completed_ms is None
    assert RAW_INFO_SENTINEL not in error.transport_trace.model_dump_json()


@pytest.mark.asyncio
async def test_transport_trace_callback_failure_preserves_original_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail_callback(self: _ProviderTransportTraceCollector, name: str) -> None:
        raise RuntimeError("synthetic callback failure")

    monkeypatch.setattr(_ProviderTransportTraceCollector, "_record_event", fail_callback)
    async with (
        _delayed_tls_server(tmp_path) as base_url,
        httpx.AsyncClient(verify=False, trust_env=False) as client,
    ):
        with pytest.raises(ProviderInvocationError) as caught:
            await OpenAIResponsesAdapter(
                client=client,
                environment={"TEST_PROVIDER_API_KEY": FAKE_KEY},
            ).invoke(_request(base_url))
    assert caught.value.category is ProviderFailureCategory.TIMEOUT
    assert caught.value.transport_trace is None


@pytest.mark.asyncio
async def test_transport_trace_event_bound_fails_closed() -> None:
    collector = _ProviderTransportTraceCollector(0.0)
    for _ in range(MAX_PROVIDER_TRANSPORT_TRACE_EVENTS + 1):
        await collector("connection.connect_tcp.started", {})
    assert collector.snapshot() is None


def test_transport_trace_schema_rejects_bad_chronology_duplicates_and_phase_overflow() -> None:
    with pytest.raises(ValidationError):
        ProviderTransportPhaseTrace(
            phase=ProviderTransportPhase.CONNECT_TCP, started_ms=2, completed_ms=1
        )
    with pytest.raises(ValidationError):
        ProviderTransportTrace(
            phases=(
                ProviderTransportPhaseTrace(phase=ProviderTransportPhase.START_TLS, started_ms=2),
                ProviderTransportPhaseTrace(phase=ProviderTransportPhase.CONNECT_TCP, started_ms=1),
            )
        )
    with pytest.raises(ValidationError):
        ProviderTransportTrace(
            phases=tuple(
                ProviderTransportPhaseTrace(
                    phase=ProviderTransportPhase.CONNECT_TCP, started_ms=index
                )
                for index in range(MAX_PROVIDER_TRANSPORT_PHASES + 1)
            )
        )
