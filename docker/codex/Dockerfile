FROM node:24-bookworm-slim@sha256:3638d9a6fe4030bd716be989438248074489337ba3275657f93595428be4fc03

ARG CODEX_VERSION=0.149.0

RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        ca-certificates \
        git \
        openjdk-17-jdk-headless \
        python3 \
    && rm -rf /var/lib/apt/lists/* \
    && npm install --global --omit=dev "@openai/codex@${CODEX_VERSION}" \
    && npm cache clean --force \
    && groupadd --gid 10001 harnesslab \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin harnesslab

ENV CODEX_HOME=/tmp/codex-home \
    HOME=/tmp/home \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER 10001:10001
WORKDIR /workspace
ENTRYPOINT ["codex"]
CMD ["--version"]
