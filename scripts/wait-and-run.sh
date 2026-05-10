#!/usr/bin/env bash
set -euo pipefail

# Host and ports (fall back to common docker-compose names)
POSTGRES_HOST=${POSTGRES_HOST:-postgres}
POSTGRES_PORT=${POSTGRES_PORT:-5432}
REDIS_HOST=${REDIS_HOST:-redis}
REDIS_PORT=${REDIS_PORT:-6379}

echo "Waiting for Postgres at ${POSTGRES_HOST}:${POSTGRES_PORT}..."
until pg_isready -h "${POSTGRES_HOST}" -p "${POSTGRES_PORT}" >/dev/null 2>&1; do
  printf "."
  sleep 1
done
echo "\nPostgres is ready"

echo "Waiting for Redis at ${REDIS_HOST}:${REDIS_PORT}..."
until (echo PING | nc -w 1 ${REDIS_HOST} ${REDIS_PORT} >/dev/null 2>&1); do
  printf "."
  sleep 1
done
echo "\nRedis is ready"

echo "Starting worker..."
exec python -m backend.evaluation.runner "$@"
