#!/usr/bin/env bash
set -euo pipefail

readonly POSTGRES_IMAGE="postgres:18.6@sha256:4ef4dbc939d61acea57712655ddb4b4ab27419c913f94cca0cd57cb3ea3c2280"
readonly POSTGRES_USER="harnesslab"
readonly POSTGRES_PASSWORD="harnesslab_ci_only"
readonly POSTGRES_DATABASE="harnesslab"
readonly LABEL_PREFIX="io.harnesslab.ci"

require_ci_identity() {
  : "${GITHUB_REPOSITORY:?GITHUB_REPOSITORY is required}"
  : "${GITHUB_RUN_ID:?GITHUB_RUN_ID is required}"
  : "${GITHUB_RUN_ATTEMPT:?GITHUB_RUN_ATTEMPT is required}"
  : "${GITHUB_JOB:?GITHUB_JOB is required}"
  : "${RUNNER_NAME:?RUNNER_NAME is required}"
}

slug() {
  printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | tr -cs 'a-z0-9_.-' '-'
}

container_name() {
  printf 'hl-ci-pg-%s-%s-%s-%s' \
    "$(slug "$GITHUB_RUN_ID")" \
    "$(slug "$GITHUB_RUN_ATTEMPT")" \
    "$(slug "$GITHUB_JOB")" \
    "$(slug "$RUNNER_NAME")"
}

cleanup_current() {
  require_ci_identity
  local name
  name="$(container_name)"
  docker rm --force "$name" >/dev/null 2>&1 || true
}

cleanup_stale_for_runner() {
  require_ci_identity
  local container_id
  while IFS= read -r container_id; do
    [ -n "$container_id" ] || continue
    docker rm --force "$container_id" >/dev/null
  done < <(
    docker ps --all --quiet \
      --filter "label=${LABEL_PREFIX}.repository=${GITHUB_REPOSITORY}" \
      --filter "label=${LABEL_PREFIX}.runner=${RUNNER_NAME}"
  )
}

start() {
  require_ci_identity
  : "${GITHUB_ENV:?GITHUB_ENV is required}"

  cleanup_current
  local name
  name="$(container_name)"
  docker run --detach \
    --name "$name" \
    --label "${LABEL_PREFIX}.owned=true" \
    --label "${LABEL_PREFIX}.repository=${GITHUB_REPOSITORY}" \
    --label "${LABEL_PREFIX}.run-id=${GITHUB_RUN_ID}" \
    --label "${LABEL_PREFIX}.run-attempt=${GITHUB_RUN_ATTEMPT}" \
    --label "${LABEL_PREFIX}.job=${GITHUB_JOB}" \
    --label "${LABEL_PREFIX}.runner=${RUNNER_NAME}" \
    --env "POSTGRES_DB=${POSTGRES_DATABASE}" \
    --env "POSTGRES_USER=${POSTGRES_USER}" \
    --env "POSTGRES_PASSWORD=${POSTGRES_PASSWORD}" \
    --health-cmd "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DATABASE}" \
    --health-interval 2s \
    --health-timeout 3s \
    --health-retries 20 \
    --publish 127.0.0.1::5432 \
    "$POSTGRES_IMAGE" >/dev/null

  local health
  for _ in $(seq 1 40); do
    health="$(docker inspect --format '{{.State.Health.Status}}' "$name")"
    if [ "$health" = "healthy" ]; then
      break
    fi
    if [ "$health" = "unhealthy" ]; then
      docker logs "$name" >&2
      return 1
    fi
    sleep 2
  done
  if [ "${health:-missing}" != "healthy" ]; then
    docker logs "$name" >&2
    return 1
  fi

  local port
  port="$(docker inspect --format '{{(index (index .NetworkSettings.Ports "5432/tcp") 0).HostPort}}' "$name")"
  if [[ ! "$port" =~ ^[0-9]+$ ]]; then
    echo "Unable to resolve the job-owned PostgreSQL port" >&2
    return 1
  fi
  printf 'DATABASE_URL=postgresql+psycopg://%s:%s@127.0.0.1:%s/%s\n' \
    "$POSTGRES_USER" "$POSTGRES_PASSWORD" "$port" "$POSTGRES_DATABASE" >>"$GITHUB_ENV"
  printf 'HARNESSLAB_CI_POSTGRES_CONTAINER=%s\n' "$name" >>"$GITHUB_ENV"
  printf 'POSTGRES_ISOLATION=dynamic-localhost-port container=%s\n' "$name"
}

case "${1:-}" in
  start)
    start
    ;;
  cleanup-current)
    cleanup_current
    ;;
  cleanup-stale)
    cleanup_stale_for_runner
    ;;
  *)
    echo "usage: $0 {start|cleanup-current|cleanup-stale}" >&2
    exit 2
    ;;
esac
