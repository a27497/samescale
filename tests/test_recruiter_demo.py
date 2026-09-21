"""Recruiter export: provenance, safe projection, no execution, and reproducible freeze."""

from __future__ import annotations

import copy
import json
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Any

import pytest
from scripts.export_recruiter_demo import ROOT, S1, S2, S3, SOURCE_PINS, export, project, render

from harnesslab.analyst.offline_replay import ReplayError


@pytest.fixture(scope="module")
def public() -> dict[str, Any]:
    return project()


def test_verified_projection_keeps_partial_and_unknown(public: dict[str, Any]) -> None:
    left, right = public["cards"]
    assert (left["result"], left["passed_checks"], left["checks"]) == ("verified_pass", 20, 20)
    assert right["result"] == "NOT_VERIFIED" and right["verifier"] == "NOT_RUN"
    assert right["checks"] is None and right["changed_files"] == []
    assert right["failure_taxonomy"] == "execution_budget_exhausted"
    assert public["s1"]["attempted"] == 2 and public["s1"]["planned"] == 16
    assert [len(card["tools"]) for card in public["cards"]] == [13, 10]
    assert public["ci"]["tests"] == 65 and public["new_model_calls"] == 0


def test_export_uses_no_network_or_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> Any:
        pytest.fail("export attempted network or process execution")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    export(tmp_path / "demo")
    assert sorted(p.name for p in (tmp_path / "demo").iterdir()) == [
        "SHA256SUMS",
        "index.html",
        "public-evidence.json",
    ]
    for name in ("index.html", "public-evidence.json", "SHA256SUMS"):
        assert (tmp_path / "demo" / name).read_bytes() == (
            ROOT / "docs/recruiter/demo" / name
        ).read_bytes()


def test_shared_files_contain_only_public_projection(public: dict[str, Any]) -> None:
    page = render(public, (ROOT / "docs/recruiter/template.html").read_text())
    shared = page + json.dumps(public)
    for forbidden in (
        "/home/",
        "/workspace/",
        "HARNESSLAB_",
        "provider_route",
        "Authorization",
        "https://",
        "http://",
        "<script",
        "<iframe",
        "<form",
        "command_path_mentions",
    ):
        assert forbidden not in shared
    assert "default-src 'none'" in page
    assert "NOT_ESTABLISHED" in page and "14 NOT_RUN" in page
    for section in ("task", "configurations", "result", "trace", "diagnosis", "replay", "ci"):
        assert f'id="{section}"' in page and f'href="#{section}"' in page


def test_projected_text_is_html_escaped(public: dict[str, Any]) -> None:
    changed = copy.deepcopy(public)
    changed["cards"][0]["label"] = '</summary><script>alert("test")</script>'
    page = render(changed, (ROOT / "docs/recruiter/template.html").read_text())
    assert "<script>" not in page and "&lt;script&gt;" in page


@pytest.mark.parametrize(
    "path", [S1, f"{S3}/github-receipt.json", f"{S2}/representative-bundles.zip"]
)
def test_source_drift_cannot_produce_a_shareable_demo(tmp_path: Path, path: str) -> None:
    root = tmp_path / "repo"
    for name in [*SOURCE_PINS, f"{S2}/representative-bundles.zip"]:
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    target = root / path
    target.write_bytes(target.read_bytes() + b"changed")
    with pytest.raises(ReplayError):
        export(tmp_path / "output", root)
    assert not (tmp_path / "output").exists()


def test_export_never_overwrites_existing_output(tmp_path: Path) -> None:
    sentinel = tmp_path / "index.html"
    sentinel.write_text("existing user work")
    with pytest.raises(ReplayError):
        export(tmp_path)
    assert sentinel.read_text() == "existing user work"
