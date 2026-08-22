FROM python:3.12.14-slim-bookworm@sha256:a116514e19457bcb7af7efe9c3dd0b9b71e85b317694e7882a1c52aa15a78134

RUN groupadd --gid 10001 harnesslab \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin harnesslab

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

USER 10001:10001
WORKDIR /workspace
ENTRYPOINT ["python"]
