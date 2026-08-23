from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from harnesslab.judgelab.models import (
    JudgeDefinition,
    JudgeSuite,
    SuiteGoldDocument,
    SuitePublicDocument,
    digest,
)
from harnesslab.tasks.package import UniqueKeyLoader


class JudgeSuiteError(ValueError):
    """The public/gold split or a Judge definition is malformed."""


def _load_yaml(path: Path, label: str) -> dict[str, Any]:
    try:
        raw = yaml.load(path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader)
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as exc:
        raise JudgeSuiteError(f"invalid {label}: {type(exc).__name__}") from exc
    if not isinstance(raw, dict):
        raise JudgeSuiteError(f"{label} must contain a mapping")
    return raw


def load_judge_definition(path: Path) -> JudgeDefinition:
    try:
        return JudgeDefinition.model_validate(_load_yaml(path, "JudgeDefinition"))
    except ValidationError as exc:
        raise JudgeSuiteError(f"invalid JudgeDefinition: {exc}") from exc


def load_judge_suite(path: Path) -> JudgeSuite:
    root = path.resolve()
    try:
        public = SuitePublicDocument.model_validate(_load_yaml(root / "suite.yaml", "suite.yaml"))
        gold = SuiteGoldDocument.model_validate(_load_yaml(root / "gold.yaml", "gold.yaml"))
        public_digest = digest(public)
        gold_digest = digest(gold)
        return JudgeSuite(
            public=public,
            gold=gold,
            public_digest=public_digest,
            gold_digest=gold_digest,
            suite_digest=digest({"public_digest": public_digest, "gold_digest": gold_digest}),
        )
    except ValidationError as exc:
        raise JudgeSuiteError(f"invalid Judge suite: {exc}") from exc
