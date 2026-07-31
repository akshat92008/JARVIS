#!/bin/zsh
set -euo pipefail
cd "${0:A:h}"

if [[ ! -x .venv/bin/python ]]; then
  print -u2 "Amaura is not installed. Run ./Install_Amaura.command first."
  exit 1
fi
if [[ ! -f .env.amaura ]]; then
  print -u2 "Amaura is not initialised. Run: .venv/bin/python -m jarvis.amaura.cli init"
  exit 1
fi

chmod 600 .env.amaura
source .venv/bin/activate
python -m jarvis.amaura.cli doctor

mkdir -p .amaura-data/logs
SERVER_LOG=".amaura-data/logs/server.log"
python -m jarvis.server >>"$SERVER_LOG" 2>&1 &
SERVER_PID=$!

cleanup() {
  if kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

HOST=$(python -c 'from jarvis.amaura.runtime import load_amaura_env; load_amaura_env(require_private_permissions=True); import os; print(os.environ.get("JARVIS_HOST", "127.0.0.1"))')
PORT=$(python -c 'from jarvis.amaura.runtime import load_amaura_env; load_amaura_env(require_private_permissions=True); import os; print(os.environ.get("JARVIS_PORT", "8000"))')
HEALTH_URL="http://${HOST}:${PORT}/api/health"
for _ in {1..40}; do
  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    print "Amaura control surface: http://${HOST}:${PORT}"
    print "Server log: $SERVER_LOG"
    python -m jarvis.amaura.cli worker
    exit $?
  fi
  if ! kill -0 "$SERVER_PID" 2>/dev/null; then
    print -u2 "Amaura server failed to start. Last log lines:"
    tail -40 "$SERVER_LOG" >&2 || true
    exit 1
  fi
  sleep 0.25
done

print -u2 "Amaura server did not become healthy at $HEALTH_URL"
tail -40 "$SERVER_LOG" >&2 || true
exit 1
