from __future__ import annotations

import ipaddress
import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator

from harnesslab.contracts.provider import validate_provider_base_url


class EgressDenied(ValueError):
    """A subject attempted a destination outside its frozen provider route."""


class ConnectionResult(StrEnum):
    ALLOWED = "allowed"
    DENIED = "denied"
    UPSTREAM_ERROR = "upstream_error"


class EgressPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    allowed_hostname: str = Field(min_length=1, max_length=253)
    allowed_port: Literal[443] = 443
    connect_only: bool = True
    tls_mitm: bool = False
    log_provider_content: bool = False

    @field_validator("allowed_hostname")
    @classmethod
    def hostname_is_external_dns(cls, value: str) -> str:
        safe = validate_provider_base_url(f"https://{value}")
        return urlsplit(safe).hostname or value

    def authorize_connect(
        self,
        hostname: str,
        port: int,
        *,
        resolved_addresses: Iterable[str] = (),
    ) -> None:
        candidate = hostname.casefold().rstrip(".")
        if port != 443:
            raise EgressDenied("only HTTPS CONNECT port 443 is allowed")
        try:
            ipaddress.ip_address(candidate)
        except ValueError:
            pass
        else:
            raise EgressDenied("IP-literal CONNECT targets are forbidden")
        if candidate != self.allowed_hostname:
            raise EgressDenied("CONNECT hostname is not the declared provider")
        for raw in resolved_addresses:
            address = ipaddress.ip_address(raw)
            if not address.is_global or address.is_link_local or address.is_loopback:
                raise EgressDenied("provider DNS resolved to local, private, or metadata space")


class SafeEgressEvent(BaseModel):
    """The complete proxy log schema; it has no headers, bodies, prompts, or model output."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    hostname: str
    port: int
    started_at: str
    ended_at: str
    bytes_upstream: int = Field(ge=0)
    bytes_downstream: int = Field(ge=0)
    result: ConnectionResult

    def json_line(self) -> str:
        return json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class ProviderScopedDockerBoundary:
    """Auditable Docker topology for one real Harness execution.

    The subject has only an internal network. The controlled proxy is the sole dual-homed
    component; the hidden verifier continues to use Docker network ``none``.
    """

    policy: EgressPolicy
    network_name: str
    proxy_name: str
    proxy_image: str = "harnesslab-egress-proxy:1"

    @property
    def verifier_network_mode(self) -> str:
        return "none"

    @property
    def subject_network_mode(self) -> str:
        return self.network_name

    @property
    def subject_can_bypass_proxy(self) -> bool:
        return False

    def create_internal_network_argv(self) -> tuple[str, ...]:
        return ("network", "create", "--internal", self.network_name)

    def create_proxy_argv(self) -> tuple[str, ...]:
        return (
            "create",
            "--name",
            self.proxy_name,
            "--network",
            self.network_name,
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges=true",
            "--env",
            f"HARNESSLAB_ALLOWED_CONNECT_HOST={self.policy.allowed_hostname}",
            "--env",
            "HARNESSLAB_ALLOWED_CONNECT_PORT=443",
            self.proxy_image,
        )

    def connect_proxy_outbound_argv(self) -> tuple[str, ...]:
        return ("network", "connect", "bridge", self.proxy_name)

    def subject_proxy_environment(self) -> dict[str, str]:
        proxy = f"http://{self.proxy_name}:8080"
        return {"HTTPS_PROXY": proxy, "https_proxy": proxy, "NO_PROXY": ""}

    async def provision(self, cli: Any) -> None:
        await cli.run(*self.create_internal_network_argv())
        try:
            await cli.run(*self.create_proxy_argv())
            await cli.run(*self.connect_proxy_outbound_argv())
            await cli.run("start", self.proxy_name)
        except Exception:
            await self.cleanup(cli)
            raise

    async def cleanup(self, cli: Any) -> None:
        await cli.run("kill", self.proxy_name, check=False)
        await cli.run("rm", "--force", self.proxy_name, check=False)
        await cli.run("network", "rm", self.network_name, check=False)

    def deterministic_fake_forward(
        self,
        hostname: str,
        port: int,
        payload: bytes,
        forward: Callable[[bytes], bytes],
    ) -> tuple[bytes, SafeEgressEvent]:
        """Exercise policy and byte forwarding with a local in-memory fake, never the network."""

        started = datetime.now(UTC).isoformat()
        self.policy.authorize_connect(hostname, port)
        response = forward(payload)
        ended = datetime.now(UTC).isoformat()
        return response, SafeEgressEvent(
            hostname=hostname,
            port=port,
            started_at=started,
            ended_at=ended,
            bytes_upstream=len(payload),
            bytes_downstream=len(response),
            result=ConnectionResult.ALLOWED,
        )


def boundary_for_provider_url(
    provider_url: str, *, network_name: str, proxy_name: str
) -> ProviderScopedDockerBoundary:
    safe = validate_provider_base_url(provider_url)
    hostname = urlsplit(safe).hostname
    assert hostname is not None
    return ProviderScopedDockerBoundary(
        EgressPolicy(allowed_hostname=hostname), network_name, proxy_name
    )
