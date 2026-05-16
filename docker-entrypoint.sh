#!/bin/sh
set -eu

python -m backend.startup

uvicorn backend.main:app --host 127.0.0.1 --port 8000 --proxy-headers --forwarded-allow-ips="127.0.0.1" &
api_pid="$!"

nginx -g "daemon off;" &
nginx_pid="$!"

terminate() {
  kill "$api_pid" "$nginx_pid" 2>/dev/null || true
  wait "$api_pid" "$nginx_pid" 2>/dev/null || true
}

trap terminate INT TERM

while true; do
  if ! kill -0 "$api_pid" 2>/dev/null; then
    echo "FastAPI process exited unexpectedly"
    terminate
    exit 1
  fi
  if ! kill -0 "$nginx_pid" 2>/dev/null; then
    echo "nginx process exited unexpectedly"
    terminate
    exit 1
  fi
  sleep 2
done
