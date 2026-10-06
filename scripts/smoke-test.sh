#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
#
# Smoke test from docs/getting-started.md (section 9): run the direct-mode
# example pair and check that the client associates and gets a directory
# response. Run from the repository root after `uv sync`:
#
#   scripts/smoke-test.sh
#
# CI runs it too (job `smoke` in .github/workflows/ci.yml), so the documented
# first-run commands can't break unnoticed.
set -euo pipefail

EXAMPLE_DIR="examples/ws61850_mode/direct"
CLIENT_SECONDS="${CLIENT_SECONDS:-10}"
LOG_DIR="$(mktemp -d)"
# Unbuffered, so the logs are complete even though both sides get killed.
export PYTHONUNBUFFERED=1
SERVER_PID=""

cleanup() {
  if [ -n "${SERVER_PID}" ]; then
    kill "${SERVER_PID}" 2>/dev/null || true
    wait "${SERVER_PID}" 2>/dev/null || true
  fi
  rm -rf "${LOG_DIR}"
}
trap cleanup EXIT

if (exec 3<>/dev/tcp/127.0.0.1/8765) 2>/dev/null; then
  echo "smoke test: port 8765 is already in use (an rti-so container, or another example?); stop it first" >&2
  exit 1
fi

uv run python "${EXAMPLE_DIR}/ws_server.py" >"${LOG_DIR}/server.log" 2>&1 &
SERVER_PID=$!

# Wait for the server to listen on 8765 (or die trying). The probe shows up as
# one "opening handshake failed" in the server log; that is expected.
for _ in $(seq 1 30); do
  if ! kill -0 "${SERVER_PID}" 2>/dev/null; then
    echo "smoke test: the server exited early:" >&2
    cat "${LOG_DIR}/server.log" >&2
    exit 1
  fi
  if (exec 3<>/dev/tcp/127.0.0.1/8765) 2>/dev/null; then
    break
  fi
  sleep 1
done

# The client keeps running; give it a few seconds, then stop it.
timeout "${CLIENT_SECONDS}" uv run python "${EXAMPLE_DIR}/ws_client.py" >"${LOG_DIR}/client.log" 2>&1 || true

failed=0
check() {
  if grep -q "$2" "${LOG_DIR}/client.log"; then
    echo "ok   $1"
  else
    echo "FAIL $1" >&2
    failed=1
  fi
}
check "association accepted" '"associateResponse"'
check "server directory returned" '"getServerDirectory":{"result"'

if [ "${failed}" -ne 0 ]; then
  echo "--- client log" >&2; cat "${LOG_DIR}/client.log" >&2
  echo "--- server log" >&2; cat "${LOG_DIR}/server.log" >&2
  exit 1
fi
echo "smoke test passed"
