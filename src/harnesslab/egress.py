from __future__ import annotations

import hashlib
import ipaddress
import json
from asyncio import CancelledError
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from harnesslab.contracts.provider import validate_provider_base_url
from harnesslab.sandbox.docker_cli import _DockerCLI
from harnesslab.sandbox.models import ImageIdentity
from harnesslab.sandbox.preflight import _docker_runtime_preflight
from harnesslab.sandbox.subprocess_loop import run_on_subprocess_loop

EGRESS_PROXY_VERSION = "1.0.0"
EGRESS_PROXY_IMAGE = f"harnesslab-egress-proxy:{EGRESS_PROXY_VERSION}"
EGRESS_PROXY_BASE = (
    "python:3.12.14-slim-bookworm@"
    "sha256:a116514e19457bcb7af7efe9c3dd0b9b71e85b317694e7882a1c52aa15a78134"
)
EGRESS_PROXY_LABEL = "com.harnesslab.role=provider-scoped-egress"
EGRESS_PROXY_SOURCE_DIGEST = (
    "sha256:6197201fdf9529cef8963c6c0de3b764608f057ab5507d2326afabb3d9d94592"
)
INTERNAL_NETWORK_DRIVER = "bridge"
INTERNAL_NETWORK_GATEWAY_MODE_OPTION = "com.docker.network.bridge.gateway_mode_ipv4"
INTERNAL_NETWORK_GATEWAY_MODE = "isolated"


class EgressDenied(ValueError):
    """A subject attempted a destination outside its frozen provider route."""


class EgressSecurityError(RuntimeError):
    """The effective Docker egress boundary was unsafe or could not be cleaned."""


class EgressNetworkIsolationUnavailable(EgressSecurityError):
    """The Docker Engine cannot prove the required host-gateway isolation."""


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


class NetworkSecurityAttestation(BaseModel):
    """Effective Docker network state recorded before a subject can start."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    network: str
    driver: Literal["bridge"]
    internal: Literal[True]
    enable_ipv6: Literal[False]
    gateway_mode_ipv4: Literal["isolated"]

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @property
    def digest(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_json().encode()).hexdigest()


class ProxySecurityAttestation(BaseModel):
    """Effective, inspected proxy state recorded before a subject can start."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    image: ImageIdentity
    privileged: bool
    read_only_rootfs: bool
    user: str
    cap_drop: tuple[str, ...]
    security_options: tuple[str, ...]
    published_ports: bool
    networks: tuple[str, str]
    internal_network: str
    internal_network_is_internal: bool
    internal_network_security: NetworkSecurityAttestation
    docker_socket_mounted: bool

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @property
    def digest(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_json().encode()).hexdigest()


class EgressProxyRuntime:
    """Build and inspect the one pinned proxy image without provider access."""

    async def ensure_image(self) -> ImageIdentity:
        return await run_on_subprocess_loop(self._ensure_image())

    async def _ensure_image(self) -> ImageIdentity:
        _, environment = await _docker_runtime_preflight()
        cli = _DockerCLI(output_limit=1_000_000, environment=environment)
        inspected = await cli.run(
            "image",
            "inspect",
            EGRESS_PROXY_IMAGE,
            "--format",
            "{{json .Config.Labels}}",
            check=False,
        )
        labels = (
            json.loads(inspected.stdout.decode())
            if inspected.returncode == 0 and inspected.stdout.strip()
            else {}
        )
        expected_labels = {
            "com.harnesslab.egress.version": EGRESS_PROXY_VERSION,
            "com.harnesslab.egress.base": EGRESS_PROXY_BASE.rsplit("@", 1)[1],
            "com.harnesslab.egress.source": EGRESS_PROXY_SOURCE_DIGEST,
        }
        if inspected.returncode != 0 or any(
            labels.get(key) != value for key, value in expected_labels.items()
        ):
            repository_root = Path(__file__).resolve().parents[2]
            dockerfile = repository_root / "docker" / "egress" / "Dockerfile"
            first_line = dockerfile.read_text(encoding="utf-8").splitlines()[0]
            if first_line != f"FROM {EGRESS_PROXY_BASE}":
                raise EgressSecurityError("egress proxy Dockerfile base identity drifted")
            await cli.run(
                "build",
                "--tag",
                EGRESS_PROXY_IMAGE,
                str(dockerfile.parent),
                timeout=600,
            )
        result = await cli.run(
            "image",
            "inspect",
            EGRESS_PROXY_IMAGE,
            "--format",
            "{{json .Id}}|{{json .RepoDigests}}",
        )
        image_id_raw, repo_digests_raw = result.stdout.decode().strip().split("|", 1)
        identity = ImageIdentity(
            reference=EGRESS_PROXY_IMAGE,
            image_id=json.loads(image_id_raw),
            repo_digests=tuple(json.loads(repo_digests_raw) or ()),
        )
        if identity.image_id == "sha256:" + "0" * 64:
            raise EgressSecurityError("egress proxy image identity was not inspected")
        labels_result = await cli.run(
            "image", "inspect", EGRESS_PROXY_IMAGE, "--format", "{{json .Config.Labels}}"
        )
        effective_labels = json.loads(labels_result.stdout.decode()) or {}
        if any(effective_labels.get(key) != value for key, value in expected_labels.items()):
            raise EgressSecurityError("egress proxy build identity labels drifted")
        return identity


@dataclass(frozen=True)
class ProviderScopedDockerBoundary:
    """Auditable Docker topology for one real Harness execution.

    The subject has only an internal network. The controlled proxy is the sole dual-homed
    component; the hidden verifier continues to use Docker network ``none``.
    """

    policy: EgressPolicy
    network_name: str
    proxy_name: str
    proxy_image: ImageIdentity
    outbound_network_name: str = "bridge"

    def __post_init__(self) -> None:
        if self.proxy_image.reference != EGRESS_PROXY_IMAGE:
            raise EgressSecurityError("unexpected egress proxy image reference")
        if self.proxy_image.image_id == "sha256:" + "0" * 64:
            raise EgressSecurityError("egress proxy requires an inspected non-zero image identity")
        if not self.network_name or self.network_name == self.outbound_network_name:
            raise EgressSecurityError("egress boundary requires distinct network identities")

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
        return (
            "network",
            "create",
            "--driver",
            INTERNAL_NETWORK_DRIVER,
            "--internal",
            "--ipv6=false",
            "-o",
            f"{INTERNAL_NETWORK_GATEWAY_MODE_OPTION}={INTERNAL_NETWORK_GATEWAY_MODE}",
            self.network_name,
        )

    def create_proxy_argv(self) -> tuple[str, ...]:
        return (
            "create",
            "--name",
            self.proxy_name,
            "--network",
            self.network_name,
            "--user",
            "10001:10001",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges=true",
            "--restart",
            "no",
            "--label",
            EGRESS_PROXY_LABEL,
            "--env",
            f"HARNESSLAB_ALLOWED_CONNECT_HOST={self.policy.allowed_hostname}",
            "--env",
            "HARNESSLAB_ALLOWED_CONNECT_PORT=443",
            self.proxy_image.reference,
        )

    def connect_proxy_outbound_argv(self) -> tuple[str, ...]:
        return ("network", "connect", self.outbound_network_name, self.proxy_name)

    def subject_proxy_environment(self) -> dict[str, str]:
        proxy = f"http://{self.proxy_name}:8080"
        return {"HTTPS_PROXY": proxy, "https_proxy": proxy, "NO_PROXY": ""}

    async def provision(self, cli: Any) -> ProxySecurityAttestation:
        await cli.run(*self.create_internal_network_argv())
        try:
            await cli.run(*self.create_proxy_argv())
            await cli.run(*self.connect_proxy_outbound_argv())
            await cli.run("start", self.proxy_name)
            return await self.attest_effective_security(cli)
        except BaseException:
            try:
                await self.cleanup(cli)
            except Exception as cleanup_exc:
                raise EgressSecurityError(
                    "egress provisioning failed and cleanup could not be verified"
                ) from cleanup_exc
            raise

    async def cleanup(self, cli: Any) -> None:
        failures: list[str] = []
        for action in (
            ("kill", self.proxy_name),
            ("rm", "--force", self.proxy_name),
            ("network", "rm", self.network_name),
        ):
            try:
                await cli.run(*action, check=False)
            except (Exception, CancelledError) as exc:
                failures.append(type(exc).__name__)
        try:
            proxy = await cli.run(
                "ps",
                "--all",
                "--quiet",
                "--no-trunc",
                "--filter",
                f"name=^/{self.proxy_name}$",
                check=False,
            )
            if proxy.returncode != 0 or proxy.stdout.strip():
                failures.append("proxy-present")
        except Exception as exc:
            failures.append(type(exc).__name__)
        try:
            network = await cli.run("network", "inspect", self.network_name, check=False)
            if network.returncode == 0:
                failures.append("network-present")
        except Exception as exc:
            failures.append(type(exc).__name__)
        if failures:
            raise EgressSecurityError(
                "egress cleanup was not verified: " + ",".join(sorted(failures))
            )

    async def attest_effective_security(self, cli: Any) -> ProxySecurityAttestation:
        network_security = await self.attest_internal_network(cli)
        template = (
            "{{json .Image}}|{{json .HostConfig.Privileged}}|"
            "{{json .HostConfig.ReadonlyRootfs}}|{{json .Config.User}}|"
            "{{json .HostConfig.CapDrop}}|{{json .HostConfig.SecurityOpt}}|"
            "{{json .HostConfig.PortBindings}}|{{json .NetworkSettings.Networks}}|"
            "{{json .Mounts}}"
        )
        result = await cli.run("inspect", self.proxy_name, "--format", template)
        values = [json.loads(value) for value in result.stdout.decode().strip().split("|")]
        if len(values) != 9:
            raise EgressSecurityError("unexpected egress proxy inspection output")
        (
            image_id,
            privileged,
            read_only,
            user,
            cap_drop,
            security_options,
            port_bindings,
            networks,
            mounts,
        ) = values
        actual_networks = tuple(sorted((networks or {}).keys()))
        expected_networks = tuple(sorted((self.network_name, self.outbound_network_name)))
        docker_socket = any(
            mount.get("Destination") == "/var/run/docker.sock" for mount in (mounts or ())
        )
        required = (
            image_id == self.proxy_image.image_id,
            not privileged,
            read_only,
            user == "10001:10001",
            "ALL" in (cap_drop or ()),
            "no-new-privileges=true" in (security_options or ()),
            not port_bindings,
            actual_networks == expected_networks,
            network_security.internal is True,
            not docker_socket,
        )
        if not all(required):
            raise EgressSecurityError("effective egress proxy security profile is not canonical")
        return ProxySecurityAttestation(
            image=self.proxy_image,
            privileged=bool(privileged),
            read_only_rootfs=bool(read_only),
            user=str(user),
            cap_drop=tuple(cap_drop or ()),
            security_options=tuple(security_options or ()),
            published_ports=bool(port_bindings),
            networks=expected_networks,
            internal_network=self.network_name,
            internal_network_is_internal=True,
            internal_network_security=network_security,
            docker_socket_mounted=False,
        )

    async def attest_internal_network(self, cli: Any) -> NetworkSecurityAttestation:
        template = "{{json .Driver}}|{{json .Internal}}|{{json .EnableIPv6}}|{{json .Options}}"
        result = await cli.run("network", "inspect", self.network_name, "--format", template)
        values = [json.loads(value) for value in result.stdout.decode().strip().split("|")]
        if len(values) != 4:
            raise EgressNetworkIsolationUnavailable(
                "EGRESS_NETWORK_ISOLATION_UNAVAILABLE: unexpected network inspection output"
            )
        driver, internal, enable_ipv6, options = values
        gateway_mode = (options or {}).get(INTERNAL_NETWORK_GATEWAY_MODE_OPTION)
        if (
            driver != INTERNAL_NETWORK_DRIVER
            or internal is not True
            or enable_ipv6 is not False
            or gateway_mode != INTERNAL_NETWORK_GATEWAY_MODE
        ):
            raise EgressNetworkIsolationUnavailable(
                "EGRESS_NETWORK_ISOLATION_UNAVAILABLE: effective network is not an "
                "IPv4 isolated internal bridge"
            )
        return NetworkSecurityAttestation(
            network=self.network_name,
            driver=driver,
            internal=internal,
            enable_ipv6=enable_ipv6,
            gateway_mode_ipv4=gateway_mode,
        )

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
    provider_url: str,
    *,
    network_name: str,
    proxy_name: str,
    proxy_image: ImageIdentity,
) -> ProviderScopedDockerBoundary:
    safe = validate_provider_base_url(provider_url)
    hostname = urlsplit(safe).hostname
    assert hostname is not None
    return ProviderScopedDockerBoundary(
        EgressPolicy(allowed_hostname=hostname), network_name, proxy_name, proxy_image
    )


async def preflight_egress_network_isolation(
    cli: Any | None = None,
) -> NetworkSecurityAttestation:
    """Create, inspect, remove, and verify an isolated bridge without provider traffic."""

    if cli is None:
        _, environment = await _docker_runtime_preflight()
        cli = _DockerCLI(output_limit=1_000_000, environment=environment)
    network_name = f"hl-egress-preflight-{uuid4().hex[:12]}"
    boundary = ProviderScopedDockerBoundary(
        EgressPolicy(allowed_hostname="preflight.invalid"),
        network_name,
        "hl-egress-preflight-unused-proxy",
        ImageIdentity(reference=EGRESS_PROXY_IMAGE, image_id="sha256:" + "1" * 64),
    )
    created = False
    attestation: NetworkSecurityAttestation | None = None
    failure: BaseException | None = None
    try:
        result = await cli.run(*boundary.create_internal_network_argv(), check=False)
        if result.returncode != 0:
            raise EgressNetworkIsolationUnavailable(
                "EGRESS_NETWORK_ISOLATION_UNAVAILABLE: Docker rejected isolated gateway mode"
            )
        created = True
        attestation = await boundary.attest_internal_network(cli)
    except BaseException as exc:
        failure = exc
    finally:
        try:
            removed = await cli.run("network", "rm", network_name, check=False)
            absent = await cli.run("network", "inspect", network_name, check=False)
            if absent.returncode == 0 or (created and removed.returncode != 0):
                failure = EgressNetworkIsolationUnavailable(
                    "EGRESS_NETWORK_ISOLATION_UNAVAILABLE: preflight cleanup was not verified"
                )
        except BaseException as exc:
            failure = EgressNetworkIsolationUnavailable(
                "EGRESS_NETWORK_ISOLATION_UNAVAILABLE: preflight cleanup was not verified"
            )
            failure.__cause__ = exc
    if failure is not None:
        if isinstance(failure, EgressNetworkIsolationUnavailable):
            raise failure
        raise EgressNetworkIsolationUnavailable(
            "EGRESS_NETWORK_ISOLATION_UNAVAILABLE: network attestation failed"
        ) from failure
    assert attestation is not None
    return attestation
