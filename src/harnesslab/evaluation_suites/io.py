from __future__ import annotations

from pathlib import Path

from pydantic import ValidationError

from harnesslab.evaluation_suites.models import EvaluationSuiteManifest
from harnesslab.evaluation_suites.service import EvaluationSuiteError


def load_evaluation_suite_manifest(path: Path) -> EvaluationSuiteManifest:
    """Load a strict canonical manifest and fail closed on schema or digest drift."""

    try:
        return EvaluationSuiteManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValidationError) as exc:
        raise EvaluationSuiteError(
            f"invalid evaluation suite manifest: {type(exc).__name__}"
        ) from exc
