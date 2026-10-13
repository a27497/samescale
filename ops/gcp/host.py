"""Root-owned deploy controller for one existing Compose project; no general Docker access."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import secrets
import signal
import stat
import subprocess
import sys
import tarfile
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol

from ops.gcp.ci_gate import REPOSITORY, fetch_json, require_ci, valid_sha

LIVE = Path("/home/dev/.local/state/samescale-grok-qa-20261009/compose.yml")
STATE = Path("/var/lib/samescale-deploy")
PROJECT = "samescale-grok-qa"
API_CONTAINER = "samescale-grok-qa-api"
HEALTH = "http://127.0.0.1:18580/api/health"
NETWORK = "samescale-grok-qa_isolated"


class DeployError(RuntimeError):
    """Safe operational reason, without subprocess output or environment values."""


@dataclass(frozen=True)
class Version:
    sha: str
    image: str
    compose: str
    ip: str


class Operations(Protocol):
    def migrate(self, candidate: Version) -> None: ...
    def activate(self, version: Version) -> None: ...
    def healthy(self, *, rehearse: bool = False) -> bool: ...
    def commit(self, candidate: Version, prior: Version) -> None: ...
    def emit(self, message: str) -> None: ...


def rollout(ops: Operations, candidate: Version, prior: Version, *, rehearse: bool = False) -> None:
    # Migrate BEFORE stopping/replacing the API. Failure leaves both live file and old API alone.
    ops.migrate(candidate)
    try:
        ops.activate(candidate)
        if not ops.healthy(rehearse=rehearse):
            raise DeployError("Candidate failed health checks")
        ops.commit(candidate, prior)
    except BaseException:
        ops.emit("ROLLBACK_STARTED")
        try:
            ops.activate(prior)
            if not ops.healthy():
                raise DeployError(
                    "Rollback health check failed; administrator intervention required"
                )
        except BaseException as rollback_error:
            raise DeployError("Rollback failed; consult the private server log") from rollback_error
        ops.emit(f"ROLLBACK_HEALTHY revision={prior.sha} image={prior.image}")
        raise


def images_only(text: str, image: str) -> str:
    """Preserve other services and secret values byte-for-byte; reject unexpected manifests."""
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", image):
        raise DeployError("Expected a local immutable image ID")
    service = ""
    in_services = False
    found = {"api": 0, "migrate": 0}
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.rstrip() == "services:":
            in_services = True
            continue
        if line.strip() and not line.startswith((" ", "#")):
            in_services = False
        match = re.fullmatch(r"  ([a-zA-Z0-9_-]+):\s*\n?", line)
        if in_services and match:
            service = match[1]
        if in_services and service in found and re.match(r"    image:\s", line):
            found[service] += 1
            lines[index] = f"    image: {image}\n"
    if set(found.values()) != {1}:
        raise DeployError("Expected exactly one explicit api and migrate image")
    return "".join(lines)


def write_private(path: Path, text: str) -> None:
    temporary = path.with_name(path.name + ".tmp-" + secrets.token_hex(4))
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "w") as file:
            file.write(text)
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class Host:
    def __init__(self, github_token: str | None = None) -> None:
        self.fetch = lambda path: fetch_json(path, github_token)
        self.run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(4)
        self.directory = STATE / "runs" / self.run_id
        self.directory.mkdir(parents=True, mode=0o700)
        self.log = self.directory / "private.log"
        self.log.touch(mode=0o600)
        self.events = self.directory / "events.log"
        self.events.touch(mode=0o600)
        self.candidate_file = LIVE.parent / f".deploy-candidate-{self.run_id}.yml"
        self.original_stat = LIVE.stat()
        self.preexisting_api_ip = ""

    def emit(self, message: str) -> None:
        # Deliberately omit raw build/migration output from the SSH/GitHub stream.
        with self.events.open("a") as file:
            file.write(message + "\n")
        # SSH disconnect does not abandon an in-progress deployment.
        with suppress(BrokenPipeError):
            print(message, flush=True)

    def run(self, args: Sequence[str], *, capture: bool = False, timeout: int = 180) -> str:
        with (
            self.log.open("ab") as log,
            subprocess.Popen(
                list(args),
                stdout=subprocess.PIPE if capture else log,
                stderr=log,
                stdin=subprocess.DEVNULL,
                start_new_session=True,
                env={
                    **os.environ,
                    "GIT_TERMINAL_PROMPT": "0",
                    "GIT_CONFIG_GLOBAL": "/dev/null",
                    "GIT_CONFIG_NOSYSTEM": "1",
                },
            ) as process,
        ):
            try:
                output, _ = process.communicate(timeout=timeout)
            except BaseException:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                raise DeployError("Deployment command interrupted or timed out") from None
            if process.returncode:
                raise DeployError("Deployment command failed; consult the private server log")
            return (output or b"").decode()

    def compose(self, file: Path, *args: str, timeout: int = 180) -> str:
        return self.run(
            [
                "docker",
                "compose",
                "--project-name",
                PROJECT,
                "--file",
                str(file),
                "--env-file",
                "/dev/null",
                *args,
            ],
            timeout=timeout,
        )

    def current(self) -> Version:
        data = json.loads(
            self.run(
                [
                    "docker",
                    "inspect",
                    "--format",
                    '{"image":{{json .Image}},"networks":{{json .NetworkSettings.Networks}}}',
                    API_CONTAINER,
                ],
                capture=True,
            )
        )
        ip = data["networks"][NETWORK]["IPAddress"]
        if not ip or "api" not in data["networks"][NETWORK]["Aliases"]:
            raise DeployError("Unexpected API network/alias")
        self.preexisting_api_ip = ip
        revision = self.run(
            [
                "docker",
                "image",
                "inspect",
                "--format",
                '{{index .Config.Labels "org.opencontainers.image.revision"}}',
                data["image"],
            ],
            capture=True,
        ).strip()
        return Version(revision, data["image"], images_only(LIVE.read_text(), data["image"]), ip)

    def prepare(self, sha: str, prior: Version, *, rehearse: bool) -> Version:
        repository = STATE / "repository.git"
        if not repository.exists():
            self.run(["git", "init", "--bare", str(repository)])
        self.fetch_main(repository, sha)
        require_ci(sha, self.fetch)
        self.emit(f"BUILD_STARTED revision={sha}")
        source = self.directory / "source"
        source.mkdir(mode=0o700)
        archive = self.directory / "source.tar"
        self.run(
            ["git", "-C", str(repository), "archive", "--format=tar", f"--output={archive}", sha]
        )
        with tarfile.open(archive) as tar:
            tar.extractall(source, filter="data")
        tag = f"samescale-grok-qa:ci-{sha}"
        args = [
            "docker",
            "build",
            "--file",
            str(source / "docker/product/Dockerfile"),
            "--build-arg",
            f"SOURCE_REVISION={sha}",
        ]
        if rehearse:
            tag = f"samescale-grok-qa:rehearsal-{sha}-{self.run_id}"
            args += ["--label", f"io.samescale.deploy.rehearsal={self.run_id}"]
        self.run([*args, "--tag", tag, str(source)], timeout=1800)
        image = self.run(
            ["docker", "image", "inspect", "--format", "{{.Id}}", tag], capture=True
        ).strip()
        revision = self.run(
            [
                "docker",
                "image",
                "inspect",
                "--format",
                '{{index .Config.Labels "org.opencontainers.image.revision"}}',
                image,
            ],
            capture=True,
        ).strip()
        if revision != sha:
            raise DeployError("Built image revision does not match the requested commit")
        # Main/CI may change during the build; do not apply an obsolete image or a red rerun.
        self.fetch_main(repository, sha)
        require_ci(sha, self.fetch)
        self.emit(f"BUILD_READY revision={sha} image={image}")
        return Version(sha, image, images_only(prior.compose, image), prior.ip)

    def fetch_main(self, repository: Path, sha: str) -> None:
        self.run(
            [
                "git",
                "-C",
                str(repository),
                "fetch",
                "--no-tags",
                "--depth=1",
                f"https://github.com/{REPOSITORY}.git",
                "+refs/heads/main:refs/remotes/origin/main",
            ]
        )
        current = self.run(
            ["git", "-C", str(repository), "rev-parse", "refs/remotes/origin/main"], capture=True
        ).strip()
        if current != sha:
            raise DeployError("Requested commit is no longer main")

    def migrate(self, candidate: Version) -> None:
        write_private(self.candidate_file, candidate.compose)
        self.emit("FORWARD_MIGRATION_STARTED old_api_still_running=true")
        # One-off migrate, no dependencies. No PostgreSQL/gateway/tunnel lifecycle command.
        name = f"samescale-deploy-migrate-{self.run_id}"
        try:
            self.compose(
                self.candidate_file,
                "run",
                "--rm",
                "--no-deps",
                "--pull",
                "never",
                "--name",
                name,
                "migrate",
                timeout=600,
            )
        finally:
            # A stopped/disconnected Compose client must not leave our one-off migration running.
            remaining = self.run(
                [
                    "docker",
                    "container",
                    "ls",
                    "--all",
                    "--filter",
                    f"name=^{name}$",
                    "--format",
                    "{{.ID}}",
                ],
                capture=True,
            ).strip()
            if remaining:
                self.run(["docker", "container", "rm", "--force", remaining])
        self.emit("FORWARD_MIGRATION_PASSED")

    def activate(self, version: Version) -> None:
        # Remove ONLY the API endpoint before recreation so nginx's cached IP can be reused.
        # Explicitly check the result; do not reload/restart nginx to conceal an address change.
        self.compose(LIVE, "stop", "--timeout", "20", "api")
        self.compose(LIVE, "rm", "--force", "api")
        write_private(LIVE, version.compose)
        os.chown(LIVE, self.original_stat.st_uid, self.original_stat.st_gid)
        os.chmod(LIVE, stat.S_IMODE(self.original_stat.st_mode))
        self.compose(LIVE, "up", "--detach", "--no-deps", "--pull", "never", "api")
        actual = json.loads(
            self.run(
                [
                    "docker",
                    "inspect",
                    "--format",
                    '{"image":{{json .Image}},"networks":{{json .NetworkSettings.Networks}}}',
                    API_CONTAINER,
                ],
                capture=True,
            )
        )
        if (
            actual["image"] != version.image
            or actual["networks"][NETWORK]["IPAddress"] != version.ip
        ):
            raise DeployError("API image/address mismatch; refusing to change the gateway")
        self.emit(f"API_STARTED revision={version.sha} image={version.image} ip={version.ip}")

    def healthy(self, *, rehearse: bool = False) -> bool:
        url = HEALTH if not rehearse else "http://127.0.0.1:18580/api/deploy-rehearsal-unhealthy"
        for _ in range(3 if rehearse else 45):
            try:
                with urllib.request.urlopen(url, timeout=3) as response:
                    data = json.load(response)
                if data.get("status") == "ok" and data.get("database") == "ok":
                    self.emit("HEALTH_PASSED")
                    return True
            except urllib.error.HTTPError as exc:
                self.emit(f"HEALTH_RETRY http_status={exc.code}")
            except (OSError, ValueError):
                self.emit("HEALTH_RETRY unavailable_or_invalid")
            time.sleep(2)
        self.emit("HEALTH_FAILED")
        return False

    def commit(self, candidate: Version, prior: Version) -> None:
        backup = self.directory / "previous.compose.yml"
        write_private(backup, prior.compose)
        record = {
            "current": {"sha": candidate.sha, "image": candidate.image},
            "previous": {"sha": prior.sha, "image": prior.image, "compose": str(backup)},
        }
        write_private(STATE / "last-success.json", json.dumps(record, indent=2) + "\n")
        (STATE / "pending.json").unlink(missing_ok=True)
        self.emit(f"DEPLOY_HEALTHY revision={candidate.sha} image={candidate.image}")

    def begin(self, prior: Version) -> None:
        backup = self.directory / "interrupted-prior.compose.yml"
        write_private(backup, prior.compose)
        write_private(
            STATE / "pending.json",
            json.dumps(
                {"sha": prior.sha, "image": prior.image, "ip": prior.ip, "compose": str(backup)}
            )
            + "\n",
        )

    def recover(self) -> None:
        pending = STATE / "pending.json"
        if not pending.exists():
            return
        data = json.loads(pending.read_text())
        backup = Path(data["compose"])
        if not backup.is_relative_to(STATE / "runs") or backup.is_symlink():
            raise DeployError("Invalid interrupted-deployment receipt")
        prior = Version(data["sha"], data["image"], backup.read_text(), data["ip"])
        self.emit("RECOVERING_INTERRUPTED_DEPLOY no_schema_downgrade=true")
        self.activate(prior)
        if not self.healthy():
            raise DeployError("Interrupted-deployment recovery failed")
        pending.unlink()
        self.emit(f"INTERRUPTED_DEPLOY_RECOVERED revision={prior.sha}")

    def rollback(self, prior: Version) -> None:
        record = json.loads((STATE / "last-success.json").read_text())
        previous = record["previous"]
        backup = Path(previous["compose"])
        if not backup.is_relative_to(STATE / "runs") or backup.is_symlink():
            raise DeployError("Invalid previous-image receipt")
        target = Version(previous["sha"], previous["image"], backup.read_text(), prior.ip)
        self.run(["docker", "image", "inspect", target.image], capture=True)
        self.begin(prior)
        self.emit("MANUAL_IMAGE_ROLLBACK_STARTED no_schema_downgrade=true")
        try:
            self.activate(target)
            if not self.healthy():
                raise DeployError("Previous image failed health checks")
            self.commit(target, prior)
        except BaseException:
            self.activate(prior)
            if not self.healthy():
                raise DeployError("Manual rollback and recovery failed") from None
            raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", help="Full main SHA, or administrator-only rollback")
    parser.add_argument("--rehearse-health-failure", action="store_true")
    args = parser.parse_args()
    if os.geteuid() != 0 or (args.target != "rollback" and not valid_sha(args.target)):
        parser.error("Root controller requires a full SHA or the administrator rollback command")
    token_line = "" if sys.stdin.isatty() else sys.stdin.readline(2049)
    github_token = token_line.rstrip("\r\n")
    if github_token and re.fullmatch(r"[A-Za-z0-9_.=\-]{1,2048}", github_token) is None:
        parser.error("Invalid ephemeral GitHub token input")
    # Token arrives only through SSH stdin: no argument, environment forwarding, log or disk copy.
    os.umask(0o077)
    STATE.mkdir(mode=0o700, exist_ok=True)
    if STATE.stat().st_uid != 0 or stat.S_IMODE(STATE.stat().st_mode) != 0o700:
        raise DeployError("Deployment state must be private and root-owned")
    # A disconnected SSH session must not strand the API halfway through replacement.
    signal.signal(signal.SIGHUP, signal.SIG_IGN)

    def interrupt(_signum: int, _frame: object) -> None:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        raise DeployError("Deployment interrupted")

    signal.signal(signal.SIGTERM, interrupt)
    with (STATE / "deploy.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("BUSY: another server deployment is running")
            return 1
        host = Host(github_token or None)
        prior: Version | None = None
        try:
            host.recover()
            prior = host.current()
            if not host.healthy():
                raise DeployError("Existing API is unhealthy; refusing an unattended replacement")
            if args.target == "rollback":
                host.rollback(prior)
            else:
                state = STATE / "last-success.json"
                if not args.rehearse_health_failure and state.exists():
                    current = json.loads(state.read_text()).get("current", {})
                    if current == {"sha": args.target, "image": prior.image}:
                        require_ci(args.target, host.fetch)
                        host.emit(f"ALREADY_HEALTHY revision={args.target}")
                        return 0
                candidate = host.prepare(args.target, prior, rehearse=args.rehearse_health_failure)
                host.begin(prior)
                rollout(host, candidate, prior, rehearse=args.rehearse_health_failure)
            return 0
        except Exception as exc:
            # Do not print raw subprocess/GitHub/Compose errors, which may contain secret material.
            host.emit(f"DEPLOY_FAILED reason_type={type(exc).__name__} receipt={host.run_id}")
            return 1
        finally:
            host.candidate_file.unlink(missing_ok=True)
            # Keep the receipt if neither promotion nor recovery can be proved healthy.
            pending = STATE / "pending.json"
            if pending.exists() and prior is not None:
                try:
                    actual = host.current()
                    if actual.image == prior.image and actual.ip == prior.ip and host.healthy():
                        pending.unlink()
                except Exception:
                    host.emit("INTERRUPTED_RECEIPT_RETAINED")


if __name__ == "__main__":
    raise SystemExit(main())
