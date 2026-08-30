FROM python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7 AS python-toolchain

FROM eclipse-temurin:21-jdk-jammy@sha256:ce5767b7222312d42395f5bab033cd91f09e44032a2f21bdfd7b5b912dbe1e77 AS java-toolchain

FROM node:24-bookworm-slim@sha256:3638d9a6fe4030bd716be989438248074489337ba3275657f93595428be4fc03

ARG DEEPSEEK_VERSION=0.1.1-rc.2

COPY --from=python-toolchain /usr/local /usr/local
COPY --from=java-toolchain /opt/java/openjdk /opt/java/openjdk

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates git sqlite3 \
    && rm -rf /var/lib/apt/lists/* \
    && npm install --global --omit=dev "@deepseek-ai/dsh@${DEEPSEEK_VERSION}" \
    && npm cache clean --force \
    && groupadd --gid 10001 harnesslab \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin harnesslab

ENV DSH_HOME=/tmp/dsh-home \
    HOME=/tmp/home \
    JAVA_HOME=/opt/java/openjdk \
    PATH=/opt/java/openjdk/bin:/usr/local/bin:/usr/local/sbin:/usr/sbin:/usr/bin:/sbin:/bin \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER 10001:10001
WORKDIR /workspace
ENTRYPOINT ["dsh"]
CMD ["--version"]
