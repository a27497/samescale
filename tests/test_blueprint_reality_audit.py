from __future__ import annotations

import json
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
AUDIT_PATH = REPOSITORY_ROOT / "release" / "blueprint-reality-audit-2026-08-30.json"
DOCUMENTATION_PATH = REPOSITORY_ROOT / "docs" / "BLUEPRINT_REALITY_AUDIT_2026-08-30.md"

EXPECTED_STAGES = ("K-B3", "K-B4", "K-C", "L", "M", "N", "O", "P", "Q", "R", "S")
ALLOWED_STATUSES = {
    "IMPLEMENTED",
    "PARTIAL",
    "MISSING",
    "BLOCKED_BY_EVIDENCE",
    "SUPERSEDED",
    "NOT_YET_REQUIRED",
}
EXPECTED_TOP_LEVEL_KEYS = {
    "schema_version",
    "audit_id",
    "audit_date",
    "audited_code_head_sha",
    "authoritative_base_sha",
    "documentation_reference",
    "blueprint_source",
    "classification_vocabulary",
    "stage_summaries",
    "requirements",
}
EXPECTED_REQUIREMENT_KEYS = {
    "stage",
    "requirement_id",
    "requirement",
    "status",
    "evidence_refs",
    "remaining_work",
    "limitations",
}


def _load_audit() -> dict[str, object]:
    raw = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw, dict)
    return raw


def test_blueprint_reality_audit_schema_and_stage_coverage() -> None:
    audit = _load_audit()
    assert set(audit) == EXPECTED_TOP_LEVEL_KEYS
    assert audit["schema_version"] == 1
    assert audit["audit_id"] == "harnesslab-blueprint-reality-2026-08-30"
    assert audit["classification_vocabulary"] == [
        "IMPLEMENTED",
        "PARTIAL",
        "MISSING",
        "BLOCKED_BY_EVIDENCE",
        "SUPERSEDED",
        "NOT_YET_REQUIRED",
    ]

    source = audit["blueprint_source"]
    assert isinstance(source, dict)
    assert set(source) == {"status", "available_authorities", "limitation"}
    assert source["status"] == "UNAVAILABLE"
    assert "not assigned inferred product meanings" in str(source["limitation"])

    summaries = audit["stage_summaries"]
    assert isinstance(summaries, list)
    assert tuple(item["stage"] for item in summaries) == EXPECTED_STAGES
    assert all(set(item) == {"stage", "status", "summary"} for item in summaries)
    assert all(item["status"] in ALLOWED_STATUSES for item in summaries)

    requirements = audit["requirements"]
    assert isinstance(requirements, list)
    assert requirements
    assert {item["stage"] for item in requirements} == set(EXPECTED_STAGES)
    requirement_ids = [item["requirement_id"] for item in requirements]
    assert len(requirement_ids) == len(set(requirement_ids))
    for item in requirements:
        assert set(item) == EXPECTED_REQUIREMENT_KEYS
        assert item["status"] in ALLOWED_STATUSES
        assert isinstance(item["requirement"], str) and item["requirement"]
        assert isinstance(item["remaining_work"], list)
        assert isinstance(item["limitations"], list) and item["limitations"]


def test_blueprint_reality_audit_evidence_refs_are_safe_and_exist() -> None:
    audit = _load_audit()
    requirements = audit["requirements"]
    assert isinstance(requirements, list)

    for item in requirements:
        evidence_refs = item["evidence_refs"]
        assert isinstance(evidence_refs, list) and evidence_refs
        for reference in evidence_refs:
            assert isinstance(reference, str) and reference
            assert not reference.startswith(("/", "http://", "https://"))
            parts = Path(reference).parts
            assert ".." not in parts
            assert (REPOSITORY_ROOT / reference).exists(), reference


def test_blueprint_reality_audit_markdown_is_linked_and_conservative() -> None:
    audit = _load_audit()
    assert audit["documentation_reference"] == str(DOCUMENTATION_PATH.relative_to(REPOSITORY_ROOT))
    documentation = DOCUMENTATION_PATH.read_text(encoding="utf-8")
    assert "final HarnessLab post-K blueprint is unavailable" in documentation
    assert "does not assign inferred feature meanings to Q or R" in documentation
    assert "release/blueprint-reality-audit-2026-08-30.json" in documentation
    for stage in EXPECTED_STAGES:
        assert stage in documentation
