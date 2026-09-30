from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from harnesslab.evidence.protection import FrozenEvidenceError, snapshot_tree
from harnesslab.tasks.models import validate_relative_path


class DemoIntegrityError(RuntimeError):
    pass


class FileIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")


class DemoRunIdentity(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    run_id: str
    experiment_id: str
    attempt: int = Field(ge=1)
    manifest: str
    digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    verifier_passed: bool

    @field_validator("manifest")
    @classmethod
    def safe_path(cls, value: str) -> str:
        return validate_relative_path(value)


class DemoBundle(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")
    schema_version: Literal[1] = 1
    demo_id: str = Field(pattern=r"^public-demo-[a-z0-9-]+$")
    generated_at: datetime
    provenance: Literal["FIXTURE_OFFLINE"] = "FIXTURE_OFFLINE"
    baseline_id: str
    candidate_id: str
    failed_run_id: str
    plan_digests: dict[str, str]
    runs: tuple[DemoRunIdentity, ...] = Field(min_length=1)
    files: dict[str, FileIdentity] = Field(min_length=1)
    historical_integrity_failures: tuple[str, ...] = ()

    @field_validator("files")
    @classmethod
    def safe_paths(cls, value: dict[str, FileIdentity]) -> dict[str, FileIdentity]:
        for name in value:
            validate_relative_path(name)
        return value


def load_bundle(path: Path, expected_digest: str) -> DemoBundle:
    try:
        if path.is_symlink():
            raise DemoIntegrityError("public demo manifest is a symlink")
        data = path.read_bytes()
        if "sha256:" + hashlib.sha256(data).hexdigest() != expected_digest:
            raise DemoIntegrityError("public demo manifest hash mismatch")
        bundle = DemoBundle.model_validate_json(data)
        snapshot = snapshot_tree(path.parent / "artifacts")
        expected = {name: identity.model_dump() for name, identity in bundle.files.items()}
        if not snapshot or snapshot != expected:
            raise DemoIntegrityError("public demo artifact inventory/hash mismatch")
        return bundle
    except (OSError, ValidationError, FrozenEvidenceError) as exc:
        raise DemoIntegrityError("public demo evidence is missing or invalid") from exc
