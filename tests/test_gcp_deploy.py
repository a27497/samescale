"""Offline deployment/authority contracts; no SSH, Docker, model or credential access."""

from __future__ import annotations

import copy
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

from ops.gcp.ci_gate import REPOSITORY, REQUIRED, NotReady, event_sha, require_ci, valid_sha
from ops.gcp.gateway import DYNAMIC, STATIC, apply_config, dynamic_config
from ops.gcp.host import NETWORK, DeployError, Host, Version, images_only, main, rollout

ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 40
OLD_IMAGE = "sha256:" + "b" * 64
NEW_IMAGE = "sha256:" + "c" * 64
COMPOSE = """services:
  postgres:
    image: postgres:pinned
    environment:
      POSTGRES_PASSWORD: test-placeholder-not-a-real-password
  migrate:
    image: prior:pinned
    command: [alembic, upgrade, head]
  api:
    image: prior:pinned
    env_file: [api.env]
    networks: [isolated]
  gateway:
    image: nginx:pinned
  tunnel:
    image: cloudflared:pinned
networks:
  isolated:
    internal: true
"""


class FakeGitHub:
    def __init__(self) -> None:
        self.main = SHA
        self.runs: dict[str, list[dict[str, Any]]] = {}
        self.jobs: dict[int, list[dict[str, Any]]] = {}
        self.requests: list[str] = []
        for index, (workflow, names) in enumerate(REQUIRED.items(), 1):
            self.runs[workflow] = [
                dict(
                    id=index,
                    run_attempt=2,
                    head_sha=SHA,
                    head_branch="main",
                    event="push",
                    status="completed",
                    conclusion="success",
                    path=f".github/workflows/{workflow}",
                    head_repository={"full_name": REPOSITORY},
                )
            ]
            self.jobs[index] = [
                dict(name=name, status="completed", conclusion="success") for name in names
            ]

    def __call__(self, path: str) -> dict[str, Any]:
        self.requests.append(path)
        if path == "/git/ref/heads/main":
            return {"object": {"sha": self.main}}
        if "/workflows/" in path:
            name = path.split("/workflows/")[1].split("/")[0]
            return {"workflow_runs": self.runs[name]}
        run = int(path.split("/runs/")[1].split("/")[0])
        assert "/attempts/2/jobs?" in path
        return {"jobs": self.jobs[run], "total_count": len(self.jobs[run])}


class FakeOperations:
    def __init__(self, failure: str = "") -> None:
        self.failure = failure
        self.events: list[str] = []
        self.image = OLD_IMAGE

    def migrate(self, candidate: Version) -> None:
        self.events.append("forward-migrate")
        if self.failure == "migration":
            raise DeployError("synthetic migration failure")

    def activate(self, version: Version) -> None:
        self.image = version.image
        self.events.append("activate-" + ("old" if version.image == OLD_IMAGE else "new"))
        if self.failure == "activate" and version.image == NEW_IMAGE:
            raise DeployError("synthetic partial activation")

    def healthy(self, *, rehearse: bool = False) -> bool:
        self.events.append("health-" + ("old" if self.image == OLD_IMAGE else "new"))
        return not (self.image == NEW_IMAGE and (rehearse or self.failure == "health"))

    def commit(self, candidate: Version, prior: Version) -> None:
        self.events.append("commit-receipt")
        if self.failure == "commit":
            raise DeployError("synthetic receipt failure")

    def emit(self, message: str) -> None:
        self.events.append(message)


class DeploymentTests(unittest.TestCase):
    def setUp(self) -> None:
        self.prior = Version("d" * 40, OLD_IMAGE, COMPOSE, "172.24.0.4")
        self.candidate = Version(SHA, NEW_IMAGE, images_only(COMPOSE, NEW_IMAGE), "172.24.0.4")

    def test_forward_migration_precedes_api_switch_and_receipt_waits_for_health(self) -> None:
        ops = FakeOperations()
        rollout(ops, self.candidate, self.prior)
        self.assertEqual(
            ops.events, ["forward-migrate", "activate-new", "health-new", "commit-receipt"]
        )
        self.assertEqual(ops.image, NEW_IMAGE)

    def test_failed_migration_does_not_touch_old_api_or_promote_a_receipt(self) -> None:
        ops = FakeOperations("migration")
        with self.assertRaises(DeployError):
            rollout(ops, self.candidate, self.prior)
        self.assertEqual(ops.events, ["forward-migrate"])
        self.assertEqual(ops.image, OLD_IMAGE)

    def test_health_partial_activation_and_receipt_failure_restore_old_image(self) -> None:
        for failure in ("health", "activate", "commit"):
            with self.subTest(failure=failure):
                ops = FakeOperations(failure)
                with self.assertRaises(DeployError):
                    rollout(ops, self.candidate, self.prior)
                self.assertEqual(ops.image, OLD_IMAGE)
                self.assertIn("activate-old", ops.events)
                self.assertIn("health-old", ops.events)
                self.assertTrue(any(event.startswith("ROLLBACK_HEALTHY") for event in ops.events))
                self.assertEqual(ops.events.count("forward-migrate"), 1)

    def test_rehearsal_uses_same_rollback_transaction_and_does_not_promote(self) -> None:
        ops = FakeOperations()
        with self.assertRaises(DeployError):
            rollout(ops, self.candidate, self.prior, rehearse=True)
        self.assertEqual(ops.image, OLD_IMAGE)
        self.assertNotIn("commit-receipt", ops.events)

    def test_failed_rollback_is_reported_not_a_success(self) -> None:
        class BrokenRollback(FakeOperations):
            def healthy(self, *, rehearse: bool = False) -> bool:
                return False

        ops = BrokenRollback()
        with self.assertRaisesRegex(DeployError, "Rollback failed"):
            rollout(ops, self.candidate, self.prior)
        self.assertFalse(any(event.startswith("ROLLBACK_HEALTHY") for event in ops.events))

    def test_manifest_changes_only_api_and_migrate_image_lines(self) -> None:
        rewritten = images_only(COMPOSE, NEW_IMAGE)
        self.assertEqual(rewritten.replace(NEW_IMAGE, "prior:pinned"), COMPOSE)
        self.assertEqual(rewritten.count(NEW_IMAGE), 2)
        self.assertIn("env_file: [api.env]", rewritten)

    def test_missing_duplicate_and_nonimmutable_image_inputs_refuse(self) -> None:
        for text, image in (
            (COMPOSE.replace("    image: prior:pinned\n", "", 1), NEW_IMAGE),
            (
                COMPOSE.replace("    image: prior:pinned\n", "    image: x\n    image: y\n", 1),
                NEW_IMAGE,
            ),
            (COMPOSE, "untrusted:latest"),
            (COMPOSE, NEW_IMAGE + "\nservices:"),
        ):
            with self.subTest(text=text, image=image), self.assertRaises(DeployError):
                images_only(text, image)

    def test_exact_current_main_ci_success_uses_explicit_latest_attempt(self) -> None:
        api = FakeGitHub()
        self.assertEqual(require_ci(SHA, api), [1, 2])
        self.assertEqual(api.requests.count("/git/ref/heads/main"), 2)
        self.assertTrue(any("/attempts/2/" in path for path in api.requests))

    def test_invalid_obsolete_or_newer_main_never_inherits_green_ci(self) -> None:
        for sha in ("main", "A" * 40, SHA + ";id", "e" * 40):
            with self.subTest(sha=sha), self.assertRaises(NotReady):
                require_ci(sha, FakeGitHub())
        api = FakeGitHub()

        def changed_main(path: str) -> dict[str, Any]:
            if len(api.requests) > 2:
                api.main = "f" * 40
            return api(path)

        with self.assertRaises(NotReady):
            require_ci(SHA, changed_main)

    def test_pending_failed_cancelled_or_missing_ci_refuses(self) -> None:
        for workflow in REQUIRED:
            for status, conclusion in (
                ("in_progress", None),
                ("completed", "failure"),
                ("completed", "cancelled"),
                ("completed", "skipped"),
            ):
                with self.subTest(workflow=workflow, conclusion=conclusion):
                    api = FakeGitHub()
                    api.runs[workflow][0].update(status=status, conclusion=conclusion)
                    with self.assertRaises(NotReady):
                        require_ci(SHA, api)
            api = FakeGitHub()
            api.runs[workflow] = []
            with self.assertRaises(NotReady):
                require_ci(SHA, api)

    def test_an_old_green_run_cannot_hide_a_new_failed_run(self) -> None:
        api = FakeGitHub()
        newer = copy.deepcopy(api.runs["ci.yml"][0])
        newer.update(id=999, conclusion="failure")
        api.runs["ci.yml"].append(newer)
        with self.assertRaises(NotReady):
            require_ci(SHA, api)

    def test_pr_fork_wrong_path_and_wrong_sha_receipts_refuse(self) -> None:
        for field, value in (
            ("event", "pull_request"),
            ("head_branch", "topic"),
            ("path", ".github/workflows/unrelated.yml"),
            ("head_sha", "f" * 40),
            ("head_repository", {"full_name": "other/samescale"}),
        ):
            api = FakeGitHub()
            api.runs["ci.yml"][0][field] = value
            with self.subTest(field=field), self.assertRaises(NotReady):
                require_ci(SHA, api)

    def test_missing_skipped_failed_duplicate_or_zero_jobs_refuse(self) -> None:
        for damage in ("missing", "skipped", "failure", "duplicate", "zero"):
            api = FakeGitHub()
            jobs = api.jobs[1]
            if damage == "missing":
                jobs.pop()
            elif damage == "zero":
                jobs.clear()
            elif damage == "duplicate":
                jobs.append(copy.deepcopy(jobs[0]))
            else:
                jobs[0]["conclusion"] = damage
            with self.subTest(damage=damage), self.assertRaises(NotReady):
                require_ci(SHA, api)

    def test_workflow_event_must_be_own_successful_main_push(self) -> None:
        event = {
            "repository": {"full_name": REPOSITORY},
            "workflow_run": FakeGitHub().runs["ci.yml"][0],
        }
        self.assertEqual(event_sha(event), SHA)
        for field, value in (
            ("event", "pull_request"),
            ("head_branch", "topic"),
            ("conclusion", "failure"),
            ("head_sha", "A" * 40),
            ("head_repository", {"full_name": "fork/samescale"}),
        ):
            broken = copy.deepcopy(event)
            broken["workflow_run"][field] = value
            with self.subTest(field=field), self.assertRaises(NotReady):
                event_sha(broken)

    def test_ssh_entry_refuses_shells_uploads_flags_and_injection_without_sudo(self) -> None:
        for command in (
            "",
            "id",
            "scp -t path",
            "deploy main",
            f"deploy {SHA}; id",
            f"deploy {SHA}\nid",
            f"deploy {SHA} extra",
            "deploy " + "A" * 40,
            f"deploy --rehearse-health-failure {SHA}",
        ):
            result = subprocess.run(
                ["sh", str(ROOT / "ops/gcp/ssh-entry.sh")],
                env={**os.environ, "SSH_ORIGINAL_COMMAND": command},
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 2, command)
            self.assertIn("Denied", result.stderr)
        self.assertTrue(valid_sha(SHA))

    def test_real_host_commands_scope_migration_and_replacement_to_two_services(self) -> None:
        class Recorder(Host):
            def __init__(self, directory: Path) -> None:
                self.run_id = "synthetic-contract"
                self.candidate_file = directory / "candidate.yml"
                self.original_stat = (directory / "compose.yml").stat()
                self.commands: list[list[str]] = []

            def emit(self, message: str) -> None:
                pass

            def run(self, args: Any, *, capture: bool = False, timeout: int = 180) -> str:
                self.commands.append(list(args))
                if list(args[:2]) == ["docker", "inspect"]:
                    return json.dumps(
                        {
                            "image": NEW_IMAGE,
                            "networks": {NETWORK: {"IPAddress": "172.24.0.4", "Aliases": ["api"]}},
                        }
                    )
                return ""

        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            live = directory / "compose.yml"
            live.write_text(COMPOSE)
            host = Recorder(directory)
            with patch("ops.gcp.host.LIVE", live):
                host.migrate(self.candidate)
                host.activate(self.candidate)
            calls = [args for args in host.commands if args[:2] == ["docker", "compose"]]
            self.assertEqual(len(calls), 4)
            self.assertEqual([args[-1] for args in calls], ["migrate", "api", "api", "api"])
            self.assertIn("--no-deps", calls[0])
            self.assertIn("--rm", calls[0])
            self.assertIn("--no-deps", calls[-1])
            self.assertIn("stop", calls[1])
            self.assertIn("rm", calls[2])
            self.assertIn("up", calls[3])
            for call in host.commands:
                for forbidden in ("down", "prune", "rmi", "downgrade", "restart"):
                    self.assertNotIn(forbidden, call)
            self.assertEqual(live.read_text(), self.candidate.compose)

    def test_workflow_has_environment_concurrency_main_barrier_and_no_manual_deploy(self) -> None:
        text = (ROOT / ".github/workflows/deploy-gcp.yml").read_text()
        self.assertIn("branches: [main]", text)
        self.assertIn("cancel-in-progress: false", text)
        self.assertIn("name: samescale-grok-qa", text)
        self.assertIn("Recheck main and CI after", text)
        self.assertIn("StrictHostKeyChecking=yes", text)
        self.assertIn("persist-credentials: false", text)
        self.assertNotIn("workflow_dispatch", text)
        self.assertNotIn("pull_request_target", text)
        self.assertNotIn("set -x", text)

    def test_ip_changes_on_promotion_and_failed_health_rollback(self) -> None:
        class MovingHost(Host):
            def __init__(self, directory: Path, fail: bool) -> None:
                self.original_stat = (directory / "compose.yml").stat()
                self.image = OLD_IMAGE
                self.ip = "172.24.0.4"
                self.next_ips = iter(["172.24.0.5", "172.24.0.6"])
                self.fail = fail
                self.messages: list[str] = []
                self.committed = False

            def run(self, args: Any, *, capture: bool = False, timeout: int = 180) -> str:
                return json.dumps(
                    {
                        "image": self.image,
                        "networks": {NETWORK: {"IPAddress": self.ip, "Aliases": ["api"]}},
                    }
                )

            def compose(self, file: Path, *args: str, timeout: int = 180) -> str:
                if args[0] == "up":
                    self.image = NEW_IMAGE if NEW_IMAGE in file.read_text() else OLD_IMAGE
                    self.ip = next(self.next_ips)
                return ""

            def emit(self, message: str) -> None:
                self.messages.append(message)

            def migrate(self, candidate: Version) -> None:
                pass

            def healthy(self, *, rehearse: bool = False) -> bool:
                return not (self.fail and self.image == NEW_IMAGE)

            def commit(self, candidate: Version, prior: Version) -> None:
                self.committed = True

        for fail in (False, True):
            with self.subTest(fail=fail), tempfile.TemporaryDirectory() as temp:
                live = Path(temp) / "compose.yml"
                live.write_text(COMPOSE)
                host = MovingHost(Path(temp), fail)
                with patch("ops.gcp.host.LIVE", live):
                    if fail:
                        with self.assertRaises(DeployError):
                            rollout(host, self.candidate, self.prior)
                    else:
                        rollout(host, self.candidate, self.prior)
                self.assertEqual(host.image, OLD_IMAGE if fail else NEW_IMAGE)
                self.assertEqual(host.ip, "172.24.0.6" if fail else "172.24.0.5")
                self.assertEqual(host.committed, not fail)
                self.assertTrue(any("ip=172.24.0.5 " in msg for msg in host.messages))
                if fail:
                    self.assertTrue(
                        any(msg.startswith("ROLLBACK_HEALTHY") for msg in host.messages)
                    )

    def test_gateway_change_preserves_policy_headers_and_uri_and_is_idempotent(self) -> None:
        text = "http {\n  if ($qa_allowed = 0) { return 403; }\n" + STATIC + "\n}"
        candidate = dynamic_config(text)
        self.assertEqual(candidate.replace(DYNAMIC, STATIC), text)
        self.assertIn("resolver 127.0.0.11 valid=5s ipv6=off;", candidate)
        self.assertIn("proxy_pass http://$qa_api_backend;", candidate)
        self.assertNotIn("proxy_pass http://$qa_api_backend/", candidate)
        self.assertEqual(dynamic_config(candidate), candidate)
        for bad in (
            text.replace(STATIC, "proxy_pass http://other;"),
            text + STATIC,
            "resolver 1.1.1.1;\n" + text,
        ):
            with self.assertRaises(DeployError):
                dynamic_config(bad)

    def test_failed_deploy_clears_recovered_receipt_even_when_rollback_ip_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            candidate = self.candidate
            prior = self.prior

            class Controller(FakeOperations):
                def __init__(self) -> None:
                    super().__init__("health")
                    self.run_id = "synthetic-contract"
                    self.candidate_file = directory / "candidate.yml"

                def recover(self) -> None:
                    pass

                def current(self) -> Version:
                    ip = "172.24.0.6" if "activate-old" in self.events else prior.ip
                    return Version(prior.sha, self.image, prior.compose, ip)

                def prepare(self, sha: str, version: Version, *, rehearse: bool) -> Version:
                    return candidate

                def begin(self, version: Version) -> None:
                    (directory / "pending.json").write_text("synthetic pending receipt")

            controller = Controller()
            directory.chmod(0o700)
            with (
                patch("ops.gcp.host.STATE") as state,
                patch("ops.gcp.host.Host", return_value=controller),
                patch("ops.gcp.host.os.geteuid", return_value=0),
                patch("ops.gcp.host.signal.signal"),
                patch("sys.stdin", io.StringIO("")),
                patch("sys.argv", ["controller", SHA]),
            ):
                state.stat.return_value.st_uid = 0
                state.stat.return_value.st_mode = 0o700
                state.__truediv__.side_effect = lambda name: directory / name
                self.assertEqual(main(), 1)
            self.assertEqual(controller.current().ip, "172.24.0.6")
            self.assertEqual(controller.image, OLD_IMAGE)
            self.assertFalse((directory / "pending.json").exists())

    def test_ip_independence_still_rejects_wrong_image_network_or_missing_alias(self) -> None:
        for damage in ("image", "network", "alias", "address"):
            with self.subTest(damage=damage), tempfile.TemporaryDirectory() as temp:
                live = Path(temp) / "compose.yml"
                live.write_text(COMPOSE)
                host = object.__new__(Host)
                host.original_stat = live.stat()
                actual: dict[str, Any] = {
                    "image": NEW_IMAGE,
                    "networks": {NETWORK: {"IPAddress": "172.24.0.5", "Aliases": ["api"]}},
                }
                if damage == "image":
                    actual["image"] = OLD_IMAGE
                elif damage == "network":
                    actual["networks"] = {}
                elif damage == "alias":
                    actual["networks"][NETWORK]["Aliases"] = None
                else:
                    actual["networks"][NETWORK]["IPAddress"] = ""
                with (
                    patch("ops.gcp.host.LIVE", live),
                    patch.object(host, "compose", return_value=""),
                    patch.object(host, "run", return_value=json.dumps(actual)),
                    patch.object(host, "emit"),
                    self.assertRaises(DeployError),
                ):
                    host.activate(self.candidate)

    def test_gateway_reload_preserves_bind_inode_and_restores_on_failure(self) -> None:
        for failure in ("", "validation", "reload", "health"):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temp:
                path = Path(temp) / "nginx.conf"
                path.write_text(STATIC)
                inode = path.stat().st_ino
                events: list[str] = []

                def stage(
                    name: str, events: list[str] = events, failure: str = failure, path: Path = path
                ) -> None:
                    events.append(name)
                    if failure == name and path.read_text() != STATIC:
                        raise DeployError("synthetic setup failure")

                def healthy(
                    events: list[str] = events, failure: str = failure, path: Path = path
                ) -> bool:
                    events.append("health")
                    return failure != "health" or path.read_text() == STATIC

                if failure:
                    with self.assertRaises(DeployError):
                        apply_config(
                            path, lambda: stage("validation"), lambda: stage("reload"), healthy
                        )
                    self.assertEqual(path.read_text(), STATIC)
                    self.assertEqual(events[-3:], ["validation", "reload", "health"])
                else:
                    apply_config(
                        path, lambda: stage("validation"), lambda: stage("reload"), healthy
                    )
                    self.assertEqual(path.read_text(), DYNAMIC)
                    self.assertEqual(events, ["validation", "reload", "health"])
                self.assertEqual(path.stat().st_ino, inode)


if __name__ == "__main__":
    unittest.main()
