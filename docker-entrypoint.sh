#!/bin/sh
set -eu

python -m backend.init_db

uvicorn backend.main:app --host 127.0.0.1 --port 8000 &
api_pid="$!"

nginx -g "daemon off;" &
nginx_pid="$!"

terminate() {
  kill "$api_pid" "$nginx_pid" 2>/dev/null || true
  wait "$api_pid" "$nginx_pid" 2>/dev/null || true
}

trap terminate INT TERM

while kill -0 "$api_pid" 2>/dev/null && kill -0 "$nginx_pid" 2>/dev/null; do
  sleep 2
done

terminate
