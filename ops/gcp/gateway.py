"""Administrator-only, one-time Docker DNS setup; keep the existing QA gateway policy."""

from __future__ import annotations

import fcntl
import os
from collections.abc import Callable
from pathlib import Path

from ops.gcp.host import LIVE, STATE, DeployError, Host, write_private

GATEWAY = "samescale-grok-qa-gateway"
STATIC = "      proxy_pass http://api:8000;"
DYNAMIC = """      resolver 127.0.0.11 valid=5s ipv6=off;
      resolver_timeout 2s;
      set $qa_api_backend api:8000;
      proxy_pass http://$qa_api_backend;
      proxy_connect_timeout 3s;"""


def dynamic_config(text: str) -> str:
    if text.count(DYNAMIC) == 1 and text.count("proxy_pass ") == 1:
        return text
    if text.count(STATIC) != 1 or text.count("proxy_pass ") != 1 or "resolver " in text:
        raise DeployError("Unexpected gateway configuration; administrator review required")
    # No URI suffix: nginx forwards the original path and query. All other rules stay exact.
    return text.replace(STATIC, DYNAMIC)


def write_bound_file(path: Path, text: str) -> None:
    # Atomic replacement changes the inode and leaves the running bind mount on the old file.
    with path.open("r+") as file:
        file.seek(0)
        file.write(text)
        file.truncate()
        file.flush()
        os.fsync(file.fileno())


def apply_config(
    path: Path,
    validate: Callable[[], object],
    reload: Callable[[], object],
    healthy: Callable[[], bool],
) -> None:
    prior = path.read_text()
    candidate = dynamic_config(prior)
    if candidate == prior:
        validate()
        if not healthy():
            raise DeployError("Gateway is unhealthy")
        return
    write_bound_file(path, candidate)
    try:
        validate()
        reload()
        if not healthy():
            raise DeployError("Gateway health check failed after reload")
    except BaseException:
        write_bound_file(path, prior)
        validate()
        reload()
        if not healthy():
            raise DeployError("Gateway configuration recovery failed") from None
        raise


def main() -> int:
    if os.geteuid() != 0:
        raise DeployError("Gateway setup requires an administrator")
    os.umask(0o077)
    # The existing installer must have provisioned private state before this admin setup.
    if not STATE.is_dir() or STATE.stat().st_uid != 0 or STATE.stat().st_mode & 0o777 != 0o700:
        raise DeployError("Expected private root-owned deployment state")
    with (STATE / "deploy.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        host = Host()
        path = LIVE.with_name("nginx.conf")
        write_private(host.directory / "previous.nginx.conf", path.read_text())
        apply_config(
            path,
            lambda: host.run(["docker", "exec", GATEWAY, "nginx", "-t"]),
            lambda: host.run(["docker", "exec", GATEWAY, "nginx", "-s", "reload"]),
            host.healthy,
        )
        host.emit("GATEWAY_DYNAMIC_DNS_READY no_container_restart=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
