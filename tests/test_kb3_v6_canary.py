from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

import harnesslab.release.v6_canary as v6_canary_module
from harnesslab.egress import EgressProxyRuntime
from harnesslab.multi_harness.models import HarnessKind
from harnesslab.multi_harness.profile import configured_qwen_alibaba_bailian_claude_profile
from harnesslab.multi_harness.prompt import render_harness_prompt
from harnesslab.multi_harness.runtime import MultiHarnessRuntime
from harnesslab.release.v6_authorization import (
    V6CanaryAuthorizationReceipt,
    V6CanaryAuthorizationRequest,
    V6MatrixAuthorizationReceipt,
)
from harnesslab.release.v6_canary import (
    EXPECTED_CALL_IDS,
    ProductionV6CanaryInvoker,
    V6CanaryCall,
    V6CanaryCallEvidence,
    V6CanaryControl,
    V6CanaryControlError,
    V6CanaryControlPlane,
    V6CanaryFailureCategory,
    V6CanaryLaunchMarker,
    V6CanaryPreflightReceipt,
    V6CanaryStatus,
    V6HostObservation,
    V6OperatorInputs,
    assess_v6_canary_preflight,
    authorize_v6_canary,
    collect_v6_host_observation,
    execute_real_v6_canary,
    load_v6_canary_control,
    persist_v6_preflight_receipt,
    v6_preflights_are_execution_equivalent,
)
from harnesslab.sandbox.models import ImageIdentity

ROOT = Path(__file__).resolve().parents[1]
OPENAI_ENDPOINT = "https://workspace-sentinel.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
ANTHROPIC_ENDPOINT = "https://workspace-sentinel.cn-beijing.maas.aliyuncs.com/apps/anthropic"
SECRET = "unit-test-secret-that-must-not-be-persisted"


def _environment() -> dict[str, str]:
    return {
        "HARNESSLAB_ALIBABA_BAILIAN_OPENAI_BASE_URL": OPENAI_ENDPOINT,
        "HARNESSLAB_ALIBABA_BAILIAN_ANTHROPIC_BASE_URL": ANTHROPIC_ENDPOINT,
        "HARNESSLAB_ALIBABA_BAILIAN_API_KEY": SECRET,
        "HARNESSLAB_ALIBABA_BAILIAN_QWEN38_MODEL_ID": "qwen3.8-max",
        "HARNESSLAB_ALIBABA_BAILIAN_GLM52_MODEL_ID": "glm-5.2",
    }


def _operator_inputs() -> V6OperatorInputs:
    return V6OperatorInputs(
        input_id="v6-canary-unit-test",
        billing_region="China (Beijing)",
        billing_currency="CNY",
        qwen_deployed_model_id="qwen3.8-max",
        glm_deployed_model_id="glm-5.2",
        cache_or_batch_adjustments="NONE_CONFIRMED",
        account_specific_promotions="NONE_CONFIRMED",
        tax_treatment="ALIYUN_CHINA_SITE_PUBLIC_PRICES_INCLUDE_VAT",
        fx_treatment="NO_FX_CNY_PRICING_AND_CNY_SETTLEMENT",
        public_region_and_model_rates_apply=True,
        host_attestation_reference="operator-host-attestation:v6-canary-unit-test",
    )


def _host() -> V6HostObservation:
    return V6HostObservation(
        docker_ready=True,
        egress_isolation_ready=True,
        cpu_count=8,
        memory_bytes=16 * 1024**3,
        disk_free_bytes=1024**3,
        claude_image=ImageIdentity(
            reference="harnesslab-phase-f-claude:2.1.241",
            image_id="sha256:" + "b" * 64,
        ),
        egress_proxy_image=ImageIdentity(
            reference="harnesslab-egress-proxy:1.0.0",
            image_id="sha256:" + "c" * 64,
        ),
    )


@pytest.fixture(scope="module")
def control() -> V6CanaryControl:
    return load_v6_canary_control(ROOT)


def _preflight(
    control: V6CanaryControl,
    *,
    environment: dict[str, str] | None = None,
    operator: V6OperatorInputs | None = None,
    host: V6HostObservation | None = None,
) -> V6CanaryPreflightReceipt:
    return assess_v6_canary_preflight(
        ROOT,
        control,
        operator or _operator_inputs(),
        environment or _environment(),
        host or _host(),
    )


def _authorization(
    control: V6CanaryControl, preflight: V6CanaryPreflightReceipt
) -> V6CanaryAuthorizationReceipt:
    return authorize_v6_canary(
        preflight,
        V6CanaryAuthorizationRequest(
            scope="CORE_REAL_MATRIX_V6_THREE_CALL_CANARY",
            authorization_id="v6-canary-unit-test-auth",
            operator_reference="operator:test",
            authorized_at=datetime(2026, 8, 31, tzinfo=UTC),
            experiment_id="core-real-matrix-v6",
            plan_digest=control.plan_digest,
            canary_plan_digest=control.digest,
            preflight_receipt_digest=preflight.receipt_digest,
            spend_authorized=True,
            allow_real_canary=True,
            max_primary_calls=3,
            max_provider_requests=18,
            max_harness_turns=16,
        ),
    )


class _FakeInvoker:
    def __init__(
        self,
        evidence_root: Path,
        *,
        fail_call: str | None = None,
    ) -> None:
        self.evidence_root = evidence_root
        self.fail_call = fail_call
        self.calls: list[str] = []

    async def invoke(
        self, call: V6CanaryCall, marker: V6CanaryLaunchMarker
    ) -> V6CanaryCallEvidence:
        self.calls.append(call.call_id)
        call_root = self.evidence_root / call.call_id
        call_root.mkdir(parents=True, exist_ok=True)
        path = call_root / "evidence.json"
        path.write_text("keyless fake evidence\n", encoding="utf-8")
        failure = V6CanaryFailureCategory.PROVIDER if call.call_id == self.fail_call else None
        return ProductionV6CanaryInvoker._call_evidence(
            call,
            marker,
            observed_model=call.requested_model,
            safe_outcome="FAKE_TERMINAL",
            failure=failure,
            evidence_reference=str(path.resolve()),
            evidence_digest="sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
        )


class _ExplodingInvoker:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def invoke(
        self, call: V6CanaryCall, marker: V6CanaryLaunchMarker
    ) -> V6CanaryCallEvidence:
        self.calls.append(call.call_id)
        raise RuntimeError(SECRET)


def test_control_is_exactly_three_calls_with_structural_zero_retries(
    control: V6CanaryControl,
) -> None:
    assert tuple(item.call_id for item in control.calls) == EXPECTED_CALL_IDS
    assert control.max_primary_calls == 3
    assert control.max_provider_requests == 18
    assert control.max_harness_turns == 16
    assert tuple(item.max_provider_requests for item in control.calls) == (1, 16, 1)
    assert tuple(item.max_harness_turns for item in control.calls) == (None, 16, None)
    assert control.retries == control.semantic_retries == control.substitutions == 0
    assert control.matrix_execution_allowed is False
    assert control.judge_initial_state == "PROVISIONAL_PENDING_REAL_CANARY"
    assert control.throughput_profile_binding.startswith("NOT_REQUIRED_FOR_THREE_CALL_CANARY")
    assert control.predecessor_canary_plan_digest == (
        "sha256:01e958bc9d68b667b0258b78980773c97f8032ca9864a642d4136c0a88065dec"
    )
    assert control.successor_reason == "CONFIRMED_INFRASTRUCTURE_EGRESS_FIX"
    assert control.treatment_change == "EGRESS_OUTBOUND_NETWORK_IMPLEMENTATION"


def test_r1_successor_changes_only_egress_treatment_and_preserves_matrix_identity(
    control: V6CanaryControl,
) -> None:
    predecessor = load_v6_canary_control(
        ROOT,
        control_reference=Path("release/core-real-matrix-v6-canary-control.json"),
    )
    matrix_control = json.loads(
        (ROOT / "release/core-real-matrix-v6-control.json").read_text(encoding="utf-8")
    )

    assert predecessor.digest == control.predecessor_canary_plan_digest
    assert control.digest != predecessor.digest
    assert control.calls == predecessor.calls
    predecessor_payload = predecessor.model_dump(mode="json")
    successor_payload = control.model_dump(mode="json")
    for field in (
        "predecessor_canary_plan_digest",
        "successor_reason",
        "treatment_change",
    ):
        predecessor_payload.pop(field)
        successor_payload.pop(field)
    assert successor_payload == predecessor_payload
    assert (
        control.plan_digest
        == matrix_control["plan_digest"]
        == ("sha256:c18afc7b003a379f3456b23649e6d161da55e4fb5a34b4702dffbff35fb3604a")
    )
    assert matrix_control["schedule_digest"] == (
        "sha256:f3ac0384cddafd4b4dd7b811f66a0e117cdc7e68b758cd111d5e6a4d6726dd2a"
    )


@pytest.mark.asyncio
async def test_attempt1_preflight_and_authorization_cannot_authorize_r1(
    tmp_path: Path, control: V6CanaryControl
) -> None:
    predecessor = load_v6_canary_control(
        ROOT,
        control_reference=Path("release/core-real-matrix-v6-canary-control.json"),
    )
    old_preflight = _preflight(predecessor)
    old_authorization = _authorization(predecessor, old_preflight)
    invoker = _FakeInvoker(tmp_path / "provider-evidence")

    assert old_preflight.canary_plan_digest == predecessor.digest
    assert old_authorization.canary_plan_digest == predecessor.digest
    assert predecessor.digest != control.digest
    assert not v6_preflights_are_execution_equivalent(old_preflight, _preflight(control))
    with pytest.raises(V6CanaryControlError, match="authorization boundary mismatch"):
        await V6CanaryControlPlane(control).execute(
            preflight=old_preflight,
            authorization=old_authorization,
            invoker=invoker,
            artifact_root=tmp_path / "must-not-exist",
            allow_real_v6_canary=True,
        )
    assert invoker.calls == []
    assert not (tmp_path / "must-not-exist").exists()


def test_attempt1_incident_is_safe_append_only_and_non_resumable() -> None:
    path = ROOT / "release/kb3-v6-canary-attempt1-infrastructure-incident.json"
    incident = json.loads(path.read_text(encoding="utf-8"))

    assert incident["append_only"] is True
    assert incident["attempt_state"] == "NON_RESUMABLE"
    assert incident["calls"][0]["status"] == "VERIFIED_PASS"
    assert incident["calls"][1]["provider_request_consumption"] == "UNKNOWN"
    assert incident["calls"][1]["confirmed_failure_stage"] == "EGRESS_PROVISIONING"
    assert incident["calls"][2]["status"] == "SKIPPED"
    assert incident["bounds_observed"] == {
        "retries": 0,
        "semantic_retries": 0,
        "substitutions": 0,
        "matrix_calls": 0,
    }
    assert incident["root_cause_reproduction"] == "KEYLESS"
    assert incident["credential_transport_finding"] == "NOT_CAUSAL"
    assert incident["immutability"]["old_artifacts_modified"] is False


def test_v6_claude_adapter_binds_turn_and_output_limits(
    tmp_path: Path, control: V6CanaryControl
) -> None:
    call = control.calls[1]
    image = _host().claude_image
    assert image is not None
    assert call.task_digest is not None
    profile = configured_qwen_alibaba_bailian_claude_profile(
        image, execution_timeout_seconds=call.timeout_seconds
    )
    prompt = render_harness_prompt(
        HarnessKind.CLAUDE_CODE,
        task_instruction="Bounded V6 canary test.",
        task_digest=call.task_digest,
        workspace_input_digest="sha256:" + "d" * 64,
        context_digest=None,
        network_policy=profile.network_policy,
    )
    plan = ProductionV6CanaryInvoker._claude_adapter(call).prepare(
        profile, prompt, workspace=tmp_path, context=None, task_id="v6-bounded-claude"
    )
    assert plan.argv.count("--max-turns") == 1
    index = plan.argv.index("--max-turns")
    assert plan.argv[index : index + 2] == ("--max-turns", "16")
    assert dict(plan.environment_literals)["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == "2000"


def test_control_binds_current_v6_source_and_public_rate_fact(
    control: V6CanaryControl,
) -> None:
    source_path = ROOT / control.v6_control_reference
    source = json.loads(source_path.read_text(encoding="utf-8"))
    assert (
        control.v6_control_sha256
        == "sha256:" + hashlib.sha256(source_path.read_bytes()).hexdigest()
    )
    assert control.public_rate_fact_digest == source["pricing"]["public_rate_fact_digest"]


@pytest.mark.parametrize(
    ("mutation", "reason_code"),
    [
        (
            {"HARNESSLAB_ALIBABA_BAILIAN_API_KEY": ""},
            "ALIBABA_CREDENTIAL_MISSING",
        ),
        (
            {
                "HARNESSLAB_ALIBABA_BAILIAN_ANTHROPIC_BASE_URL": (
                    "https://other-workspace.cn-beijing.maas.aliyuncs.com/apps/anthropic"
                )
            },
            "ALIBABA_ENDPOINT_WORKSPACE_MISMATCH",
        ),
        (
            {"HARNESSLAB_ALIBABA_BAILIAN_QWEN38_MODEL_ID": "qwen-different"},
            "ALIBABA_DEPLOYED_MODEL_ID_MISMATCH",
        ),
    ],
)
def test_failed_identity_preflight_is_blocked_and_zero_call(
    control: V6CanaryControl,
    mutation: dict[str, str],
    reason_code: str,
) -> None:
    environment = {**_environment(), **mutation}
    receipt = _preflight(control, environment=environment)
    assert receipt.status is V6CanaryStatus.BLOCKED
    assert reason_code in {item.reason_code for item in receipt.findings}
    assert (receipt.provider_calls, receipt.harness_provider_calls, receipt.judge_calls) == (
        0,
        0,
        0,
    )


def test_missing_pricing_inputs_stay_required_and_never_become_zero(
    control: V6CanaryControl,
) -> None:
    incomplete = V6OperatorInputs(input_id="v6-incomplete-pricing")
    receipt = _preflight(control, operator=incomplete)
    pricing = [item for item in receipt.findings if item.check_id.startswith("pricing:")]
    assert receipt.status is V6CanaryStatus.BLOCKED
    assert receipt.pricing_status == "OPERATOR_INPUTS_REQUIRED"
    assert pricing and all(item.status.value == "BLOCKED" for item in pricing)
    assert "pricing:account-reference" not in {item.check_id for item in receipt.findings}
    assert all("not treated as zero" in item.detail for item in pricing)


def test_stale_usd_operator_currency_is_blocked_and_zero_call(
    control: V6CanaryControl,
) -> None:
    operator = _operator_inputs().model_copy(update={"billing_currency": "USD"})
    receipt = _preflight(control, operator=operator)
    currency = next(
        item for item in receipt.findings if item.check_id == "pricing:billing-currency"
    )
    assert receipt.status is V6CanaryStatus.BLOCKED
    assert receipt.pricing_status == "OPERATOR_INPUTS_REQUIRED"
    assert currency.status.value == "BLOCKED"
    assert (receipt.provider_calls, receipt.harness_provider_calls, receipt.judge_calls) == (
        0,
        0,
        0,
    )


def test_certified_tokyo_memory_passes_and_sub_16_gb_class_memory_blocks(
    control: V6CanaryControl,
) -> None:
    certified = assess_v6_canary_preflight(
        ROOT,
        control,
        _operator_inputs(),
        _environment(),
        _host().model_copy(update={"memory_bytes": 16768626688}),
    )
    below_floor = assess_v6_canary_preflight(
        ROOT,
        control,
        _operator_inputs(),
        _environment(),
        _host().model_copy(update={"memory_bytes": 15999999999}),
    )
    certified_memory = next(item for item in certified.findings if item.check_id == "host:memory")
    below_floor_memory = next(
        item for item in below_floor.findings if item.check_id == "host:memory"
    )
    assert control.host_minimums.memory_bytes == 16000000000
    assert certified.status is V6CanaryStatus.READY
    assert certified_memory.status.value == "PASS"
    assert certified_memory.reason_code == "PRODUCTION_MEMORY_READY"
    assert below_floor.status is V6CanaryStatus.BLOCKED
    assert below_floor_memory.status.value == "BLOCKED"
    assert below_floor_memory.reason_code == "PRODUCTION_MEMORY_INSUFFICIENT"
    assert (certified.provider_calls, certified.harness_provider_calls, certified.judge_calls) == (
        0,
        0,
        0,
    )
    assert (
        below_floor.provider_calls,
        below_floor.harness_provider_calls,
        below_floor.judge_calls,
    ) == (0, 0, 0)


@pytest.mark.asyncio
async def test_host_observation_requires_full_proxy_topology_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    host = _host()
    checked_images: list[ImageIdentity] = []

    async def docker_ready() -> None:
        return None

    async def claude_image_ready(self: object) -> ImageIdentity:
        assert host.claude_image is not None
        return host.claude_image

    async def proxy_image_ready(self: object) -> ImageIdentity:
        assert host.egress_proxy_image is not None
        return host.egress_proxy_image

    async def broken_outbound_topology(*, proxy_image: ImageIdentity) -> None:
        checked_images.append(proxy_image)
        raise RuntimeError("default bridge is unavailable")

    monkeypatch.setattr(v6_canary_module, "docker_preflight", docker_ready)
    monkeypatch.setattr(
        MultiHarnessRuntime,
        "ensure_image",
        claude_image_ready,
    )
    monkeypatch.setattr(
        EgressProxyRuntime,
        "ensure_image",
        proxy_image_ready,
    )
    monkeypatch.setattr(
        v6_canary_module,
        "preflight_egress_network_isolation",
        broken_outbound_topology,
    )

    observation = await collect_v6_host_observation(ROOT)

    assert checked_images == [host.egress_proxy_image]
    assert observation.docker_ready is True
    assert observation.egress_isolation_ready is False
    assert observation.claude_image == host.claude_image
    assert observation.egress_proxy_image == host.egress_proxy_image


def test_ready_receipt_contains_only_references_and_fingerprints(
    control: V6CanaryControl,
) -> None:
    receipt = _preflight(control)
    serialized = receipt.model_dump_json()
    assert receipt.status is V6CanaryStatus.READY
    assert "account_reference_fingerprint" not in V6OperatorInputs.model_fields
    assert "pricing:account-reference" not in {item.check_id for item in receipt.findings}
    assert receipt.endpoint_evidence.same_workspace is True
    assert receipt.endpoint_evidence.openai_endpoint_fingerprint is not None
    assert receipt.endpoint_evidence.anthropic_endpoint_fingerprint is not None
    assert receipt.endpoint_evidence.workspace_fingerprint is not None
    assert (
        receipt.endpoint_evidence.openai_endpoint_fingerprint
        != receipt.endpoint_evidence.anthropic_endpoint_fingerprint
    )
    assert receipt.credential_present is True
    assert receipt.max_primary_calls == 3
    assert receipt.max_provider_requests == 18
    assert receipt.max_harness_turns == 16
    assert receipt.retries == receipt.semantic_retries == receipt.substitutions == 0
    assert receipt.matrix_execution_authorized is False
    assert SECRET not in serialized
    assert OPENAI_ENDPOINT not in serialized
    assert ANTHROPIC_ENDPOINT not in serialized
    assert "workspace-sentinel" not in serialized
    assert receipt.judge_state == "PROVISIONAL_PENDING_REAL_CANARY"


def test_identical_ready_preflights_are_execution_equivalent(
    control: V6CanaryControl,
) -> None:
    authorized = _preflight(control)
    assert v6_preflights_are_execution_equivalent(authorized, authorized)


def test_ready_preflights_allow_only_disk_free_bytes_to_vary(
    control: V6CanaryControl,
) -> None:
    authorized = _preflight(control)
    current = _preflight(
        control,
        host=_host().model_copy(update={"disk_free_bytes": 2 * 1024**3}),
    )
    assert authorized.host_observation.disk_free_bytes != current.host_observation.disk_free_bytes
    assert authorized.status is current.status is V6CanaryStatus.READY
    assert v6_preflights_are_execution_equivalent(authorized, current)


def test_disk_derived_receipt_digest_difference_is_execution_equivalent(
    control: V6CanaryControl,
) -> None:
    authorized = _preflight(control)
    current = _preflight(
        control,
        host=_host().model_copy(update={"disk_free_bytes": 2 * 1024**3}),
    )
    assert authorized.receipt_digest != current.receipt_digest
    assert v6_preflights_are_execution_equivalent(authorized, current)


@pytest.mark.asyncio
async def test_current_disk_below_minimum_blocks_before_invoker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    control: V6CanaryControl,
) -> None:
    authorized = _preflight(control)
    current = _preflight(
        control,
        host=_host().model_copy(
            update={"disk_free_bytes": control.host_minimums.disk_free_bytes - 1}
        ),
    )
    authorization = _authorization(control, authorized)
    constructions = 0

    async def current_preflight(*args: object, **kwargs: object) -> V6CanaryPreflightReceipt:
        return current

    def unexpected_invoker(*args: object, **kwargs: object) -> None:
        nonlocal constructions
        constructions += 1
        raise AssertionError("blocked preflight constructed the production invoker")

    monkeypatch.setattr(v6_canary_module, "run_v6_canary_preflight", current_preflight)
    monkeypatch.setattr(v6_canary_module, "ProductionV6CanaryInvoker", unexpected_invoker)
    assert current.status is V6CanaryStatus.BLOCKED
    assert not v6_preflights_are_execution_equivalent(authorized, current)
    with pytest.raises(V6CanaryControlError, match="current V6 preflight is not READY"):
        await execute_real_v6_canary(
            ROOT,
            operator_inputs=_operator_inputs(),
            preflight_receipt=authorized,
            authorization=authorization,
            artifact_root=tmp_path / "below-disk-floor",
            allow_real_v6_canary=True,
            environment=_environment(),
        )
    assert constructions == 0


@pytest.mark.parametrize(
    "drift",
    (
        "endpoint-fingerprint",
        "same-workspace",
        "credential-present",
        "model-binding",
        "operator-input-digest",
        "pricing-status",
        "public-rate-digest",
        "docker-status",
        "egress-isolation",
        "cpu-count",
        "memory-bytes",
        "claude-image-identity",
        "egress-image-identity",
        "max-primary-calls",
        "max-provider-requests",
        "max-harness-turns",
        "judge-state",
        "finding-reason",
    ),
)
@pytest.mark.asyncio
async def test_nonvolatile_preflight_drift_blocks_before_invoker(
    drift: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    control: V6CanaryControl,
) -> None:
    authorized = _preflight(control)
    current = authorized
    other_digest = "sha256:" + "e" * 64
    if drift == "endpoint-fingerprint":
        current = current.model_copy(
            update={
                "endpoint_evidence": current.endpoint_evidence.model_copy(
                    update={"openai_endpoint_fingerprint": other_digest}
                )
            }
        )
    elif drift == "same-workspace":
        current = current.model_copy(
            update={
                "endpoint_evidence": current.endpoint_evidence.model_copy(
                    update={"same_workspace": False}
                )
            }
        )
    elif drift == "credential-present":
        current = current.model_copy(update={"credential_present": False})
    elif drift == "model-binding":
        changed_binding = current.model_bindings[0].model_copy(
            update={"execution_binding_identity": other_digest}
        )
        current = current.model_copy(
            update={"model_bindings": (changed_binding, *current.model_bindings[1:])}
        )
    elif drift == "operator-input-digest":
        current = current.model_copy(update={"operator_input_digest": other_digest})
    elif drift == "pricing-status":
        current = current.model_copy(update={"pricing_status": "OPERATOR_INPUTS_REQUIRED"})
    elif drift == "public-rate-digest":
        current = current.model_copy(update={"public_rate_fact_digest": other_digest})
    elif drift == "docker-status":
        current = current.model_copy(
            update={
                "host_observation": current.host_observation.model_copy(
                    update={"docker_ready": False}
                )
            }
        )
    elif drift == "egress-isolation":
        current = current.model_copy(
            update={
                "host_observation": current.host_observation.model_copy(
                    update={"egress_isolation_ready": False}
                )
            }
        )
    elif drift == "cpu-count":
        current = current.model_copy(
            update={
                "host_observation": current.host_observation.model_copy(update={"cpu_count": 7})
            }
        )
    elif drift == "memory-bytes":
        current = current.model_copy(
            update={
                "host_observation": current.host_observation.model_copy(
                    update={"memory_bytes": 17 * 1024**3}
                )
            }
        )
    elif drift == "claude-image-identity":
        assert current.host_observation.claude_image is not None
        current = current.model_copy(
            update={
                "host_observation": current.host_observation.model_copy(
                    update={
                        "claude_image": current.host_observation.claude_image.model_copy(
                            update={"image_id": other_digest}
                        )
                    }
                )
            }
        )
    elif drift == "egress-image-identity":
        assert current.host_observation.egress_proxy_image is not None
        current = current.model_copy(
            update={
                "host_observation": current.host_observation.model_copy(
                    update={
                        "egress_proxy_image": (
                            current.host_observation.egress_proxy_image.model_copy(
                                update={"image_id": other_digest}
                            )
                        )
                    }
                )
            }
        )
    elif drift == "max-primary-calls":
        current = current.model_copy(update={"max_primary_calls": 4})
    elif drift == "max-provider-requests":
        current = current.model_copy(update={"max_provider_requests": 19})
    elif drift == "max-harness-turns":
        current = current.model_copy(update={"max_harness_turns": 17})
    elif drift == "judge-state":
        current = current.model_copy(update={"judge_state": "CANARY_QUALIFIED"})
    elif drift == "finding-reason":
        changed_finding = current.findings[0].model_copy(
            update={"reason_code": "UNEXPECTED_REASON_DRIFT"}
        )
        current = current.model_copy(update={"findings": (changed_finding, *current.findings[1:])})
    else:  # pragma: no cover - the parameter list is closed above
        raise AssertionError(f"unknown drift case: {drift}")

    authorization = _authorization(control, authorized)
    constructions = 0

    async def current_preflight(*args: object, **kwargs: object) -> V6CanaryPreflightReceipt:
        return current

    def unexpected_invoker(*args: object, **kwargs: object) -> None:
        nonlocal constructions
        constructions += 1
        raise AssertionError("nonvolatile drift constructed the production invoker")

    monkeypatch.setattr(v6_canary_module, "run_v6_canary_preflight", current_preflight)
    monkeypatch.setattr(v6_canary_module, "ProductionV6CanaryInvoker", unexpected_invoker)
    assert not v6_preflights_are_execution_equivalent(authorized, current)
    with pytest.raises(V6CanaryControlError, match="differs from the authorized"):
        await execute_real_v6_canary(
            ROOT,
            operator_inputs=_operator_inputs(),
            preflight_receipt=authorized,
            authorization=authorization,
            artifact_root=tmp_path / drift,
            allow_real_v6_canary=True,
            environment=_environment(),
        )
    assert constructions == 0


@pytest.mark.asyncio
async def test_execution_uses_current_host_and_original_authorized_receipt_binding(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    control: V6CanaryControl,
) -> None:
    authorized = _preflight(control)
    current = _preflight(
        control,
        host=_host().model_copy(update={"disk_free_bytes": 2 * 1024**3}),
    )
    authorization = _authorization(control, authorized)
    authorization_digest = authorization.authorization_digest
    observed_hosts: list[V6HostObservation] = []

    async def current_preflight(*args: object, **kwargs: object) -> V6CanaryPreflightReceipt:
        return current

    def fake_production_invoker(
        repository_root: Path,
        environment: dict[str, str],
        artifact_root: Path,
        host_observation: V6HostObservation,
    ) -> _FakeInvoker:
        observed_hosts.append(host_observation)
        return _FakeInvoker(artifact_root / "provider-evidence")

    monkeypatch.setattr(v6_canary_module, "run_v6_canary_preflight", current_preflight)
    monkeypatch.setattr(v6_canary_module, "ProductionV6CanaryInvoker", fake_production_invoker)
    artifact_root = tmp_path / "current-host-original-binding"
    closeout = await execute_real_v6_canary(
        ROOT,
        operator_inputs=_operator_inputs(),
        preflight_receipt=authorized,
        authorization=authorization,
        artifact_root=artifact_root,
        allow_real_v6_canary=True,
        environment=_environment(),
    )
    marker = json.loads(
        (artifact_root / "launch-journal" / f"001-{EXPECTED_CALL_IDS[0]}.json").read_text(
            encoding="utf-8"
        )
    )
    assert observed_hosts == [current.host_observation]
    assert closeout.preflight_receipt_digest == authorized.receipt_digest
    assert marker["preflight_receipt_digest"] == authorized.receipt_digest
    assert authorization.preflight_receipt_digest == authorized.receipt_digest
    assert authorization.authorization_digest == authorization_digest


def test_receipt_persistence_is_immutable_and_idempotent(
    tmp_path: Path, control: V6CanaryControl
) -> None:
    receipt = _preflight(control)
    first = persist_v6_preflight_receipt(tmp_path, receipt)
    assert persist_v6_preflight_receipt(tmp_path, receipt) == first
    first.write_text("changed\n", encoding="utf-8")
    with pytest.raises(V6CanaryControlError, match="different bytes"):
        persist_v6_preflight_receipt(tmp_path, receipt)


def test_authorization_scopes_reject_v5_and_matrix_reuse(
    control: V6CanaryControl,
) -> None:
    preflight = _preflight(control)
    authorization = _authorization(control, preflight)
    assert authorization.max_primary_calls == 3
    assert authorization.max_provider_requests == 18
    assert authorization.max_harness_turns == 16
    assert authorization.retries == authorization.semantic_retries == 0
    assert authorization.substitutions == 0
    assert authorization.matrix_execution_authorized is False
    raw = authorization.model_dump(mode="json", exclude={"authorization_digest"})
    for required in ("max_primary_calls", "max_provider_requests", "max_harness_turns"):
        missing = {**raw}
        missing.pop(required)
        with pytest.raises(ValidationError):
            V6CanaryAuthorizationRequest.model_validate(missing)
    for field, wrong in (
        ("max_primary_calls", 4),
        ("max_provider_requests", 17),
        ("max_harness_turns", 15),
    ):
        with pytest.raises(ValidationError):
            V6CanaryAuthorizationRequest.model_validate({**raw, field: wrong})
    with pytest.raises(ValidationError):
        V6CanaryAuthorizationRequest.model_validate(
            {
                **raw,
                "scope": "CORE_REAL_MATRIX_V5_CANARY",
            }
        )
    with pytest.raises(ValidationError):
        V6MatrixAuthorizationReceipt.model_validate(authorization.model_dump(mode="json"))


@pytest.mark.asyncio
async def test_failed_preflight_never_invokes_and_fourth_call_is_rejected(
    tmp_path: Path, control: V6CanaryControl
) -> None:
    blocked = _preflight(
        control,
        environment={**_environment(), "HARNESSLAB_ALIBABA_BAILIAN_API_KEY": ""},
    )
    ready = _preflight(control)
    authorization = _authorization(control, ready)
    invoker = _FakeInvoker(tmp_path / "blocked" / "provider-evidence")
    with pytest.raises(V6CanaryControlError, match="failed V6 preflight"):
        await V6CanaryControlPlane(control).execute(
            preflight=blocked,
            authorization=authorization,
            invoker=invoker,
            artifact_root=tmp_path / "blocked",
            allow_real_v6_canary=True,
        )
    assert invoker.calls == []

    four_calls = (*control.calls, control.calls[-1])
    with pytest.raises(V6CanaryControlError, match="exactly three preregistered primary launches"):
        await V6CanaryControlPlane(control).execute(
            preflight=ready,
            authorization=authorization,
            invoker=invoker,
            artifact_root=tmp_path / "fourth",
            allow_real_v6_canary=True,
            calls=four_calls,
        )
    assert invoker.calls == []


@pytest.mark.asyncio
async def test_exact_execution_is_bounded_and_resume_is_idempotent(
    tmp_path: Path, control: V6CanaryControl
) -> None:
    preflight = _preflight(control)
    authorization = _authorization(control, preflight)
    artifact_root = tmp_path / "canary"
    invoker = _FakeInvoker(artifact_root / "provider-evidence")
    plane = V6CanaryControlPlane(control)
    closeout = await plane.execute(
        preflight=preflight,
        authorization=authorization,
        invoker=invoker,
        artifact_root=artifact_root,
        allow_real_v6_canary=True,
    )
    assert tuple(invoker.calls) == EXPECTED_CALL_IDS
    assert closeout.attempted_primary_calls == 3
    assert closeout.max_primary_calls == 3
    assert closeout.max_provider_requests == 18
    assert closeout.max_harness_turns == 16
    assert closeout.retries == closeout.semantic_retries == closeout.substitutions == 0
    assert closeout.matrix_execution_authorized is False
    assert closeout.judge_state == "CANARY_QUALIFIED"

    resumed = _FakeInvoker(artifact_root / "provider-evidence")
    assert (
        await plane.execute(
            preflight=preflight,
            authorization=authorization,
            invoker=resumed,
            artifact_root=artifact_root,
            allow_real_v6_canary=True,
        )
        == closeout
    )
    assert resumed.calls == []

    evidence_file = artifact_root / "provider-evidence" / EXPECTED_CALL_IDS[0] / "evidence.json"
    evidence_file.write_text("tampered\n", encoding="utf-8")
    with pytest.raises(V6CanaryControlError, match="artifact digest mismatch"):
        await plane.execute(
            preflight=preflight,
            authorization=authorization,
            invoker=resumed,
            artifact_root=artifact_root,
            allow_real_v6_canary=True,
        )
    assert resumed.calls == []


@pytest.mark.asyncio
async def test_failure_stops_suffix_and_judge_remains_provisional(
    tmp_path: Path, control: V6CanaryControl
) -> None:
    preflight = _preflight(control)
    authorization = _authorization(control, preflight)
    artifact_root = tmp_path / "failed"
    invoker = _FakeInvoker(artifact_root / "provider-evidence", fail_call=EXPECTED_CALL_IDS[1])
    closeout = await V6CanaryControlPlane(control).execute(
        preflight=preflight,
        authorization=authorization,
        invoker=invoker,
        artifact_root=artifact_root,
        allow_real_v6_canary=True,
    )
    assert tuple(invoker.calls) == EXPECTED_CALL_IDS[:2]
    assert closeout.attempted_primary_calls == 2
    assert closeout.failing_call_id == EXPECTED_CALL_IDS[1]
    assert closeout.judge_state == "PROVISIONAL_PENDING_REAL_CANARY"


@pytest.mark.asyncio
async def test_post_launch_exception_persists_unknown_consumption_and_blocks_suffix(
    tmp_path: Path, control: V6CanaryControl
) -> None:
    preflight = _preflight(control)
    authorization = _authorization(control, preflight)
    artifact_root = tmp_path / "post-launch-exception"
    invoker = _ExplodingInvoker()
    plane = V6CanaryControlPlane(control)

    closeout = await plane.execute(
        preflight=preflight,
        authorization=authorization,
        invoker=invoker,
        artifact_root=artifact_root,
        allow_real_v6_canary=True,
    )
    evidence_path = artifact_root / "per-call-evidence" / f"001-{EXPECTED_CALL_IDS[0]}.json"
    evidence = V6CanaryCallEvidence.model_validate_json(evidence_path.read_text())
    persisted = evidence_path.read_text()

    assert invoker.calls == [EXPECTED_CALL_IDS[0]]
    assert closeout.status.value == "ABORTED"
    assert closeout.attempted_primary_calls == 1
    assert closeout.failing_call_id == EXPECTED_CALL_IDS[0]
    assert closeout.failure_category is V6CanaryFailureCategory.UNKNOWN
    assert closeout.judge_state == "PROVISIONAL_PENDING_REAL_CANARY"
    assert evidence.safe_outcome == "POST_LAUNCH_FAILURE_PROVIDER_REQUESTS_UNKNOWN"
    assert evidence.failure_category is V6CanaryFailureCategory.UNKNOWN
    assert evidence.evidence_references == evidence.evidence_digests == ()
    assert SECRET not in persisted

    resumed = _ExplodingInvoker()
    assert (
        await plane.execute(
            preflight=preflight,
            authorization=authorization,
            invoker=resumed,
            artifact_root=artifact_root,
            allow_real_v6_canary=True,
        )
        == closeout
    )
    assert resumed.calls == []


@pytest.mark.asyncio
async def test_launch_without_terminal_evidence_can_never_retry(
    tmp_path: Path, control: V6CanaryControl
) -> None:
    preflight = _preflight(control)
    authorization = _authorization(control, preflight)
    artifact_root = tmp_path / "crashed"
    marker = V6CanaryControlPlane(control)._launch_marker(
        control.calls[0], preflight, authorization
    )
    marker_path = artifact_root / "launch-journal" / f"001-{control.calls[0].call_id}.json"
    marker_path.parent.mkdir(parents=True)
    marker_path.write_text(
        marker.model_dump_json() + "\n",
        encoding="utf-8",
    )
    invoker = _FakeInvoker(tmp_path / "fake")
    with pytest.raises(V6CanaryControlError, match="retries are zero"):
        await V6CanaryControlPlane(control).execute(
            preflight=preflight,
            authorization=authorization,
            invoker=invoker,
            artifact_root=artifact_root,
            allow_real_v6_canary=True,
        )
    assert invoker.calls == []


def test_call_evidence_schema_cannot_represent_retries_or_substitution(
    control: V6CanaryControl,
) -> None:
    assert V6CanaryCallEvidence.model_fields["retry_count"].default == 0
    assert V6CanaryCallEvidence.model_fields["semantic_retry_count"].default == 0
    assert V6CanaryCallEvidence.model_fields["substitution_count"].default == 0
    with pytest.raises(ValidationError):
        V6CanaryCallEvidence.model_validate(
            {
                "retry_count": 1,
                "semantic_retry_count": 0,
                "substitution_count": 0,
            }
        )
    assert all(item.route_identity.startswith("alibaba-bailian|") for item in control.calls)
