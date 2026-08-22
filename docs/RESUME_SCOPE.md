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
- Remote GitHub Actions Gate A + Gate B for the Phase B implementation baseline
  `238613d5140d34e20ee1136cf48bbc32f7abe831` (run `32575558448`, result `success`)

Evidence date: 2026-08-22. Evidence is local Gate A and Gate B output plus the named remote CI
runs. This does not imply any model/harness evaluation capability or untrusted-code isolation.

## IMPLEMENTED_NOT_YET_MASTERED

None recorded. This category requires an implemented capability whose operational ownership has
not yet been demonstrated.

## DESIGN_ONLY

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

None recorded for the Phase A or Phase B gates. Future capabilities remain `DESIGN_ONLY` until
their own implementation and verification gates exist.
