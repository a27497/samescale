# syntax=docker/dockerfile:1.7

FROM node:24.18.1-bookworm-slim@sha256:235600a8101ab264e117b1768e925532262668dc9b581ef1dd7d96ced463b8e7 AS workbench-build

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM ghcr.io/astral-sh/uv:0.12.5@sha256:e85be844203885286c60ffad8a858d48afb6c5a5c237ca0e67f12e74b8f174b1 AS uv-locked

FROM python:3.12.14-slim-bookworm@sha256:0f5b26b9518d002b6173fd61daad821fa340635ebfec5bba471013f9ca114579 AS python-build

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/harnesslab/.venv
WORKDIR /opt/harnesslab
COPY --from=uv-locked /uv /usr/local/bin/uv
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-dev --no-install-project
COPY . ./
RUN uv sync --locked --no-dev

FROM python:3.12.14-slim-bookworm@sha256:0f5b26b9518d002b6173fd61daad821fa340635ebfec5bba471013f9ca114579 AS product

ARG SOURCE_REVISION=unknown
LABEL org.opencontainers.image.title="HarnessLab AI" \
      org.opencontainers.image.description="Keyless HarnessLab control API and bundled Workbench" \
      org.opencontainers.image.revision="${SOURCE_REVISION}"

ENV PATH=/opt/harnesslab/.venv/bin:/usr/local/bin:/usr/bin:/bin \
    HOME=/tmp/harnesslab-home \
    HARNESSLAB_ENVIRONMENT=production \
    HARNESSLAB_WORKBENCH_DIST=/opt/harnesslab/frontend/dist \
    HARNESSLAB_WORKBENCH_ARTIFACT_ROOTS='["/opt/harnesslab/artifacts","/opt/harnesslab/harnesslab-artifacts"]' \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN install -d -o 10001 -g 10001 \
        /opt/harnesslab/artifacts \
        /opt/harnesslab/harnesslab-artifacts \
        /tmp/harnesslab-home

WORKDIR /opt/harnesslab
COPY --from=python-build /opt/harnesslab/.venv .venv
COPY --chown=10001:10001 src/ src/
COPY --chown=10001:10001 alembic/ alembic/
COPY --chown=10001:10001 docs/ docs/
COPY --chown=10001:10001 judge_suites/ judge_suites/
COPY --chown=10001:10001 profiles/ profiles/
COPY --chown=10001:10001 release/ release/
COPY --chown=10001:10001 scripts/ scripts/
COPY --chown=10001:10001 tasks/ tasks/
COPY --chown=10001:10001 alembic.ini pyproject.toml uv.lock README.md rules.md ./
COPY --from=workbench-build --chown=10001:10001 /build/frontend/dist/ frontend/dist/
COPY --chown=10001:10001 docker/product/healthcheck.py /opt/harnesslab/docker/product/healthcheck.py

USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=6 \
    CMD ["python", "/opt/harnesslab/docker/product/healthcheck.py"]
CMD ["harnesslab", "serve", "--host", "0.0.0.0", "--port", "8000"]
