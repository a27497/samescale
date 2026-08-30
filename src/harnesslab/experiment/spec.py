from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from harnesslab.comparability.models import ComparabilityIntent
from harnesslab.contracts.common import EvaluationLane, Identifier, NetworkPolicy, Sha256Digest
from harnesslab.tasks.models import validate_relative_path
from harnesslab.tasks.package import UniqueKeyLoader


class ExperimentSpecError(ValueError):
    """An experiment specification cannot be trusted or resolved."""


class ExperimentCellSpec(BaseModel):
    """One frozen M- or H-Lane configuration expanded across every task and repeat."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Identifier
    lane: Literal[EvaluationLane.MODEL, EvaluationLane.HARNESS]
    requested_model: str = Field(min_length=1, max_length=300)
    provider_route: str = Field(min_length=1, max_length=500)
    profile_reference: str = Field(min_length=1, max_length=300)
    profile_identity: Sha256Digest
    harness: str = Field(min_length=1, max_length=100)
    harness_version: str = Field(min_length=1, max_length=100)
    harness_config_identity: Sha256Digest
    reasoning_effort: str | None = Field(default=None, max_length=100)
    resource_budget_identity: Sha256Digest
    network_policy: NetworkPolicy
    runner_contract: str = Field(min_length=1, max_length=100)
    credential_reference: str | None = Field(
        default=None,
        pattern=r"^[A-Z][A-Z0-9_]*$",
        description="Environment-variable name only; never secret material.",
    )
    base_provider_profile_identity: Sha256Digest | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    effective_runtime_profile_identity: Sha256Digest | None = Field(
        default=None, exclude_if=lambda value: value is None
    )
    resource_envelope_identity: Sha256Digest | None = Field(
        default=None, exclude_if=lambda value: value is None
    )

    @field_validator("profile_reference")
    @classmethod
    def reference_is_safe(cls, value: str) -> str:
        if value.startswith("builtin:"):
            name = value.removeprefix("builtin:")
            if not name or any(
                character not in "abcdefghijklmnopqrstuvwxyz0123456789-._" for character in name
            ):
                raise ValueError("invalid builtin profile reference")
            return value
        return validate_relative_path(value)


class PairedComparisonSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Identifier
    left_cell_id: Identifier
    right_cell_id: Identifier
    intent: Literal[ComparabilityIntent.HARNESS_UPLIFT] = ComparabilityIntent.HARNESS_UPLIFT


class AblationSpec(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Identifier
    base_cell_id: Identifier
    variant_cell_id: Identifier
    changed_dimension: Literal["reasoning_effort"]
    intent: Literal[ComparabilityIntent.CONTROLLED_ABLATION] = (
        ComparabilityIntent.CONTROLLED_ABLATION
    )


class ExperimentSpec(BaseModel):
    """Strict, secret-free, versioned Phase G matrix input."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    schema_version: Literal[1] = 1
    experiment_id: Identifier
    name: str = Field(min_length=1, max_length=200)
    task_packages: tuple[str, ...] = Field(min_length=1)
    cells: tuple[ExperimentCellSpec, ...] = Field(min_length=1)
    repeat_count: int = Field(default=5, ge=1, le=10_000)
    execution_seed: int = 0
    comparison_intent: ComparabilityIntent = ComparabilityIntent.GENERAL
    paired_comparisons: tuple[PairedComparisonSpec, ...] = ()
    ablations: tuple[AblationSpec, ...] = ()

    @field_validator("task_packages")
    @classmethod
    def task_paths_are_safe(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(validate_relative_path(value) for value in values)
        if len(set(normalized)) != len(normalized):
            raise ValueError("duplicate task package path")
        if any(not value.startswith("tasks/") for value in normalized):
            raise ValueError("task packages must live below tasks/")
        return normalized

    @model_validator(mode="after")
    def matrix_references_are_coherent(self) -> ExperimentSpec:
        cells = {cell.id: cell for cell in self.cells}
        if len(cells) != len(self.cells):
            raise ValueError("duplicate cell id")
        pair_ids = {pair.id for pair in self.paired_comparisons}
        if len(pair_ids) != len(self.paired_comparisons):
            raise ValueError("duplicate pair id")
        ablation_ids = {ablation.id for ablation in self.ablations}
        if len(ablation_ids) != len(self.ablations):
            raise ValueError("duplicate ablation id")

        for pair in self.paired_comparisons:
            try:
                left = cells[pair.left_cell_id]
                right = cells[pair.right_cell_id]
            except KeyError as exc:
                raise ValueError("paired comparison references an unknown cell") from exc
            if left.id == right.id:
                raise ValueError("paired comparison requires two distinct cells")
            if left.lane is not EvaluationLane.MODEL or right.lane is not EvaluationLane.HARNESS:
                raise ValueError("P-Lane requires an M-Lane left cell and H-Lane right cell")

        control_fields = (
            "lane",
            "requested_model",
            "provider_route",
            "profile_reference",
            "harness",
            "harness_version",
            "resource_budget_identity",
            "network_policy",
            "runner_contract",
            "credential_reference",
            "base_provider_profile_identity",
            "resource_envelope_identity",
        )
        for ablation in self.ablations:
            try:
                base = cells[ablation.base_cell_id]
                variant = cells[ablation.variant_cell_id]
            except KeyError as exc:
                raise ValueError("ablation references an unknown cell") from exc
            if base.id == variant.id:
                raise ValueError("ablation requires two distinct cells")
            drift = [
                field for field in control_fields if getattr(base, field) != getattr(variant, field)
            ]
            if drift:
                raise ValueError(f"ablation has undeclared hard-control drift: {','.join(drift)}")
            if base.reasoning_effort == variant.reasoning_effort:
                raise ValueError("ablation declared reasoning_effort but it did not change")
            deliberate_r1_contract = "intent" in ablation.model_fields_set
            if deliberate_r1_contract and base.profile_identity != variant.profile_identity:
                raise ValueError(
                    "reasoning_effort must not be hidden inside the comparison profile identity"
                )
            if base.harness_config_identity == variant.harness_config_identity:
                raise ValueError("ablation executable profile identities must remain distinct")
        return self


def load_experiment_spec(path: Path) -> ExperimentSpec:
    try:
        raw: Any = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise ExperimentSpecError(f"invalid experiment spec: {type(exc).__name__}") from exc
    if not isinstance(raw, dict):
        raise ExperimentSpecError("experiment spec must contain a mapping")
    try:
        return ExperimentSpec.model_validate(raw)
    except ValidationError as exc:
        raise ExperimentSpecError(f"invalid experiment spec: {exc}") from exc
