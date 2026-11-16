#!/usr/bin/env bash
# One-command start for Linux and macOS: sets everything up the first time, then runs Noodle.
#   ./run.sh            start (installs and builds on first run)
#   ./run.sh --update   pull the latest code, rebuild, then start
# Needs: Python 3.11-3.13 and Bun (https://bun.sh). Data is kept in ./data. Stop with Ctrl+C.
set -euo pipefail
cd "$(dirname "$0")"

PY=""
for c in python3.13 python3.12 python3.11 python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(not ((3, 11) <= sys.version_info[:2] <= (3, 13)))' 2>/dev/null; then PY="$c"; break; fi
done
[ -n "$PY" ] || { echo "Python 3.11, 3.12 or 3.13 is required. Install it from https://www.python.org/downloads/ (or your package manager) and run this again."; exit 1; }

if [ "${1:-}" = "--update" ]; then
  git pull --ff-only
  rm -rf frontend/build .venv/.deps-ok
fi

if [ ! -f frontend/build/index.html ]; then
  command -v bun >/dev/null 2>&1 || { echo "Bun is required to build the interface. Install it: curl -fsSL https://bun.sh/install | bash   then open a new terminal and run this again."; exit 1; }
  echo "Building the interface (first run, takes a minute)..."
  (cd frontend && bun install --frozen-lockfile && bun run build)
fi

if [ ! -f .venv/.deps-ok ]; then
  echo "Installing Python packages..."
  "$PY" -m venv .venv
  .venv/bin/pip install --quiet --upgrade pip
  .venv/bin/pip install --quiet -r backend/requirements.txt
  touch .venv/.deps-ok
fi

export NOODLE_DATA="${NOODLE_DATA:-$PWD/data}"
export NOODLE_STATIC="$PWD/frontend/build"
export NOODLE_EXTRA_PORT="${NOODLE_EXTRA_PORT:-0}"   # port 80 needs root; set to 80 to also serve http://this-machine
mkdir -p "$NOODLE_DATA"

echo "Noodle is starting. Open http://localhost:${NOODLE_PORT:-8090}"
cd backend
exec ../.venv/bin/python -m noodle
