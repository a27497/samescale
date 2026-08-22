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

Evidence date: 2026-08-22. Evidence is local Gate A output and does not imply a remote CI run or any
model/harness evaluation capability.

## IMPLEMENTED_NOT_YET_MASTERED

None recorded. This category requires an implemented capability whose operational ownership has
not yet been demonstrated.

## DESIGN_ONLY

- Task directory format, hidden verifier/oracle, and reward-hacking detection
- Docker sandbox execution
- Model provider and harness adapters
- Normalized traces and the experiment execution engine
- PostgreSQL queue/lease/worker lifecycle
- Statistical intervals and pass@k
- JudgeLab and judge calibration implementation
- Matrix UI and analyst workbench

## WORKBENCH_ONLY

None implemented. Future UI or analyst conveniences belong here and are not Core evidence.

## NOT_VERIFIED

- Remote GitHub Actions execution (workflow exists, but a remote run requires a pushed repository)
