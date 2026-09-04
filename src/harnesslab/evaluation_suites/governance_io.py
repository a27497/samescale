from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from harnesslab.evaluation_suites.admission import AdmissionDecision, AdmissionPolicy
from harnesslab.evaluation_suites.exposure import ExposureHistory, VisibilityPolicy
from harnesslab.evaluation_suites.holdout import HoldoutEligibilityResult


class GovernanceArtifactError(ValueError):
    """A persisted governance artifact failed strict schema or digest validation."""


def _load[T](path: Path, validator: Callable[[Any], T], label: str) -> T:
    try:
        return validator(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValidationError) as exc:
        raise GovernanceArtifactError(f"invalid {label}: {type(exc).__name__}") from exc


def load_admission_policy(path: Path) -> AdmissionPolicy:
    return _load(path, AdmissionPolicy.model_validate_json, "admission policy")


def load_admission_decision(path: Path) -> AdmissionDecision:
    return _load(path, AdmissionDecision.model_validate_json, "admission decision")


def load_exposure_history(path: Path) -> ExposureHistory:
    return _load(path, ExposureHistory.model_validate_json, "exposure history")


def load_visibility_policy(path: Path) -> VisibilityPolicy:
    return _load(path, VisibilityPolicy.model_validate_json, "visibility policy")


def load_holdout_eligibility(path: Path) -> HoldoutEligibilityResult:
    return _load(path, HoldoutEligibilityResult.model_validate_json, "holdout eligibility")
