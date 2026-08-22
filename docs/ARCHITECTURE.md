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
the host solely to validate this contract.

## Phase C native Docker boundary

Phase C adds the first boundary for an untrusted subject workspace. Trusted HarnessLab code owns
all Docker CLI argv construction; callers cannot supply raw Docker flags, mount destinations, or
host paths. Each run materializes the same Phase B package into a new managed directory and then
uses a fresh, labeled container.

```text
Phase B package ─ fresh managed workspace ─ subject container ─ safe artifact snapshot
                                                │                       │
                                                └─ destroyed ───────────┘

artifact workspace (read-only) ─┬─ isolated verifier container ─ deterministic report
hidden verifier (read-only) ─────┘
```

The subject container never sees `verifier/` or `oracle/`. The verifier is a separate hardened
container whose subject workspace and hidden verifier mounts are read-only. Both roles use no
network, no Docker socket, no added capabilities, a read-only root filesystem, non-root identity,
resource limits, bounded output, and finally-style cleanup. Local artifacts remain filesystem
bundles rather than database blobs.

Phase C also persists only a minimal execution lease: ownership, heartbeat, expiry, recovery
attempt, cancellation request, and status. It is not the planned experiment queue or worker
scheduler. Docker subprocess work on Windows runs on an isolated Proactor thread so the existing
psycopg/Uvicorn selector-loop boundary remains unchanged.

## Phase D M-Lane direct model

Phase D adds one direct-model path without a coding harness. A versioned logical prompt contains
only task instructions, the subject-visible fresh workspace, optional subject-visible context,
and the strict patch output contract. Provider adapters receive no tools. Trusted HarnessLab code
validates and applies the returned JSON patch; model-generated code is evaluated only when the
existing Phase C hidden-verifier container reads the final workspace.

```text
Phase B package ─ fresh workspace ─ direct-patch-v1 prompt ─ Provider API (no tools)
                                           │                       │
                                           │                public JSON patch
                                           │                       │
                                           └─ trusted safe apply ──┘
                                                       │
                                      Phase C isolated hidden verifier
                                                       │
                                   immutable direct-model evidence + score
```

The async httpx provider boundary implements OpenAI Responses, Anthropic Messages, and generic
OpenAI-compatible Chat Completions. It normalizes only public text, route/model identity, safe
request identifiers, usage counts, stop/status, latency, and attempt count. Raw responses,
headers, reasoning items, and thinking blocks are not evidence. Profiles contain credential
environment-variable names only. Gate D uses fake and MockTransport providers; real-provider
execution is not required or claimed.

## Planned Core boundaries

The following are **PLANNED**, not implemented:

- Harness adapters at explicit external-system boundaries
- Normalized execution traces and aggregate scoring/statistics
- A PostgreSQL-backed durable experiment queue and full worker lifecycle
- Remote/cloud artifact storage and worker execution

## Deliberate exclusions

Core remains Python because the evaluation ecosystem, schemas, subprocess orchestration, and
analysis tooling are Python-centered; adding Java would create a second runtime without solving an
adapter boundary. Redis and Celery are unnecessary while PostgreSQL can later provide durable
state and queue semantics transactionally. Kafka/RocketMQ and Kubernetes solve scale and
operations problems not established by current evidence. RAG and multi-agent frameworks do not
solve HarnessLab's core reproducibility and adapter problem.

These exclusions are decisions against premature complexity, not claims that those technologies
are universally unsuitable.
