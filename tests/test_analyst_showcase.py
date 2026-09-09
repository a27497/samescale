from __future__ import annotations

import json
import shutil
from pathlib import Path

import httpx
import pytest

from harnesslab.analyst import api, real_backend, showcase
from harnesslab.analyst.models import (
    AttributionReport,
    ToolCall,
    ToolEvidence,
    resolve_fact_assertion,
)
from harnesslab.api.app import create_app

ROOT = Path(__file__).resolve().parents[1]


async def test_examples_are_database_and_provider_independent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Example must not open a database or construct a provider")

    monkeypatch.setattr(api, "create_engine", forbidden)
    monkeypatch.setattr(api, "AnalystSessions", forbidden)
    monkeypatch.setattr(real_backend, "RealAnalystBackend", forbidden)
    monkeypatch.setenv("HARNESSLAB_ANALYST_REAL_ENABLED", "1")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        first = await client.post("/api/workbench/analyst/examples/offline")
        second = await client.post("/api/workbench/analyst/examples/offline")
        assert first.status_code == second.status_code == 200
        assert first.json() == second.json()
        result = first.json()
        assert result["kind"] == "offline_fake"
        assert result["metadata"]["provider_requests"] == 0
        assert result["metadata"]["decisions"] == 2
        assert result["metadata"]["tools"] == 2
        report = AttributionReport.model_validate(result["report"])
        assert report.execution.status.value == "COMPLETED"
        assert report.verified_facts
        catalog = {entry.ref.id: entry for entry in report.evidence_catalog}
        for fact in report.verified_facts:
            for assertion in fact.assertions:
                assert resolve_fact_assertion(assertion, catalog[assertion.evidence_ref]) == (
                    assertion.expected_value
                )
        history = await client.get("/api/workbench/analyst/examples/historical")
        assert history.status_code == 200
        assert history.json()["kind"] == "historical_real"
        assert "session_id" not in history.json()
        assert history.json()["metadata"]["decision_limit"] == 4
        assert history.json()["report"] == json.loads(
            (ROOT / "docs/evidence/real-agent-smoke-v6/report.json").read_bytes()
        )


async def test_historical_corruption_fails_closed_without_replacing_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    destination = tmp_path / "docs/evidence/real-agent-smoke-v6"
    shutil.copytree(ROOT / "docs/evidence/real-agent-smoke-v6", destination)
    with (destination / "report.json").open("ab") as stream:
        stream.write(b" ")
    monkeypatch.setattr(api, "ROOT", tmp_path)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.get("/api/workbench/analyst/examples/historical")
        assert response.status_code == 409
        assert "HISTORICAL_EVIDENCE_UNAVAILABLE" in response.text
        assert (await client.post("/api/workbench/analyst/examples/offline")).status_code == 200


def test_packaged_historical_example_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shutil.copytree(
        ROOT / "docs/evidence/real-agent-smoke-v6",
        tmp_path / "harnesslab/productization/distribution/docs/evidence/real-agent-smoke-v6",
    )
    monkeypatch.setattr(showcase, "__file__", str(tmp_path / "harnesslab/analyst/showcase.py"))
    assert showcase.historical_example(tmp_path / "missing-source-root").kind == "historical_real"


async def test_demo_facts_fail_closed_when_tool_data_contradicts_script(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = showcase.DemoTools.execute

    async def contradict(self: showcase.DemoTools, call: ToolCall) -> tuple[ToolEvidence, ...]:
        values = await original(self, call)
        return tuple(
            value.model_copy(update={"data": {**value.data, "observed": ["unexpected"]}})
            for value in values
        )

    monkeypatch.setattr(showcase.DemoTools, "execute", contradict)
    with pytest.raises(ValueError, match="did not produce a validated report"):
        await showcase.offline_demo()
