# K-B2R Matrix redesign and authorization dossier

Date: 2026-08-30

Phase: `K-B2R_REAL_MATRIX_REDESIGN`

Selection rule: scientific coverage, comparability, operational viability, non-speculative capability, and implementation complexity only. Historical scores were not consulted.

## Candidate A — controlled reference topology (selected)

All listed configuration references are present in private mode-0600 operator sources. Pricing is unavailable for every active route and is therefore `UNKNOWN`, never zero.

| Cell | Role | Provider / protocol / requested model | Harness and runtime profile | Exact route / credential reference | Trace / observed model | New code, configuration, and risk |
|---|---|---|---|---|---|---|
| `model-gpt56-relay-responses` | M + P | GPT relay / Responses / `gpt-5.6-sol` medium | Direct / `direct-gpt56-relay-gpt56-responses` | `gpt56-relay\|responses\|env:HARNESSLAB_GPT56_RELAY_BASE_URL/responses`; `HARNESSLAB_GPT56_RELAY_BASE_URL`, `HARNESSLAB_GPT56_RELAY_API_KEY` | Final output; run-evidence exposure | No binding code; configured. Relay provenance and observed identity require real evidence. |
| `model-qwen38-opencode-go-messages` | M | OpenCode Go / Messages / `qwen3.8-max` | Direct / `direct-opencode-go-qwen38-messages` | `opencode-go\|messages\|https://opencode.ai/zen/go/v1/messages`; `HARNESSLAB_OPENCODE_GO_API_KEY` | Final output; run-evidence exposure | No binding code; configured. Third-party inference provenance remains explicit. |
| `model-deepseek-v4pro-chat` | M | DeepSeek official / Chat Completions / `deepseek-v4-pro` | Direct / `direct-deepseek-official-v4pro-chat` | `deepseek-official\|chat_completions\|https://api.deepseek.com/chat/completions`; `DEEPSEEK_API_KEY` | Final output; run-evidence exposure | No binding code; configured. Direct and harness cells use different DeepSeek variants. |
| `harness-codex-gpt56-medium` | H + P | GPT relay / Responses / `gpt-5.6-sol` medium | Codex 0.149.0 / `codex-gpt56-medium` | Same relay route and references as the paired Direct cell | Full stream; run-evidence exposure required | No binding code; configured. Operator-trusted relay identity is the principal comparability risk. |
| `harness-codex-gpt56-high` | H | GPT relay / Responses / `gpt-5.6-sol` high | Codex 0.149.0 / `codex-gpt56-high` | Same relay route and references as medium | Full stream; run-evidence exposure required | No binding code; configured. Only reasoning effort may differ from medium. |
| `harness-claude-qwen38-opencode-go` | H | OpenCode Go / Messages / `qwen3.8-max` | Claude Code 2.1.241 / `claude-qwen38-opencode-go` | Same OpenCode Messages route; `HARNESSLAB_OPENCODE_GO_API_KEY` | Full stream; run-evidence exposure | No binding code; configured. No formal P claim is preregistered for this cell. |
| `harness-deepseek-v4flash` | H | DeepSeek official / Chat Completions / `deepseek-v4-flash` | DeepSeek Harness 0.1.1-rc.2 / `deepseek-harness-v4flash` | Same official endpoint class; `DEEPSEEK_API_KEY` | Final output; observed model not exposed by contract | No binding code; configured. Developer-preview runtime and model-variant difference restrict comparability. |

Matched pair: `model-gpt56-relay-responses` ↔ `harness-codex-gpt56-medium`, with model, route, protocol, task/workspace/verifier identities, credential references, resource budget, and network policy frozen.

Controlled ablation: `harness-codex-gpt56-medium` ↔ `harness-codex-gpt56-high`; the sole changed dimension is `reasoning_effort=medium|high`.

Judge: `judge-glm52-opencode-go-chat`, OpenCode Go Chat Completions, `glm-5.2`, `HARNESSLAB_OPENCODE_GO_API_KEY`, 63 fixed full-campaign calls. L0 deterministic > L1 Human Gold > L2 LLM Judge; the Judge never overturns deterministic verifier failure.

## Candidate B — Alibaba-centered P lane (qualified alternative)

Alibaba Registry profiles for Qwen Messages/Responses, DeepSeek Chat, and Claude Code Qwen Messages are explicit. The candidate does not infer Codex-on-Alibaba or DeepSeek-Harness-on-Alibaba support.

| Cell | Role | Provider / protocol / requested model | Harness and runtime profile | Exact route / credential reference | Trace / observed model | New code, configuration, and risk |
|---|---|---|---|---|---|---|
| `model-qwen38-alibaba-messages` | M + P | Alibaba Bailian / Messages / `qwen3.8-max` | Direct / `direct-alibaba-bailian-qwen3.8-max-messages` | `alibaba-bailian\|messages\|env:HARNESSLAB_ALIBABA_BAILIAN_ANTHROPIC_BASE_URL/v1/messages`; Alibaba Anthropic base URL + API key refs | Final output; run-evidence exposure | Binding exists; configured. Requires v4 smoke orchestration wiring. |
| `model-qwen38-alibaba-responses` | M | Alibaba Bailian / Responses / `qwen3.8-max` | Direct / `direct-alibaba-bailian-qwen3.8-max-responses` | `alibaba-bailian\|responses\|env:HARNESSLAB_ALIBABA_BAILIAN_OPENAI_BASE_URL/responses`; Alibaba OpenAI base URL + API key refs | Final output; run-evidence exposure | Binding exists; configured. Protocol change is not treated as a score comparison. |
| `model-deepseek-v4pro-alibaba-chat` | M | Alibaba Bailian / Chat Completions / `deepseek-v4-pro` | Direct / `direct-alibaba-bailian-deepseek-v4-pro-chat` | `alibaba-bailian\|chat_completions\|env:HARNESSLAB_ALIBABA_BAILIAN_OPENAI_BASE_URL/chat/completions`; Alibaba OpenAI base URL + API key refs | Final output; run-evidence exposure | Binding exists; configured. Hosted-provider provenance differs from official DeepSeek. |
| `harness-claude-qwen38-alibaba` | H + P | Alibaba Bailian / Messages / `qwen3.8-max` | Claude Code 2.1.241 / `claude-qwen38-alibaba-bailian` | Same Alibaba Messages route and refs as paired Direct cell | Full stream; run-evidence exposure | Binding exists; configured. Requires v4 smoke orchestration wiring. |
| `harness-codex-gpt56-medium` | H | GPT relay / Responses / `gpt-5.6-sol` medium | Codex 0.149.0 / `codex-gpt56-medium` | Candidate-A relay route and refs | Full stream; run-evidence exposure required | Existing binding/config. Separate provider from the P pair. |
| `harness-codex-gpt56-high` | H | GPT relay / Responses / `gpt-5.6-sol` high | Codex 0.149.0 / `codex-gpt56-high` | Candidate-A relay route and refs | Full stream; run-evidence exposure required | Existing binding/config; controlled reasoning ablation retained. |
| `harness-deepseek-v4flash` | H | DeepSeek official / Chat Completions / `deepseek-v4-flash` | DeepSeek Harness 0.1.1-rc.2 / `deepseek-harness-v4flash` | Candidate-A official route and ref | Final output; observed model not exposed | Existing binding/config; developer-preview and variant risks remain. |

Matched pair: `model-qwen38-alibaba-messages` ↔ `harness-claude-qwen38-alibaba`. Controlled ablation: the same Codex medium ↔ high pair as Candidate A. Pricing is unknown. Configuration is available from the separate Alibaba and core-smoke private sources. Required code is narrow v4 orchestration support for the already-registered Alibaba Direct/Claude bindings; no Adapter SDK work is justified.

## Selection and freeze

Candidate A was selected without score evidence. It preserves the original scientific purposes with an already-enforced Direct↔Harness route identity, an already-enforced reasoning ablation, all four runtime types, and no new provider/harness binding. Candidate B remains a valid future redesign option but changes the P-lane model/provider and needs new smoke orchestration.

The new immutable successor is `core-real-matrix-v4`, plan digest `sha256:2e30dcaa50d0e836577d4c985c0d84caca41ed22df36987faa46a98991eeedcb`, using 18 tasks at version 1.0.2, 7 cells, 5 repeats, 630 planned subjects, and 63 separately budgeted Judge calls. v3 and v3r1 were not modified or resumed.

## Split preflight and canary outcome

- `CANARY_PREFLIGHT`: `READY_WITH_WARNINGS`, digest `sha256:bd3c515e7eed6ac9148756e71e393182e9606853e52775741e0016dd6912926d`. The sole warning was unknown pricing. It authorized exactly 7 subjects + 1 conditional Judge, with no full-Matrix authority.
- `FULL_MATRIX_PREFLIGHT`: `BLOCKED`, digest `sha256:119e6b4aadabf62f07a12470ea50d6c208d2bd700e1e0886bab17d63b66cc6ea`. Blocking reasons: `FULL_MATRIX_PRICING_UNKNOWN` and `FULL_MATRIX_BUDGET_NOT_AUTHORIZED`.
- Real canary: `ABORTED` after 4 subject launches. Calls 1–3 reached terminal subject outcomes. Call 4 (`harness-codex-gpt56-medium`) passed the deterministic verifier but exposed no observed model, violating the frozen P-lane identity requirement and producing `OBSERVED_MODEL_CONFLICT`.
- Calls 5–7 and the Judge were not launched. Retries, fallbacks, substitutions, and recovery attempts: zero.

The authorization decision is `HARD_STOPPED`. The 630-run Matrix is not authorized and was not launched. Historic Qwen timeout root cause remains `UNRESOLVED`; this canary did not investigate or rewrite it.

Worst-case monetary projections for 630 subjects and 63 Judge calls remain `UNKNOWN_NOT_ZERO`. The sequential frozen timeout envelope is 119,070 seconds (33h 4m 30s); it is a ceiling, not a cost or throughput promise.
