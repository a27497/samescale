# Budget semantics v2.2

Budget equality is not resource-envelope equality unless the value, scope,
enforcement mechanism, and observability all match. `BudgetScope` therefore
binds each methodology budget dimension to a bounded scope. Scope is optional
only when reading historical methodology-v2 artifacts; an unscoped contract
cannot establish a resource-normalized comparison.

## Contract layers

| Layer | Field | Meaning | Runtime authority |
|---|---|---|---|
| Task `ResourceBudget` | `timeout_seconds` | Legacy task declaration; 90 seconds in the Alibaba portfolio | Not consumed as the Direct provider timeout or Claude process timeout |
| Task `ResourceBudget` | `max_output_tokens` | Legacy task declaration; 2,000 in the Alibaba portfolio | Does not itself configure either runner |
| Task `ResourceBudget` | `network_policy` | Task-level subject-network requirement | Persisted in evidence; enforcement depends on the selected runner/profile |
| Methodology `BudgetContract` | six resource dimensions | Planning and comparison contract | A claim boundary, not proof that a runner implemented the values |
| Runtime | profile, payload, process timeout, operator wrapper | Effective operational envelope | Authoritative for enforcement and observability |

Historical manifests and plans remain readable. A missing `scopes` field is
preserved during serialization, so their canonical identities do not change.

## Effective Alibaba Messages envelopes

The following table records the effective configuration used by
`portfolio-alibaba-breadth-v1`, rather than inferring enforcement from its
task budget.

| Dimension | Direct M-Lane value | Direct scope | Direct enforcement / observability | Claude Code H-Lane value | Claude scope | Claude enforcement / observability |
|---|---:|---|---|---:|---|---|
| Wall time | 180 s provider request; 240 s complete-run operator wall | per provider request; per logical run | HTTP client and operator wrapper enforced; provider latency and terminal state observed | 180 s Claude process; 240 s complete-run operator wall | process phase; per logical run | backend timeout and operator wrapper enforced; duration and timeout observed |
| Output tokens | 2,000 | per provider request and, because exactly one request is issued, per logical run | `max_tokens` is sent in the Messages payload; usage is observed when returned | NOT_AVAILABLE | NOT_AVAILABLE | the Claude adapter passes no token ceiling to the CLI; aggregate usage is observed only when the terminal result exposes it |
| Model turns | 1 | per logical run | enforced structurally by one adapter invocation; observable | NOT_AVAILABLE | NOT_AVAILABLE | Claude may use multiple turns; no trustworthy aggregate count is persisted |
| Provider requests | 1 | per logical run | enforced structurally by one adapter invocation; observable | NOT_AVAILABLE | NOT_AVAILABLE | internal provider-call count is not exposed by the current CLI evidence |
| Tool calls | 0 | per logical run | Direct prompt and tool-free provider payload; observable | no enforced maximum | observed only | Read/Edit/Write/Bash are enabled; normalized trace events are visible but do not preserve an exact aggregate call count |
| Cost | NOT_AVAILABLE | NOT_AVAILABLE | no trusted run ceiling or exact total | NOT_AVAILABLE | NOT_AVAILABLE | no trusted run ceiling or exact total |

The task's numeric 2,000-token value therefore describes neither a common
aggregate logical-run token ceiling nor a common compute envelope. Existing
Claude evidence with more than 2,000 aggregate output tokens is consistent
with the adapter implementation and directly contradicts that interpretation.

## Fairness classes

`RESOURCE_NORMALIZED_COMPARISON` requires identical, explicitly scoped
contracts, a common enforced logical-run wall, and either:

- a common enforced logical-run aggregate output, model-turn, and
  provider-request envelope; or
- a common trusted logical-run cost ceiling.

`NATIVE_HARNESS_SYSTEM_COMPARISON` evaluates the configured end-to-end systems.
Native multi-turn planning and tools are treatment components. This supports a
statement such as "the Claude Code system achieved X versus Direct under the
configured operational envelopes." It does not support a causal
compute-held-constant Harness uplift statement.

## Pair B claim-boundary addendum v2.2

The original preregistration is immutable. Its Pair B label remains historical
provenance, but v2.2 classifies C (Qwen Direct / Alibaba Messages) versus D
(Claude Code + Qwen / Alibaba Messages) as
`NATIVE_HARNESS_SYSTEM_COMPARISON`, a bounded end-to-end system comparison.
The reason is specific: model, provider, route, protocol, tasks, and verifiers
match, while Direct is one request with no tools and Claude permits multiple
unobserved provider requests/turns plus native tools. No common aggregate
compute or trusted cost ceiling is proven. Formal resource-normalized
`HARNESS_UPLIFT` is therefore `NOT_AVAILABLE` for this pair.

The 10 acquired C/D logical slots remain reportable. At the v2.2 checkpoint,
Direct has 2 verified passes in 5 slots, 209,736 ms total provider latency,
8,525 output tokens, 1,923 input tokens, zero tools, and zero logical infra
failures. Claude has 3 verified passes in 5 slots, 534,941 ms total process
duration, 15,205 output tokens and 812 input tokens across four usage-bearing
terminal results, 116,702 cached-input tokens, 24,280 cache-write-input tokens,
and zero logical infra failures after the existing semantic-v2.1 timeout
classification. One raw Claude process timed out at 180,944 ms. Its exact tool
call count is not available; the manifests contain 59 normalized
`COMMAND_EXECUTION` and 5 `FILE_CHANGE` events.

## Frozen Direct Chat comparison

`portfolio-alibaba-model-chat-v1` uses a symmetric 4,000-token Direct budget.
The prior 2,000-token value was inherited rather than methodologically chosen,
and 7 of 11 acquired Qwen Direct slots exhausted that ceiling. The increase is
frozen before Chat evaluation, applies equally to Qwen3.8 Max and DeepSeek V4
Pro, and was not selected from model scores or a winner. Both cells use one
provider request, one model turn, zero tools, the same 180-second request
timeout, the same 240-second complete-run wall, Alibaba Chat Completions, the
same task/verifier/network controls, and no trusted cost ceiling.

The keyless plan contains 18 deterministic task blocks and 36 immutable slot
identities under `BLOCKED_INTERLEAVED_SCHEDULING`. It is not enqueued. Execution
must bind the 4,000-token scoped runtime contract in evidence; the legacy task
`ResourceBudget` is not sufficient evidence of that binding.
