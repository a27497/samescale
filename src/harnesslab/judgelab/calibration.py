from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from harnesslab.judgelab.fake import FakeJudgeProvider
from harnesslab.judgelab.models import JudgeCalibrationPlan, JudgeDefinition, JudgeSuite
from harnesslab.judgelab.persistence import (
    complete_calibration,
    enqueue_calibration,
    evaluation_records,
    pending_slots,
    persist_evidence_reference,
)
from harnesslab.judgelab.report import JudgeCalibrationReport, build_judge_report
from harnesslab.judgelab.runner import JudgeRunner
from harnesslab.model_lane.models import ProviderAdapter, ProviderRequest, ProviderResult
from harnesslab.model_lane.providers import adapter_for_profile


class LiveProviderAdapter:
    """Thin reuse bridge to the approved Phase D protocol adapters."""

    async def invoke(self, request: ProviderRequest) -> ProviderResult:
        return await adapter_for_profile(request).invoke(request)


def adapters_for_plan(plan: JudgeCalibrationPlan) -> dict[str, ProviderAdapter]:
    adapters: dict[str, ProviderAdapter] = {}
    for cell in plan.judge_cells:
        if cell.runner_contract == "phase-h-fake-good-v1":
            adapters[cell.id] = FakeJudgeProvider("GOOD")
        elif cell.runner_contract == "phase-h-fake-biased-v1":
            adapters[cell.id] = FakeJudgeProvider("BIASED")
        else:
            adapters[cell.id] = LiveProviderAdapter()
    return adapters


async def execute_calibration(
    session: AsyncSession,
    *,
    plan: JudgeCalibrationPlan,
    suite: JudgeSuite,
    definitions: Mapping[str, JudgeDefinition],
    artifact_root: Path,
    adapters: Mapping[str, ProviderAdapter] | None = None,
) -> JudgeCalibrationReport:
    await enqueue_calibration(session, plan)
    await session.commit()
    cases = {case.case_id: case for case in suite.public.cases}
    cells = {cell.id: cell for cell in plan.judge_cells}
    selected = dict(adapters) if adapters is not None else adapters_for_plan(plan)
    runner = JudgeRunner(artifact_root)
    for slot in await pending_slots(session, plan.calibration_id):
        cell = cells[slot.judge_cell_id]
        definition = definitions[cell.id]
        if definition.definition_digest != cell.definition_digest:
            raise ValueError(f"definition digest mismatch for Judge cell {cell.id}")
        result = await runner.run(
            slot=slot,
            case=cases[slot.case_id],
            suite_id=plan.suite_id,
            suite_version=plan.suite_version,
            suite_digest=plan.suite_digest,
            definition=definition,
            profile_identity=cell.profile_identity,
            profile=cell.model_profile,
            adapter=selected[cell.id],
        )
        await persist_evidence_reference(
            session,
            slot=slot,
            path=(str(result.artifact_path.resolve()) if result.artifact_path else None),
            evidence=result.evidence,
        )
        await session.commit()
        if result.artifact_path is None:
            raise RuntimeError("JudgeEvidence persistence failed with ARTIFACT_ERROR")
    records = await evaluation_records(session, plan.calibration_id)
    report = build_judge_report(
        plan=plan,
        suite=suite,
        definitions={key: value.model_dump(mode="json") for key, value in definitions.items()},
        records=records,
    )
    report_root = artifact_root / plan.calibration_id
    report_root.mkdir(parents=True, exist_ok=True)
    json_path = report_root / "report.json"
    markdown_path = report_root / "report.md"
    json_path.write_text(report.canonical_json() + "\n", encoding="utf-8")
    markdown_path.write_text(report.markdown(), encoding="utf-8")
    await complete_calibration(
        session,
        plan.calibration_id,
        report_json_path=str(json_path.resolve()),
        report_markdown_path=str(markdown_path.resolve()),
        report_digest=report.report_digest,
    )
    await session.commit()
    return report
