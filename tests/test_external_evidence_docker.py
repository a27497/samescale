"""Independent real Docker Verifier only; the supplied run records are synthetic fixtures."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from harnesslab.external_evidence import service
from harnesslab.external_evidence.models import EvidencePolicy
from harnesslab.external_evidence.verification import verify_workspace
from harnesslab.local_execution.sandbox import PinnedVerifierSandbox
from harnesslab.local_plans.tasks import LocalImport, import_task, load_policy
from harnesslab.tasks.package import TaskPackage, digest_tree
from tests.local_execution_helpers import prepare_execution_fixture
from tests.test_external_evidence import native_source
from tests.test_external_evidence_generic import generic_source


@pytest.mark.parametrize("harness", ["codex-hooks", "claude-code", "code-only"])
async def test_independent_saved_workspace_pass_fail_timeout_and_consumed_attempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, harness: str
) -> None:
    # Two actual isolated baseline/oracle observations, not fabricated admission receipts.
    task_policy, execution_path, package_path = await prepare_execution_fixture(
        tmp_path / "trusted"
    )
    monkeypatch.setenv("HARNESSLAB_LOCAL_TASK_POLICY", str(task_policy))
    inspection = import_task(
        load_policy(), LocalImport(root_id="trusted", relative_path="micro-python-clamp/1.0.2")
    )
    assert inspection.eligible_for_planning
    package = TaskPackage.load(package_path)
    from harnesslab.local_execution.models import ExecutionPolicy

    execution = ExecutionPolicy.model_validate_json(execution_path.read_bytes())
    outcomes = []
    original = PinnedVerifierSandbox.__init__
    for scenario in ("baseline", "oracle", "timeout", "interrupted"):
        case_root = tmp_path / ("case-" + scenario)
        source = (
            native_source(case_root)
            if harness == "codex-hooks"
            else generic_source(case_root, harness)
        )
        shutil.rmtree(source.workspace)
        shutil.copytree(package_path / "workspace", source.workspace)
        if scenario != "baseline":
            for path in package.oracle_path.rglob("*"):
                if path.is_file():
                    shutil.copyfile(path, source.workspace / path.relative_to(package.oracle_path))
        source = source.model_copy(
            update={
                "workspace_digest": digest_tree(source.workspace),
                "task_reference": inspection.reference,
                "task_digest": package.definition.content_digest,
            }
        )
        policy = EvidencePolicy(
            store=case_root / "records",
            sources=(source,),
            verifier_image_id=execution.verifier_image_identity,
            runtime_root=case_root / "runtime",
            artifact_root=case_root / "artifacts",
        )
        item = service.ingest(policy, source.source_id)
        assert item["diagnosis"]["workspace_acceptance"] == "NOT_VERIFIED"
        assert item["record"]["source"]["source_kind"] == "synthetic"
        before = (policy.store / item["identity"] / "record.json").read_bytes()
        if scenario == "interrupted":
            (policy.store / item["identity"] / ".verifier-started").write_text("INTERRUPTED")
            with pytest.raises(FileExistsError):
                await verify_workspace(policy, item["identity"])
            assert (
                service.view(policy, item["identity"])["diagnosis"]["workspace_acceptance"]
                == "NOT_VERIFIED"
            )
            continue

        def timeout_sandbox(self: PinnedVerifierSandbox, **kwargs: object) -> None:
            original(self, **kwargs, force_timeout=True)  # type: ignore[arg-type]

        with monkeypatch.context() as m:
            if scenario == "timeout":
                m.setattr(PinnedVerifierSandbox, "__init__", timeout_sandbox)
            receipt = await verify_workspace(policy, item["identity"])
        assert await verify_workspace(policy, item["identity"]) == receipt
        assert (policy.store / item["identity"] / "record.json").read_bytes() == before
        assert receipt["agent_reexecuted"] is False and receipt["automatic_retry"] is False
        assert receipt["physical_attempts"] == 1
        if scenario == "timeout":
            assert receipt["acceptance"] == "NOT_VERIFIED" and receipt["checks"] == 0
        else:
            assert receipt["checks"] == 3
            assert receipt["acceptance"] == (
                "VERIFIED_PASS" if scenario == "oracle" else "VERIFIED_FAIL"
            )
            assert (
                service.view(policy, item["identity"])["record"]["original_acceptance"]
                == "NOT_VERIFIED"
            )
        packet = service.export_record(policy, item["identity"])
        if scenario == "baseline" and harness == "codex-hooks":
            # Real isolated FAIL already exists. Arbitrary diagnosis outputs/errors/timeouts
            # cannot change its receipt, imported Episode/record or subsequent export/replay.
            import json

            from harnesslab.failure_diagnosis.service import canonical, diagnose, sha256
            from harnesslab.failure_diagnosis.storage import load_input
            from tests.test_failure_diagnosis import Fake, answer
            from tests.test_failure_diagnosis import packet as public_packet

            snapshot = {p: p.read_bytes() for p in policy.store.rglob("*") if p.is_file()}
            failed_ordinal = next(r["ordinal"] for r in receipt["check_results"] if not r["passed"])
            excerpts = public_packet()
            excerpts["excerpts"][2]["reference"] = f"check:{failed_ordinal}"
            public_path = case_root / "public-packet.json"
            public_path.write_bytes(canonical(excerpts))
            receipt_path = policy.store / item["identity"] / "verification.json"
            diagnostic_input = load_input(
                receipt_path, sha256(receipt_path.read_bytes()), public_path
            )
            for backend in (
                Fake(json.dumps(answer())),
                Fake('{"verdict":"PASS"}'),
                Fake(error=RuntimeError("failed")),
                Fake(delay=True),
            ):
                diagnosed = await diagnose(diagnostic_input, backend, timeout_seconds=0.02)
                assert diagnosed.input.acceptance.status == "VERIFIED_FAIL"
                assert {p: p.read_bytes() for p in snapshot} == snapshot
                assert await verify_workspace(policy, item["identity"]) == receipt
                assert service.export_record(policy, item["identity"]) == packet
        from harnesslab.tasks.package import sha256_bytes

        assert (
            service.replay_export(packet, sha256_bytes(packet))["diagnosis"]["workspace_acceptance"]
            == receipt["acceptance"]
        )
        outcomes.append(receipt["acceptance"])
    assert outcomes == ["VERIFIED_FAIL", "VERIFIED_PASS", "NOT_VERIFIED"]
