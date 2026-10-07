# One real Codex attempt, independently checked

Codex repaired a small Python retry ledger: store the first success, ignore identical retries,
and reject conflicting retries while preserving the original. SameScale passively captured native
SessionStart → five paired tool calls → Stop, then bound the final two-file workspace to a
separate deterministic verifier. **All five checks passed on the first attempt.** No failure was
fabricated and no repair run was needed. Two offline replays produced byte-identical outputs,
without running Codex, the verifier, or network calls.

**Proven:** this saved workspace satisfies the five task checks; the saved evidence can be
reconstructed deterministically. **Unproven:** general coding ability, model rankings, causal
improvements, instruction compliance, human ownership, or recruiter comprehension.

[Machine-readable receipt](receipt.json) · [Original CUSTOM Episode](frozen/attempt-1/episode.json) ·
[Workspace inventory](frozen/attempt-1/workspace-inventory.json) ·
[Independent verifier report](frozen/attempt-1/verifier-run/stdout.txt) ·
[Replay 1](replay-1.json) · [Replay 2](replay-2.json)

The operator observed **one real Codex CLI 0.160.1 execution**, configured for `gpt-6.1-sol` / high,
in a disposable workspace with a temporary Codex home and reviewed passive hooks. The invocation
used `--no-daemon`, `--ephemeral`, and temporary hook trust; global configuration was unchanged.
Subject output was discarded. Ephemeral log/thread tables contained zero rows and no rollout files
were created. Verifier inputs were read-only in the existing network-disabled Docker sandbox;
its ten lifecycle stages completed and cleanup was verified. `contract.txt` remained unchanged.

The Episode retains `NOT_VERIFIED`: hooks alone do not verify a task. The separately bound L0
result is `VERIFIED_PASS`, **5/5**. Tool exit codes, actual serving model, request count, usage,
cost, and root cause remain unknown. Hashes bind bytes, not origin authenticity; source authenticity
remains `NOT_ATTESTED`. This is CUSTOM evidence, not Official benchmark evidence or a comparison.

The frozen bundle contains content-free hook projections, public task-package source assets,
final workspace code, and structured verifier evidence. The task instruction is an existing
public contract asset; the composed invocation prompt was never saved. `stdout.txt` contains only
the deterministic verifier JSON, not subject stdout. No private transcript, reasoning, raw native
payload, credential, or subject output is included.

The only product changes unblock this case: `freeze-hooks --allow-pass` emits a neutral verified
observation, and task identity comparison respects set semantics. The existing failure-only
regression format still rejects passing workspaces. The byte-preserving frozen inputs and two
replay outputs are pinned by [receipt.json](receipt.json). Source changes and this case are
uncommitted; no CI, deployment, release, or human participation acceptance is claimed.

From the repository root, with its existing locked environment, replay into a fresh directory:

```bash
case_path=docs/evidence/real-codex-native-hook-20261007/frozen/case.json
case_sha=sha256:c2cb4498702e136a1791b020d828f4da557934a3eaf9af6ea27f8f6349e707b8
replay_dir=$(mktemp -d /tmp/samescale-native-replay-XXXXXX)
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python scripts/replay_hook.py \
  --case "$case_path" --sha256 "$case_sha" --output "$replay_dir/1.json"
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src .venv/bin/python scripts/replay_hook.py \
  --case "$case_path" --sha256 "$case_sha" --output "$replay_dir/2.json"
cmp "$replay_dir/1.json" "$replay_dir/2.json"
```

The replay entrypoint installs an audit guard rejecting network and subprocess operations.
Replay validates saved inputs; it does not rerun checks or certify source authenticity.
