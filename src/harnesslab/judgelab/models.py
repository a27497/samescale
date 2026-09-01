from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from harnesslab.contracts.common import Identifier, Sha256Digest
from harnesslab.contracts.model import ModelProfile
from harnesslab.model_lane.models import ProviderError, ProviderFailureCategory, ProviderUsage


def canonical_json(value: BaseModel | dict[str, object]) -> str:
    raw = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    return json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value: BaseModel | dict[str, object]) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


class JudgeMode(StrEnum):
    LABEL = "LABEL"
    SCORE = "SCORE"
    PAIRWISE = "PAIRWISE"


class GoldSource(StrEnum):
    DETERMINISTIC_L0 = "DETERMINISTIC_L0"
    CURATED_HUMAN_L1 = "CURATED_HUMAN_L1"


class OrderVariant(StrEnum):
    ORIGINAL = "ORIGINAL"
    SWAPPED = "SWAPPED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class JudgeRunOutcome(StrEnum):
    JUDGED = "JUDGED"
    ABSTAINED = "ABSTAINED"
    JUDGE_OUTPUT_ERROR = "JUDGE_OUTPUT_ERROR"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    ARTIFACT_ERROR = "ARTIFACT_ERROR"


class JudgeOutputFailureKind(StrEnum):
    NON_UTF8 = "NON_UTF8"
    TOO_LARGE = "TOO_LARGE"
    NOT_BARE_JSON = "NOT_BARE_JSON"
    MALFORMED_JSON = "MALFORMED_JSON"
    DUPLICATE_KEY = "DUPLICATE_KEY"
    NOT_JSON_OBJECT = "NOT_JSON_OBJECT"
    PRIVATE_FIELD_PRESENT = "PRIVATE_FIELD_PRESENT"
    STRICT_SCHEMA_VALIDATION = "STRICT_SCHEMA_VALIDATION"
    LABEL_NOT_ALLOWED = "LABEL_NOT_ALLOWED"
    SCORE_INVARIANT = "SCORE_INVARIANT"
    SCORE_OUT_OF_RANGE = "SCORE_OUT_OF_RANGE"
    ABSTENTION_NOT_ALLOWED = "ABSTENTION_NOT_ALLOWED"
    JUSTIFICATION_TOO_LONG = "JUSTIFICATION_TOO_LONG"
    UNKNOWN = "UNKNOWN"


class QualificationStatus(StrEnum):
    QUALIFIED_FOR_SUITE = "QUALIFIED_FOR_SUITE"
    LIMITED = "LIMITED"
    NOT_QUALIFIED = "NOT_QUALIFIED"


class JudgeDefinition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    definition_id: Identifier
    version: str = Field(min_length=1, max_length=100)
    public_instruction: str = Field(min_length=1, max_length=10_000)
    supported_modes: tuple[JudgeMode, ...] = Field(min_length=1)
    output_schema_version: Literal[1] = 1
    maximum_public_justification_length: int = Field(ge=1, le=2_000)
    allow_abstention: bool
    pairwise_blinding_required: bool
    order_swap_policy: Literal["REQUIRED", "DISABLED"]
    private_reasoning_exclusion_policy: Literal["REJECT_PRIVATE_REASONING_FIELDS"]

    @field_validator("supported_modes")
    @classmethod
    def modes_are_unique(cls, value: tuple[JudgeMode, ...]) -> tuple[JudgeMode, ...]:
        if len(set(value)) != len(value):
            raise ValueError("duplicate supported Judge mode")
        return value

    def canonical_json(self) -> str:
        return canonical_json(self)

    @property
    def definition_digest(self) -> str:
        return digest(self)


class PublicCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: Identifier
    mode: JudgeMode
    question: str = Field(min_length=1, max_length=10_000)
    rubric: str = Field(min_length=1, max_length=10_000)
    candidate: str | None = Field(default=None, min_length=1, max_length=100_000)
    candidate_a: str | None = Field(default=None, min_length=1, max_length=100_000)
    candidate_b: str | None = Field(default=None, min_length=1, max_length=100_000)
    allowed_labels: tuple[str, ...] = ()
    score_min: float | None = None
    score_max: float | None = None
    metadata: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def mode_shape_is_strict(self) -> PublicCase:
        if self.mode is JudgeMode.LABEL:
            if self.candidate is None or len(self.allowed_labels) < 2:
                raise ValueError("LABEL requires candidate and at least two allowed labels")
            if len(set(self.allowed_labels)) != len(self.allowed_labels):
                raise ValueError("duplicate allowed label")
            if any(not label.strip() or label == "UNKNOWN" for label in self.allowed_labels):
                raise ValueError("allowed labels must be nonempty and exclude reserved UNKNOWN")
            if any(
                v is not None
                for v in (self.candidate_a, self.candidate_b, self.score_min, self.score_max)
            ):
                raise ValueError("LABEL contains fields for another mode")
        elif self.mode is JudgeMode.SCORE:
            if self.candidate is None or self.score_min is None or self.score_max is None:
                raise ValueError("SCORE requires candidate and score range")
            if self.score_min >= self.score_max:
                raise ValueError("invalid score range")
            if self.allowed_labels or self.candidate_a is not None or self.candidate_b is not None:
                raise ValueError("SCORE contains fields for another mode")
        else:
            if self.candidate_a is None or self.candidate_b is None:
                raise ValueError("PAIRWISE requires Candidate A and Candidate B")
            if (
                self.candidate is not None
                or self.allowed_labels
                or self.score_min is not None
                or self.score_max is not None
            ):
                raise ValueError("PAIRWISE contains fields for another mode")
        return self

    @property
    def public_digest(self) -> str:
        return digest(self)


class ProbeMetadata(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    position_probe: bool = False
    verbosity_probe: bool = False
    longer_candidate: Literal["A", "B"] | None = None

    @model_validator(mode="after")
    def verbosity_is_coherent(self) -> ProbeMetadata:
        if self.verbosity_probe != (self.longer_candidate is not None):
            raise ValueError("verbosity probe requires exactly one longer candidate")
        return self


GoldValue = Annotated[str | float, Field()]


class GoldCase(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    case_id: Identifier
    mode: JudgeMode
    gold_source: GoldSource
    expected: GoldValue
    score_tolerance: float | None = Field(default=None, ge=0)
    probe: ProbeMetadata = Field(default_factory=ProbeMetadata)
    curator_note: str | None = Field(default=None, max_length=2_000)
    deterministic_authority: Literal["L0_AUTHORITATIVE"] | None = None

    @model_validator(mode="after")
    def gold_shape_is_strict(self) -> GoldCase:
        if self.mode is JudgeMode.SCORE:
            if not isinstance(self.expected, int | float) or isinstance(self.expected, bool):
                raise ValueError("SCORE gold must be numeric")
        else:
            if not isinstance(self.expected, str):
                raise ValueError("categorical gold must be text")
            allowed = {"A", "B", "TIE", "UNKNOWN"} if self.mode is JudgeMode.PAIRWISE else None
            if allowed is not None and self.expected not in allowed:
                raise ValueError("PAIRWISE gold must be A, B, TIE, or UNKNOWN")
            if self.score_tolerance is not None:
                raise ValueError("score tolerance is SCORE-only")
        if self.mode is not JudgeMode.PAIRWISE and (
            self.probe.position_probe or self.probe.verbosity_probe
        ):
            raise ValueError("bias probes are PAIRWISE-only")
        if self.probe.verbosity_probe and self.expected != "TIE":
            raise ValueError("verbosity probe gold must be TIE")
        if self.gold_source is GoldSource.DETERMINISTIC_L0:
            if self.deterministic_authority != "L0_AUTHORITATIVE":
                raise ValueError("deterministic gold requires explicit L0 authority")
        elif self.deterministic_authority is not None:
            raise ValueError("L1 gold cannot claim deterministic authority")
        return self


class SuitePublicDocument(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    suite_id: Identifier
    version: str = Field(min_length=1, max_length=100)
    cases: tuple[PublicCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def case_ids_are_unique(self) -> SuitePublicDocument:
        if len({case.case_id for case in self.cases}) != len(self.cases):
            raise ValueError("duplicate public case id")
        return self


class SuiteGoldDocument(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    suite_id: Identifier
    version: str = Field(min_length=1, max_length=100)
    gold: tuple[GoldCase, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def case_ids_are_unique(self) -> SuiteGoldDocument:
        if len({case.case_id for case in self.gold}) != len(self.gold):
            raise ValueError("duplicate gold case id")
        return self


class JudgeSuite(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    public: SuitePublicDocument
    gold: SuiteGoldDocument
    public_digest: Sha256Digest
    gold_digest: Sha256Digest
    suite_digest: Sha256Digest

    @model_validator(mode="after")
    def split_is_coherent(self) -> JudgeSuite:
        if (self.public.suite_id, self.public.version) != (self.gold.suite_id, self.gold.version):
            raise ValueError("public/gold suite identity mismatch")
        public = {case.case_id: case for case in self.public.cases}
        gold = {case.case_id: case for case in self.gold.gold}
        if set(public) != set(gold):
            raise ValueError("public and gold case sets must match exactly")
        for case_id, case in public.items():
            expected = gold[case_id]
            if case.mode is not expected.mode:
                raise ValueError(f"mode/gold mismatch for {case_id}")
            if (
                case.mode is JudgeMode.LABEL
                and expected.expected not in case.allowed_labels
                and expected.expected != "UNKNOWN"
            ):
                raise ValueError(f"invalid label gold for {case_id}")
            if case.mode is JudgeMode.SCORE and not (
                case.score_min <= float(expected.expected) <= case.score_max  # type: ignore[operator]
            ):
                raise ValueError(f"score gold outside range for {case_id}")
        if self.public_digest != digest(self.public) or self.gold_digest != digest(self.gold):
            raise ValueError("suite component digest mismatch")
        combined = digest({"public_digest": self.public_digest, "gold_digest": self.gold_digest})
        if self.suite_digest != combined:
            raise ValueError("overall suite digest mismatch")
        return self


class LabelJudgment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    label: str = Field(min_length=1, max_length=200)
    reason: str


class ScoreJudgment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    score: float | None
    abstain: bool
    reason: str


class PairwiseJudgment(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    preference: Literal["LEFT", "RIGHT", "TIE", "UNKNOWN"]
    reason: str


ParsedJudgment = LabelJudgment | ScoreJudgment | PairwiseJudgment


class JudgeEvaluationSlot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    slot_id: Sha256Digest
    slot_order: int = Field(ge=0)
    calibration_id: Identifier
    judge_cell_id: Identifier
    case_id: Identifier
    case_mode: JudgeMode
    case_public_digest: Sha256Digest
    repeat_index: int = Field(ge=0)
    order_variant: OrderVariant


class QualificationPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_id: Identifier
    version: str
    minimum_coverage: float = Field(ge=0, le=1)
    minimum_label_accuracy: float = Field(ge=0, le=1)
    minimum_macro_f1: float = Field(ge=0, le=1)
    require_score_metrics: bool = Field(default=True, exclude_if=lambda value: value is True)
    maximum_score_mae: float = Field(ge=0)
    minimum_spearman_rho: float = Field(ge=-1, le=1)
    require_spearman: bool = True
    minimum_pairwise_accuracy: float = Field(ge=0, le=1)
    minimum_position_consistency: float = Field(ge=0, le=1)
    minimum_repeat_consistency: float = Field(ge=0, le=1)
    maximum_abstain_error_rate: float = Field(ge=0, le=1)
    maximum_verbosity_bias_rate: float = Field(ge=0, le=1)
    qualification_rule: Literal["ALL_REQUIRED_CHECKS_PASS"]


class JudgeCellSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Identifier
    definition_reference: str
    definition_digest: Sha256Digest
    model_profile: ModelProfile
    profile_identity: Sha256Digest
    runner_contract: Literal[
        "phase-h-fake-good-v1", "phase-h-fake-biased-v1", "provider-adapter-v1"
    ]

    @model_validator(mode="after")
    def profile_digest_matches(self) -> JudgeCellSpec:
        if digest(self.model_profile) != self.profile_identity:
            raise ValueError("Judge cell profile identity mismatch")
        return self


class JudgeCalibrationSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    calibration_id: Identifier
    name: str = Field(min_length=1, max_length=200)
    suite_reference: str
    suite_digest: Sha256Digest
    judge_cells: tuple[JudgeCellSpec, ...] = Field(min_length=1)
    repeat_count: int = Field(default=3, ge=1, le=100)
    execution_seed: int = 0
    qualification_policy: QualificationPolicy

    @model_validator(mode="after")
    def cells_are_unique(self) -> JudgeCalibrationSpec:
        if len({cell.id for cell in self.judge_cells}) != len(self.judge_cells):
            raise ValueError("duplicate Judge cell id")
        return self


class JudgeCalibrationPlan(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    calibration_id: Identifier
    name: str
    suite_id: Identifier
    suite_version: str
    suite_digest: Sha256Digest
    public_digest: Sha256Digest
    judge_cells: tuple[JudgeCellSpec, ...]
    repeat_count: int
    execution_seed: int
    qualification_policy: QualificationPolicy
    slots: tuple[JudgeEvaluationSlot, ...]

    def canonical_json(self) -> str:
        return canonical_json(self)

    @property
    def plan_digest(self) -> str:
        return digest(self)


class JudgeEvidence(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    evaluation_id: Identifier
    calibration_id: Identifier
    judge_cell_id: Identifier
    case_id: Identifier
    case_mode: JudgeMode
    case_public_digest: Sha256Digest
    suite_id: Identifier
    suite_version: str
    suite_digest: Sha256Digest
    definition_id: Identifier
    definition_version: str
    definition_digest: Sha256Digest
    model_profile_identity: Sha256Digest
    requested_judge_model: str
    observed_judge_model: str | None
    provider: str
    endpoint: str
    protocol: str
    prompt_template_version: Literal["judge-public-v1"] = "judge-public-v1"
    prompt_hash: Sha256Digest
    order_variant: OrderVariant
    logical_repeat_index: int
    provider_request_id: str | None
    provider_usage: ProviderUsage
    latency_ms: int | None
    attempt_count: Literal[1] = 1
    public_response_digest: Sha256Digest | None
    parsed_judgment: dict[str, object] | None
    outcome: JudgeRunOutcome
    judge_output_failure_kind: JudgeOutputFailureKind | None = None
    provider_failure: ProviderFailureCategory | None
    provider_error: ProviderError | None
    evidence_content_digest: Sha256Digest | None = None

    @model_validator(mode="after")
    def output_failure_kind_is_safe_and_coherent(self) -> JudgeEvidence:
        if (
            self.judge_output_failure_kind is not None
            and self.outcome is not JudgeRunOutcome.JUDGE_OUTPUT_ERROR
        ):
            raise ValueError("Judge output failure kind requires JUDGE_OUTPUT_ERROR")
        return self

    def canonical_json(self, *, include_content_digest: bool = True) -> str:
        raw = self.model_dump(mode="json")
        if self.judge_output_failure_kind is None:
            raw.pop("judge_output_failure_kind")
        if not include_content_digest:
            raw["evidence_content_digest"] = None
        return canonical_json(raw)


class AuthorityResolution(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    authority_level: Literal["L0", "L1", "L2"]
    authoritative_value: str | float
    judge_disagreement: bool
    l0_override_count: Literal[0] = 0


class EvaluationAuthorityResolution(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    evaluation_id: Identifier
    case_id: Identifier
    authority_level: Literal["L0", "L1", "L2"]
    authoritative_value: str | float
    judge_disagreement: bool
    l0_override_count: Literal[0] = 0


def resolve_authority(
    *,
    l0_deterministic: str | float | None,
    l1_human_gold: str | float | None,
    l2_judge: str | float,
) -> AuthorityResolution:
    if l0_deterministic is not None:
        return AuthorityResolution(
            authority_level="L0",
            authoritative_value=l0_deterministic,
            judge_disagreement=l0_deterministic != l2_judge,
        )
    if l1_human_gold is not None:
        return AuthorityResolution(
            authority_level="L1",
            authoritative_value=l1_human_gold,
            judge_disagreement=l1_human_gold != l2_judge,
        )
    return AuthorityResolution(
        authority_level="L2", authoritative_value=l2_judge, judge_disagreement=False
    )
