# Product installation and startup

HarnessLab's product baseline runs PostgreSQL, schema migrations, the FastAPI control plane, and
the production Vue Workbench in Docker. The normal host needs HarnessLab and Docker Engine with
Docker Compose v2; it does not need Node.js, Java, Python tooling, `uv`, Alembic, or a Vite server.

This distribution is keyless by default. Startup, status, and doctor operations do not receive
provider credentials and do not make provider or Judge calls.

## Start and stop

From a HarnessLab distribution checkout, start the complete local product:

```text
harnesslab up
```

`up` performs the Docker preflight, builds the locked multi-stage product image when necessary,
starts PostgreSQL, runs `alembic upgrade head` in a one-shot migration container, and waits for the
API's database-backed readiness check. The same image contains the compiled Workbench, so no Vite
process runs in production. Repeating `harnesslab up` is safe: Compose reconciles the services and
Alembic rechecks the current head.

Open <http://127.0.0.1:8000/> after startup. Both a direct navigation and a browser refresh on a
Workbench route are handled by the bundled SPA fallback. API paths remain under `/api`; the
authoritative readiness endpoint is <http://127.0.0.1:8000/api/health>.

Inspect the lifecycle without invoking a provider or Judge:

```text
harnesslab status
harnesslab doctor
```

`status` reports the PostgreSQL, migration, API, and Workbench state. `doctor` checks Docker,
configuration, database connectivity, API health, and bundled-asset reachability. A failed or
not-configured check stays visible and returns a nonzero exit status.

Stop the product cleanly:

```text
harnesslab down
```

The named PostgreSQL and artifact volumes are retained across `down` and the next `up`. Removing
those volumes is intentionally not part of the normal lifecycle because it destroys local data.

## Configuration

The defaults are local-development placeholders, never production credentials. Compose reads
these optional values from the shell or a `.env` file beside the selected trusted Compose
manifest:

| Variable | Default | Purpose |
| --- | --- | --- |
| `HARNESSLAB_PORT` | `8000` | Loopback port for the API and Workbench |
| `POSTGRES_PORT` | `5432` | Loopback port for local database tooling |
| `POSTGRES_DB` | `harnesslab` | Local database name |
| `POSTGRES_USER` | `harnesslab` | Local database user |
| `POSTGRES_PASSWORD` | `harnesslab_dev_only` | Local-only database password |
| `HARNESSLAB_IMAGE` | unset | Prebuilt image reference; setting it disables the source build |
| `HARNESSLAB_COMPOSE_FILE` | bundled source manifest | Explicit trusted distribution manifest |
| `HARNESSLAB_SOURCE_REVISION` | `unknown` | Source revision recorded in the image label |

Use a URL-safe database password because the same value is interpolated into the internal
`DATABASE_URL`. Do not commit `.env`; it is excluded from the Docker build context. Provider keys
are deliberately absent from the product services. The settings UI may show presence-only state,
but secrets are never bundled into the frontend, returned by the API, or written to browser
storage.

## Startup architecture and boundaries

The product image has separate locked build stages. Node `24.18.1` installs exactly the frontend
lockfile and emits static assets; `uv 0.12.5` installs the locked Python 3.12 environment. The final
Python image contains neither Node nor `uv`. All base images are pinned by digest.

Compose orders startup as follows:

```text
PostgreSQL healthy -> migration completed -> API + bundled Workbench healthy
```

The API and migration containers run as UID/GID `10001`, drop Linux capabilities, enable
`no-new-privileges`, use a read-only root filesystem, and receive only dedicated writable
artifact volumes and a temporary filesystem. PostgreSQL and HTTP ports bind to loopback rather
than all host interfaces. Services share an isolated Compose bridge, and no Docker socket is
mounted into the control-plane container. Existing hardened execution, verifier, and egress images remain
separate; this product image does not replace or relax those boundaries.

## Compose-level diagnostics

If the HarnessLab launcher cannot complete, these read-only commands expose the underlying state:

```text
docker compose --project-name harnesslab ps --all
docker compose --project-name harnesslab logs migrate api postgres
docker compose --project-name harnesslab config --quiet
```

For a source checkout, `docker compose --project-name harnesslab build api` performs the entire
frontend and Python build inside Docker. `docker compose --project-name harnesslab up --detach
--wait api` is the low-level equivalent of starting the service graph, but the HarnessLab lifecycle
commands are the supported product interface.

The automatic Compose path is bound to the trusted HarnessLab source distribution. The launcher
does not execute a generic Compose file found in the current directory. An external distribution
manifest must be selected explicitly with `--compose-file` or `HARNESSLAB_COMPOSE_FILE`. Setting
`HARNESSLAB_IMAGE` selects a prebuilt image and makes `harnesslab up` pass `--no-build`; without it,
the trusted source distribution is built locally. HarnessLab wheels embed this same locked build
context, including the Workbench sources and task/runtime metadata, so the lifecycle does not
depend on retaining the original repository checkout after installation. Compose is always given
an explicit environment file; a generic `.env` in the current directory is never loaded.

Do not add provider keys merely to make readiness pass. `/api/health` proves a real PostgreSQL
round trip; it does not authorize an experiment, call a provider, run a Judge, or claim scientific
readiness.
