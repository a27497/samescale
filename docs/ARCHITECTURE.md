# Architecture

## Foundation and deterministic task verification

HarnessLab is CLI-first. The `harnesslab` Typer CLI is the operator entry point, while the FastAPI
application is a small control API. Both use one Pydantic Settings model and the same database
health service. PostgreSQL 18 is the only infrastructure service. SQLAlchemy 2 uses psycopg 3 for
async application access; Alembic uses the same driver and metadata for schema changes.

Pydantic contracts describe domain inputs and reproducibility facts. They are intentionally
separate from SQLAlchemy persistence models: contracts protect API/domain meaning, while database
models describe storage. Phase A persists only a schema metadata foundation and does not pretend
that future experiment execution tables exist.

```text
Typer CLI ─┬─ doctor ───────────┐
           └─ serve ─ FastAPI ──┼─ Settings ─ SQLAlchemy/psycopg ─ PostgreSQL 18
                         health ┘

Pydantic contracts: Task × Model × Harness × Experiment Config → Run facts
```

Phase B adds a versioned task-package boundary without adding an execution engine. A strict
manifest names the subject workspace, optional context bundle, hidden verifier, optional oracle,
toolchain expectations, and execution policy. Deterministic digests bind the task package and the
materialized subject workspace independently.

```text
Versioned task package ── strict load + digest ──┬─ fresh workspace/context ─ subject edits
                                                │                                │
                                                ├─ hidden verifier ───────────────┤
                                                └─ oracle overlay (validation) ───┘
                                                                                 │
                                                   bounded result + immutable evidence
```

The subject-facing workspace never contains the package's hidden verifier or oracle. Package
validation requires the untouched baseline to fail and a separately materialized oracle overlay
to pass. The repository's Python, Java, and TypeScript fixtures execute trusted verifier code on
the host solely to validate this contract. This is not a security boundary for arbitrary or
untrusted task code; process/container isolation belongs to the planned Docker sandbox phase.

## Planned Core boundaries

The following are **PLANNED**, not implemented:

- Provider and harness adapters at explicit external-system boundaries
- A Docker sandbox that produces reproducible execution artifacts
- Normalized execution traces and aggregate scoring/statistics
- A PostgreSQL-backed durable experiment queue and worker lifecycle
- A local artifact store for immutable task, run, and trace evidence

## Deliberate exclusions

Core remains Python because the evaluation ecosystem, schemas, subprocess orchestration, and
analysis tooling are Python-centered; adding Java would create a second runtime without solving an
adapter boundary. Redis and Celery are unnecessary while PostgreSQL can later provide durable
state and queue semantics transactionally. Kafka/RocketMQ and Kubernetes solve scale and
operations problems not established by current evidence. RAG and multi-agent frameworks do not
solve HarnessLab's core reproducibility and adapter problem.

These exclusions are decisions against premature complexity, not claims that those technologies
are universally unsuitable.
