#!/usr/bin/env bash
# Builds the web interface and a pip-installable wheel of the hub (with the interface inside it).
# Needs: bun, python3 with the `build` package (pip install build); set PYTHON=... to use another interpreter.  Result: backend/dist/noodle_home-*.whl
#   pip install backend/dist/noodle_home-*.whl   then run:  noodle
set -euo pipefail
cd "$(dirname "$0")"

(cd frontend && bun install --frozen-lockfile && bun run build)

rm -rf backend/noodle/static backend/build backend/dist
cp -r frontend/build backend/noodle/static

(cd backend && "${PYTHON:-python3}" -m build --wheel)
rm -rf backend/noodle/static backend/build   # keep the source tree clean

ls -1 backend/dist
