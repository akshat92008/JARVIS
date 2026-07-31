#!/bin/zsh
set -euo pipefail
cd "${0:A:h}"

PYTHON_BIN="${PYTHON_BIN:-python3}"
if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  print -u2 "Python 3.11+ is required. Install it, then rerun this file."
  exit 1
fi

"$PYTHON_BIN" - <<'PY'
import sys
if sys.version_info < (3, 11):
    raise SystemExit(f"Python 3.11+ is required; found {sys.version.split()[0]}")
PY

"$PYTHON_BIN" -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e '.[dev]'

if [[ ! -f .env.amaura ]]; then
  python -m jarvis.amaura.cli init
else
  chmod 600 .env.amaura
  print "Existing .env.amaura preserved."
fi

./scripts/verify_amaura.sh
./Setup_Amaura_Runtime.command

print "\nAmaura installation and live certification completed."
print "Start with: ./Launch_Amaura.command"
