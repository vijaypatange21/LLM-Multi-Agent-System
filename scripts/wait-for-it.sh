#!/usr/bin/env bash
# Simple wait-for-it style script used by container entrypoints if needed.
set -e

host="$1"
port="$2"
shift 2 || true
cmd="$@"

if [ -z "$host" ] || [ -z "$port" ]; then
  echo "Usage: $0 host port [-- command args]"
  exit 2
fi

echo "Waiting for $host:$port..."
while ! (echo > /dev/tcp/${host}/${port}) >/dev/null 2>&1; do
  printf "."
  sleep 1
done

echo "\n$host:$port is available"
if [ -n "$cmd" ]; then
  exec $cmd
fi
