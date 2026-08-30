from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError


class PreflightInputError(ValueError):
    """A keyless control manifest is unreadable or structurally invalid."""


def load_control_manifest[ModelT: BaseModel](path: Path, model: type[ModelT]) -> ModelT:
    """Load strict JSON without reflecting rejected content into error messages."""

    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PreflightInputError(
            f"control manifest could not be read as JSON ({type(exc).__name__})"
        ) from exc
    try:
        return model.model_validate(raw)
    except ValidationError as exc:
        count = len(exc.errors(include_url=False, include_context=False, include_input=False))
        raise PreflightInputError(
            f"control manifest has {count} field validation error(s)"
        ) from exc
