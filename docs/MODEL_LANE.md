# M-Lane direct model boundary

Phase D implements one model-only evaluation flow:

```text
Task package → direct-patch-v1 prompt → one provider attempt → strict JSON patch
→ trusted workspace mutation → Phase C isolated verifier → evidence and score
```

The model receives task instructions, a stable UTF-8 serialization of the fresh subject workspace,
optional subject-visible context, and the patch schema. It receives no shell, filesystem tool,
web tool, function tool, MCP, coding harness, verifier, or oracle. Supporting files are ordered by
POSIX relative path and the logical prompt is hashed with its template version.

## Provider protocols

- OpenAI Responses: `POST /responses`, `instructions` plus `input`, no tools, `store=false`,
  protocol-compatible reasoning efforts including GPT-5.6 `max`, and public content collected from
  valid `output_text` and `refusal` blocks.
- Anthropic Messages: `POST /v1/messages`, top-level `system`, one user message, explicit
  `max_tokens`, and optional `output_config.effort` only when configured.
- Generic OpenAI-compatible: configured `POST .../chat/completions`, system/user messages, and
  only explicitly configured generation controls. Generic compatibility does not imply support
  for OpenAI reasoning settings.

All adapters use async httpx with one attempt. They preserve requested and observed model identity,
safe request ID, public output, usage counts, status/stop reason, endpoint/protocol, and latency.
Only 2xx responses with protocol-defined terminal public-text or refusal signals complete an
attempt. OpenAI Responses `status=incomplete` is read only through the bounded
`incomplete_details.reason`: `max_output_tokens` is a successful provider result that terminates
as the capability outcome `subject_output_error`, while content filtering, provider interruption,
missing reasons, and unknown reasons remain conservative provider failures. The max-token case is
never parsed as a patch, never invokes the verifier, and never retries. Redirects, tool
continuations, other truncation, filtering without a refusal signal, malformed UTF-8 text, and
provider failures are normalized without persisting response bodies. OpenAI
Responses refusal content, Anthropic `stop_reason=refusal`, and a generic compatible
`message.refusal` are successful model refusals, not provider or infrastructure failures.
They never persist raw response bodies, authorization headers, OpenAI reasoning items, or Anthropic
thinking blocks. Profiles store only the credential environment-variable name.

Profiles are trusted operator credential-routing configuration, not task/subject input. Core sends
credentials only over HTTPS. The two canonical official origins are accepted directly; any generic
or alternate origin requires the operator to pass `--allow-custom-endpoint` explicitly. That flag
means the operator has verified the configured origin is intended to receive the referenced
environment credential; it is not suitable for profiles supplied by an untrusted task or model.

## Patch and evidence boundary

The public model response must be exactly one `direct-patch-v1` JSON object. Only bounded `write`
and file `delete` operations are supported. Absolute paths, `..`, duplicate targets, symlink
traversal, protected task files, non-file deletes, and oversized content fail closed as subject
output errors. HarnessLab applies operations; it never executes model-supplied shell commands.
Application is staged on the same filesystem, checked against the exact prompt workspace identity,
and switched into place only after the complete patch and protected-file identities validate.
Storage, staging, rollback, or verifier-boundary failures remain infrastructure failures rather than
being blame-assigned to the model.

A normalized model refusal produces `subject_refusal` evidence after one provider attempt. It
retains provider/model/request/usage/stop/latency and public-refusal identity, but it is never parsed
as a patch, never mutates the workspace, never invokes the verifier, and never retries or falls back.

Before evidence is published, the final workspace and staged artifact tree are scanned for exact
credential values in both relative paths and regular-file bytes. A match withholds the artifact.
The M-Lane manifest stores the public response and digest, parsed-patch digest, input/output
workspace digests, prompt identity, safe provider facts, verifier result, score, and outcome.
Failure manifests retain only normalized safe facts when available (category, bounded incomplete
reason, timeout phase, status code, request ID, response/stop status, bounded latency, and the
single attempt count), never a raw body. Timeout phase is the typed `connect`, `read`, `write`,
`pool`, or `unknown` transport
stage; it is null for non-timeout failures and for historical timeout evidence collected before the
phase field existed. It never contains an exception message, URL, header, credential, body, or
traceback.
The complete Phase C verifier artifact tree is copied under the manifest-declared `verifier/`
namespace and bound by its own tree digest, so its relative stdout, stderr, manifest, and workspace
references remain self-contained in the Phase D bundle.

Gate D is deterministic and keyless. Provider protocol tests use httpx MockTransport, and the E2E
uses a fake direct provider followed by the real Phase C Docker verifier. Real-provider smoke is
optional and reported separately as `NOT_RUN` unless explicitly executed with an already-configured
credential reference.
