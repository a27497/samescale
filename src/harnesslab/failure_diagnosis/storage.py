"""Separate append-only advisory artifacts. Never opens acceptance files for writing."""

from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator  # type: ignore[import-untyped]

from harnesslab.failure_diagnosis.models import (
    DiagnosisArtifact,
    DiagnosisInput,
    FailedAcceptance,
    PublicEvidence,
)
from harnesslab.failure_diagnosis.service import canonical, sha256, validate_explanation

MAX_BYTES = 200_000


def read_bounded(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError("regular bounded input file required")
    with path.open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError("oversized input")
    return data


def load_input(receipt: Path, expected_sha256: str, public_packet: Path) -> DiagnosisInput:
    data = read_bounded(receipt)
    if sha256(data) != expected_sha256:
        raise ValueError("receipt content does not match operator pin")
    value = json.loads(data)
    if value.get("authority") != "L0_INDEPENDENT_VERIFIER":
        raise ValueError("independent verifier receipt required")
    if value.get("receipt_digest") != "sha256:" + sha256(
        canonical({k: v for k, v in value.items() if k != "receipt_digest"}).rstrip(b"\n")
    ):
        raise ValueError("receipt self digest mismatch")
    rows = value["check_results"]
    if (
        len(rows) != value["checks"]
        or [r["ordinal"] for r in rows] != list(range(1, value["checks"] + 1))
        or any(type(r["passed"]) is not bool for r in rows)
        or sum(r["passed"] for r in rows) != value["passed_checks"]
    ):
        raise ValueError("receipt check inventory mismatch")
    acceptance = FailedAcceptance(
        status=value["acceptance"],
        record_identity=value["record_identity"],
        receipt_digest=value["receipt_digest"],
        receipt_file_sha256=expected_sha256,
        checks=value["checks"],
        passed_checks=value["passed_checks"],
        failed_check_ordinals=tuple(
            r["ordinal"] for r in value["check_results"] if r["passed"] is False
        ),
    )
    packet = json.loads(read_bounded(public_packet))
    Draft202012Validator(PublicEvidence.model_json_schema()).validate(packet)
    return DiagnosisInput(
        acceptance=acceptance,
        evidence=PublicEvidence.model_validate(packet),
    )


def save_artifact(artifact: DiagnosisArtifact, directory: Path, protected: tuple[Path, ...]) -> str:
    root = directory.resolve()
    if any((parent / ".git").exists() for parent in (root, *root.parents)):
        raise ValueError("diagnosis storage must be outside Git")
    repository = Path(__file__).resolve().parents[3]
    for source in (*protected, repository):
        parent = source.resolve() if source.is_dir() else source.resolve().parent
        if root.is_relative_to(parent) or parent.is_relative_to(root):
            raise ValueError("diagnosis storage must be outside source and repository storage")
    # A fresh directory prevents overwriting receipts, Episodes or earlier diagnoses.
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    data = canonical(artifact.model_dump(mode="json"))
    digest = sha256(data)
    with (root / "diagnosis.json").open("xb") as stream:
        stream.write(data)
    (root / "diagnosis.json").chmod(0o600)
    with (root / "export.json").open("xb") as stream:
        stream.write(canonical({"artifact_sha256": digest, "artifact": json.loads(data)}))
    (root / "export.json").chmod(0o600)
    return digest


def replay(data: bytes, expected_sha256: str) -> DiagnosisArtifact:
    """Consistency only; no import of a backend, no new diagnosis or verdict."""
    if len(data) > MAX_BYTES:
        raise ValueError("oversized export")
    value = json.loads(data)
    if set(value) != {"artifact_sha256", "artifact"}:
        raise ValueError("invalid export envelope")
    if (
        value["artifact_sha256"] != expected_sha256
        or sha256(canonical(value["artifact"])) != expected_sha256
    ):
        raise ValueError("diagnosis artifact digest mismatch")
    Draft202012Validator(DiagnosisArtifact.model_json_schema()).validate(value["artifact"])
    artifact = DiagnosisArtifact.model_validate(value["artifact"])
    validate_explanation(canonical(value["artifact"]["explanation"]).decode(), artifact.input)
    if (artifact.mode == "模型辅助诊断") != (artifact.fallback_reason.value == "未降级"):
        raise ValueError("inconsistent diagnosis mode")
    return artifact
