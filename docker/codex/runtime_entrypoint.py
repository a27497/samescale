#!/usr/bin/env python3
"""Materialize the private Codex relay URL in ephemeral container storage only."""

from __future__ import annotations

import ipaddress
import json
import os
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

BASE_URL_REFERENCE = "HARNESSLAB_GPT56_RELAY_BASE_URL"
RUNTIME_PROFILE = "harnesslab-runtime"
CODEX_HOME = Path("/tmp/codex-home")


def _validated_base_url(value: str) -> str:
    try:
        value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("invalid runtime provider URL") from exc
    parsed = urlsplit(value)
    path_parts = parsed.path.split("/")[1:]
    if path_parts and path_parts[-1] == "":
        path_parts.pop()
    if (
        parsed.scheme != "https"
        or parsed.netloc == ""
        or parsed.hostname is None
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.port not in {None, 443}
        or unquote(parsed.path) != parsed.path
        or any(part in {"", ".", ".."} for part in path_parts)
    ):
        raise ValueError("invalid runtime provider URL")
    hostname = parsed.hostname.casefold().rstrip(".")
    if hostname in {"localhost", "metadata.google.internal"} or hostname.endswith(
        (".localhost", ".local", ".internal")
    ):
        raise ValueError("invalid runtime provider URL")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise ValueError("invalid runtime provider URL")
    return f"https://{hostname}{parsed.path.rstrip('/')}"


def _materialize_runtime_profile(base_url: str) -> None:
    if os.environ.get("CODEX_HOME") != str(CODEX_HOME):
        raise RuntimeError("Codex runtime home is not isolated")
    CODEX_HOME.mkdir(mode=0o700, parents=True, exist_ok=True)
    profile_path = CODEX_HOME / f"{RUNTIME_PROFILE}.config.toml"
    config = "\n".join(
        (
            'model_provider = "harnesslab_gpt56_relay"',
            "[model_providers.harnesslab_gpt56_relay]",
            'name = "HarnessLab trusted GPT relay"',
            f"base_url = {json.dumps(base_url)}",
            'env_key = "HARNESSLAB_GPT56_RELAY_API_KEY"',
            'wire_api = "responses"',
            "supports_websockets = false",
            "",
        )
    )
    descriptor = os.open(profile_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(config)


def main() -> None:
    runtime_value = os.environ.get(BASE_URL_REFERENCE)
    profile_selected = "--profile" in sys.argv[1:] and RUNTIME_PROFILE in sys.argv[1:]
    if profile_selected != (runtime_value is not None):
        raise RuntimeError("Codex runtime provider configuration is incomplete")
    if runtime_value is not None:
        _materialize_runtime_profile(_validated_base_url(runtime_value))
    child_environment = dict(os.environ)
    child_environment.pop(BASE_URL_REFERENCE, None)
    os.execvpe("codex", ("codex", *sys.argv[1:]), child_environment)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("Codex runtime provider configuration failed", file=sys.stderr)
        raise SystemExit(78) from None
