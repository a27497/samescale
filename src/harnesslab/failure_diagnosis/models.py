# ruff: noqa: RUF001
from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

NOTICE = "诊断仅供参考，不影响验收"


class FrozenModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class EvidenceKind(StrEnum):
    TASK = "任务描述"
    DIFF = "最终代码差异"
    CHECK = "公开失败检查信息"
    SELF_REPORT = "Agent自报内容"


class EvidenceExcerpt(FrozenModel):
    id: str = Field(pattern=r"^[a-z][a-z0-9-]{0,79}$")
    kind: EvidenceKind
    reference: str = Field(min_length=1, max_length=500)
    text: str = Field(min_length=1, max_length=16000)


class PublicEvidence(FrozenModel):
    """Explicitly reviewed excerpts only; no arbitrary file/directory loading or hidden assets."""

    public_only_reviewed: Literal[True]
    excerpts: tuple[EvidenceExcerpt, ...] = Field(min_length=3, max_length=32)

    @model_validator(mode="after")
    def check_packet(self) -> PublicEvidence:
        if len({e.id for e in self.excerpts}) != len(self.excerpts):
            raise ValueError("duplicate evidence references")
        kinds = {e.kind for e in self.excerpts}
        if not {EvidenceKind.TASK, EvidenceKind.DIFF, EvidenceKind.CHECK} <= kinds:
            raise ValueError("task, diff and failed-check excerpts required")
        if sum(len(e.text.encode()) for e in self.excerpts) > 64000:
            raise ValueError("public input exceeds bounded evidence limit")
        return self


class FailedAcceptance(FrozenModel):
    status: Literal["VERIFIED_FAIL"]
    record_identity: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    receipt_digest: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    receipt_file_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    checks: int = Field(gt=0)
    passed_checks: int = Field(ge=0)
    failed_check_ordinals: tuple[int, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def failed_checks_exist(self) -> FailedAcceptance:
        if self.passed_checks >= self.checks:
            raise ValueError("independent failed checks required")
        if len(set(self.failed_check_ordinals)) != self.checks - self.passed_checks or any(
            n < 1 or n > self.checks for n in self.failed_check_ordinals
        ):
            raise ValueError("failed check ordinals do not match receipt")
        return self


class DiagnosisInput(FrozenModel):
    acceptance: FailedAcceptance
    evidence: PublicEvidence

    @model_validator(mode="after")
    def bind_checks(self) -> DiagnosisInput:
        allowed = {f"check:{n}" for n in self.acceptance.failed_check_ordinals}
        if any(
            e.reference not in allowed
            for e in self.evidence.excerpts
            if e.kind is EvidenceKind.CHECK
        ):
            raise ValueError("public check is not a failed check in the receipt")
        return self


class FailureCategory(StrEnum):
    EDGE_CASE = "边界条件遗漏"
    FORMAT = "输出格式不符"
    LOGIC = "逻辑或算法问题"
    RUNTIME = "运行时异常"
    BUILD = "构建或依赖问题"
    TIMEOUT = "超时"
    UNKNOWN = "原因未知"


class FailureExplanation(FrozenModel):
    category: FailureCategory
    evidence_references: tuple[str, ...] = Field(min_length=1, max_length=16)
    explanation: str = Field(min_length=1, max_length=4000)
    confidence: float = Field(ge=0, le=1)
    notice: Literal["诊断仅供参考，不影响验收"]
    affects_acceptance: Literal[False]


class FallbackReason(StrEnum):
    NONE = "未降级"
    DISABLED = "未启用模型"
    TIMEOUT = "模型调用超时"
    CALL_FAILED = "模型调用失败"
    INVALID_SCHEMA = "输出未通过结构校验"
    INVALID_REFERENCE = "输出引用不属于输入证据"
    FORBIDDEN_TOOL = "检测到禁止的工具调用"


class BackendObservation(FrozenModel):
    backend: str
    model: str | None
    cli_version: str | None
    invocation_count: int = Field(ge=0)
    tokens: dict[str, int] | None
    billing: Literal["ChatGPT 订阅额度，无单独计费", "未调用订阅模型"]


class DiagnosisArtifact(FrozenModel):
    schema_version: Literal[1] = 1
    input: DiagnosisInput
    explanation: FailureExplanation
    mode: Literal["模型辅助诊断", "规则降级", "诊断不可用"]
    fallback_reason: FallbackReason
    backend: BackendObservation
