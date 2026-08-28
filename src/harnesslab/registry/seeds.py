from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import TypeAdapter, ValidationError

from harnesslab.contracts.common import Identifier, Protocol
from harnesslab.contracts.provider import validate_provider_base_url
from harnesslab.experiment.methodology import EvaluationMode
from harnesslab.harness_lane.profile import CODEX_CLI_VERSION, CODEX_IMAGE
from harnesslab.multi_harness.profile import (
    CLAUDE_CLI_VERSION,
    CLAUDE_IMAGE,
    CLAUDE_PACKAGE_INTEGRITY,
    DEEPSEEK_CLI_VERSION,
    DEEPSEEK_IMAGE,
    DEEPSEEK_PACKAGE_INTEGRITY,
)
from harnesslab.registry.models import (
    BillingMode,
    EndpointClass,
    HarnessDefinition,
    HarnessProfileDefinition,
    ModelDefinition,
    ObservedModelCapability,
    ProviderDefinition,
    ProviderHealthStatus,
    ProviderModelProfile,
    ReasoningControls,
    RegistryCatalog,
    RegistryDefaults,
    TaskRegistryItem,
    TraceCoverage,
    canonical_digest,
    freeze_provider_model_profile,
)

ALIBABA_BASE_URL_REFERENCE = "HARNESSLAB_ALIBABA_BAILIAN_BASE_URL"
ALIBABA_CREDENTIAL_REFERENCE = "HARNESSLAB_ALIBABA_BAILIAN_API_KEY"
ALIBABA_MODEL_IDS_REFERENCE = "HARNESSLAB_ALIBABA_BAILIAN_MODEL_IDS"
METHODOLOGY_PATH = Path("release/evaluation-methodology-v2.json")

_PROVIDER_STATUS_REFERENCES = {
    "gpt56-relay": "HARNESSLAB_GPT56_RELAY_STATUS",
    "opencode-go": "HARNESSLAB_OPENCODE_GO_STATUS",
    "deepseek-official": "HARNESSLAB_DEEPSEEK_OFFICIAL_STATUS",
    "alibaba-bailian": "HARNESSLAB_ALIBABA_BAILIAN_STATUS",
}
_PROVIDER_ENABLED_REFERENCES = {
    provider_id: reference.removesuffix("_STATUS") + "_ENABLED"
    for provider_id, reference in _PROVIDER_STATUS_REFERENCES.items()
}
_IDENTIFIER_ADAPTER = TypeAdapter(Identifier)


def _status(environment: Mapping[str, str], provider_id: str) -> ProviderHealthStatus:
    value = environment.get(_PROVIDER_STATUS_REFERENCES[provider_id], "UNKNOWN").strip().upper()
    try:
        return ProviderHealthStatus(value)
    except ValueError:
        return ProviderHealthStatus.UNKNOWN


def _enabled(environment: Mapping[str, str], provider_id: str) -> bool:
    value = environment.get(_PROVIDER_ENABLED_REFERENCES[provider_id], "true").strip().casefold()
    return value not in {"0", "false", "no", "disabled"}


def _fingerprint(
    environment: Mapping[str, str], reference: str, *, alibaba: bool = False
) -> tuple[str | None, tuple[str, ...]]:
    raw = environment.get(reference)
    if raw is None or not raw.strip():
        return None, ("RUNTIME_ENDPOINT_REFERENCE_MISSING",)
    try:
        normalized = validate_provider_base_url(raw)
        if alibaba:
            parsed = urlsplit(normalized)
            if not parsed.hostname or not parsed.hostname.endswith(".cn-beijing.maas.aliyuncs.com"):
                raise ValueError("Alibaba endpoint is not in the cn-beijing workspace domain")
            if parsed.path != "/compatible-mode/v1":
                raise ValueError("Alibaba endpoint path is not compatible-mode/v1")
    except ValueError:
        return None, ("RUNTIME_ENDPOINT_INVALID",)
    return canonical_digest({"runtime_endpoint": normalized}), ()


def _alibaba_model_ids(environment: Mapping[str, str]) -> tuple[str, ...]:
    raw = environment.get(ALIBABA_MODEL_IDS_REFERENCE, "")
    if not raw.strip():
        return ()
    values = tuple(item.strip() for item in raw.split(",") if item.strip())
    if len(set(values)) != len(values) or len(values) > 20:
        return ()
    try:
        for value in values:
            _IDENTIFIER_ADAPTER.validate_python(value)
            if len(value) > 60:
                raise ValueError("configured Alibaba model ID is too long")
    except (ValidationError, ValueError):
        return ()
    return values


def _provider_definitions(environment: Mapping[str, str]) -> tuple[ProviderDefinition, ...]:
    relay_fingerprint, relay_reasons = _fingerprint(environment, "HARNESSLAB_GPT56_RELAY_BASE_URL")
    alibaba_fingerprint, alibaba_endpoint_reasons = _fingerprint(
        environment, ALIBABA_BASE_URL_REFERENCE, alibaba=True
    )
    alibaba_models = _alibaba_model_ids(environment)
    alibaba_reasons = list(alibaba_endpoint_reasons)
    if not alibaba_models:
        alibaba_reasons.append("CONFIGURED_MODEL_ID_REQUIRED")
    return (
        ProviderDefinition(
            provider_id="gpt56-relay",
            display_name="GPT-5.6 operator relay",
            provider_family="OpenAI-compatible relay",
            region="operator-managed",
            protocols=(Protocol.RESPONSES,),
            endpoint_class=EndpointClass.PRIVATE_RELAY,
            base_url_reference="HARNESSLAB_GPT56_RELAY_BASE_URL",
            credential_reference="HARNESSLAB_GPT56_RELAY_API_KEY",
            billing_mode=BillingMode.RELAY_ACCOUNT,
            automation_allowed=True,
            enabled=_enabled(environment, "gpt56-relay"),
            health_status=_status(environment, "gpt56-relay"),
            capabilities=("responses", "reasoning-effort"),
            runtime_endpoint_fingerprint=relay_fingerprint,
            configuration_reason_codes=relay_reasons,
        ),
        ProviderDefinition(
            provider_id="opencode-go",
            display_name="OpenCode Go",
            provider_family="Third-party inference platform",
            region="global",
            protocols=(Protocol.MESSAGES, Protocol.CHAT_COMPLETIONS),
            endpoint_class=EndpointClass.PUBLIC_SHARED,
            credential_reference="HARNESSLAB_OPENCODE_GO_API_KEY",
            billing_mode=BillingMode.CONTRACT,
            automation_allowed=True,
            enabled=_enabled(environment, "opencode-go"),
            health_status=_status(environment, "opencode-go"),
            capabilities=("messages", "chat-completions"),
            pricing_snapshot_reference="release/opencode-go-route-snapshot.json",
        ),
        ProviderDefinition(
            provider_id="deepseek-official",
            display_name="DeepSeek official API",
            provider_family="DeepSeek",
            region="global",
            protocols=(Protocol.CHAT_COMPLETIONS,),
            endpoint_class=EndpointClass.PUBLIC_OFFICIAL,
            credential_reference="DEEPSEEK_API_KEY",
            billing_mode=BillingMode.PAY_AS_YOU_GO,
            automation_allowed=True,
            enabled=_enabled(environment, "deepseek-official"),
            health_status=_status(environment, "deepseek-official"),
            capabilities=("chat-completions", "thinking-control"),
        ),
        ProviderDefinition(
            provider_id="alibaba-bailian",
            display_name="Alibaba Bailian",
            provider_family="Alibaba Cloud Model Studio",
            region="cn-beijing",
            protocols=(Protocol.CHAT_COMPLETIONS, Protocol.RESPONSES),
            endpoint_class=EndpointClass.WORKSPACE_DEDICATED,
            base_url_reference=ALIBABA_BASE_URL_REFERENCE,
            credential_reference=ALIBABA_CREDENTIAL_REFERENCE,
            billing_mode=BillingMode.PAY_AS_YOU_GO,
            automation_allowed=True,
            enabled=_enabled(environment, "alibaba-bailian"),
            health_status=_status(environment, "alibaba-bailian"),
            capabilities=("openai-compatible", "chat-completions", "responses"),
            runtime_endpoint_fingerprint=alibaba_fingerprint,
            configuration_reason_codes=tuple(alibaba_reasons),
        ),
    )


def _model_definitions(environment: Mapping[str, str]) -> tuple[ModelDefinition, ...]:
    builtins = (
        ModelDefinition(
            model_id="gpt-5.6-sol",
            display_name="GPT-5.6 Sol",
            model_family="GPT-5.6",
            capabilities=("coding", "reasoning"),
            context_metadata_status="NOT_AVAILABLE",
            reasoning_controls=ReasoningControls(effort=True),
            supported_protocols=(Protocol.RESPONSES,),
        ),
        ModelDefinition(
            model_id="qwen3.8-max",
            display_name="Qwen3.8 Max",
            model_family="Qwen",
            capabilities=("coding",),
            context_metadata_status="NOT_AVAILABLE",
            reasoning_controls=ReasoningControls(),
            supported_protocols=(Protocol.MESSAGES,),
        ),
        ModelDefinition(
            model_id="glm-5.2",
            display_name="GLM-5.2",
            model_family="GLM",
            capabilities=("judge-candidate",),
            context_metadata_status="NOT_AVAILABLE",
            reasoning_controls=ReasoningControls(),
            supported_protocols=(Protocol.CHAT_COMPLETIONS,),
        ),
        ModelDefinition(
            model_id="deepseek-v4-pro",
            display_name="DeepSeek V4 Pro",
            model_family="DeepSeek V4",
            capabilities=("coding", "thinking-control"),
            context_metadata_status="NOT_AVAILABLE",
            reasoning_controls=ReasoningControls(thinking_toggle=True),
            supported_protocols=(Protocol.CHAT_COMPLETIONS,),
        ),
        ModelDefinition(
            model_id="deepseek-v4-flash",
            display_name="DeepSeek V4 Flash",
            model_family="DeepSeek V4",
            capabilities=("coding",),
            context_metadata_status="NOT_AVAILABLE",
            reasoning_controls=ReasoningControls(),
            supported_protocols=(Protocol.CHAT_COMPLETIONS,),
        ),
    )
    configured = tuple(
        ModelDefinition(
            model_id=model_id,
            display_name=model_id,
            model_family="OPERATOR_CONFIGURED_ALIBABA_MODEL",
            capabilities=("operator-configured",),
            context_metadata_status="NOT_AVAILABLE",
            reasoning_controls=ReasoningControls(thinking_toggle=True),
            supported_protocols=(Protocol.CHAT_COMPLETIONS, Protocol.RESPONSES),
        )
        for model_id in _alibaba_model_ids(environment)
        if model_id not in {item.model_id for item in builtins}
    )
    return builtins + configured


def _profiles(environment: Mapping[str, str]) -> tuple[ProviderModelProfile, ...]:
    provider_by_id = {item.provider_id: item for item in _provider_definitions(environment)}
    relay = provider_by_id["gpt56-relay"]
    alibaba = provider_by_id["alibaba-bailian"]
    profiles = [
        freeze_provider_model_profile(
            profile_id="gpt56-relay-gpt56-responses",
            model_id="gpt-5.6-sol",
            provider_id="gpt56-relay",
            requested_model="gpt-5.6-sol",
            protocol=Protocol.RESPONSES,
            route="/responses",
            provider_route_identity=(
                "gpt56-relay|responses|env:HARNESSLAB_GPT56_RELAY_BASE_URL/responses"
            ),
            credential_reference="HARNESSLAB_GPT56_RELAY_API_KEY",
            reasoning_effort="medium",
            max_output_tokens=2000,
            request_timeout_seconds=180,
            observed_model_capability=ObservedModelCapability.RUN_EVIDENCE_ONLY,
            automation_allowed=True,
            enabled=relay.enabled,
            runtime_endpoint_fingerprint=relay.runtime_endpoint_fingerprint,
        ),
        freeze_provider_model_profile(
            profile_id="opencode-go-qwen38-messages",
            model_id="qwen3.8-max",
            provider_id="opencode-go",
            requested_model="qwen3.8-max",
            protocol=Protocol.MESSAGES,
            route="/v1/messages",
            provider_route_identity=("opencode-go|messages|https://opencode.ai/zen/go/v1/messages"),
            credential_reference="HARNESSLAB_OPENCODE_GO_API_KEY",
            max_output_tokens=2000,
            request_timeout_seconds=180,
            observed_model_capability=ObservedModelCapability.RUN_EVIDENCE_ONLY,
            automation_allowed=True,
            enabled=provider_by_id["opencode-go"].enabled,
            pricing_snapshot_reference="release/opencode-go-route-snapshot.json",
        ),
        freeze_provider_model_profile(
            profile_id="opencode-go-glm52-chat",
            model_id="glm-5.2",
            provider_id="opencode-go",
            requested_model="glm-5.2",
            protocol=Protocol.CHAT_COMPLETIONS,
            route="/v1/chat/completions",
            provider_route_identity=(
                "opencode-go|chat_completions|https://opencode.ai/zen/go/v1/chat/completions"
            ),
            credential_reference="HARNESSLAB_OPENCODE_GO_API_KEY",
            max_output_tokens=256,
            request_timeout_seconds=90,
            observed_model_capability=ObservedModelCapability.RUN_EVIDENCE_ONLY,
            automation_allowed=True,
            enabled=provider_by_id["opencode-go"].enabled,
            pricing_snapshot_reference="release/opencode-go-route-snapshot.json",
        ),
        freeze_provider_model_profile(
            profile_id="deepseek-official-v4pro-chat",
            model_id="deepseek-v4-pro",
            provider_id="deepseek-official",
            requested_model="deepseek-v4-pro",
            protocol=Protocol.CHAT_COMPLETIONS,
            route="/chat/completions",
            provider_route_identity=(
                "deepseek-official|chat_completions|https://api.deepseek.com/chat/completions"
            ),
            credential_reference="DEEPSEEK_API_KEY",
            max_output_tokens=2000,
            request_timeout_seconds=180,
            observed_model_capability=ObservedModelCapability.RUN_EVIDENCE_ONLY,
            automation_allowed=True,
            enabled=provider_by_id["deepseek-official"].enabled,
        ),
        freeze_provider_model_profile(
            profile_id="deepseek-official-v4flash-chat",
            model_id="deepseek-v4-flash",
            provider_id="deepseek-official",
            requested_model="deepseek-v4-flash",
            protocol=Protocol.CHAT_COMPLETIONS,
            route="/chat/completions",
            provider_route_identity=(
                "deepseek-official|chat_completions|https://api.deepseek.com/chat/completions"
            ),
            credential_reference="DEEPSEEK_API_KEY",
            max_output_tokens=2000,
            request_timeout_seconds=180,
            observed_model_capability=ObservedModelCapability.RUN_EVIDENCE_ONLY,
            automation_allowed=True,
            enabled=provider_by_id["deepseek-official"].enabled,
        ),
    ]
    for model_id in _alibaba_model_ids(environment):
        for protocol, suffix, route in (
            (Protocol.CHAT_COMPLETIONS, "chat", "/chat/completions"),
            (Protocol.RESPONSES, "responses", "/responses"),
        ):
            profiles.append(
                freeze_provider_model_profile(
                    profile_id=f"alibaba-bailian-{model_id}-{suffix}",
                    model_id=model_id,
                    provider_id="alibaba-bailian",
                    requested_model=model_id,
                    protocol=protocol,
                    route=route,
                    provider_route_identity=(
                        f"alibaba-bailian|{protocol.value}|env:{ALIBABA_BASE_URL_REFERENCE}{route}"
                    ),
                    credential_reference=ALIBABA_CREDENTIAL_REFERENCE,
                    max_output_tokens=2000,
                    request_timeout_seconds=180,
                    observed_model_capability=ObservedModelCapability.RUN_EVIDENCE_ONLY,
                    automation_allowed=True,
                    enabled=alibaba.enabled,
                    runtime_endpoint_fingerprint=alibaba.runtime_endpoint_fingerprint,
                )
            )
    return tuple(profiles)


def _harnesses(environment: Mapping[str, str]) -> tuple[HarnessDefinition, ...]:
    profiles = _profiles(environment)
    direct_profiles = tuple(
        HarnessProfileDefinition(
            profile_id=f"direct-{item.profile_id}",
            profile_reference=f"builtin:registry.direct.{item.profile_id}",
            supported_provider_profile_ids=(item.profile_id,),
            reasoning_effort=item.reasoning_effort,
            harness_config_identity=canonical_digest(
                {
                    "runner": "direct-model-v1",
                    "provider_profile_identity": item.profile_identity,
                }
            ),
        )
        for item in profiles
    )
    return (
        HarnessDefinition(
            harness_id="direct-model",
            display_name="Direct model adapter",
            version="evidence-schema-1",
            image_reference="harnesslab-sandbox:task-runtime",
            cli_runtime_identity="harnesslab.model_lane.runner.DirectModelRunner",
            profiles=direct_profiles,
            supported_protocols=(
                Protocol.RESPONSES,
                Protocol.MESSAGES,
                Protocol.CHAT_COMPLETIONS,
            ),
            tool_surface=(),
            trace_coverage=TraceCoverage.FINAL_OUTPUT_ONLY,
            observed_model_exposure=ObservedModelCapability.RUN_EVIDENCE_ONLY,
            network_capability="PROVIDER_ALLOWLIST",
            mcp_capability=False,
            workspace_mutation=True,
            native_tools=False,
            runtime_health=ProviderHealthStatus.UNKNOWN,
            runner_contract="direct-model-v1",
        ),
        HarnessDefinition(
            harness_id="codex",
            display_name="Codex",
            version=CODEX_CLI_VERSION,
            image_reference=CODEX_IMAGE,
            cli_runtime_identity=f"codex-cli-{CODEX_CLI_VERSION}",
            profiles=(
                HarnessProfileDefinition(
                    profile_id="codex-gpt56-medium",
                    profile_reference="builtin:registry.codex-gpt56",
                    supported_provider_profile_ids=("gpt56-relay-gpt56-responses",),
                    reasoning_effort="medium",
                    harness_config_identity=canonical_digest(
                        {"runtime": f"codex-cli-{CODEX_CLI_VERSION}", "effort": "medium"}
                    ),
                ),
                HarnessProfileDefinition(
                    profile_id="codex-gpt56-high",
                    profile_reference="builtin:registry.codex-gpt56",
                    supported_provider_profile_ids=("gpt56-relay-gpt56-responses",),
                    reasoning_effort="high",
                    harness_config_identity=canonical_digest(
                        {"runtime": f"codex-cli-{CODEX_CLI_VERSION}", "effort": "high"}
                    ),
                ),
            ),
            supported_protocols=(Protocol.RESPONSES,),
            tool_surface=("shell", "workspace"),
            trace_coverage=TraceCoverage.FULL_STREAM,
            observed_model_exposure=ObservedModelCapability.RUN_EVIDENCE_ONLY,
            network_capability="PROVIDER_ALLOWLIST",
            mcp_capability=True,
            workspace_mutation=True,
            native_tools=True,
            runtime_health=ProviderHealthStatus.UNKNOWN,
            runner_contract="codex-harness-v1",
        ),
        HarnessDefinition(
            harness_id="claude-code",
            display_name="Claude Code",
            version=CLAUDE_CLI_VERSION,
            image_reference=CLAUDE_IMAGE,
            cli_runtime_identity=canonical_digest(
                {"version": CLAUDE_CLI_VERSION, "package_integrity": CLAUDE_PACKAGE_INTEGRITY}
            ),
            profiles=(
                HarnessProfileDefinition(
                    profile_id="claude-qwen38-opencode-go",
                    profile_reference="builtin:registry.claude-qwen38-opencode-go",
                    supported_provider_profile_ids=("opencode-go-qwen38-messages",),
                    harness_config_identity=canonical_digest(
                        {
                            "runtime": CLAUDE_CLI_VERSION,
                            "package_integrity": CLAUDE_PACKAGE_INTEGRITY,
                            "provider_profile": "opencode-go-qwen38-messages",
                        }
                    ),
                ),
            ),
            supported_protocols=(Protocol.MESSAGES,),
            tool_surface=("Read", "Edit", "Write", "Bash"),
            trace_coverage=TraceCoverage.FULL_STREAM,
            observed_model_exposure=ObservedModelCapability.RUN_EVIDENCE_ONLY,
            network_capability="PROVIDER_ALLOWLIST",
            mcp_capability=False,
            workspace_mutation=True,
            native_tools=True,
            runtime_health=ProviderHealthStatus.UNKNOWN,
            runner_contract="claude-code-harness-v1",
        ),
        HarnessDefinition(
            harness_id="deepseek-harness",
            display_name="DeepSeek Harness",
            version=DEEPSEEK_CLI_VERSION,
            image_reference=DEEPSEEK_IMAGE,
            cli_runtime_identity=canonical_digest(
                {
                    "version": DEEPSEEK_CLI_VERSION,
                    "package_integrity": DEEPSEEK_PACKAGE_INTEGRITY,
                }
            ),
            profiles=(
                HarnessProfileDefinition(
                    profile_id="deepseek-harness-v4flash",
                    profile_reference="builtin:registry.deepseek-v4flash",
                    supported_provider_profile_ids=("deepseek-official-v4flash-chat",),
                    harness_config_identity=canonical_digest(
                        {
                            "runtime": DEEPSEEK_CLI_VERSION,
                            "package_integrity": DEEPSEEK_PACKAGE_INTEGRITY,
                            "provider_profile": "deepseek-official-v4flash-chat",
                        }
                    ),
                ),
            ),
            supported_protocols=(Protocol.CHAT_COMPLETIONS,),
            tool_surface=("headless-profile-public-contract",),
            trace_coverage=TraceCoverage.FINAL_OUTPUT_ONLY,
            observed_model_exposure=ObservedModelCapability.NOT_AVAILABLE,
            network_capability="PROVIDER_ALLOWLIST",
            mcp_capability=False,
            workspace_mutation=True,
            native_tools=True,
            runtime_health=ProviderHealthStatus.UNKNOWN,
            runner_contract="deepseek-harness-v1",
        ),
    )


def _tasks(repository_root: Path) -> tuple[TaskRegistryItem, ...]:
    path = repository_root / "release/core-corpus.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    tasks = raw.get("tasks") if isinstance(raw, dict) else None
    if not isinstance(tasks, list) or len(tasks) != 18:
        raise ValueError("core corpus must contain exactly 18 registered tasks")
    return tuple(
        TaskRegistryItem(
            task_id=item["task_id"],
            task_version=item["version"],
            task_digest=item["task_digest"],
            package_path=item["package_path"],
        )
        for item in tasks
    )


def _defaults(environment: Mapping[str, str], profile_ids: set[str]) -> RegistryDefaults:
    profile = environment.get(
        "HARNESSLAB_REGISTRY_DEFAULT_PROVIDER_PROFILE", "gpt56-relay-gpt56-responses"
    )
    if profile not in profile_ids:
        profile = "gpt56-relay-gpt56-responses"
    try:
        mode = EvaluationMode(
            environment.get("HARNESSLAB_REGISTRY_DEFAULT_EVALUATION_MODE", "QUICK")
        )
    except ValueError:
        mode = EvaluationMode.QUICK
    try:
        seed = int(environment.get("HARNESSLAB_REGISTRY_DEFAULT_SCHEDULE_SEED", "20260828"))
        concurrency = int(environment.get("HARNESSLAB_REGISTRY_DEFAULT_CONCURRENCY", "1"))
    except ValueError:
        seed, concurrency = 20260828, 1
    concurrency = min(64, max(1, concurrency))
    return RegistryDefaults(
        default_provider_profile_id=profile,
        default_evaluation_mode=mode,
        default_schedule_seed=seed,
        default_concurrency=concurrency,
    )


def build_registry_catalog(
    repository_root: Path, environment: Mapping[str, str]
) -> RegistryCatalog:
    providers = _provider_definitions(environment)
    profiles = _profiles(environment)
    return RegistryCatalog(
        providers=providers,
        models=_model_definitions(environment),
        provider_model_profiles=profiles,
        harnesses=_harnesses(environment),
        tasks=_tasks(repository_root),
        defaults=_defaults(environment, {item.profile_id for item in profiles}),
    )


def provider_status_reference(provider_id: str) -> str:
    return _PROVIDER_STATUS_REFERENCES[provider_id]


def provider_enabled_reference(provider_id: str) -> str:
    return _PROVIDER_ENABLED_REFERENCES[provider_id]
