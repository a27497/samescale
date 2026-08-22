# HarnessLab AI

HarnessLab AI is a reproducible **Model × Harness × Judge** evaluation and attribution
platform. The repository currently contains **Phase A — Foundation & Contracts** and
**Phase B — Task Contract + Deterministic Verifier**, plus **Phase C — Native Docker Sandbox**.

## Implemented now

- An exact Python 3.12.14 runtime and uv lockfile
- A Typer CLI with `--help`, `--version`, `doctor`, and `serve`
- A FastAPI control API with a database-aware `GET /api/health`
- Secret-safe settings loaded with Pydantic Settings
- PostgreSQL 18 development service, SQLAlchemy 2 async access, psycopg 3, and Alembic
- Pydantic v2 contracts for Task, Model, Harness, Experiment, and Run
- Versioned, strict-YAML task packages with deterministic task and workspace digests
- Fresh subject workspaces that exclude hidden verifiers and oracle overlays
- Fail-closed deterministic verification with baseline-fail/oracle-pass polarity validation,
  bounded partial scores, protected-file checks, and immutable evidence manifests
- Python, Java 21, and TypeScript/Node 24 controlled micro-task fixtures
- `harnesslab task validate` and an authoritative Gate B runner
- A Docker CLI sandbox with a fresh non-root Linux container per subject/verifier run
- Inspect-verified capability, privilege, network, rootfs, PID, CPU, memory, and mount controls
- Bounded/redacted logs, immutable image identity, safe workspace snapshots, and hashed artifacts
- Timeout/cancellation cleanup and fresh-run workspace isolation
- A minimal PostgreSQL execution lease with heartbeat and expiry recovery
- `harnesslab sandbox doctor` and an authoritative Gate C runner
- pytest integration/unit coverage, Ruff, mypy, and one authoritative Gate A runner
- GitHub Actions using PostgreSQL 18 without model-provider credentials

## Planned Core

Provider and harness adapters, normalized traces, experiment execution, the full durable queue and
worker scheduler, aggregate scoring/statistics, and judge calibration are **PLANNED**. Phase B's
host verifier remains for trusted fixture validation; Phase C adds the first untrusted-workspace
Docker boundary and an independently isolated verifier container.

## Workbench later

Matrix UI, visual analysis, and analyst workflows are future **WORKBENCH** concerns. No frontend,
LangGraph analyst, RAG, or multi-agent framework is present.

## Local setup

Gate A prerequisites are Docker and [uv](https://docs.astral.sh/uv/). Gate B additionally requires
Java 21 (`java` and `javac`) and Node.js 24 or newer on `PATH`. Gate C requires a reachable local
Docker Engine, or Docker Desktop using Linux containers; remote TCP/SSH contexts are unsupported.

```powershell
Copy-Item .env.example .env
uv sync --locked
docker compose up -d
uv run alembic upgrade head
uv run harnesslab doctor
uv run harnesslab sandbox doctor
```

Start the API and query its health endpoint:

```powershell
uv run harnesslab serve
Invoke-RestMethod http://127.0.0.1:8000/api/health
```

`doctor` returns exit `0` when all required checks pass, `1` for a failed configured check, and
`2` when required configuration is not available. Health returns HTTP 503 when the database
round trip fails and never returns a DSN or credential.

## Verification

With PostgreSQL running and `DATABASE_URL` configured, the authoritative local/CI gate is:

```powershell
uv run --locked python scripts/verify_gate_a.py
```

This runner executes locked sync, CLI checks, pytest (including an empty-database migration),
Ruff, mypy, Alembic, and Git whitespace validation. It rejects zero collected tests, skipped
critical tests, imports outside the working tree, or an absent database configuration. Exit `2`
means **NOT_VERIFIED**, not success.

The authoritative Phase B gate is:

```powershell
uv run --locked python scripts/verify_gate_b.py
```

It runs the Phase B test corpus, validates all three language fixtures through the public CLI,
checks their baseline/oracle polarity and critical tests, then runs Ruff, formatting, mypy, and
Git whitespace validation. Individual task packages can be inspected without exposing hidden
assets:

```powershell
uv run harnesslab task validate tasks/micro-python-clamp/1.0.0
```

The Phase C gate runs real hardened subject and verifier containers, verifies cleanup and
fresh-workspace behavior, checks artifact/redaction integrity, exercises lease expiry recovery,
and invokes the Phase A and Phase B gates as regressions:

```powershell
uv run --locked python scripts/verify_gate_c.py
```

See [Architecture](docs/ARCHITECTURE.md), [Evaluation Methodology](docs/EVAL_METHODOLOGY.md), and
[Task Format](docs/TASK_FORMAT.md), [Sandbox Security](docs/SANDBOX_SECURITY.md), and
[Resume Scope](docs/RESUME_SCOPE.md).
