"""Natural A/candidate/1 failure remains bounded through read-only replay."""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Any

import pytest
from scripts.replay_d2 import ROOT, replay

from harnesslab.analyst.offline_replay import ReplayError


def test_natural_failure_two_read_only_replays(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("D2 replay attempted network or process execution")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    first = replay()
    second = replay()
    assert first == second
    assert first["original_episode"] == "NOT_VERIFIED"
    assert first["original_verifier"] == "NOT_RUN"
    assert first["saved_changed_files"] == 5
    assert (first["independent_verifier_passed"], first["independent_verifier_total"]) == (71, 75)
    assert first["model_root_cause"] == first["harness_root_cause"] == "NOT_ESTABLISHED"


def test_natural_failure_evidence_tamper_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    freeze = json.loads(
        (ROOT / "docs/evidence/d2-natural-failure-20260923/freeze.json").read_text()
    )
    for relative in ["d2-natural-failure-20260923/freeze.json", *freeze["source_pins"]]:
        source = ROOT / "docs/evidence" / relative
        target = root / "docs/evidence" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    report = (
        root / "docs/evidence/l1-a-candidate-offline-audit-20260921/verifier-evidence/report.json"
    )
    report.write_bytes(report.read_bytes() + b"tampered")
    with pytest.raises(ReplayError, match="D2 source drift"):
        replay(root)
