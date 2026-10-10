# Private saved Codex evidence MVP

SameScale accepts an explicitly reviewed saved run and final source snapshot. It never starts
Codex, reruns an Agent, reads development login/session directories, or takes over subscription
authentication. REAL_CODEX remains unconditionally closed; SIWC is outside this workflow.

## Operator boundary and sources

Enable the existing loopback/operator/origin boundary described in [local planning](LOCAL_PLANNING.md).
Set `HARNESSLAB_EXTERNAL_EVIDENCE_POLICY` to a canonical, operator-owned JSON file with mode 0600.
Use a separate private store outside the repository, source directories and verifier/task storage.
The store must be owned by the operator and inaccessible to other users. Do not use a service,
historical database or existing execution directory as this store. No schema migration is needed.

Each source is an individual opt-in item with a source ID, format, classification and externally
retained exact digests. There is no directory discovery, arbitrary HTTP upload/server path, automatic
session collection or API verifier command. Example (digests below must be replaced with reviewed pins):

```json
{
  "schema_version": 1,
  "store": "/srv/samescale-private/external-records",
  "sources": [{
    "source_id": "reviewed-saved-run-001",
    "format": "codex-jsonl-v1",
    "source_kind": "unverified",
    "path": "/srv/samescale-inbox/reviewed-run-001/trace",
    "digest": "sha256:<exact-approved-source-tree-digest>",
    "workspace": "/srv/samescale-inbox/reviewed-run-001/final-workspace",
    "workspace_digest": "sha256:<exact-approved-workspace-tree-digest>"
  }]
}
```

`digest_tree` in the existing Task package library defines tree digests: sorted relative file names
and bytes, each length-prefixed. The verified-hook format instead pins its existing `bundle.json`
digest, as required by its existing reader. Pins must come from the operator's separately reviewed
copy, not from an untrusted manifest's self-declaration. A source/Workspace pairing is an operator
assertion; matching hashes never authenticate its producer, ownership or instruction compliance.

Supported inputs:

| Format | Explicitly approved source | Treatment |
| --- | --- | --- |
| `codex-jsonl-v1` | A dedicated directory containing only `events.jsonl`, the user's already saved `exec --json` stream | Existing Codex sanitizer/Trace normalization; text, reasoning, output, usage and diagnostics omitted before persistence. No fabricated Episode. |
| `native-hook-v1` | Existing content-free hook spool plus separately pinned final Workspace | Reuse Hook Episode/Trace derivation. Incomplete paired lifecycle remains partial, without inventing an Episode. |
| `verified-hook-v1` | Existing pinned verified-hook bundle and its final Workspace | Strict existing bundle reader checks task, trace, report, lifecycle and Workspace bindings. Original Episode stays unchanged. |
| `codex-h-lane-v1` | Existing completed H-Lane artifact bundle and its pinned Workspace | Reuse Episode reader; original recorded pass/fail stays distinct from new independent admission. |

Do not provide `~/.codex`, authentication files, private rollouts or unreviewed transcripts.
Rollout `response_item` format is rejected. `historical`, `synthetic` and `unverified` are operator
classifications, not authenticity attestations. The original Episode classification is retained;
a known synthetic verified-hook bundle cannot be relabelled historical. Other supplied classifications
cannot be independently attested. The admitted historical example is the repository's explicitly
approved [saved real Hook observation](evidence/real-codex-native-hook-20261007/README.md).

## Private UI and API

Open `/external-runs`, unlock with the local operator credential (page memory only), select an
approved source and explicitly approve intake. Saved records survive app restart and source removal.
Import is content-addressed and idempotent; a private lock plus atomic directory rename prevents a
partial import from being listed as complete. Changed/corrupt saved records are refused, not replaced.

All `/api/external-evidence/*` endpoints require the existing private boundary, including reads:

- `GET /sources`: explicit source bindings, no server paths.
- `POST /records`: `{ "source_id": "…", "consent": "IMPORT_APPROVED_SAVED_EVIDENCE" }`.
- `GET /records` and `GET /records/{identity}`: source/completeness, sanitized Trace and diagnosis.
- `GET /records/{identity}/export`: reviewed source snapshot and projected evidence; SHA in
  `X-Evidence-SHA256`, `Cache-Control: no-store`. Public Demo cannot read or import.

Diagnostics link ordinal/call identities, Agent report presence, observed tool failures, file changes,
independent Workspace acceptance and infrastructure observations. They are deterministic descriptive
observations, not LLM diagnosis or causal attribution. Command bodies are hashed; Agent message text,
reasoning, prompts, raw output and auth never enter the new record. Missing fields stay unknown.
Hooks have causal pairs, not wall-clock ordering. A raw JSONL turn end does not establish process
exit, task acceptance or complete collection. File changes require a bound baseline; otherwise they
are absent or explicitly source-reported, not reconstructed. No Official result or comparable ranking
is created. No existing Episode/Run/Diagnosis, matrix cell or frozen result is rewritten.

## Separate independent Workspace verification

Strict saved verified-hook results can be read offline. A new independent check requires a separate
operator task mapping (`task_reference` and exact `task_digest` in the approved source), an existing
Managed TaskStore snapshot and **valid prior Custom qualification / baseline-fail / oracle-pass**
through `HARNESSLAB_LOCAL_TASK_POLICY`. A contradictory existing task binding is refused. An arbitrary
Subject command, self-report or source-provided verifier is never executable authority.

The optional evidence policy must also specify `verifier_image_id` (existing local content ID),
`runtime_root` and `artifact_root`, all isolated from source/store/task assets. The API has no process
or Docker privilege. The trusted operator runs:

```bash
uv run --locked harnesslab external-evidence verify-workspace RECORD_ID \
  --confirm-independent-verifier
```

This reuses `PinnedVerifierSandbox`: no image build/pull; non-root/read-only root, network none,
no credentials/socket, read-only `/workspace` and hidden `/verifier`, existing resource limits and
at most 30 seconds (or the shorter task timeout). It verifies a private copy, preserving the stored
snapshot and protected contract files. The original Episode remains immutable; a separate digest-bound
receipt records checks and outcome. Zero checks, malformed/contradictory output, timeout or failed
cleanup stay `NOT_VERIFIED`. One physical attempt is durably marked before execution; repeated completed
reads return the same receipt and interrupted attempts cannot automatically retry. There is no new
Worker, Agent runtime, provider call, subscription/quota access or automatic repair. Refresh the UI to
read the independent result. Missing task/admission/runtime prerequisites refuse execution.

## Export and offline replay

Export includes only the admitted UTF-8 source snapshot, source/Workspace pins, projected Trace,
original Episode reference/classification and independent summary/receipt. It excludes raw transcripts,
prompt/command bodies, hidden verifier/oracle code, raw verifier logs and server paths. Retain the
export digest **separately**, then run in a fresh output path:

```bash
PYTHONPATH=src:. .venv/bin/python scripts/replay_external_evidence.py \
  --evidence saved-evidence.json --sha256 sha256:EXTERNALLY_RETAINED_DIGEST \
  --output replay.json
```

The entrypoint installs the existing offline audit guard rejecting network/process operations. Replay
checks the external pin, record identity, Workspace inventory/bytes, receipt bindings/check semantics
and deterministic diagnosis. It executes neither Agent nor Verifier. It verifies the retained receipt;
it is not another execution of hidden checks, independent origin attestation or reproduction of model
behavior. The CLI also exposes a pure data reader at `external-evidence replay`.

## Envelope and remaining limits

Final snapshots: nonempty UTF-8 ordinary source files, at most 500 files / 4 MB. Trace: 4096 events;
source snapshots: 4000 nodes / 32 MB, bounded depth; export: 12 MB. Ancestor/file `O_NOFOLLOW` opens,
inode checks, hardlink/special-file rejection and pre-write known credential-pattern checks protect
intake against substitution. Workspace credential/config/repository and hidden verifier/oracle paths
are rejected. Root stores and policy files must be separately owned/private.

Pattern rejection is not universal secret or intellectual-property detection: review and sanitize
every supplied item, including source code and filenames, before approving its pin. Binary/large
repositories, interactive Codex private session formats, remote uploads, multi-user isolation, a
general source-authenticity attestation, asynchronous verifier scheduling/cancellation UI and automated
collection are outside this MVP. Real execution and SIWC qualification remain separate closed gates.
Historical REAL evidence and controlled fixtures retain distinct labels. [Acceptance](qa/external-evidence-mvp-20261011/README.md).
