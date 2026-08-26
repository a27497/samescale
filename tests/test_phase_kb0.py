from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from harnesslab.comparability.engine import ComparabilityEngine
from harnesslab.comparability.models import (
    ComparabilityIntent,
    ComparabilityStatus,
    ComparisonFacts,
    canonical_digest,
)
from harnesslab.contracts.common import NetworkPolicy, Protocol
from harnesslab.contracts.model import ModelProfile, ReasoningProfile
from harnesslab.contracts.provider import (
    ProviderProvenance,
    ThinkingMode,
    ThinkingTransport,
    validate_provider_base_url,
)
from harnesslab.egress import (
    EGRESS_PROXY_IMAGE,
    EgressDenied,
    EgressPolicy,
    ProviderScopedDockerBoundary,
)
from harnesslab.harness_lane.adapter import CodexHarnessAdapter
from harnesslab.harness_lane.docker_backend import DockerCodexBackend
from harnesslab.harness_lane.profile import (
    canonical_codex_profile,
    configured_gpt56_relay_codex_profile,
)
from harnesslab.harness_lane.prompt import render_codex_harness_prompt
from harnesslab.model_lane.models import ProviderRequest
from harnesslab.model_lane.providers import AnthropicMessagesAdapter, OpenAICompatibleChatAdapter
from harnesslab.multi_harness.adapter import ClaudeCodeAdapter
from harnesslab.multi_harness.docker_backend import DockerMultiHarnessBackend
from harnesslab.multi_harness.models import HarnessKind
from harnesslab.multi_harness.profile import (
    configured_deepseek_v4flash_profile,
    configured_qwen_opencode_go_claude_profile,
)
from harnesslab.multi_harness.prompt import render_harness_prompt
from harnesslab.release.contracts import (
    load_real_evidence_plan,
    load_real_smoke_plan,
    load_release_evidence,
)
from harnesslab.release.models import EvidenceState, PairedClaimPolicy
from harnesslab.release.provider_config import configured_model_profile
from harnesslab.sandbox.models import ImageIdentity

ROOT = Path(__file__).resolve().parents[1]
RELEASE = ROOT / "release"
SENTINEL = "kb0-secret-sentinel-never-persist"
OPENCODE_GO_BASE_URL = "https://opencode.ai/zen/go"


def image(reference: str) -> ImageIdentity:
    return ImageIdentity(reference=reference, image_id="sha256:" + "7" * 64)


def test_kb0_provider_contracts_freeze_truthful_selected_profiles() -> None:
    plan = load_real_evidence_plan(RELEASE / "core-real-evidence-plan.json")
    profiles = {item.profile_id: item for item in plan.selected_profiles}

    assert len(profiles) == 8
    assert "OPENAI_FIRST_PARTY" not in ProviderProvenance.__members__
    relay = profiles["model-gpt56-relay-responses"]
    assert relay.provider_provenance is ProviderProvenance.TRUSTED_THIRD_PARTY_RELAY
    assert relay.upstream_model_claim == "gpt-5.6-sol"
    assert relay.operator_trust_assertion == "VERIFIED_BY_OPERATOR"
    assert relay.upstream_first_party_provenance == "NOT_INDEPENDENTLY_VERIFIED"
    qwen = profiles["model-qwen38-opencode-go-messages"]
    assert (qwen.requested_model, qwen.protocol, qwen.reasoning_effort) == (
        "qwen3.8-max",
        Protocol.MESSAGES,
        None,
    )
    deepseek = profiles["model-deepseek-v4pro-chat"]
    assert deepseek.fixed_base_url == "https://api.deepseek.com"
    assert deepseek.thinking_mode is ThinkingMode.DISABLED
    judge = profiles["judge-glm52-opencode-go-chat"]
    assert judge.requested_model == "glm-5.2"
    assert judge.provider_provenance is ProviderProvenance.THIRD_PARTY_INFERENCE_PLATFORM
    assert judge.max_output_tokens == 256
    assert all(item.profile_digest == item.expected_profile_digest for item in profiles.values())
    qwen_runtime = configured_model_profile(qwen, {})
    assert qwen_runtime.requested_model == "qwen3.8-max"
    assert qwen_runtime.route == "/v1/messages"
    assert (
        qwen.resolved_route_identity({})
        == "opencode-go|messages|https://opencode.ai/zen/go/v1/messages"
    )
    assert qwen.provider_provenance is ProviderProvenance.THIRD_PARTY_INFERENCE_PLATFORM
    assert qwen.inference_provider == "OpenCode Go"
    serialized = json.dumps(plan.model_dump(mode="json"))
    assert SENTINEL not in serialized
    assert all(item.credential_reference.isupper() for item in profiles.values())


def test_kb0_provider_url_validation_is_offline_and_fail_closed() -> None:
    assert validate_provider_base_url("https://relay.example.test/v1") == (
        "https://relay.example.test/v1"
    )
    for unsafe in (
        "http://relay.example.test/v1",
        "https://user:secret@relay.example.test/v1",
        "https://relay.example.test:8443/v1",
        "https://relay.example.test/v1?token=secret",
        "https://localhost/v1",
        "https://127.0.0.1/v1",
        "https://10.0.0.1/v1",
        "https://169.254.169.254/latest",
        "https://[::1]/v1",
        "https://metadata.google.internal/v1",
    ):
        with pytest.raises(ValueError):
            validate_provider_base_url(unsafe)


def test_kb0_typed_chat_thinking_options_emit_only_approved_shapes() -> None:
    def payload(transport: ThinkingTransport) -> dict[str, object]:
        profile = ModelProfile(
            requested_model="approved-model",
            provider="approved-provider",
            base_url="https://provider.example.test/v1",
            route="/chat/completions",
            protocol=Protocol.CHAT_COMPLETIONS,
            reasoning=ReasoningProfile(max_output_tokens=256),
            thinking_mode=ThinkingMode.DISABLED,
            thinking_transport=transport,
            credential_reference="APPROVED_API_KEY",
        )
        return OpenAICompatibleChatAdapter()._payload(
            ProviderRequest(profile=profile, instructions="system", input="input")
        )

    assert payload(ThinkingTransport.DEEPSEEK_THINKING_OBJECT)["thinking"] == {"type": "disabled"}
    bailian = payload(ThinkingTransport.BAILIAN_ENABLE_THINKING)
    assert bailian["enable_thinking"] is False
    assert "extra_body" not in bailian


def test_kb0_codex_custom_provider_is_explicit_secret_free_and_single_treatment(
    tmp_path: Path,
) -> None:
    medium = configured_gpt56_relay_codex_profile(
        image("harnesslab-phase-e-codex:0.149.0"),
        provider_base_url_reference="HARNESSLAB_GPT56_RELAY_BASE_URL",
        reasoning_effort="medium",
    )
    high = configured_gpt56_relay_codex_profile(
        medium.codex_image,
        provider_base_url_reference="HARNESSLAB_GPT56_RELAY_BASE_URL",
        reasoning_effort="high",
    )
    left = medium.model_dump(exclude={"reasoning_effort"})
    right = high.model_dump(exclude={"reasoning_effort"})
    assert left == right
    assert medium.provider_config_digest == high.provider_config_digest
    prompt = render_codex_harness_prompt(
        task_instruction="Fix task.",
        task_digest="sha256:" + "1" * 64,
        workspace_input_digest="sha256:" + "2" * 64,
        context_digest=None,
        network_policy=NetworkPolicy.DENY,
    )
    argv = (
        CodexHarnessAdapter()
        .prepare(medium, prompt, workspace=tmp_path, context=None, task_id="task")
        .argv
    )
    joined = " ".join(argv)
    assert "--ignore-user-config" in argv
    assert argv[argv.index("--profile") + 1] == "harnesslab-runtime"
    assert medium.provider_base_url_reference == "HARNESSLAB_GPT56_RELAY_BASE_URL"
    assert "https://relay.example.test/v1" not in joined
    assert medium.provider_credential_reference == "HARNESSLAB_GPT56_RELAY_API_KEY"
    assert SENTINEL not in joined
    assert canonical_codex_profile(medium.codex_image).provider_route != medium.provider_route


def test_opencode_go_claude_qwen_uses_typed_api_key_transport(tmp_path: Path) -> None:
    profile = configured_qwen_opencode_go_claude_profile(image("harnesslab-phase-f-claude:2.1.241"))
    prompt = render_harness_prompt(
        HarnessKind.CLAUDE_CODE,
        task_instruction="Fix task.",
        task_digest="sha256:" + "1" * 64,
        workspace_input_digest="sha256:" + "2" * 64,
        context_digest=None,
        network_policy=NetworkPolicy.DENY,
    )
    execution = ClaudeCodeAdapter().prepare(
        profile, prompt, workspace=tmp_path, context=None, task_id="task"
    )
    assert profile.requested_model == "qwen3.8-max"
    assert execution.environment_references == (
        ("ANTHROPIC_API_KEY", "HARNESSLAB_OPENCODE_GO_API_KEY"),
    )
    assert execution.environment_literals == (
        ("ANTHROPIC_BASE_URL", OPENCODE_GO_BASE_URL),
        ("ANTHROPIC_MODEL", "qwen3.8-max"),
    )
    assert "api.anthropic.com" not in json.dumps(profile.model_dump(mode="json"))
    assert SENTINEL not in execution.argv
    docker_argv = DockerMultiHarnessBackend(
        credentials={
            "HARNESSLAB_OPENCODE_GO_API_KEY": SENTINEL,
        }
    ).create_argv(execution, "claude-subject")
    assert "ANTHROPIC_BASE_URL" in docker_argv
    assert "ANTHROPIC_API_KEY" in docker_argv
    assert "ANTHROPIC_AUTH_TOKEN" not in docker_argv
    assert "HARNESSLAB_OPENCODE_GO_API_KEY" not in docker_argv
    assert SENTINEL not in docker_argv


@pytest.mark.asyncio
async def test_opencode_go_messages_exact_url_headers_and_shared_claude_route(
    tmp_path: Path,
) -> None:
    plan = load_real_evidence_plan(RELEASE / "core-real-evidence-plan.json")
    profiles = {item.profile_id: item for item in plan.selected_profiles}
    direct_provider = profiles["model-qwen38-opencode-go-messages"]
    direct_profile = configured_model_profile(direct_provider, {})
    requested_urls: list[str] = []
    requested_headers: list[httpx.Headers] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        requested_headers.append(request.headers)
        return httpx.Response(
            200,
            json={
                "id": "keyless-opencode-go-contract",
                "model": "qwen3.8-max",
                "content": [{"type": "text", "text": "{}"}],
                "stop_reason": "end_turn",
                "usage": {"input_tokens": 1, "output_tokens": 1},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await AnthropicMessagesAdapter(
            client=client,
            environment={"HARNESSLAB_OPENCODE_GO_API_KEY": "fake-key"},
        ).invoke(ProviderRequest(profile=direct_profile, instructions="system", input="input"))

    expected_endpoint = f"{OPENCODE_GO_BASE_URL}/v1/messages"
    assert requested_urls == [expected_endpoint]
    assert result.endpoint_identity == direct_profile.provider_route_identity
    assert direct_profile.requested_model == "qwen3.8-max"
    assert direct_profile.credential_reference == "HARNESSLAB_OPENCODE_GO_API_KEY"
    assert requested_headers[0]["x-api-key"] == "fake-key"
    assert "authorization" not in requested_headers[0]
    assert direct_provider.provider_provenance is ProviderProvenance.THIRD_PARTY_INFERENCE_PLATFORM

    claude_profile = configured_qwen_opencode_go_claude_profile(
        image("harnesslab-phase-f-claude:2.1.241")
    )
    prompt = render_harness_prompt(
        HarnessKind.CLAUDE_CODE,
        task_instruction="Fix task.",
        task_digest="sha256:" + "1" * 64,
        workspace_input_digest="sha256:" + "2" * 64,
        context_digest=None,
        network_policy=NetworkPolicy.DENY,
    )
    execution = ClaudeCodeAdapter().prepare(
        claude_profile, prompt, workspace=tmp_path, context=None, task_id="task"
    )
    operator_environment = {
        "HARNESSLAB_OPENCODE_GO_API_KEY": "fake-key",
        "ANTHROPIC_AUTH_TOKEN": "ambient-host-token-must-not-be-used",
    }
    container_environment = {
        target: operator_environment[source] for target, source in execution.environment_references
    }
    container_environment.update(execution.environment_literals)
    assert container_environment["ANTHROPIC_BASE_URL"] == OPENCODE_GO_BASE_URL
    assert not container_environment["ANTHROPIC_BASE_URL"].endswith("/v1")
    assert execution.environment_references[0] == (
        "ANTHROPIC_API_KEY",
        "HARNESSLAB_OPENCODE_GO_API_KEY",
    )
    assert "ANTHROPIC_AUTH_TOKEN" not in container_environment
    assert claude_profile.requested_model == "qwen3.8-max"
    assert claude_profile.provider_provenance is ProviderProvenance.THIRD_PARTY_INFERENCE_PLATFORM
    assert f"{container_environment['ANTHROPIC_BASE_URL']}/v1/messages" == expected_endpoint


@pytest.mark.asyncio
async def test_opencode_go_judge_exact_route_bearer_and_public_content_only() -> None:
    plan = load_real_evidence_plan(RELEASE / "core-real-evidence-plan.json")
    provider = next(
        item for item in plan.selected_profiles if item.profile_id == "judge-glm52-opencode-go-chat"
    )
    profile = configured_model_profile(provider, {})
    requests: list[httpx.Request] = []
    private_reasoning = "PRIVATE_GLM_REASONING_MUST_NOT_PERSIST"

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "id": "judge-keyless-contract",
                "model": "glm-5.2",
                "choices": [
                    {
                        "message": {
                            "content": '{"label":"PASS","score":1.0}',
                            "reasoning_content": private_reasoning,
                        },
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = OpenAICompatibleChatAdapter(
            client=client,
            environment={"HARNESSLAB_OPENCODE_GO_API_KEY": "fake-key"},
        )
        payload = adapter._payload(
            ProviderRequest(profile=profile, instructions="judge", input="case")
        )
        result = await adapter.invoke(
            ProviderRequest(profile=profile, instructions="judge", input="case")
        )

    assert str(requests[0].url) == "https://opencode.ai/zen/go/v1/chat/completions"
    assert requests[0].headers["authorization"] == "Bearer fake-key"
    assert "x-api-key" not in requests[0].headers
    assert "enable_thinking" not in payload and "thinking" not in payload
    assert provider.thinking_mode is None
    assert provider.thinking_transport is None
    assert result.public_output_text == '{"label":"PASS","score":1.0}'
    assert private_reasoning not in result.model_dump_json()


def test_kb0_deepseek_harness_e1_is_official_and_e2_deferred() -> None:
    profile = configured_deepseek_v4flash_profile(
        image("harnesslab-phase-f-deepseek:0.1.1-rc.2"), "sha256:" + "8" * 64
    )
    plan = load_real_evidence_plan(RELEASE / "core-real-evidence-plan.json")
    assert profile.requested_model == "deepseek-v4-flash"
    assert profile.provider_route.startswith("deepseek-official|chat_completions|")
    assert plan.deepseek_e2 is EvidenceState.DEFERRED_NOT_VERIFIED


def test_kb0_provider_scoped_egress_allows_fake_and_denies_bypass_and_targets() -> None:
    policy = EgressPolicy(allowed_hostname="provider.example.test")
    boundary = ProviderScopedDockerBoundary(
        policy, "kb0-internal", "kb0-proxy", image(EGRESS_PROXY_IMAGE)
    )
    response, event = boundary.deterministic_fake_forward(
        "provider.example.test", 443, b"opaque-tls", lambda value: value[::-1]
    )
    assert response == b"slt-euqapo"
    assert event.hostname == "provider.example.test"
    assert SENTINEL not in event.json_line()
    assert boundary.subject_network_mode == "kb0-internal"
    assert not boundary.subject_can_bypass_proxy
    assert boundary.verifier_network_mode == "none"
    assert "--internal" in boundary.create_internal_network_argv()
    assert "docker.sock" not in " ".join(boundary.create_proxy_argv())
    for host, port, addresses in (
        ("other.example.test", 443, ()),
        ("provider.example.test", 80, ()),
        ("127.0.0.1", 443, ()),
        ("169.254.169.254", 443, ()),
        ("provider.example.test", 443, ("10.0.0.2",)),
        ("provider.example.test", 443, ("169.254.169.254",)),
        ("provider.example.test", 443, ("::1",)),
    ):
        with pytest.raises(EgressDenied):
            policy.authorize_connect(host, port, resolved_addresses=addresses)


def test_kb0_subject_docker_uses_only_internal_proxy_network(tmp_path: Path) -> None:
    boundary = ProviderScopedDockerBoundary(
        EgressPolicy(allowed_hostname="relay.example.test"),
        "kb0-internal",
        "kb0-proxy",
        image(EGRESS_PROXY_IMAGE),
    )
    profile = configured_gpt56_relay_codex_profile(
        image("harnesslab-phase-e-codex:0.149.0"),
        provider_base_url_reference="HARNESSLAB_GPT56_RELAY_BASE_URL",
        reasoning_effort="medium",
    )
    prompt = render_codex_harness_prompt(
        task_instruction="Fix task.",
        task_digest="sha256:" + "1" * 64,
        workspace_input_digest="sha256:" + "2" * 64,
        context_digest=None,
        network_policy=NetworkPolicy.DENY,
    )
    plan = CodexHarnessAdapter().prepare(
        profile, prompt, workspace=tmp_path, context=None, task_id="task"
    )
    argv = DockerCodexBackend(
        credentials={"HARNESSLAB_GPT56_RELAY_API_KEY": SENTINEL},
        egress_boundary=boundary,
    ).create_argv(plan, "subject")
    assert argv[argv.index("--network") + 1] == "kb0-internal"
    assert any(value.startswith("HTTPS_PROXY=http://kb0-proxy:8080") for value in argv)
    assert SENTINEL not in argv
    assert "--privileged" not in argv and "docker.sock" not in " ".join(argv)


def comparison(route: str, model: str, harness: str) -> ComparisonFacts:
    return ComparisonFacts(
        evidence_identity=canonical_digest({"harness": harness}),
        task_id="task",
        task_version="1.0.0",
        task_digest=canonical_digest({"task": 1}),
        workspace_input_digest=canonical_digest({"workspace": 1}),
        context_identity="NONE",
        verifier_identity=canonical_digest({"verifier": 1}),
        requested_model=model,
        observed_model=None,
        provider_route=route,
        harness=harness,
        harness_version="1",
        harness_profile_identity=canonical_digest({"profile": harness}),
        prompt_identity=canonical_digest({"prompt": harness}),
        budget_identity=canonical_digest({"budget": 1}),
        network_policy="allowlist",
        trace_coverage="FULL",
    )


def test_kb0_pair_is_configured_but_never_claims_comparable_or_uplift() -> None:
    plan = load_real_evidence_plan(RELEASE / "core-real-evidence-plan.json")
    cells = {item.cell_id: item for item in plan.cells}
    left = cells[plan.paired_lane.left_cell_id]
    right = cells[plan.paired_lane.right_cell_id]
    assert left.provider_route == right.provider_route
    assert left.requested_model == right.requested_model == "gpt-5.6-sol"
    assert plan.paired_lane.configuration_state == "CONFIGURED_NOT_VERIFIED"
    assert plan.paired_lane.comparability_state is EvidenceState.NOT_VERIFIED
    observed_states = {item.observed_model_state for item in plan.selected_profiles}
    assert observed_states == {"NOT_VERIFIED_UNTIL_SMOKE"}
    evidence = load_release_evidence(RELEASE / "release-evidence.json")
    assert evidence.paired_claim_policy is PairedClaimPolicy.NOT_SELECTED
    direct = comparison(left.provider_route or "", "gpt-5.6-sol", "direct-model")
    assert (
        ComparabilityEngine()
        .assess(
            direct,
            comparison("different-route", "gpt-5.6-sol", "codex"),
            intent=ComparabilityIntent.HARNESS_UPLIFT,
        )
        .status
        is ComparabilityStatus.NOT_COMPARABLE
    )
    assert (
        ComparabilityEngine()
        .assess(
            direct,
            comparison(left.provider_route or "", "other-model", "codex"),
            intent=ComparabilityIntent.HARNESS_UPLIFT,
        )
        .status
        is ComparabilityStatus.NOT_COMPARABLE
    )


def test_kb0_smoke_plan_is_exact_bounded_and_unexecuted() -> None:
    release = load_real_evidence_plan(RELEASE / "core-real-evidence-plan.json")
    smoke = load_real_smoke_plan(RELEASE / "core-real-smoke-plan.json")
    evidence = load_release_evidence(RELEASE / "release-evidence.json")
    assert smoke.release_plan_digest == release.digest
    assert len(smoke.calls) == smoke.max_top_level_launch_count == 8
    assert smoke.max_output_token_ceiling == 14_256
    assert {item.profile_id for item in smoke.calls} == {
        item.profile_id for item in release.selected_profiles
    }
    assert smoke.execution_state is EvidenceState.NOT_RUN
    assert smoke.real_evaluation_call_count == 0
    assert smoke.authorization_required
    assert evidence.real_statuses["REAL_PROVIDER_SMOKE"] is EvidenceState.NOT_VERIFIED
    assert evidence.real_statuses["REAL_CODEX_SMOKE"] is EvidenceState.NOT_VERIFIED
    assert all(
        state is EvidenceState.NOT_RUN
        for key, state in evidence.real_statuses.items()
        if key not in {"REAL_PROVIDER_SMOKE", "REAL_CODEX_SMOKE"}
    )
    assert evidence.real_matrix.state is EvidenceState.NOT_RUN
    assert evidence.judge_report.state is EvidenceState.NOT_RUN
    assert not evidence.core_release_ready
    assert evidence.real_evidence_authorization_required


def test_v1_history_and_opencode_go_route_snapshot_are_frozen() -> None:
    plan = load_real_evidence_plan(RELEASE / "core-real-evidence-plan.json")
    history = json.loads((ROOT / plan.history_reference).read_text(encoding="utf-8"))
    snapshot = json.loads(
        (ROOT / plan.official_route_snapshot_reference).read_text(encoding="utf-8")
    )
    assert history["authoritative_commit"] == "45e83d735cee48d9a29361da5964cee83d048a42"
    assert history["evidence_plan"]["canonical_digest"] == (
        "sha256:b97a0798b7855b0544c8acdb861551bc918d57fc6fbda834cc13c992955ad098"
    )
    assert history["smoke_plan"]["canonical_digest"] == (
        "sha256:a9a21424199fc30437589e4526a4bf91dbe2dce65520a69077924098d7dc528f"
    )
    assert len(history["attempts"]) == 3
    assert "verifier_score=0.8" in history["attempts"][2]["facts"]
    assert "HTTP 403 AUTHENTICATION" in history["attempts"][2]["facts"]
    assert snapshot["provider_provenance"] == "THIRD_PARTY_INFERENCE_PLATFORM"
    assert {(item["requested_model"], item["endpoint"]) for item in snapshot["models"]} == {
        ("qwen3.8-max", "https://opencode.ai/zen/go/v1/messages"),
        ("glm-5.2", "https://opencode.ai/zen/go/v1/chat/completions"),
    }
    assert snapshot["judge_thinking_control"] == ("PROVIDER_DEFAULT_NOT_EXPLICITLY_CONFIGURED")
    assert snapshot["live_model_probe_performed"] is False


def test_kb0_matrix_preflight_and_release_hard_stop_are_unchanged() -> None:
    plan = load_real_evidence_plan(RELEASE / "core-real-evidence-plan.json")
    assert (len(plan.cells), plan.preflight.total_subject_runs) == (7, 630)
    assert plan.preflight.judge_calls == 63
    assert plan.preflight.total_top_level_external_calls == 693
    assert plan.preflight.total_output_token_ceiling == 1_276_128
    assert len(json.loads((RELEASE / "core-corpus.json").read_text())["tasks"]) == 18
    assert plan.real_evidence_authorization_required
