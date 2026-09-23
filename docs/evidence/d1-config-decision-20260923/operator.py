"""Bounded D1 operator over the verified S1 runtime; immutable trial records."""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
import runpy
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

from scripts.prepare_lecturelens_development import DevelopmentSandbox
from scripts.s1_claude_controls import SECCOMP, S1IsolatedClaudeAdapter, S1IsolatedClaudeBackend
from scripts.s1_credentials import resolved_s1_credentials
from scripts.s1_mini_benchmark import (
    ROOT,
    check_seal,
    project_result,
    prompt_for,
    require,
    seal,
    write,
)
from scripts.s1_official_codex import AUTH_SOURCE, PROXY_IMAGE_ID, OfficialBoundary, read_auth
from scripts.s1_official_custom_tools import (
    REPAIR_IMAGE,
    RepairAdapter,
    RepairBackend,
    repair_profile,
)
from scripts.s1_protocol_repair import budget_compliance

from harnesslab.egress import boundary_for_provider_url
from harnesslab.harness_lane.runner import CodexHarnessRunner
from harnesslab.multi_harness.models import MultiHarnessProfile
from harnesslab.multi_harness.runner import MultiHarnessRunner
from harnesslab.sandbox.artifacts import assert_tree_has_no_run_secrets
from harnesslab.sandbox.models import ImageIdentity
from harnesslab.tasks.package import TaskPackage, digest_tree, sha256_bytes
from harnesslab.tasks.quality import TaskIdentity

BASE = Path("/home/dev/artifacts/samescale-d1-20260923")
FREEZE = Path(__file__).resolve().parent
CUSTOM = ROOT / "docs/evidence/s1-official-custom-tools-20260921"
PROXY = ImageIdentity(reference="harnesslab-egress-proxy:1.0.0", image_id=PROXY_IMAGE_ID)


def load(p):
    return json.loads(p.read_text())


def now():
    return datetime.now(UTC).isoformat()


def inventory():
    return {
        "containers": set(
            subprocess.check_output(["docker", "ps", "-a", "--format", "{{.Names}}"], timeout=30)
            .decode()
            .splitlines()
        ),
        "networks": set(
            subprocess.check_output(
                ["docker", "network", "ls", "--format", "{{.Name}}"], timeout=30
            )
            .decode()
            .splitlines()
        ),
    }


def verify():
    with contextlib.redirect_stdout(io.StringIO()):
        runpy.run_path(str(CUSTOM / "readback.py"))
    p = load(FREEZE / "campaign.json")
    check_seal(p)
    require(sha256_bytes(Path(__file__).read_bytes()) == p["operator_sha256"], "Operator drift")
    require(p["kind"] == "D1_CONFIGURATION_DECISION_20_RUNS", "Wrong phase")
    require(len(p["tasks"]) == 2 and len(p["cells"]) == 20, "Scope drift")
    require(p["comparison_type"] == "AI_CODING_CONFIGURATION_COMPARISON", "Claim drift")
    parent = load(CUSTOM / "campaign.json")
    require(
        p["tasks"] == [t for t in parent["tasks"] if t["task"]["task_id"] in p["task_ids"]]
        and p["configs"] == parent["configs"],
        "Inputs drift",
    )
    require(
        p["task_ids"] == [
            "lecturelens-analysis-progress-stream-reconnect",
            "lecturelens-embedded-subtitle-language-metadata",
        ],
        "Task selection drift",
    )
    require(
        p["trials_per_cell"] == 5
        and p["operator_retries"] == 0
        and p["subject_timeout_seconds"] == 600
        and p["verifier_timeout_seconds"] == 300,
        "Trial controls drift",
    )
    require(len({c["identity"] for c in p["cells"]}) == 20, "Duplicate trial identity")
    require(
        {(c["task_id"], c["config"], c["trial"]) for c in p["cells"]}
        == {
            (t, side, trial)
            for t in p["task_ids"]
            for side in p["configs"]
            for trial in range(1, 6)
        },
        "Missing trial",
    )
    for rel, digest in p["implementation_files"].items():
        require(sha256_bytes((ROOT / rel).read_bytes()) == digest, "Runtime source drift")
    for cell in p["cells"]:
        check_seal(cell)
        require(cell["config_identity"] == p["configs"][cell["config"]]["identity"], "Config drift")
        require(cell["attempt"] == 1 and cell["retry"] == 0, "Attempt policy drift")
    for task in p["tasks"]:
        package = TaskPackage.load(Path(task["package_path"]))
        require(
            TaskIdentity.from_package(package).model_dump(mode="json") == task["task"], "Task drift"
        )
        require(package.oracle_digest == task["oracle_digest"], "Oracle drift")
    return p


def readback(output):
    for rel, digest in load(output / "sha256.json").items():
        require(sha256_bytes((output / rel).read_bytes()) == digest, "Artifact drift")
    receipt = load(output / "receipt.json")
    check_seal(receipt)
    raw = load(output / "result.json")["projection"]["original_evidence"]
    run = Path(receipt["artifact_directory"])
    require(load(run / "manifest.json") == raw, "Manifest drift")
    require(digest_tree(run / "workspace") == raw["workspace_output_digest"], "Workspace drift")
    require(digest_tree(run) == receipt["artifact_digest"], "Bundle drift")
    for rel, field in [("trace/normalized.json", "normalized_trace_digest")]:
        require(sha256_bytes((run / rel).read_bytes()) == raw[field], "Trace drift")
    return receipt


async def execute(index):
    plan = verify()
    phase = load(FREEZE / "phase-authorization.json")
    check_seal(phase)
    require(
        phase["campaign_identity"] == plan["identity"] and phase["execution_authorized"],
        "Authorization drift",
    )
    require(0 <= index < 20, "Index out of scope")
    output = BASE / f"campaign-{index:02d}"
    require(not output.exists(), "Attempt identity consumed")
    if index:
        require(
            readback(BASE / f"campaign-{index - 1:02d}")["continue_allowed"],
            "Previous hard failure; no resume",
        )
    cell = plan["cells"][index]
    side = cell["config"]
    cfg = plan["configs"][side]
    reservation = phase["cells"][index]
    require(reservation["cell_identity"] == cell["identity"], "Reservation mismatch")
    task = next(t for t in plan["tasks"] if t["task"]["task_id"] == cell["task_id"])
    profile = (
        repair_profile() if side == "codex" else MultiHarnessProfile.model_validate(cfg["profile"])
    )
    require(profile.fingerprint == cfg["profile_identity"], "Profile drift")
    package = TaskPackage.load(Path(task["package_path"]))
    prompt = prompt_for(package, side, profile)
    require(
        prompt.prompt_hash == cell["prompt_identity"] and prompt.text == cell["prompt_text"],
        "Prompt drift",
    )
    output.mkdir(mode=0o700)
    write(
        output / "authorization.json",
        seal(
            dict(
                kind="D1_ONE_TRIAL_AUTHORIZATION",
                phase_identity=phase["identity"],
                campaign_identity=plan["identity"],
                **reservation,
                issued_at=now(),
                execution_authorized=True,
                attempt=1,
                retry=0,
                resume=False,
                fallback=False,
                judge=False,
                declared_output_tokens=6000,
                session_hard_cap_enforced=False,
            )
        ),
    )
    before = inventory()
    write(output / "runtime-before.json", {k: sorted(v) for k, v in before.items()})
    started = time.monotonic()
    secrets = ()
    auth_bytes = None
    auth = None
    backend = None
    boundary = None
    result = None
    raw = None
    report = None
    errors = []
    dispatched = False
    audit = "NOT_RUN"
    credential_context = contextlib.ExitStack()
    attestation = None
    handoff = None
    try:
        if side == "codex":
            auth = read_auth()
            auth_bytes = AUTH_SOURCE.read_bytes()
            document = json.loads(auth_bytes)
            require(document["tokens"]["access_token"] == auth["access_token"], "Auth read drift")
            secrets = tuple(
                v for v in document["tokens"].values() if isinstance(v, str) and len(v) > 8
            )
            boundary = OfficialBoundary(image=REPAIR_IMAGE, auth=auth, proxy_image=PROXY)
            adapter = RepairAdapter()
            backend = RepairBackend(boundary, explicitly_enabled=True)
        else:
            credentials = credential_context.enter_context(
                resolved_s1_credentials(
                    load(ROOT / "docs/evidence/s1-mini-benchmark-successor-20260921/campaign.json")
                )
            )
            secrets = tuple(v for values in credentials.values() for v in values.values())
            boundary = boundary_for_provider_url(
                credentials[side][cfg["connection"]["provider_base_url_reference"]],
                network_name="s1-final-" + reservation["execution_id"],
                proxy_name="s1-final-" + reservation["execution_id"] + "-proxy",
                proxy_image=PROXY,
            )
            adapter = S1IsolatedClaudeAdapter()
            backend = S1IsolatedClaudeBackend(
                cfg["profile"]["image"]["image_id"],
                seccomp_digest=sha256_bytes(SECCOMP.read_bytes()),
                explicitly_enabled=True,
                credentials=credentials[side],
                egress_boundary=boundary,
            )
        original = backend.run

        async def guarded(execution):
            nonlocal dispatched
            require(not dispatched, "Repeated dispatch")
            inv = cell["invocation"]
            require(
                list(execution.argv) == inv["argv"] and execution.prompt == cell["prompt_text"],
                "Invocation drift",
            )
            require(
                [list(x) for x in execution.environment_references]
                == inv["environment_references"],
                "Environment references drift",
            )
            require(
                [list(x) for x in getattr(execution, "environment_literals", ())]
                == inv["environment_literals"],
                "Environment literals drift",
            )
            require(
                execution.timeout_seconds == 600 and execution.context is None, "Controls drift"
            )
            require(
                digest_tree(execution.workspace) == task["task"]["workspace_digest"],
                "Workspace drift",
            )
            if auth is not None:
                require(auth["expires_at"] > time.time() + 900, "Auth expires too soon")
            dispatched = True
            write(
                output / "dispatch.json",
                seal(
                    dict(
                        execution_id=reservation["execution_id"],
                        time=now(),
                        attempt_consumed=True,
                        invocation_equals_freeze=True,
                    )
                ),
            )
            return await original(execution)

        backend.run = guarded
        sandbox = DevelopmentSandbox(
            artifact_root=output / "verifier", runtime_root=output / "sandbox"
        )
        common = dict(
            artifact_root=output / "runs",
            runtime_root=output / "runtime",
            sandbox=sandbox,
            plan_harness_config_identity=cfg["identity"],
            plan_profile_identity=cfg["profile_identity"],
        )
        if side == "codex":
            runner = CodexHarnessRunner(**common, adapter=adapter)
            result = await runner.run(
                Path(task["package_path"]),
                profile,
                backend=backend,
                run_id=reservation["execution_id"],
            )
        else:
            runner = MultiHarnessRunner(**common)
            result = await runner.run(
                Path(task["package_path"]),
                profile,
                adapter=adapter,
                backend=backend,
                run_id=reservation["execution_id"],
            )
        raw = result.evidence.model_dump(mode="json")
        write(
            output / "result.json",
            seal(
                dict(
                    scope="campaign",
                    counted_in_campaign=True,
                    projection=project_result(
                        raw, cell=cell, campaign=plan["identity"], mode="REAL"
                    ),
                )
            ),
        )
        require(raw["profile_hash"] == cfg["profile_identity"], "Evidence profile drift")
        require(
            raw["workspace_input_digest"] == task["task"]["workspace_digest"],
            "Evidence workspace drift",
        )
        require(
            raw["verifier_definition_digest"] == task["task"]["verifier_digest"], "Verifier drift"
        )
        if (result.artifact_directory / "verifier/stdout.txt").exists():
            report = load(result.artifact_directory / "verifier/stdout.txt")
    except Exception as exc:
        errors.append("execution_or_evidence:" + type(exc).__name__)
    finally:
        if backend:
            if backend.egress_attestation:
                attestation = backend.egress_attestation.model_dump(mode="json")
            handoff = getattr(backend, "permission_handoff", None)
            if hasattr(backend, "credentials"):
                backend.credentials.clear()
        if side == "codex" and boundary:
            write(
                output / "route-observation.json",
                dict(broker_records=boundary.records, broker_security=boundary.security),
            )
        try:
            require(bool(secrets), "Secret audit values unavailable")
            assert_tree_has_no_run_secrets(output, secrets)
            audit = "PASS"
        except Exception:
            audit = "FAIL"
            errors.append("secret_audit_failed")
        credential_context.close()
    after = inventory()
    remaining = {k: sorted(after[k] - before[k]) for k in before}
    runtime_empty = all(
        not list((output / p).iterdir()) for p in ("runtime", "sandbox") if (output / p).exists()
    )
    unchanged = auth_bytes is None or AUTH_SOURCE.read_bytes() == auth_bytes
    cleanup = not any(remaining.values()) and runtime_empty and unchanged
    if side == "codex":
        cleanup = cleanup and bool(boundary and boundary.cleanup_verified)
    write(
        output / "cleanup.json",
        seal(
            dict(
                status="PASS" if cleanup else "FAIL",
                remaining=remaining,
                runtime_directories_empty=runtime_empty,
                auth_source_unchanged=unchanged,
                egress_attestation=attestation,
                permission_handoff=handoff,
            )
        ),
    )
    write(
        output / "secret-audit.json",
        seal(
            dict(
                status=audit, actual_values_checked_in_memory=bool(secrets), values_persisted=False
            )
        ),
    )
    stop = list(errors)
    if audit != "PASS":
        stop.append("secret_audit_not_pass")
    if not cleanup:
        stop.append("cleanup_failure")
    if raw is None:
        stop.append("missing_run_evidence")
    else:
        if raw["outcome"] not in ("verified_pass", "verified_fail"):
            stop.append(raw.get("harness_failure") or raw["outcome"])
        if raw.get("backend_failure"):
            stop.append("backend_failure")
        if raw["timed_out"] or raw.get("cancelled"):
            stop.append("timeout_or_cancelled")
        if raw.get("retry_count") not in (0, None):
            stop.append("retry_observed")
        if not raw.get("trace_event_count"):
            stop.append("missing_trace")
        if not report or not report.get("checks"):
            stop.append("missing_verifier_or_zero_checks")
        m = raw.get("verifier_sandbox_manifest")
        if (
            not m
            or not m["cleanup_verified"]
            or m["timed_out"]
            or m["cancelled"]
            or m["exit_code"] != 0
        ):
            stop.append("verifier_process_not_valid")
        if side == "claude" and (
            not handoff
            or not handoff.get("cleanup_verified")
            or not handoff.get("content_unchanged")
        ):
            stop.append("permission_handoff_not_valid")
        if not attestation:
            stop.append("missing_egress_attestation")
    try:
        verify()
    except Exception:
        stop.append("frozen_identity_readback_failed")
    compliance = budget_compliance(raw.get("usage") if raw else None)
    receipt = seal(
        dict(
            index=index,
            side=side,
            task_id=cell["task_id"],
            cell_identity=cell["identity"],
            campaign_identity=plan["identity"],
            config_identity=cfg["identity"],
            execution_id=reservation["execution_id"],
            consumed=True,
            backend_dispatches=int(dispatched),
            outcome=raw["outcome"] if raw else "NOT_VERIFIED",
            task_success=raw.get("verifier_passed")
            if raw and raw["outcome"] in ("verified_pass", "verified_fail")
            else None,
            continue_allowed=not stop,
            stop_reasons=stop,
            subject_duration_ms=raw["duration_ms"] if raw else None,
            end_to_end_observed_ms=int((time.monotonic() - started) * 1000),
            usage=raw.get("usage") if raw else None,
            cost_usd=None,
            budget_compliance=compliance,
            verifier_checks=len(report["checks"]) if report else None,
            verifier_passed_checks=sum(c["passed"] for c in report["checks"]) if report else None,
            secret_audit=audit,
            cleanup_verified=cleanup,
            provider_request_count=None,
            judge_calls=0,
            artifact_directory=str(result.artifact_directory) if result else None,
            artifact_digest=digest_tree(result.artifact_directory) if result else None,
        )
    )
    write(output / "receipt.json", receipt)
    assert_tree_has_no_run_secrets(output, secrets)
    write(
        output / "sha256.json",
        {
            str(p.relative_to(output)): sha256_bytes(p.read_bytes())
            for p in sorted(output.rglob("*"))
            if p.is_file()
        },
    )
    if result:
        readback(output)
    print(
        json.dumps(
            {
                k: receipt[k]
                for k in (
                    "index",
                    "side",
                    "task_id",
                    "outcome",
                    "continue_allowed",
                    "stop_reasons",
                    "subject_duration_ms",
                    "verifier_checks",
                    "verifier_passed_checks",
                    "budget_compliance",
                )
            }
        ),
        flush=True,
    )
    return not stop


if __name__ == "__main__":
    try:
        ok = asyncio.run(execute(int(sys.argv[1])))
        sys.exit(0 if ok else 2)
    except Exception as exc:
        print(json.dumps({"status": "BLOCKED", "error_type": type(exc).__name__}), flush=True)
        sys.exit(1)
