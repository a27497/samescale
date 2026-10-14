# Codex real coding pilot — 2026-10-14 (Asia/Shanghai)

**Pilot complete; full stage NOT_RUN, waiting for explicit user confirmation.**
Three operator-observed native Codex **0.162.1** attempts, requested **gpt-6.1-sol / high**,
on the first three tasks of a preselected 30-task HumanEval subset. The coding Agent never received
hidden tests or reference solutions. All final candidates were independently checked in separate
network-disabled, credential-free Docker containers. No model Judge, repair or retry was used.

| Task | Agent self-report | Independent acceptance | Primary failure type | Agent seconds | Input / cached / output tokens | API-equivalent estimate |
| --- | --- | --- | --- | ---: | ---: | ---: |
| HumanEval/122 | PASS | PASS | NONE | 44.172 | 47,072 / 41,984 / 783 | $0.02220 |
| HumanEval/33 | PASS | PASS | NONE | 50.433 | 46,790 / 43,520 / 622 | $0.01711 |
| HumanEval/153 | PASS | PASS | NONE | 31.440 | 47,185 / 32,000 / 608 | $0.03965 |

- **Self-report pass rate: 3/3 = 100%; independent pass rate: 3/3 = 100%; gap: 0 percentage points.**
- False completions **0**; unknown claims **0**; unverified candidates **0**. Primary distribution:
  `NONE=3`; build, hidden-test, timeout, environment and unknown failures each **0** in these attempts.
- Agent total **126.045s**; hidden verifier total
  **1.248s** (Docker provisioning/calibration outside Agent timing).
- Tokens: **141,047 input** including **117,504 cached input**,
  plus **2,013 output**. Input + output **143,060**;
  cached input is a subset, not an additional token count.
- Total API-equivalent estimate **$0.078966**, mean
  **$0.026322/task**, observed range **$0.017112–$0.039650/task**.
  **Actual subscription debit / invoice is UNKNOWN**, retained as `null`, never zero.

## Full projection to review before confirmation

Using the mean of three observations, **30 tasks including this pilot** project to
**1,410,470 input** (including
**1,175,040 cached**) +
**20,130 output** =
**1,430,600 total tokens**,
**$0.7897 API-equivalent**, and
**21.0 minutes of Agent time**.
The **remaining 27** project to **$0.7107** and
**18.9 minutes**, plus provisioning/verification overhead.

This is an extrapolation, not a spending cap or confidence interval. Observed input caching is
**83.3%**. If caching disappears with identical token
volume, the 30-task estimate becomes **$3.0222**; **$3.50 API-equivalent** is a practical
planning allowance for that scenario, not a guaranteed ceiling. More difficult tasks/longer traces
can exceed it. The initial 2× mean allowance ($1.60) communicated during packaging did not cover
complete loss of caching; the explicit cold-cache scenario above is the final planning basis.
Agent wall-time limit is 300s/task (30-task aggregate maximum 150 minutes before overhead).

Pricing: short-context Standard API reference for the requested model, $2/M input, $0.10/M cached
input, $10/M output as of 2026-10-14, from [official OpenAI pricing](https://developers.openai.com/api/docs/pricing).
[Configuration](../../../evaluation/coding-agent/config.json) fixes these rates and their basis;
subscription billing and actual serving model/tier are not attested by that reference.

## Reproduce and audit

[Protocol, selection/license, one-command pilot, classification, isolation and limitations](../../../evaluation/coding-agent/README.md).
[Generated JSON report](report.json) · [per-task CSV](results.csv) ·
[artifact receipt / complete selection / digests](artifact-receipt.json) · [offline-review receipt](offline-review.json).

Raw evidence is in **separate local storage outside Git**:
`/home/dev/.local/state/samescale-eval/coding-agent-pilot-20261014-v3.tar.gz` (142,941 bytes).
Archive SHA-256: `5c2a5bf9e417e0a0b72e36a0bda7c53d325ded22f466d962fab60e1d10255fec`.
Pilot-summary SHA-256: `fe14209cb3760190da9119d2b9a66a27f0fe0a3ab3d2f97002e2be6183a992ee`.
The compressed bundle contains native redacted events, complete final regular-file snapshots,
process/container/network receipts, verifier outputs/logs, dataset/license/oracles, executable
protocol sources and inventories. It contains no credential or private reasoning content and no
native executable. It is local storage, not a remote release attachment; remote reviewers need the
bundle supplied separately. No release/tag, deployment or source-publication change was performed.

```bash
# New trial with a new external directory; performs only the three-task pilot and stops:
bash evaluation/coding-agent/run-pilot.sh /absolute/new/external/campaign /absolute/codex/vendor /absolute/existing/auth.json
# After downloading/extracting the saved bundle, keyless offline review (no Docker/model calls):
uv run --locked python scripts/coding_agent_eval.py replay --root /absolute/extracted/pilot-20261014-v3
# ONLY AFTER user confirmation, preserve the pilot and execute the remaining 27:
uv run --locked python scripts/coding_agent_eval.py full --root /absolute/original/pilot-20261014-v3 --codex-vendor /absolute/codex/vendor --auth-file /absolute/existing/auth.json --confirm-pilot-sha256 fe14209cb3760190da9119d2b9a66a27f0fe0a3ab3d2f97002e2be6183a992ee
```

Source base at preparation: `9f634dce7b39cec8eacc2d3ad646b4cb2d1f7efd`; the then-uncommitted executed
runner and verifier are independently bound by SHA-256 in the protocol receipt and bundled
verbatim. Final publication commits must retain those file hashes; the base Git SHA alone is not
presented as the executed implementation. The final PR/head identity is reported at publication.

## Verification and retained preflight failures

- Keyless focused tests **10 PASS**; changed Python Ruff/format and strict mypy **PASS**;
  wrapper Bash syntax and local documentation links **PASS**.
- **36 verifier controls PASS**: 30 reference solutions; three empty implementations and three
  early-exit negative controls. Pinned native CLI/version/config probe used no network/credential/model.
- Extracted archive complete inventory **PASS**; two keyless offline replays match the frozen
  summary exactly; independently rerunning all **3 saved final candidates** in Docker yields **3 PASS**,
  with **zero model calls** during offline review.
- Campaign-created subject/verifier/proxy containers and networks have been removed. Original dirty
  UI-2 worktree, existing services, main, historical evidence and locked dependencies are retained.
  Remote CI is reported separately against the exact pushed head; local checks do not imply CI.

Preflight v1 rejected the reference for HumanEval/33 because that upstream test also calls the
function by name; the verifier now copies candidate bindings into the test namespace before
loading the upstream check. Preflight v2 passed all 36 verifier controls but its CLI probe omitted
the temporary home/workspace setup. Both failures remain in their original external directories,
and incurred **zero model calls**. Corrected v3 passed both prerequisites before any paid attempt.
No failed real attempt was erased or replaced; the three pilot attempts each ran once.

## Limits

This result observed **zero gap** and supports no empirical claim of widespread false completion.
HumanEval is public, potentially memorized, limited to small Python functions, and its tests are
hidden only from the running Agent. Upstream testing semantics (including some self-comparisons)
are preserved; passing this suite is not proof of all behavior. No inference to real issue repair,
SWE-bench, other Agents, model rankings, malicious anti-cheating resistance or causality is warranted.
Three pilot tasks are insufficient to estimate rare failure rates reliably. Requested model, price
reference, deterministic offline derivation and operator provenance remain distinct from serving-model
attestation and an authoritative bill. Claude Code remains disabled configuration, with no Claude
execution/acceptance claim. A fresh model run may differ even with the same frozen protocol.
