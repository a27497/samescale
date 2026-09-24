from __future__ import annotations

import hashlib
import json
import shutil
from collections import Counter
from pathlib import Path

import httpx
import pytest

from harnesslab.analyst import api, real_backend
from harnesslab.analyst.comparison_showcase import CELL_IDS, SOURCE_HASHES, comparison_example
from harnesslab.api.app import create_app

ROOT = Path(__file__).resolve().parents[1]


def copy_sources(root: Path) -> None:
    for relative in SOURCE_HASHES:
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, destination)


def test_comparison_matches_frozen_rows_and_preserves_denominators() -> None:
    case = comparison_example(ROOT)
    rows = [
        json.loads(line)
        for line in (ROOT / "release/core-real-matrix-v6-analysis-dataset.jsonl")
        .read_text()
        .splitlines()
    ]
    for cell in case.cells:
        selected = [row for row in rows if row["cell_id"] == cell.cell_id]
        outcomes = Counter(row["effective_outcome"] for row in selected)
        assert cell.planned == len(selected) == 90
        assert cell.passed == outcomes["capability_pass"]
        assert cell.failed == outcomes["capability_fail"]
        assert cell.denominator == cell.passed + cell.failed == 86
        assert cell.infra_missing == outcomes["infra_failure"]
        assert cell.cancelled == outcomes["cancelled"]
        assert cell.primary_passed + cell.recovered_passes == cell.passed
        assert cell.explicit_cost_usd is None
    assert [cell.passed for cell in case.cells] == [83, 65]
    assert case.task_count == 18 and case.repeat_count == 5
    raw = case.comparison
    assert raw["causal_interpretation_permitted"] is False
    comparability = raw["comparability"]
    assert isinstance(comparability, dict)
    assert comparability["formal_eligible"] is False
    pairs = comparability["complete_pair_comparability"]
    assert isinstance(pairs, dict)
    assert pairs["PARTIALLY_COMPARABLE"] == 82
    statistics = raw["descriptive_statistics"]
    assert isinstance(statistics, dict)
    capability = statistics["capability"]
    assert isinstance(capability, dict)
    assert capability["complete_pairs"] == 82
    assert [(c.test_failures, c.budget_failures, c.output_failures) for c in case.cells] == [
        (2, 0, 1),
        (3, 18, 0),
    ]


def test_every_citation_is_an_exact_source_fragment_and_digest() -> None:
    case = comparison_example(ROOT)
    assert len({source.id for source in case.sources}) == len(case.sources) == 12
    assert all(source.path.startswith("release/") for source in case.sources)
    for source in case.sources:
        raw = (ROOT / source.path).read_bytes()
        assert source.sha256 == f"sha256:{hashlib.sha256(raw).hexdigest()}"
        value = json.loads(raw) if source.path.endswith(".json") else raw.decode()
        for token in source.pointer.split("/")[1:]:
            if isinstance(value, list):
                value = value[int(token)]
            else:
                assert isinstance(value, dict)
                value = value[token]
        assert value == source.data
    serialized = case.model_dump_json()
    assert "/home/" not in serialized
    assert "api_key" not in serialized.lower()


def test_specific_failure_keeps_actual_task_contract_and_unknown_cause() -> None:
    case = comparison_example(ROOT)
    failure = case.failure
    assert failure.cell_id == CELL_IDS[0]
    assert failure.status == "VERIFIED"
    assert failure.verifier_result == "capability_fail:verified_fail"
    assert "empty-key-rejected" in failure.observed_failure
    assert failure.root_cause is None
    assert failure.trace_status == "NOT_REPORTED"
    assert failure.both_member_bundles_verified is False
    assert failure.verifier["passed"] is False
    checks = failure.verifier["checks"]
    assert isinstance(checks, list)
    failed_checks = []
    for check in checks:
        assert isinstance(check, dict)
        if not check["passed"]:
            failed_checks.append(check["name"])
    assert failed_checks == ["empty-key-rejected"]


@pytest.mark.parametrize("relative", list(SOURCE_HASHES))
@pytest.mark.parametrize("corruption", ["missing", "changed"])
def test_comparison_fails_closed_on_missing_or_changed_source(
    tmp_path: Path, relative: str, corruption: str
) -> None:
    copy_sources(tmp_path)
    target = tmp_path / relative
    if corruption == "missing":
        target.unlink()
    else:
        target.write_bytes(target.read_bytes() + b" ")
    with pytest.raises((OSError, ValueError)):
        comparison_example(tmp_path)


def test_portable_source_projection_never_uses_current_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    distribution = tmp_path / "installed/distribution"
    copy_sources(distribution)
    monkeypatch.chdir(tmp_path)
    assert comparison_example(distribution) == comparison_example(ROOT)


async def test_endpoint_reads_existing_portable_distribution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    distribution = tmp_path / "installed/distribution"
    copy_sources(distribution)
    monkeypatch.setattr(api, "distribution_root", lambda: distribution)
    monkeypatch.chdir(tmp_path)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://test"
    ) as client:
        response = await client.get("/api/workbench/analyst/examples/comparison")
    assert response.status_code == 200
    assert response.json() == comparison_example(distribution).model_dump(mode="json")


async def test_workspace_read_without_database_or_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Comparison must not construct a database or a provider")

    monkeypatch.setattr(api, "create_engine", forbidden)
    monkeypatch.setattr(api, "AnalystSessions", forbidden)
    monkeypatch.setattr(real_backend, "RealAnalystBackend", forbidden)
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/workbench/analyst/examples/comparison")
        assert response.status_code == 200
        assert response.json() == comparison_example(ROOT).model_dump(mode="json")
        assert response.json()["kind"] == "historical_comparison"
        assert response.json()["read_only"] is True


async def test_endpoint_source_failure_has_no_fallback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    copy_sources(tmp_path)
    (tmp_path / next(iter(SOURCE_HASHES))).unlink()
    monkeypatch.setattr(api, "distribution_root", lambda: tmp_path)
    app = create_app()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/api/workbench/analyst/examples/comparison")
        assert response.status_code == 409
        assert "COMPARISON_EVIDENCE_UNAVAILABLE" in response.text
        assert str(tmp_path) not in response.text
        assert "historical_comparison" not in response.text
