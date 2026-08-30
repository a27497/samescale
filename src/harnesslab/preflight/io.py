from __future__ import annotations

import json
import os
import re
import stat
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError


class PreflightInputError(ValueError):
    """A keyless control manifest is unreadable or structurally invalid."""


_ENVIRONMENT_REFERENCE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def load_secret_environment_file(path: Path, allowed_references: frozenset[str]) -> dict[str, str]:
    """Load a private assignment-only environment file without shell evaluation."""

    try:
        metadata = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            raise PreflightInputError("secret environment source must be a regular file")
        if metadata.st_uid != os.getuid() or stat.S_IMODE(metadata.st_mode) & 0o077:
            raise PreflightInputError(
                "secret environment source must be owned by the current user with private mode"
            )
        lines = path.read_text(encoding="utf-8").splitlines()
    except PreflightInputError:
        raise
    except (OSError, UnicodeDecodeError) as exc:
        raise PreflightInputError(
            f"secret environment source could not be read ({type(exc).__name__})"
        ) from exc

    loaded: dict[str, str] = {}
    for line in lines:
        candidate = line.strip()
        if not candidate or candidate.startswith("#"):
            continue
        reference, separator, raw_value = candidate.partition("=")
        reference = reference.strip()
        if (
            not separator
            or _ENVIRONMENT_REFERENCE.fullmatch(reference) is None
            or reference not in allowed_references
            or reference in loaded
        ):
            raise PreflightInputError("secret environment source has an invalid assignment")
        value = raw_value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        if not value:
            raise PreflightInputError("secret environment source has an empty assignment")
        loaded[reference] = value
    return loaded


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
