from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from typing import Literal, cast

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from harnesslab.api.app import create_app
from harnesslab.api.workbench_dependencies import workbench_artifact_roots, workbench_session
from harnesslab.diagnosis.models import (
    AttributionKind,
    BadCaseExportRequest,
    CausalStrength,
    DiagnosisInput,
    DiagnosisReport,
    EvidenceOrigin,
    FailureClass,
    FailureScope,
    ToolCallEvidence,
    TraceEvidence,
    VerifierEvidence,
    WorkspaceDiffEvidence,
)
from harnesslab.diagnosis.service import (
    CLUSTER_DIMENSIONS,
    DiagnosisRequestError,
    build_badcase_export,
    build_diagnosis_report,
)

DIGEST = "sha256:" + "1" * 64


def _input(
    run_id: str,
    *,
    failure: FailureClass | None = FailureClass.TEST_FAILURE,
    origin: EvidenceOrigin = EvidenceOrigin.SYNTHETIC_QUALIFICATION,
    cell: str = "cell-a",
    outcome: str = "capability_fail",
    provider_failure: str | None = None,
    harness_failure: str | None = None,
    artifact_available: bool = True,
    workspace_pattern: str = "paths=1;statuses=modified:1;extensions=.py:1",
    protected: tuple[str, ...] = (),
    failed_codes: tuple[int, ...] = (),
    verifier_status: Literal["PASSED", "FAILED", "NOT_RUN", "NOT_REPORTED"] = "FAILED",
    verifier_subtype: str | None = None,
) -> DiagnosisInput:
    return DiagnosisInput(
        run_id=run_id,
        origin=origin,
        cell_id=cell,
        task_id="task-a",
        task_version="1.0.0",
        model="model-a",
        harness="codex",
        language="python",
        task_family="bug-fix",
        normalized_outcome=outcome,
        source_outcome="verified_fail",
        declared_failure_class=failure,
        provider_failure=provider_failure,
        harness_failure=harness_failure,
        artifact_available=artifact_available,
        evidence_identity=DIGEST if artifact_available else None,
        trace=TraceEvidence(
            status="REPORTED",
            coverage="FULL_STREAM",
            digest=DIGEST,
            pattern="coverage=FULL_STREAM;types=COMMAND_EXECUTION:1;failed_commands=0",
        ),
        workspace_diff=WorkspaceDiffEvidence(
            status="REPORTED",
            input_digest=DIGEST,
            output_digest="sha256:" + "2" * 64,
            pattern=workspace_pattern,
            protected_paths_changed=protected,
        ),
        tool_calls=ToolCallEvidence(
            status="REPORTED",
            count=1,
            pattern=f"count=1;failed={len(failed_codes)}",
            failed_exit_codes=failed_codes,
        ),
        verifier=VerifierEvidence(
            status=verifier_status,
            score=0,
            sandbox_status="succeeded",
            failure_subtype=verifier_subtype,
        ),
    )


@pytest.mark.parametrize("failure", tuple(FailureClass))
def test_exact_failure_taxonomy_is_stable_and_qualified_synthetically(
    failure: FailureClass,
) -> None:
    report = build_diagnosis_report(
        experiment_id="synthetic-taxonomy",
        plan_digest=DIGEST,
        inputs=(_input(f"synthetic-{failure.name.lower()}", failure=failure),),
    )

    run = report.cells[0].task_families[0].clusters[0].runs[0]
    assert run.failure_class is failure
    assert run.failure_scope is FailureScope.CAPABILITY
    assert {item.kind for item in run.attributions} == {
        AttributionKind.VERIFIED_FACT,
        AttributionKind.HYPOTHESIS,
    }


@pytest.mark.parametrize(
    ("item", "expected"),
    (
        (
            _input("provider-timeout", failure=None, provider_failure="timeout"),
            FailureClass.TIMEOUT,
        ),
        (
            _input("provider", failure=None, provider_failure="authentication"),
            FailureClass.PROVIDER_FAILURE,
        ),
        (
            _input("protocol", failure=None, harness_failure="protocol_error"),
            FailureClass.HARNESS_PROTOCOL_FAILURE,
        ),
        (
            _input("protected", failure=None, protected=("contract.txt",)),
            FailureClass.PROTECTED_FILE_MUTATION,
        ),
        (
            _input("no-change", failure=None, workspace_pattern="no-modification"),
            FailureClass.NO_MODIFICATION,
        ),
        (
            _input("tool", failure=None, failed_codes=(1,)),
            FailureClass.TOOL_FAILURE,
        ),
        (
            _input("artifact", failure=None, artifact_available=False),
            FailureClass.ARTIFACT_FAILURE,
        ),
        (
            _input(
                "verifier",
                failure=None,
                verifier_subtype="VERIFIER_PROCESS_START_FAILED",
            ),
            FailureClass.VERIFIER_FAILURE,
        ),
    ),
)
def test_structured_facts_drive_deterministic_classification(
    item: DiagnosisInput, expected: FailureClass
) -> None:
    report = build_diagnosis_report(
        experiment_id="structured-classification", plan_digest=DIGEST, inputs=(item,)
    )
    assert report.cells[0].task_families[0].clusters[0].failure_class is expected


def test_clustering_is_stable_and_preserves_capability_vs_infrastructure() -> None:
    real = _input(
        "real-run",
        origin=EvidenceOrigin.IMMUTABLE_EXPERIMENT,
        outcome="infra_failure",
    )
    synthetic = _input("synthetic-run")
    first = build_diagnosis_report(
        experiment_id="clustered",
        plan_digest=DIGEST,
        inputs=(synthetic, real),
    )
    second = build_diagnosis_report(
        experiment_id="clustered",
        plan_digest=DIGEST,
        inputs=(real, synthetic),
    )

    assert first == second
    assert first.cluster_dimensions == CLUSTER_DIMENSIONS
    scopes = {
        cluster.failure_scope
        for cell in first.cells
        for family in cell.task_families
        for cluster in family.clusters
    }
    assert scopes == {FailureScope.CAPABILITY, FailureScope.INFRASTRUCTURE}
    assert first.real_run_count == 1
    assert first.synthetic_run_count == 1


def test_controlled_ablation_strengthens_association_without_claiming_causality() -> None:
    report = build_diagnosis_report(
        experiment_id="ablation",
        plan_digest=DIGEST,
        inputs=(
            _input("base", cell="base"),
            _input("variant", cell="variant"),
        ),
        verified_ablation_contrast_run_ids=frozenset({"variant"}),
    )

    hypotheses = [
        attribution
        for cell in report.cells
        for family in cell.task_families
        for cluster in family.clusters
        for run in cluster.runs
        for attribution in run.attributions
        if attribution.kind is AttributionKind.HYPOTHESIS
    ]
    assert hypotheses
    by_statement = {item.statement: item for item in hypotheses}
    strengthened = by_statement[
        "The failure pattern is associated with a preregistered controlled-ablation pair."
    ]
    assert strengthened.causal_strength is CausalStrength.CONTROLLED_ABLATION_ASSOCIATION
    assert "does not by itself prove causality" in (strengthened.caveat or "")
    assert any(item.causal_strength is CausalStrength.CORRELATION_ONLY for item in hypotheses)


def test_badcase_export_never_promotes_synthetic_cases_to_real() -> None:
    report = build_diagnosis_report(
        experiment_id="badcases",
        plan_digest=DIGEST,
        inputs=(
            _input("real", origin=EvidenceOrigin.IMMUTABLE_EXPERIMENT),
            _input(
                "infra",
                origin=EvidenceOrigin.IMMUTABLE_EXPERIMENT,
                outcome="infra_failure",
            ),
            _input(
                "missing-artifact",
                origin=EvidenceOrigin.IMMUTABLE_EXPERIMENT,
                artifact_available=False,
            ),
            _input(
                "verifier-not-run",
                origin=EvidenceOrigin.IMMUTABLE_EXPERIMENT,
                verifier_status="NOT_RUN",
            ),
            _input("synthetic"),
        ),
    )

    real_only = build_badcase_export(report, BadCaseExportRequest())
    qualified = build_badcase_export(
        report, BadCaseExportRequest(include_synthetic_qualification=True)
    )

    assert real_only.real_case_count == 1
    assert real_only.synthetic_qualification_case_count == 0
    assert {item.run_id for item in real_only.cases} == {"real"}
    assert qualified.real_case_count == 1
    assert qualified.synthetic_qualification_case_count == 1
    assert {item.run_id for item in qualified.cases} == {"real", "synthetic"}
    assert {item.origin for item in qualified.cases} == {
        EvidenceOrigin.IMMUTABLE_EXPERIMENT,
        EvidenceOrigin.SYNTHETIC_QUALIFICATION,
    }
    real_case = next(item for item in qualified.cases if item.run_id == "real")
    assert real_case.evidence_identity == DIGEST
    assert real_case.verifier_status == "FAILED"
    with pytest.raises(DiagnosisRequestError, match="unknown failure cluster"):
        build_badcase_export(report, BadCaseExportRequest(cluster_ids=("sha256:" + "f" * 64,)))


async def test_diagnosis_api_precedes_productized_spa_mount(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = tmp_path / "dist"
    bundle.mkdir()
    (bundle / "index.html").write_text("<main>workbench</main>", encoding="utf-8")
    report = build_diagnosis_report(
        experiment_id="api-diagnosis",
        plan_digest=DIGEST,
        inputs=(_input("api-run", origin=EvidenceOrigin.IMMUTABLE_EXPERIMENT),),
    )

    async def fake_diagnose(*_args: object, **_kwargs: object) -> DiagnosisReport:
        return report

    async def fake_session() -> AsyncIterator[AsyncSession]:
        yield cast(AsyncSession, object())

    monkeypatch.setattr("harnesslab.api.routes.workbench.diagnose_experiment", fake_diagnose)
    application = create_app(workbench_dist=bundle)
    application.dependency_overrides[workbench_session] = fake_session
    application.dependency_overrides[workbench_artifact_roots] = lambda: (tmp_path,)
    async with AsyncClient(
        transport=ASGITransport(app=application), base_url="http://test"
    ) as client:
        response = await client.get("/api/workbench/experiments/api-diagnosis/diagnosis")
        export = await client.post(
            "/api/workbench/experiments/api-diagnosis/diagnosis/badcases",
            json={},
        )
        deep_link = await client.get("/diagnosis")

    assert response.status_code == 200
    assert response.json()["report_digest"] == report.report_digest
    assert export.status_code == 200
    assert export.json()["real_case_count"] == 1
    assert deep_link.status_code == 200
    assert "workbench" in deep_link.text
