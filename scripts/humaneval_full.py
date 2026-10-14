"""Two fixed HumanEval controls through existing task admission/intake/independent Verifier."""

from __future__ import annotations

import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

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
from scripts.coding_agent_eval import SPEC, digest, load, run_capture, save
from scripts.swe_full_native import run_native


async def human(
    root: Path,
    retained_root: Path,
    identity: str,
    vendor: Path,
    auth: Path,
    *,
    initial: float,
    limit: float,
) -> dict[str, Any]:
    slug = identity.replace("/", "_")
    case = root / "humaneval" / slug
    case.mkdir(parents=True)
    config = load(SPEC / "config.json")
    oracle = load(retained_root / "hidden" / slug / "task.json")
    trusted = case / "trusted"
    trusted.mkdir()
    package_path = trusted / "sources" / ("humaneval-" + identity.split("/")[1]) / "1.0.0"
    for name in ("workspace", "oracle", "verifier"):
        (package_path / name).mkdir(parents=True)
    (package_path / "workspace/solution.py").write_text(oracle["prompt"])
    (package_path / "oracle/solution.py").write_text(
        oracle["prompt"] + oracle["canonical_solution"]
    )
    shutil.copyfile(SPEC / "humaneval_payload_verifier.py", package_path / "verifier/verify.py")
    save(package_path / "verifier/task.json", oracle)
    (package_path / "instruction.md").write_text(
        "Implement the fixed HumanEval function; hidden check remains independent.\n"
    )
    task_id = "humaneval-" + identity.split("/")[1]
    (package_path / "task.yaml").write_text(
        "schema_version: 1\nid: " + task_id + "\nversion: 1.0.0\ndomain: software-engineering\n"
        "lane_support: [H]\ninstruction_path: instruction.md\nworkspace_path: workspace\n"
        'verifier:\n  kind: python\n  version: "1"\n'
        "  entrypoint: verifier/verify.py\n  timeout_seconds: 20\n"
        "oracle:\n  path: oracle\nbudget:\n  timeout_seconds: 300\n"
        "  max_output_tokens: 16000\n  network_policy: deny\n"
    )
    package = TaskPackage.load(package_path)
    context = trusted / "image"
    context.mkdir()
    (context / "Dockerfile").write_text(
        "FROM " + config["python_image"] + '\nENTRYPOINT ["python"]\n'
    )
    status = run_capture(
        ["docker", "build", "--network", "none", "--iidfile", str(context / "id"), str(context)],
        trusted / "build",
        timeout=120,
    )
    save(trusted / "build-process.json", status)
    if status["exit_code"]:
        raise RuntimeError("HumanEval verifier image failed")
    image = (context / "id").read_text().strip()
    observations = []
    for gold in (False, True):
        materialized = package.materialize()
        try:
            if gold:
                package.apply_oracle(materialized)
            observed = await PinnedVerifierSandbox(
                image_id=image,
                run_id=task_id + ("-gold" if gold else "-base"),
                runtime_root=trusted / "runtime",
                artifact_root=trusted / "artifacts",
            ).run_hidden_verifier_workspace(package, materialized.workspace, timeout_seconds=20)
            report = VerifierReport.model_validate_json(observed.run.stdout)
            if report.passed is not gold:
                raise RuntimeError("HumanEval baseline/gold mismatch")
            manifest = observed.run.manifest
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
                    result=VerifierExecutionResult(
                        passed=report.passed,
                        score=report.score,
                        checks=report.checks,
                        summary=report.summary,
                        category=OutcomeCategory.SUBJECT_RESULT,
                        exit_code=manifest.exit_code,
                        duration_ms=manifest.duration_ms,
                        stdout_digest=manifest.stdout.digest,
                        stderr_digest=manifest.stderr.digest,
                    ),
                    run_kind="oracle" if gold else "baseline",
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
    evidence = {
        QualificationCheck.PACKAGE_VALID: package.definition.content_digest,
        QualificationCheck.BASELINE_FAILS: canonical_digest(
            observations[0].model_dump(mode="json")
        ),
        QualificationCheck.ORACLE_PASSES: canonical_digest(observations[1].model_dump(mode="json")),
        QualificationCheck.WORKSPACE_ISOLATION: canonical_digest(
            {
                "image": image,
                "workspace": package.definition.workspace.digest,
                "boundary": "readonly independent isolated Docker",
            }
        ),
        QualificationCheck.HIDDEN_ASSETS_ISOLATED: package.verifier_digest,
    }
    qualification = qualify_task(
        TaskQualityMetadata.from_package(package, source_kind=TaskSourceKind.CUSTOM),
        qualification_id=task_id + "-full-admission",
        evidence=tuple(
            QualificationEvidence(check=c, evidence_identity=evidence[c])
            for c in sorted(CUSTOM_TECHNICAL_CHECKS)
        ),
    )
    save(trusted / "validation.json", validation.model_dump(mode="json"))
    save(trusted / "qualification.json", qualification.model_dump(mode="json"))
    save(
        trusted / "task-policy.json",
        {
            "source_roots": {"campaign": str(trusted / "sources")},
            "managed_store": str(trusted / "managed"),
            "admissions": [
                {
                    "task_identity": package.definition.content_digest,
                    "qualification_file": str(trusted / "qualification.json"),
                    "qualification_identity": qualification.qualification_identity,
                    "validation_file": str(trusted / "validation.json"),
                    "validation_identity": canonical_digest(validation.model_dump(mode="json")),
                }
            ],
        },
    )
    for filename in ("validation.json", "qualification.json", "task-policy.json"):
        (trusted / filename).chmod(0o600)
    policy = LocalTaskPolicy.model_validate_json((trusted / "task-policy.json").read_bytes())
    os.environ["HARNESSLAB_LOCAL_TASK_POLICY"] = str(trusted / "task-policy.json")
    inspection = import_task(
        policy, LocalImport(root_id="campaign", relative_path=task_id + "/1.0.0")
    )
    if not inspection.eligible_for_planning:
        raise RuntimeError("HumanEval TaskStore refused")
    (case / "workspace").mkdir()
    (case / "workspace/solution.py").write_text(oracle["prompt"])
    prompt = (
        "Implement solution.py using its specification. You may use Python to test "
        "your own examples. The independent hidden tests are unavailable. "
        "Do not retrieve the benchmark or access credentials. "
        "In your final message include exactly one standalone line: "
        "SAMESCALE_SELF_REPORT=PASS, SAMESCALE_SELF_REPORT=FAIL, or "
        "SAMESCALE_SELF_REPORT=UNKNOWN. PASS means you believe the task is fully "
        "correct, FAIL means you believe it is incomplete/incorrect, UNKNOWN means "
        "you cannot decide. Your claim will be recorded separately from verification."
    )
    (case / "prompt.txt").write_text(prompt)
    save(case / "runtime-config.json", config)
    meter = await run_native(case, config, vendor, auth, initial=initial, limit=limit)
    raw_final = case / "final"
    shutil.copytree(case / "workspace", raw_final, symlinks=True)
    final = case / "final-reviewed"
    shutil.copytree(
        raw_final,
        final,
        symlinks=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    stream = case / "import-stream"
    stream.mkdir()
    shutil.copyfile(case / "agent.stdout", stream / "events.jsonl")
    source = ApprovedSource(
        source_id=task_id,
        format="stream-json-v1",
        harness=HarnessIdentity(name="codex", version=config["codex_version"]),
        source_kind="unverified",
        path=stream,
        digest=digest_tree(stream),
        workspace=final,
        workspace_digest=digest_tree(final),
        task_reference=inspection.reference,
        task_digest=inspection.task_identity,
    )
    ep = EvidencePolicy(
        store=case / "records",
        sources=(source,),
        verifier_image_id=image,
        runtime_root=case / "acceptance-runtime",
        artifact_root=case / "acceptance-artifacts",
    )
    save(case / "evidence-policy.json", ep.model_dump(mode="json"))
    (case / "evidence-policy.json").chmod(0o600)
    os.environ["HARNESSLAB_EXTERNAL_EVIDENCE_POLICY"] = str(case / "evidence-policy.json")
    ep = service.load_policy()
    intake = service.ingest(ep, source.source_id)
    save(case / "intake.json", intake)
    receipt = await verify_workspace(ep, intake["identity"])
    save(case / "acceptance.json", receipt)
    packet = service.export_record(ep, intake["identity"])
    (case / "export.json").write_bytes(packet)
    save(case / "export-replay.json", service.replay_export(packet, "sha256:" + digest(packet)))
    events = [json.loads(s) for s in (case / "agent.stdout").read_text().splitlines()]
    messages = [
        e["item"].get("text", "")
        for e in events
        if e.get("type") == "item.completed" and e.get("item", {}).get("type") == "agent_message"
    ]
    claims = re.findall(
        r"^SAMESCALE_SELF_REPORT=(PASS|FAIL|UNKNOWN)$", messages[-1] if messages else "", re.M
    )
    claim = claims[0] if len(claims) == 1 else "UNKNOWN"
    verdict = {"VERIFIED_PASS": "PASS", "VERIFIED_FAIL": "FAIL", "NOT_VERIFIED": "NOT_VERIFIED"}[
        receipt["acceptance"]
    ]
    manifests = list((case / "acceptance-artifacts").rglob("manifest.json"))
    final_manifest = load(manifests[0])
    full_report = load(manifests[0].parent / "stdout.txt") if verdict != "NOT_VERIFIED" else None
    failure = full_report["checks"][0]["detail"] if full_report else "ENVIRONMENT_FAILURE"
    process = load(case / "agent-process.json")
    if process["timed_out"]:
        failure = "TIMEOUT"
    return {
        "task_id": identity,
        "group": "HumanEval",
        "retained": False,
        "environment": "PASS",
        "self_report": claim,
        "verifier": verdict,
        "failure_type": failure,
        "false_completion": claim == "PASS" and verdict == "FAIL",
        "checks": receipt["checks"],
        "passed_checks": receipt["passed_checks"],
        "agent_seconds": process["duration_seconds"],
        "verifier_seconds": final_manifest["duration_ms"] / 1000,
        "usage": meter["usage"],
        "api_equivalent_usd": round(meter["api_equivalent_usd"], 8),
        "actual_billed_usd": None,
        "record_identity": receipt["record_identity"],
        "receipt_digest": receipt["receipt_digest"],
        "physical_agent_attempts": 1,
        "physical_verifier_attempts": receipt["physical_attempts"],
        "evidence_path": str(case),
    }
