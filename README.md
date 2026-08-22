# HarnessLab AI

HarnessLab AI is a reproducible **Model × Harness × Judge** evaluation and attribution
platform. The repository currently contains only **Phase A — Foundation & Contracts**.

## Implemented now

- An exact Python 3.12.14 runtime and uv lockfile
- A Typer CLI with `--help`, `--version`, `doctor`, and `serve`
- A FastAPI control API with a database-aware `GET /api/health`
- Secret-safe settings loaded with Pydantic Settings
- PostgreSQL 18 development service, SQLAlchemy 2 async access, psycopg 3, and Alembic
- Pydantic v2 contracts for Task, Model, Harness, Experiment, and Run
- pytest integration/unit coverage, Ruff, mypy, and one authoritative Gate A runner
- GitHub Actions using PostgreSQL 18 without model-provider credentials

## Planned Core

Task packages and hidden deterministic verification, sandboxed execution, provider and harness
adapters, normalized traces, experiment execution, durable queueing, scoring/statistics, and judge
calibration are **PLANNED**. They are not implemented in Phase A.

## Workbench later

Matrix UI, visual analysis, and analyst workflows are future **WORKBENCH** concerns. No frontend,
LangGraph analyst, RAG, or multi-agent framework is present.

## Local setup

Prerequisites are Docker and [uv](https://docs.astral.sh/uv/).

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

See [Architecture](docs/ARCHITECTURE.md), [Evaluation Methodology](docs/EVAL_METHODOLOGY.md), and
[Resume Scope](docs/RESUME_SCOPE.md).
