"""Prepare trusted campaign adapters, qualify, import and verify saved external deliveries."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
from pathlib import Path
from uuid import uuid4

from harnesslab.external_evidence import service
from harnesslab.external_evidence.models import ApprovedSource, EvidencePolicy, HarnessIdentity
from harnesslab.external_evidence.verification import verify_workspace
from harnesslab.local_execution.sandbox import PinnedVerifierSandbox
from harnesslab.local_plans.tasks import LocalImport, LocalTaskPolicy, import_task
from harnesslab.registry.models import canonical_digest
from harnesslab.tasks.models import (
    EvidenceAsset,
    EvidenceManifest,
    OutcomeCategory,
    TaskValidationResult,
    VerifierExecutionResult,
    VerifierReport,
)
from harnesslab.tasks.package import TaskPackage, digest_tree
from harnesslab.tasks.quality import (
    CUSTOM_TECHNICAL_CHECKS,
    QualificationCheck,
    QualificationEvidence,
    TaskQualityMetadata,
    TaskSourceKind,
    qualify_task,
)
from scripts.coding_agent_eval import SPEC, docker, load, run_capture, save
from scripts.swe_mixed_eval import check_inputs


async def prepare(root: Path, trusted: Path, reuse_images: Path | None = None) -> None:
    check_inputs(root)
    mixed = load(root / "config.json")
    trusted.mkdir(parents=True, mode=0o700)
    admissions = []
    image_ids = {}
    for identity in mixed["pilot_task_ids"]:
        task = next(t for t in mixed["tasks"] if t["instance_id"] == identity)
        row = load(root / "hidden" / (identity + ".json"))
        case = trusted / identity
        case.mkdir()
        prior = reuse_images / identity / "image.json" if reuse_images else None
        if prior is not None and prior.exists():
            image = load(prior)["image_id"]
            docker("image", "inspect", image)
        else:
            (case / "test.patch").write_text(row["test_patch"])
            name = "samescale-verifier-warm-" + uuid4().hex
            install = (
                "python -m pip install -e .[test] --verbose"
                if task["repo"] == "astropy/astropy"
                else "python -m pip install -e ."
            )
            command = (
                "source /opt/miniconda3/bin/activate && conda activate testbed && "
                "cd /testbed && git reset --hard "
                + task["base_commit"]
                + " && "
                + install
                + " && git apply /warming/test.patch && rm -rf .git && "
                "chmod -R a+rX /testbed"
            )
            docker(
                "create",
                "--name",
                name,
                "--network",
                "none",
                "--memory",
                "4g",
                "--cpus",
                "2",
                "--env",
                "PIP_NO_INDEX=1",
                "--mount",
                f"type=bind,src={case},dst=/warming,readonly",
                task["image"],
                "/bin/bash",
                "-c",
                command,
            )
            try:
                status = run_capture(
                    ["docker", "start", "--attach", name], case / "warm", timeout=600
                )
                save(case / "warm-process.json", status)
                if status["exit_code"]:
                    raise RuntimeError("verifier warming failed")
                image = (
                    docker(
                        "commit",
                        "--change",
                        'ENTRYPOINT ["python"]',
                        "--change",
                        "ENV PATH=/opt/miniconda3/envs/testbed/bin:/opt/miniconda3/bin:"
                        "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
                        name,
                        timeout=600,
                    )
                    .stdout.decode()
                    .strip()
                )
            finally:
                docker("rm", "--force", name)
        image_ids[identity] = image
        save(case / "image.json", {"source": task["image"], "image_id": image})
        package_path = trusted / "sources" / identity.replace("__", "-") / "1.0.0"
        for directory in ("workspace", "oracle", "verifier"):
            (package_path / directory).mkdir(parents=True)
        (package_path / "workspace/solution.patch").write_text("")
        (package_path / "oracle/solution.patch").write_text(row["patch"])
        (package_path / "instruction.md").write_text(
            "Apply the supplied delivery to the fixed SWE baseline "
            "and check required hidden tests.\n"
        )
        shutil.copyfile(SPEC / "swe_payload_verifier.py", package_path / "verifier/verify.py")
        (package_path / "verifier/test.patch").write_text(row["test_patch"])
        hidden_paths = re.findall(r"^\+\+\+ b/(.+)$", row["test_patch"], re.M)
        if task["repo"] == "astropy/astropy":
            # Exact predeclared upstream required IDs; avoid unrelated suite resource peaks.
            test_command = ["python", "-m", "pytest", "-rA", "--color=no"] + (
                json.loads(row["FAIL_TO_PASS"]) + json.loads(row["PASS_TO_PASS"])
            )
        elif task["repo"] == "sphinx-doc/sphinx":
            # Preserve collection order/shared fixtures, bound reporting only.
            test_command = [
                "python",
                "-m",
                "pytest",
                "-rA",
                "--color=no",
                "--tb=short",
                "--show-capture=no",
                "tests/test_intl.py",
            ]
        else:
            test_command = [
                "python",
                "bin/test",
                "-C",
                "--verbose",
                "sympy/printing/tests/test_conventions.py",
                "sympy/testing/quality_unicode.py",
            ]
        save(
            package_path / "verifier/acceptance.json",
            {
                "repo": task["repo"],
                "test_command": test_command,
                "hidden_test_paths": hidden_paths,
                "fail_to_pass": json.loads(row["FAIL_TO_PASS"]),
                "pass_to_pass": json.loads(row["PASS_TO_PASS"]),
                "image_id": image,
                "base_commit": task["base_commit"],
            },
        )
        (package_path / "task.yaml").write_text(
            "schema_version: 1\nid: " + identity.replace("__", "-") + "\nversion: 1.0.0\n"
            "domain: software-engineering\nlane_support: [H]\ninstruction_path: instruction.md\n"
            'workspace_path: workspace\nverifier:\n  kind: python\n  version: "1"\n'
            "  entrypoint: verifier/verify.py\n  timeout_seconds: 30\noracle:\n  path: oracle\n"
            "budget:\n  timeout_seconds: 900\n  max_output_tokens: 16000\n  network_policy: deny\n"
            "metadata:\n  language: python\n  category: targeted-bug-fix\n"
        )
        package = TaskPackage.load(package_path)
        observations = []
        for oracle in (False, True):
            materialized = package.materialize()
            try:
                if oracle:
                    package.apply_oracle(materialized)
                sandbox = PinnedVerifierSandbox(
                    image_id=image,
                    run_id=identity.replace("__", "-") + ("-gold" if oracle else "-base"),
                    runtime_root=case / "runtime",
                    artifact_root=case / "artifacts",
                )
                observed = await sandbox.run_hidden_verifier_workspace(
                    package, materialized.workspace, timeout_seconds=30
                )
                report = VerifierReport.model_validate_json(observed.run.stdout)
                required = json.loads(row["FAIL_TO_PASS"]) + json.loads(row["PASS_TO_PASS"])
                expected = (
                    [True] * len(required)
                    if oracle
                    else [False] * len(json.loads(row["FAIL_TO_PASS"]))
                    + [True] * len(json.loads(row["PASS_TO_PASS"]))
                )
                if report.passed is not oracle or [c.passed for c in report.checks] != expected:
                    raise RuntimeError("wrapper baseline/gold admission mismatch")
                manifest = observed.run.manifest
                result = VerifierExecutionResult(
                    passed=report.passed,
                    score=report.score,
                    checks=report.checks,
                    summary=report.summary,
                    category=OutcomeCategory.SUBJECT_RESULT,
                    exit_code=manifest.exit_code,
                    duration_ms=manifest.duration_ms,
                    stdout_digest=manifest.stdout.digest,
                    stderr_digest=manifest.stderr.digest,
                )
                observations.append(
                    EvidenceManifest(
                        task_id=package.definition.id,
                        task_version=package.definition.version,
                        task_digest=package.definition.content_digest,
                        workspace_digest=digest_tree(materialized.workspace),
                        verifier=EvidenceAsset(
                            kind="hidden_verifier",
                            path=package.manifest.verifier.entrypoint,
                            digest=package.verifier_digest,
                        ),
                        result=result,
                        run_kind="oracle" if oracle else "baseline",
                    )
                )
            finally:
                materialized.cleanup()
        validation = TaskValidationResult(
            valid=True,
            task_id=package.definition.id,
            task_version=package.definition.version,
            task_digest=package.definition.content_digest,
            baseline=observations[0],
            oracle=observations[1],
        )
        identities = {
            QualificationCheck.PACKAGE_VALID: package.definition.content_digest,
            QualificationCheck.BASELINE_FAILS: canonical_digest(
                observations[0].model_dump(mode="json")
            ),
            QualificationCheck.ORACLE_PASSES: canonical_digest(
                observations[1].model_dump(mode="json")
            ),
        }
        for check in (
            QualificationCheck.WORKSPACE_ISOLATION,
            QualificationCheck.HIDDEN_ASSETS_ISOLATED,
        ):
            identities[check] = canonical_digest(
                {
                    "image_id": image,
                    "workspace": package.definition.workspace.digest,
                    "verifier": package.verifier_digest,
                    "boundary": "network-none, readonly, distinct verifier mount",
                }
            )
        qualification = qualify_task(
            TaskQualityMetadata.from_package(package, source_kind=TaskSourceKind.CUSTOM),
            qualification_id=identity.replace("__", "-") + "-external-admission",
            evidence=tuple(
                QualificationEvidence(check=c, evidence_identity=identities[c])
                for c in sorted(CUSTOM_TECHNICAL_CHECKS)
            ),
        )
        save(case / "validation.json", validation.model_dump(mode="json"))
        save(case / "qualification.json", qualification.model_dump(mode="json"))
        admissions.append(
            {
                "task_identity": package.definition.content_digest,
                "qualification_file": str(case / "qualification.json"),
                "qualification_identity": qualification.qualification_identity,
                "validation_file": str(case / "validation.json"),
                "validation_identity": canonical_digest(validation.model_dump(mode="json")),
            }
        )
        for filename in ("validation.json", "qualification.json"):
            (case / filename).chmod(0o600)
        print("ADAPTER ADMITTED " + identity, flush=True)
    save(trusted / "images.json", image_ids)
    save(
        trusted / "task-policy.json",
        {
            "source_roots": {"campaign": str(trusted / "sources")},
            "managed_store": str(trusted / "managed"),
            "admissions": admissions,
        },
    )
    (trusted / "task-policy.json").chmod(0o600)


async def accept(root: Path, trusted: Path, output: Path) -> None:
    policy = LocalTaskPolicy.model_validate_json((trusted / "task-policy.json").read_bytes())
    os.environ["HARNESSLAB_LOCAL_TASK_POLICY"] = str(trusted / "task-policy.json")
    images = load(trusted / "images.json")
    for identity in load(root / "config.json")["pilot_task_ids"]:
        case = output / identity
        inspection = import_task(
            policy,
            LocalImport(root_id="campaign", relative_path=identity.replace("__", "-") + "/1.0.0"),
        )
        if not inspection.eligible_for_planning:
            raise RuntimeError("TaskStore admission refused: " + repr(inspection.reason_codes))
        stream = case / "import-stream"
        if not stream.exists():
            stream.mkdir()
            shutil.copyfile(case / "agent.stdout", stream / "events.jsonl")
        if (stream / "events.jsonl").read_bytes() != (case / "agent.stdout").read_bytes():
            raise ValueError("approved stream drift")
        source = ApprovedSource(
            source_id=identity.replace("__", "-"),
            format="stream-json-v1",
            harness=HarnessIdentity(name="codex", version="0.162.1"),
            source_kind="unverified",
            path=stream,
            digest=digest_tree(stream),
            workspace=case / "delivery-v2",
            workspace_digest=digest_tree(case / "delivery-v2"),
            task_reference=inspection.reference,
            task_digest=inspection.task_identity,
        )
        evidence_policy = EvidencePolicy(
            store=case / "records",
            sources=(source,),
            verifier_image_id=images[identity],
            runtime_root=case / "acceptance-runtime",
            artifact_root=case / "acceptance-artifacts",
        )
        policy_value = evidence_policy.model_dump(mode="json")
        if (case / "evidence-policy.json").exists():
            if load(case / "evidence-policy.json") != policy_value:
                raise ValueError("approved policy drift")
        else:
            save(case / "evidence-policy.json", policy_value)
        (case / "evidence-policy.json").chmod(0o600)
        os.environ["HARNESSLAB_EXTERNAL_EVIDENCE_POLICY"] = str(case / "evidence-policy.json")
        evidence_policy = service.load_policy()
        item = service.ingest(evidence_policy, source.source_id)
        if not (case / "intake.json").exists():
            save(case / "intake.json", item)
        receipt = await verify_workspace(evidence_policy, item["identity"])
        if not (case / "acceptance.json").exists():
            save(case / "acceptance.json", receipt)
        elif load(case / "acceptance.json") != receipt:
            raise ValueError("acceptance drift")
        packet = service.export_record(evidence_policy, item["identity"])
        if not (case / "export.json").exists():
            (case / "export.json").write_bytes(packet)
        elif (case / "export.json").read_bytes() != packet:
            raise ValueError("export drift")
        if not (case / "export-replay.json").exists():
            save(
                case / "export-replay.json",
                service.replay_export(
                    packet, "sha256:" + __import__("hashlib").sha256(packet).hexdigest()
                ),
            )
        print(json.dumps({"task": identity, "acceptance": receipt}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("prepare", "accept"))
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--trusted", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--reuse-images", type=Path)
    args = parser.parse_args()
    if args.command == "prepare":
        asyncio.run(prepare(args.root.absolute(), args.trusted.absolute(), args.reuse_images))
    else:
        asyncio.run(accept(args.root.absolute(), args.trusted.absolute(), args.output.absolute()))
