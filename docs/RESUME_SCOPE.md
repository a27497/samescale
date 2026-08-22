# Evidence and resume scope

This file separates repository evidence from intended design. A capability moves to
`IMPLEMENTED_AND_VERIFIED` only after its named gate has produced current evidence.

## IMPLEMENTED_AND_VERIFIED

- Python 3.12.14/uv project installation from the repository lock
- Typer CLI help/version, fail-closed doctor, and Uvicorn serve entry point
- FastAPI database-aware health endpoint, including healthy and unavailable behavior
- PostgreSQL 18.6 connectivity through SQLAlchemy 2 async and psycopg 3
- Alembic upgrade from a newly created empty PostgreSQL database
- Pydantic v2 contracts for Task, Model, Harness, Experiment, and Run comparability facts
- Local pytest, Ruff, mypy, and working-tree checks through the authoritative Gate A runner
- Remote GitHub Actions Gate A for baseline commit
  `f97f5218cfd898a349f1237505b2e5731a65452e` (run `32572916235`, result `success`)
- Versioned task packages with strict YAML loading, duplicate/unknown-field rejection, safe paths,
  symlink rejection, and deterministic task/workspace digests
- Fresh subject-workspace materialization that excludes hidden verifier and oracle assets
- Hidden deterministic verification with fail-closed malformed-output, timeout, and protected-file
  handling; bounded partial scores; and immutable evidence manifests
- Baseline-fail/oracle-pass validation and tamper-resistance tests
- Controlled Python, Java 21, and TypeScript/Node task fixtures
- `harnesslab task validate` and the authoritative local Gate B runner
- Remote GitHub Actions Gate A + Gate B for the approved Phase B head
  `99edecc8c09aedece35ad847c319fbe3fb722b5c` (run `32576411069`, result `success`)
- Local Docker/Docker Desktop Linux-container preflight with remote TCP/SSH context rejection
- Fresh hardened subject and isolated-verifier containers with inspect-derived security evidence
- Timeout and cancellation cleanup, fresh-workspace isolation, bounded redacted output, immutable
  image identity, and symlink-safe local artifact bundles
- Containerized Fake Subject solving the Python micro task followed by isolated hidden verification
- Minimal PostgreSQL execution lease with owner heartbeat, expiry recovery, attempt count, and
  cancellation request
- `harnesslab sandbox doctor` and the authoritative local Gate C runner
- Remote GitHub Actions Gate A + Gate B + Gate C for the final approved Phase C head
  `cdf37c6b5c21a712194120b1d2d96a8d37a49f76` (run `32582365570`, result `success`)
- Credential-reference-only profiles and async httpx adapters for OpenAI Responses, Anthropic
  Messages, and generic OpenAI-compatible Chat Completions
- Versioned deterministic `direct-patch-v1` prompt identity and bounded strict write/delete patch
  application with traversal, symlink, protected-file, and exact-secret defenses
- M-Lane fake-provider execution from fresh Phase B workspace through the Phase C isolated hidden
  verifier, with immutable direct-model evidence and requested/observed model separation
- `harnesslab model run`, model profile validation, and the authoritative no-key Gate D runner
- Remote GitHub Actions Gate A + Gate B + Gate C + Gate D for the Phase D implementation head
  `efacc13397f3f12d3eff6c120c50809fea6d6a5d` (run `32588389612`, result `success`)
- A pinned, project-owned Codex 0.149.0 image/profile and the minimal Codex HarnessAdapter contract
- `codex-harness-v1`, sanitized native JSONL, Normalized Trace v1, filesystem-authoritative
  workspace diffs, explicit Harness failure taxonomy, and immutable H-Lane evidence
- Deterministic Fake Codex execution of all three controlled tasks through the Phase C isolated
  hidden verifier, including fail-closed protocol/profile/artifact and self-report-negative cases
- `harnesslab harness codex doctor` and the authoritative no-key Gate E runner

Evidence date: 2026-08-23. Phase E entries above are local Gate E evidence pending this change's
named remote CI run. Phase D provider contracts are MockTransport/fake-provider verified; Phase E
Codex behavior is deterministic Fake Codex verified. Neither implies a real provider/model call or
VM-level isolation.

## IMPLEMENTED_NOT_YET_MASTERED

None recorded. This category requires an implemented capability whose operational ownership has
not yet been demonstrated.

## DESIGN_ONLY

- Additional Harness adapters
- P-Lane comparability and the experiment execution engine
- Full PostgreSQL queue, scheduler, and worker lifecycle
- Statistical intervals and pass@k
- JudgeLab and judge calibration implementation
- Matrix UI and analyst workbench

## WORKBENCH_ONLY

None implemented. Future UI or analyst conveniences belong here and are not Core evidence.

## NOT_VERIFIED

`REAL_PROVIDER_SMOKE = NOT_RUN` and `REAL_CODEX_SMOKE = NOT_RUN`. No real provider credential is
required for Gate D or Gate E, no ambient Codex login is consumed, and no real-provider/model
invocation is claimed. The provider-control-plane versus subject-network separation is not yet
operationally verified. Future capabilities remain `DESIGN_ONLY` until their own gates exist.
