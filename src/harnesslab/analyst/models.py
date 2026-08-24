from __future__ import annotations

import hashlib
import json
import re
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    TypeAdapter,
    field_validator,
    model_validator,
)

from harnesslab.contracts.common import Identifier, Sha256Digest

MAX_DECISION_ITERATIONS = 8
MAX_TOOL_CALLS = 12
MAX_QUERY_RESULTS = 100

_SENSITIVE = re.compile(
    r"(?i)(authorization\s*:|bearer\s+[a-z0-9._-]+|api[_-]?key\s*[=:]|"
    r"(?<![\w])/(?:home|root|etc|var|tmp|workspace|Users|usr|opt|srv)/|[A-Z]:\\)"
)


def safe_public_text(value: str, *, limit: int) -> str:
    value = value[:limit]
    return _SENSITIVE.sub("[REDACTED]", value)


class StrictModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class AnalysisRequest(StrictModel):
    experiment_id: Identifier
    question: str = Field(min_length=1, max_length=2_000)

    @field_validator("question")
    @classmethod
    def question_is_public(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("analysis question must not be blank")
        if safe_public_text(cleaned, limit=2_000) != cleaned:
            raise ValueError("analysis question contains credential-like or absolute-path text")
        return cleaned

    @property
    def analysis_id(self) -> str:
        payload = json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        return "analysis-" + hashlib.sha256(payload.encode()).hexdigest()[:32]


class AnalysisScope(StrictModel):
    experiment_id: Identifier
    plan_digest: Sha256Digest
    cell_ids: tuple[Identifier, ...]
    task_ids: tuple[Identifier, ...]
    run_ids: tuple[str, ...]
    ablation_ids: tuple[Identifier, ...]


class ToolName(StrEnum):
    QUERY_RUNS = "query_runs"
    COMPARE_CELLS = "compare_cells"
    INSPECT_TRACE = "inspect_trace"
    INSPECT_FAILURE = "inspect_failure"
    GET_TASK_CONTRACT = "get_task_contract"
    GET_ABLATION = "get_ablation"


class QueryRunsArgs(StrictModel):
    task_id: Identifier | None = None
    cell_id: Identifier | None = None
    status: str | None = Field(default=None, min_length=1, max_length=30)
    outcome: str | None = Field(default=None, min_length=1, max_length=30)
    limit: int = Field(default=50, ge=1, le=MAX_QUERY_RESULTS)


class CompareCellsArgs(StrictModel):
    left_cell_id: Identifier
    right_cell_id: Identifier


class InspectTraceArgs(StrictModel):
    run_id: str = Field(min_length=1, max_length=100)
    start_ordinal: int = Field(default=1, ge=1)
    limit: int = Field(default=50, ge=1, le=100)


class InspectFailureArgs(StrictModel):
    run_id: str = Field(min_length=1, max_length=100)


class GetTaskContractArgs(StrictModel):
    task_id: Identifier


class GetAblationArgs(StrictModel):
    ablation_id: Identifier


class QueryRunsCall(StrictModel):
    name: Literal[ToolName.QUERY_RUNS]
    arguments: QueryRunsArgs


class CompareCellsCall(StrictModel):
    name: Literal[ToolName.COMPARE_CELLS]
    arguments: CompareCellsArgs


class InspectTraceCall(StrictModel):
    name: Literal[ToolName.INSPECT_TRACE]
    arguments: InspectTraceArgs


class InspectFailureCall(StrictModel):
    name: Literal[ToolName.INSPECT_FAILURE]
    arguments: InspectFailureArgs


class GetTaskContractCall(StrictModel):
    name: Literal[ToolName.GET_TASK_CONTRACT]
    arguments: GetTaskContractArgs


class GetAblationCall(StrictModel):
    name: Literal[ToolName.GET_ABLATION]
    arguments: GetAblationArgs


ToolCall = Annotated[
    QueryRunsCall
    | CompareCellsCall
    | InspectTraceCall
    | InspectFailureCall
    | GetTaskContractCall
    | GetAblationCall,
    Field(discriminator="name"),
]
TOOL_CALL_ADAPTER: TypeAdapter[ToolCall] = TypeAdapter(ToolCall)


class EvidenceRef(StrictModel):
    id: str = Field(min_length=1, max_length=260)

    @field_validator("id")
    @classmethod
    def identity_is_logical(cls, value: str) -> str:
        patterns = (
            r"run:[A-Za-z0-9._-]{1,100}",
            r"trace:[A-Za-z0-9._-]{1,100}#event:[1-9][0-9]*",
            r"task:[A-Za-z0-9._-]{1,100}@[A-Za-z0-9._-]{1,100}",
            r"cell:[A-Za-z0-9._-]{1,100}:[A-Za-z0-9._-]{1,100}",
            r"pair:[A-Za-z0-9._-]{1,100}:[A-Za-z0-9._-]{1,100}",
            r"ablation:[A-Za-z0-9._-]{1,100}:[A-Za-z0-9._-]{1,100}",
        )
        if not any(re.fullmatch(pattern, value) for pattern in patterns):
            raise ValueError("evidence reference must be a stable non-path logical identity")
        return value


class ToolEvidence(StrictModel):
    ref: EvidenceRef
    tool: ToolName
    digest_bindings: tuple[Sha256Digest, ...] = ()
    data: dict[str, JsonValue]


class EvidenceEntry(StrictModel):
    ref: EvidenceRef
    tools: tuple[ToolName, ...]
    digest_bindings: tuple[Sha256Digest, ...] = ()
    data_by_tool: dict[str, dict[str, JsonValue]]


class ClaimClass(StrEnum):
    VERIFIED_FACT = "VERIFIED_FACT"
    HYPOTHESIS = "HYPOTHESIS"


class FactOperator(StrEnum):
    EQ = "EQ"


class FactAssertion(StrictModel):
    evidence_ref: str = Field(min_length=1, max_length=260)
    tool: ToolName
    field_path: tuple[str | int, ...] = Field(min_length=1, max_length=16)
    operator: Literal[FactOperator.EQ] = FactOperator.EQ
    expected_value: JsonValue

    @field_validator("evidence_ref")
    @classmethod
    def evidence_identity_is_logical(cls, value: str) -> str:
        EvidenceRef(id=value)
        return value

    @field_validator("field_path")
    @classmethod
    def field_path_is_bounded(cls, value: tuple[str | int, ...]) -> tuple[str | int, ...]:
        for segment in value:
            if isinstance(segment, str):
                if not segment or len(segment) > 200:
                    raise ValueError("fact field path keys must be 1..200 characters")
            elif segment < 0:
                raise ValueError("fact field path indexes cannot be negative")
        return value

    @field_validator("expected_value")
    @classmethod
    def expected_value_is_canonical_json(cls, value: JsonValue) -> JsonValue:
        try:
            json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError("fact expected value must be canonical JSON") from exc
        return value


def canonical_json_value(value: JsonValue) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def resolve_fact_assertion(assertion: FactAssertion, entry: EvidenceEntry) -> JsonValue:
    tool_key = assertion.tool.value
    if assertion.tool not in entry.tools or tool_key not in entry.data_by_tool:
        raise ValueError("fact assertion tool namespace is absent from the cited evidence")
    current: JsonValue = entry.data_by_tool[tool_key]
    for segment in assertion.field_path:
        if isinstance(segment, str):
            if not isinstance(current, dict) or segment not in current:
                raise ValueError("fact assertion field path is absent from the cited evidence")
            current = current[segment]
        else:
            if not isinstance(current, list) or segment >= len(current):
                raise ValueError("fact assertion field path is absent from the cited evidence")
            current = current[segment]
    return current


def fact_evidence_refs(assertions: tuple[FactAssertion, ...]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(assertion.evidence_ref for assertion in assertions))


def canonical_fact_statement(assertions: tuple[FactAssertion, ...]) -> str:
    expressions = []
    for assertion in assertions:
        path = ""
        for segment in assertion.field_path:
            if isinstance(segment, int):
                path += f"[{segment}]"
            elif re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", segment):
                path += f".{segment}"
            else:
                path += f"[{json.dumps(segment, ensure_ascii=False)}]"
        expected = json.dumps(
            assertion.expected_value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        expressions.append(
            f"{assertion.tool.value}[{assertion.evidence_ref}]{path} "
            f"{assertion.operator.value} {expected}"
        )
    return "Observed " + "; ".join(expressions) + "."


class VerifiedFactDraft(StrictModel):
    classification: Literal[ClaimClass.VERIFIED_FACT] = ClaimClass.VERIFIED_FACT
    assertions: tuple[FactAssertion, ...] = Field(min_length=1, max_length=16)


class HypothesisClaim(StrictModel):
    classification: Literal[ClaimClass.HYPOTHESIS] = ClaimClass.HYPOTHESIS
    statement: str = Field(min_length=1, max_length=2_000)
    evidence_refs: tuple[str, ...] = ()
    additional_evidence_needed: str = Field(min_length=1, max_length=2_000)

    @field_validator("statement", "additional_evidence_needed")
    @classmethod
    def text_is_safe(cls, value: str) -> str:
        return safe_public_text(value, limit=2_000)


class VerifiedFact(StrictModel):
    classification: Literal[ClaimClass.VERIFIED_FACT] = ClaimClass.VERIFIED_FACT
    statement: str = Field(min_length=1, max_length=8_000)
    evidence_refs: tuple[str, ...] = Field(min_length=1)
    assertions: tuple[FactAssertion, ...] = Field(min_length=1, max_length=16)

    @model_validator(mode="after")
    def prose_and_citations_are_canonical(self) -> VerifiedFact:
        if self.evidence_refs != fact_evidence_refs(self.assertions):
            raise ValueError("VERIFIED_FACT citations must be derived from its assertions")
        if self.statement != canonical_fact_statement(self.assertions):
            raise ValueError("VERIFIED_FACT prose must be canonical structured-fact rendering")
        return self


type AttributionClaim = Annotated[
    VerifiedFactDraft | HypothesisClaim,
    Field(discriminator="classification"),
]


class AttributionDraft(StrictModel):
    summary: str = Field(min_length=1, max_length=4_000)
    claims: tuple[AttributionClaim, ...]
    ablation_refs: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()

    @field_validator("summary")
    @classmethod
    def summary_is_safe(cls, value: str) -> str:
        return safe_public_text(value, limit=4_000)

    @field_validator("limitations")
    @classmethod
    def limitations_are_safe(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(safe_public_text(value, limit=2_000) for value in values)


class ToolDecision(StrictModel):
    kind: Literal["tools"] = "tools"
    calls: tuple[ToolCall, ...] = Field(min_length=1, max_length=6)


class FinalDecision(StrictModel):
    kind: Literal["final"] = "final"
    draft: AttributionDraft


BackendDecision = Annotated[ToolDecision | FinalDecision, Field(discriminator="kind")]


class ExecutionStatus(StrEnum):
    COMPLETED = "COMPLETED"
    LIMIT_REACHED = "LIMIT_REACHED"


class ExecutionMetadata(StrictModel):
    status: ExecutionStatus
    decision_iterations: int = Field(ge=0, le=MAX_DECISION_ITERATIONS)
    tool_calls: int = Field(ge=0, le=MAX_TOOL_CALLS)
    max_decision_iterations: Literal[8] = 8
    max_tool_calls: Literal[12] = 12


class AttributionReport(StrictModel):
    schema_version: Literal[1] = 1
    analysis_id: str = Field(pattern=r"^analysis-[a-f0-9]{32}$")
    source_experiment_id: Identifier
    source_plan_digest: Sha256Digest
    analysis_question: str = Field(min_length=1, max_length=2_000)
    execution: ExecutionMetadata
    summary: str = Field(min_length=1, max_length=4_000)
    evidence_catalog: tuple[EvidenceEntry, ...]
    verified_facts: tuple[VerifiedFact, ...]
    hypotheses: tuple[HypothesisClaim, ...]
    ablation_refs: tuple[str, ...]
    limitations: tuple[str, ...]

    @model_validator(mode="after")
    def report_is_internally_classified(self) -> AttributionReport:
        ids = tuple(entry.ref.id for entry in self.evidence_catalog)
        if len(ids) != len(set(ids)):
            raise ValueError("evidence catalog contains duplicate identities")
        catalog = {entry.ref.id: entry for entry in self.evidence_catalog}
        if any(
            claim.classification is not ClaimClass.VERIFIED_FACT for claim in self.verified_facts
        ):
            raise ValueError("verified_facts contains a non-fact claim")
        if any(claim.classification is not ClaimClass.HYPOTHESIS for claim in self.hypotheses):
            raise ValueError("hypotheses contains a non-hypothesis claim")
        for fact in self.verified_facts:
            for assertion in fact.assertions:
                entry = catalog.get(assertion.evidence_ref)
                if entry is None:
                    raise ValueError("claim cites evidence absent from the catalog")
                actual = resolve_fact_assertion(assertion, entry)
                if canonical_json_value(actual) != canonical_json_value(assertion.expected_value):
                    raise ValueError("fact assertion expected value contradicts the cited evidence")
        for hypothesis in self.hypotheses:
            if set(hypothesis.evidence_refs) - set(catalog):
                raise ValueError("claim cites evidence absent from the catalog")
        if any(ref not in catalog or not ref.startswith("ablation:") for ref in self.ablation_refs):
            raise ValueError("ablation reference is missing or not an ablation identity")
        return self

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @property
    def digest(self) -> str:
        return "sha256:" + hashlib.sha256(self.canonical_json().encode()).hexdigest()

    def markdown(self) -> str:
        lines = [
            f"# Attribution analysis `{self.analysis_id}`",
            "",
            f"Experiment: `{self.source_experiment_id}`",
            f"Plan digest: `{self.source_plan_digest}`",
            f"Report digest: `{self.digest}`",
            f"Question: {self.analysis_question}",
            "",
            self.summary,
            "",
            "## Verified facts",
            "",
        ]
        lines.extend(
            f"- {claim.statement} ({', '.join(f'`{ref}`' for ref in claim.evidence_refs)})"
            for claim in self.verified_facts
        )
        if not self.verified_facts:
            lines.append("- None established.")
        lines.extend(["", "## Hypotheses", ""])
        lines.extend(
            f"- {claim.statement} Additional evidence: {claim.additional_evidence_needed}"
            for claim in self.hypotheses
        )
        if not self.hypotheses:
            lines.append("- None reported.")
        lines.extend(["", "## Limitations", ""])
        lines.extend(f"- {item}" for item in self.limitations)
        lines.extend(
            [
                "",
                f"Bounded execution: {self.execution.decision_iterations}/8 decisions, "
                f"{self.execution.tool_calls}/12 tool calls; {self.execution.status.value}.",
                "",
            ]
        )
        return "\n".join(lines)
