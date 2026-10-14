"""Live external-CLI budget monitor; no product gate or Provider credentials."""

from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from contextlib import suppress
from pathlib import Path
from typing import Any
from uuid import uuid4

from scripts.coding_agent_eval import SPEC, docker, save


class ResponseMeter:
    def __init__(
        self, case: Path, *, network: str, image: str, initial: float, limit: float
    ) -> None:
        self.root = case / "meter"
        self.root.mkdir(mode=0o700)
        save(self.root / "config.json", {"initial_api_equivalent_usd": initial, "limit_usd": limit})
        self.name = "samescale-budget-" + uuid4().hex
        self.closed = threading.Event()
        self.stopped = False
        self.thread: threading.Thread | None = None
        docker(
            "run",
            "--detach",
            "--name",
            self.name,
            "--network",
            network,
            "--read-only",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges=true",
            "--memory",
            "128m",
            "--cpus",
            ".5",
            "--pids-limit",
            "32",
            "--mount",
            f"type=bind,src={self.root},dst=/meter",
            "--mount",
            f"type=bind,src={SPEC / 'budget_collector.py'},dst=/collector.py,readonly",
            image,
            "python",
            "-B",
            "/collector.py",
        )

    def arguments(self) -> list[str]:
        return [
            "-c",
            "otel.log_user_prompt=false",
            "-c",
            'otel.exporter={otlp-http={endpoint="http://'
            + self.name
            + ':4318/v1/logs",protocol="json"}}',
        ]

    def environment(self) -> dict[str, str]:
        return {
            "NO_PROXY": self.name + ",localhost,127.0.0.1",
            "no_proxy": self.name + ",localhost,127.0.0.1",
            "OTEL_BLRP_SCHEDULE_DELAY": "100",
            "OTEL_BLRP_MAX_EXPORT_BATCH_SIZE": "1",
        }

    def watch(self, agent_container: str) -> None:
        def monitor() -> None:
            while not self.closed.wait(0.05):
                if any(
                    (self.root / marker).exists() for marker in ("STOP_BUDGET", "STOP_METER_ERROR")
                ):
                    self.stopped = True
                    with suppress(subprocess.CalledProcessError):
                        docker("kill", agent_container)
                    return

        self.thread = threading.Thread(target=monitor)
        self.thread.start()

    def finish(self) -> dict[str, Any]:
        # Native exporter flushes on normal shutdown. No opaque telemetry body is persisted.
        time.sleep(0.15)
        self.closed.set()
        if self.thread:
            self.thread.join(timeout=5)
        docker("rm", "--force", self.name)
        values = (
            [json.loads(line) for line in (self.root / "usage.jsonl").read_text().splitlines()]
            if (self.root / "usage.jsonl").exists()
            else []
        )
        totals = {
            key: sum(v[key] for v in values)
            for key in (
                "input_tokens",
                "cached_input_tokens",
                "cache_write_input_tokens",
                "output_tokens",
            )
        }
        result = {
            "response_count": len(values),
            "usage": totals,
            "api_equivalent_usd": sum(v["api_equivalent_usd"] for v in values),
            "stopped_budget": (self.root / "STOP_BUDGET").exists(),
            "stopped_meter_error": (self.root / "STOP_METER_ERROR").exists(),
        }
        save(self.root / "receipt.json", result)
        return result
