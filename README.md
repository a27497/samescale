# HarnessLab AI

HarnessLab AI is a reproducible **Model × Harness × Judge** evaluation and attribution
platform. The repository currently contains **Phase A — Foundation & Contracts** and
**Phase B — Task Contract + Deterministic Verifier**.

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
- pytest integration/unit coverage, Ruff, mypy, and one authoritative Gate A runner
- GitHub Actions using PostgreSQL 18 without model-provider credentials

## Planned Core

Sandboxed execution, provider and harness adapters, normalized traces, experiment execution,
durable queueing, aggregate scoring/statistics, and judge calibration are **PLANNED**. Phase B's
host-executed verifier fixtures are controlled repository tests, not an untrusted-code sandbox.

## Workbench later

Matrix UI, visual analysis, and analyst workflows are future **WORKBENCH** concerns. No frontend,
LangGraph analyst, RAG, or multi-agent framework is present.

## Local setup

Gate A prerequisites are Docker and [uv](https://docs.astral.sh/uv/). Gate B additionally requires
Java 21 (`java` and `javac`) and Node.js 24 or newer on `PATH`.

```powershell
Copy-Item .env.example .env
uv sync --locked
docker compose up -d
uv run alembic upgrade head
uv run harnesslab doctor
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

See [Architecture](docs/ARCHITECTURE.md), [Evaluation Methodology](docs/EVAL_METHODOLOGY.md), and
[Task Format](docs/TASK_FORMAT.md), and [Resume Scope](docs/RESUME_SCOPE.md).
