"""Keyless product entrypoints; no database, credentials, or session reconstruction."""

# Localized Chinese product copy intentionally uses fullwidth punctuation.
# ruff: noqa: RUF001
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import JsonValue

from harnesslab.analyst.backend import ScriptedFakeAnalystBackend
from harnesslab.analyst.graph import AttributionGraph
from harnesslab.analyst.models import (
    AnalysisRequest,
    AnalysisScope,
    AttributionDraft,
    AttributionReport,
    EvidenceRef,
    FactAssertion,
    FinalDecision,
    HypothesisClaim,
    InspectFailureArgs,
    InspectFailureCall,
    InvestigationState,
    ProposedRegressionPlan,
    QueryRunsArgs,
    QueryRunsCall,
    StrictModel,
    ToolCall,
    ToolDecision,
    ToolEvidence,
    ToolName,
    VerifiedFactDraft,
)
from harnesslab.comparability.models import canonical_digest


class InvestigationExample(StrictModel):
    kind: Literal["offline_fake", "historical_real"]
    provenance: str
    report: AttributionReport
    next_steps: tuple[str, ...]
    metadata: dict[str, JsonValue]
    proposal: ProposedRegressionPlan | None = None


# Synthetic inputs deliberately have their own identities, separate from frozen real evidence.
DEMO_DATA: dict[str, JsonValue] = {
    "status": "failed_subject",
    "task": "demo-order-preserving-dedup",
    "input": ["b", "a", "b"],
    "expected": ["b", "a"],
    "observed": ["a", "b"],
    "verifier": "FAIL: output order differs from first occurrence order",
}


class DemoTools:
    async def execute(self, call: ToolCall) -> tuple[ToolEvidence, ...]:
        if not isinstance(call, QueryRunsCall | InspectFailureCall):
            raise ValueError("Unsupported demo tool")
        if isinstance(call, InspectFailureCall) and call.arguments.run_id != "demo-dedup-run":
            raise ValueError("Outside synthetic demo scope")
        return (
            ToolEvidence(
                ref=EvidenceRef(id="run:demo-dedup-run"),
                tool=call.name,
                digest_bindings=(canonical_digest(DEMO_DATA),),
                data=DEMO_DATA,
            ),
        )


async def offline_demo() -> InvestigationExample:
    """Run the bounded graph and fact validator with a Fake script and synthetic tools."""
    request = AnalysisRequest(
        experiment_id="offline-dedup-demo",
        question="去重任务为何失败？从输入、预期输出和实际输出定位证据，并提出回归检查。",
    )
    scope = AnalysisScope(
        experiment_id=request.experiment_id,
        plan_digest=canonical_digest(DEMO_DATA),
        task_ids=("demo-order-preserving-dedup",),
        cell_ids=(),
        run_ids=("demo-dedup-run",),
        ablation_ids=(),
    )
    reference = "run:demo-dedup-run"
    backend = ScriptedFakeAnalystBackend(
        (
            ToolDecision(
                calls=(
                    QueryRunsCall(name=ToolName.QUERY_RUNS, arguments=QueryRunsArgs(limit=1)),
                    InspectFailureCall(
                        name=ToolName.INSPECT_FAILURE,
                        arguments=InspectFailureArgs(run_id="demo-dedup-run"),
                    ),
                )
            ),
            FinalDecision(
                draft=AttributionDraft(
                    summary="合成案例中，去重后的元素顺序与预期不一致：预期 [b, a]，实际 [a, b]。"
                    "这定位了失败表现；仅凭输出不能证明具体代码根因。",
                    claims=(
                        VerifiedFactDraft(
                            assertions=tuple(
                                FactAssertion(
                                    evidence_ref=reference,
                                    tool=ToolName.INSPECT_FAILURE,
                                    field_path=(field,),
                                    expected_value=DEMO_DATA[field],
                                )
                                for field in ("input", "expected", "observed", "verifier")
                            )
                        ),
                        HypothesisClaim(
                            statement="实现可能在去重后排序，或使用了不保留首次出现顺序的数据结构。",
                            evidence_refs=(reference,),
                            additional_evidence_needed="检查实际补丁与执行轨迹，并增加非排序输入的回归用例。",
                        ),
                    ),
                    limitations=(
                        "这是固定脚本与合成工具数据，不是模型推理或真实工程运行。",
                        "没有源码或执行轨迹，不能确认根因，也不能推断模型能力排名。",
                        "本次结果不写入数据库；刷新后可重新运行，不能用于演示持久化恢复。",
                    ),
                )
            ),
        )
    )
    state = await AttributionGraph(backend, DemoTools()).advance(
        InvestigationState(
            request=request,
            scope=scope,
            max_decision_iterations=2,
            max_tool_calls=3,
        )
    )
    if state.report is None:
        raise ValueError("Demo did not produce a validated report")
    return InvestigationExample(
        kind="offline_fake",
        provenance="Fake / 离线合成案例 · 本次运行 · 无 Provider 调用",
        report=state.report,
        next_steps=(
            "补充 [b, a, b]、空数组与全部重复元素用例，检查首次出现顺序。",
            "审阅方案后，在独立授权范围内执行确定性验证；本演示不修改代码或执行回归。",
        ),
        metadata={
            "provider_requests": 0,
            "persistence": "none",
            "decisions": state.decision_iterations,
            "tools": state.tool_calls,
            "completed_calls": [call.call.name.value for call in state.completed_calls],
        },
    )


FROZEN_HASHES = {
    "report.json": "a71bf5bb8550828dfdcce38d79621f1c75cc2e1f5d21cc749e51c373ea957131",
    "session-summary.json": "10ffef60fd7ccdb7a4dc6173fcd12ffd3e880ff25884909a587d52a2ae2c0f52",
    "proposal.json": "27b8c407eb7e75a78e82f53a1b517051c799b8e43f649709728edd4d7d160448",
}


def historical_example(root: Path) -> InvestigationExample:
    directory = root / "docs/evidence/real-agent-smoke-v6"
    if not directory.is_dir():
        directory = (
            Path(__file__).resolve().parents[1]
            / "productization/distribution/docs/evidence/real-agent-smoke-v6"
        )
    contents: dict[str, bytes] = {}
    for name, digest in FROZEN_HASHES.items():
        raw = (directory / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest:
            raise ValueError("Frozen example digest mismatch")
        contents[name] = raw
    report = AttributionReport.model_validate_json(contents["report.json"])
    summary = json.loads(contents["session-summary.json"])
    proposal = ProposedRegressionPlan.model_validate_json(contents["proposal.json"])
    return InvestigationExample(
        kind="historical_real",
        provenance="历史真实调查 · 2026-09-09 冻结文件 · 只读，原数据库会话未恢复",
        report=report,
        proposal=proposal,
        next_steps=proposal.acceptance_criteria,
        metadata={
            "session_id": summary["session_id"],
            "profile_id": summary["profile_id"],
            "decisions": summary["decision_iterations"],
            "decision_limit": summary["decision_limit"],
            "tools": summary["tool_calls"],
            "tool_limit": summary["tool_limit"],
            "totals": summary["totals"],
            "report_digest": summary["report_digest"],
            "source_file": "docs/evidence/real-agent-smoke-v6/report.json",
            "source_file_sha256": FROZEN_HASHES["report.json"],
            "limit_correction": "原报告显示 4/8，实际会话上限为 4/4；保留原始报告字节。",
            "trace_limit": "该成功调查没有调用 inspect_trace；不能借用其他会话的轨迹。",
        },
    )
