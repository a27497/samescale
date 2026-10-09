"""Bounded trusted-local ingestion; all inspection is data-only, never verifier execution."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
from pathlib import Path

from pydantic import Field

from harnesslab.api.workbench_errors import WorkbenchAPIError
from harnesslab.contracts.common import EvaluationLane, Identifier, Sha256Digest
from harnesslab.custom_eval.models import SourceType
from harnesslab.custom_eval.store import ManagedTaskStore
from harnesslab.local_plans.models import TaskInspection
from harnesslab.productization.assets import distribution_root
from harnesslab.registry.models import RegistryModel, canonical_digest
from harnesslab.tasks.models import OutcomeCategory, TaskValidationResult
from harnesslab.tasks.package import TaskPackage
from harnesslab.tasks.quality import (
    QualificationCheck,
    QualificationStatus,
    TaskFamily,
    TaskIdentity,
    TaskQualification,
)


class PriorAdmission(RegistryModel):
    task_identity: Sha256Digest
    qualification_file: Path
    qualification_identity: Sha256Digest
    validation_file: Path
    validation_identity: Sha256Digest


class LocalTaskPolicy(RegistryModel):
    schema_version: int = Field(default=1, ge=1, le=1)
    source_roots: dict[Identifier, Path] = Field(min_length=1, max_length=20)
    managed_store: Path
    runtime_images: dict[str, Sha256Digest] = Field(default_factory=dict, max_length=20)
    admissions: tuple[PriorAdmission, ...] = ()

    @property
    def identity(self) -> str:
        return canonical_digest(self.model_dump(mode="json"))


class LocalImport(RegistryModel):
    root_id: Identifier
    relative_path: str = Field(min_length=1, max_length=240)


def fail(code: str, message: str, status_code: int = 422) -> WorkbenchAPIError:
    return WorkbenchAPIError(status_code, code, message)


def no_links(path: Path) -> None:
    if (
        not path.is_absolute()
        or path != path.resolve()
        or any(p.is_symlink() for p in (path, *path.parents))
    ):
        raise fail("UNSAFE_LOCAL_PATH", "Use a canonical local path without links.")


def read_owned_json(path: Path) -> object:
    no_links(path)
    info = path.stat()
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_size > 2_000_000
        or info.st_uid != os.getuid()
        or info.st_mode & 0o022
    ):
        raise fail(
            "UNTRUSTED_POLICY", "Policy/evidence files must be owned and not shared-writable."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def load_policy() -> LocalTaskPolicy:
    try:
        path = Path(os.environ["HARNESSLAB_LOCAL_TASK_POLICY"])
        policy = LocalTaskPolicy.model_validate(read_owned_json(path))
        no_links(policy.managed_store)
        if path == policy.managed_store or policy.managed_store in path.parents:
            raise ValueError("policy cannot be inside the managed store")
        for root in policy.source_roots.values():
            no_links(root)
            if (
                not root.is_dir()
                or root == policy.managed_store
                or root in policy.managed_store.parents
                or policy.managed_store in root.parents
            ):
                raise ValueError("source/storage overlap")
            if path == root or root in path.parents:
                raise ValueError("policy cannot be inside a subject source")
        protected = tuple(distribution_root() / p for p in ("tasks", "release", "docs"))
        if any(p == policy.managed_store or p in policy.managed_store.parents for p in protected):
            raise ValueError("protected store")
        for admission in policy.admissions:
            for evidence in (admission.qualification_file, admission.validation_file):
                no_links(evidence)
                if any(
                    r == evidence or r in evidence.parents
                    for r in (*policy.source_roots.values(), policy.managed_store)
                ):
                    raise ValueError("admission evidence must be outside subject/store")
        if len({a.task_identity for a in policy.admissions}) != len(policy.admissions):
            raise ValueError("duplicate admission")
        return policy
    except (KeyError, OSError, ValueError):
        raise fail(
            "LOCAL_TASK_POLICY_INVALID",
            "Configure a trusted local task policy and separate evidence files.",
            503,
        ) from None


def source_path(policy: LocalTaskPolicy, request: LocalImport) -> Path:
    parts = request.relative_path.split("/")
    if (
        request.root_id not in policy.source_roots
        or request.relative_path.startswith("/")
        or any(p in {"", ".", ".."} for p in parts)
        or "\\" in request.relative_path
        or ":" in request.relative_path
        or "\x00" in request.relative_path
        or len(parts) > 8
    ):
        raise fail("UNSAFE_LOCAL_PATH", "Choose a task beneath an approved local source root.")
    root = policy.source_roots[request.root_id]
    path = root.joinpath(*parts)
    no_links(path)
    if root.resolve() not in path.resolve().parents:
        raise fail("UNSAFE_LOCAL_PATH", "Task path is outside its approved source root.")
    return path


def bounded_files(path: Path, *, max_files: int = 4000, max_bytes: int = 64_000_000) -> None:
    no_links(path)
    total = 0
    count = 0
    for current, dirs, names in os.walk(path, followlinks=False):
        for name in (*dirs, *names):
            p = Path(current) / name
            info = p.lstat()
            if p.is_symlink() or not (stat.S_ISREG(info.st_mode) or stat.S_ISDIR(info.st_mode)):
                raise fail(
                    "UNSAFE_TASK_FILE",
                    "Task packages may contain only ordinary files and directories.",
                )
            if name == ".git" or name == ".env" or name in {"auth.json", "credentials.json"}:
                raise fail(
                    "PRIVATE_TASK_FILE",
                    "Remove repository metadata and credentials from the task snapshot.",
                )
            if stat.S_ISREG(info.st_mode):
                count += 1
                total += info.st_size
                if (
                    info.st_nlink != 1
                    or info.st_size > 8_000_000
                    or count > max_files
                    or total > max_bytes
                ):
                    raise fail(
                        "TASK_SIZE_OR_LINK_LIMIT",
                        "Task snapshot exceeds the local ingestion envelope.",
                    )


def bounded_package(path: Path) -> TaskPackage:
    bounded_files(path)
    return TaskPackage.load(path)


def task_store(policy: LocalTaskPolicy) -> ManagedTaskStore:
    no_links(policy.managed_store)
    # Legacy snapshot hashing reads file bytes. Reject special/link/oversized files before it.
    bounded_files(policy.managed_store, max_files=40_000, max_bytes=512_000_000)
    store = ManagedTaskStore(policy.managed_store)
    for p in (store.snapshots_root, store.index_root):
        no_links(p)
    return store


def oracle_workspace_identity(package: TaskPackage) -> str:
    """Hash the expected baseline + oracle overlay without materializing or executing it."""
    workspace = package.root / package.manifest.workspace_path
    contents = {
        p.relative_to(workspace).as_posix(): p.read_bytes()
        for p in workspace.rglob("*")
        if p.is_file()
    }
    contents.update(
        {
            p.relative_to(package.oracle_path).as_posix(): p.read_bytes()
            for p in package.oracle_path.rglob("*")
            if p.is_file()
        }
    )
    digest = hashlib.sha256()
    for name, content in sorted(contents.items()):
        relative = name.encode("utf-8")
        digest.update(len(relative).to_bytes(8, "big") + relative)
        digest.update(len(content).to_bytes(8, "big") + content)
    return "sha256:" + digest.hexdigest()


def qualification(
    policy: LocalTaskPolicy, package: TaskPackage
) -> tuple[str | None, tuple[str, ...]]:
    admission = next(
        (a for a in policy.admissions if a.task_identity == package.definition.content_digest), None
    )
    if admission is None:
        return None, ("TRUSTED_PRIOR_QUALIFICATION_REQUIRED",)
    try:
        q = TaskQualification.model_validate(read_owned_json(admission.qualification_file))
        validation = TaskValidationResult.model_validate(read_owned_json(admission.validation_file))
        if (
            q.qualification_identity != admission.qualification_identity
            or canonical_digest(validation.model_dump(mode="json")) != admission.validation_identity
        ):
            raise ValueError("admission digest")
        if (
            q.status is not QualificationStatus.QUALIFIED
            or q.quality.family is not TaskFamily.CUSTOM
            or q.quality.task != TaskIdentity.from_package(package)
        ):
            raise ValueError("admission task binding")
        if q.quality.provenance.source_identity != package.definition.content_digest:
            raise ValueError("source identity")
        if (
            not validation.valid
            or validation.errors
            or validation.task_id != package.definition.id
            or validation.task_version != package.definition.version
            or validation.task_digest != package.definition.content_digest
        ):
            raise ValueError("behavioral result binding")
        for manifest, kind, passed in (
            (validation.baseline, "baseline", False),
            (validation.oracle, "oracle", True),
        ):
            result = manifest.result
            if (
                manifest.task_digest != package.definition.content_digest
                or manifest.task_id != package.definition.id
                or manifest.task_version != package.definition.version
                or manifest.verifier.digest != package.verifier_digest
                or manifest.verifier.path != package.manifest.verifier.entrypoint
                or manifest.run_kind != kind
                or result.category is not OutcomeCategory.SUBJECT_RESULT
                or result.exit_code != 0
                or result.passed is not passed
                or not result.checks
                or (passed and not all(c.passed for c in result.checks))
                or (not passed and all(c.passed for c in result.checks))
            ):
                raise ValueError("behavioral result semantics")
        if validation.baseline.workspace_digest != package.definition.workspace.digest:
            raise ValueError("baseline workspace binding")
        if validation.oracle.workspace_digest != oracle_workspace_identity(package):
            raise ValueError("oracle workspace binding")
        evidence = {item.check: item.evidence_identity for item in q.evidence}
        expected = {
            QualificationCheck.PACKAGE_VALID: package.definition.content_digest,
            QualificationCheck.BASELINE_FAILS: canonical_digest(
                validation.baseline.model_dump(mode="json")
            ),
            QualificationCheck.ORACLE_PASSES: canonical_digest(
                validation.oracle.model_dump(mode="json")
            ),
        }
        if any(evidence.get(k) != v for k, v in expected.items()):
            raise ValueError("qualification evidence binding")
        return q.qualification_identity, ()
    except (OSError, ValueError, WorkbenchAPIError):
        return None, ("TRUSTED_PRIOR_QUALIFICATION_INVALID",)


def inspect_task(policy: LocalTaskPolicy, reference: str) -> tuple[TaskInspection, TaskPackage]:
    store = task_store(policy)
    record, package = store.load_package(reference)
    source = Path(record.provenance.source_reference)
    binding = next(
        ((key, root) for key, root in policy.source_roots.items() if root in source.parents), None
    )
    if binding is None or record.provenance.source_type is not SourceType.LOCAL_FOLDER:
        raise fail(
            "TASK_SOURCE_NOT_TRUSTED",
            "This managed task is outside the trusted-local source contract.",
        )
    key, root = binding
    relative = source.relative_to(root).as_posix()
    original = bounded_package(
        source_path(policy, LocalImport(root_id=key, relative_path=relative))
    )
    if (
        original.definition.content_digest != record.task_identity
        or record.provenance.source_content_identity != record.task_identity
    ):
        raise fail(
            "TASK_SOURCE_DRIFT",
            "The source task changed. Import a new task version and preflight again.",
            409,
        )
    bounded_package(package.root)
    q, reasons = qualification(policy, package)
    if EvaluationLane.HARNESS not in package.definition.lane_support:
        reasons = (*reasons, "HARNESS_LANE_REQUIRED")
    return TaskInspection(
        reference=record.reference,
        task_owner=record.task_owner,
        task_category=record.task_category,
        task_identity=record.task_identity,
        workspace_identity=record.workspace_identity,
        verifier_identity=record.verifier_identity,
        oracle_identity=package.oracle_digest,
        managed_snapshot_identity=record.managed_snapshot_identity,
        source_root_id=key,
        source_relative_path=relative,
        source_identity=record.provenance.source_content_identity,
        behavioral_validation="TRUSTED_PRIOR_RESULT" if q else "NOT_VERIFIED",
        qualification_identity=q,
        eligible_for_planning=not reasons,
        reason_codes=reasons,
    ), package


def import_task(policy: LocalTaskPolicy, request: LocalImport) -> TaskInspection:
    source = source_path(policy, request)
    bounded_package(source)
    store = task_store(policy)
    lock_path = policy.managed_store / ".product-import.lock"
    no_links(lock_path)
    with lock_path.open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        record = store.import_local_folder(source)
        result, _ = inspect_task(policy, record.reference)
        return result
