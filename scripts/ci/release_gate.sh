#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/../.."

python3 scripts/ci/secret_guard.py
uv run pytest tests_py -q
python3 -m compileall -q src/mdtero

(
  cd extension
  if [[ ! -x node_modules/.bin/vitest || package-lock.json -nt node_modules/.package-lock.json ]]; then
    npm ci
  fi
  npm audit --audit-level=moderate
  npm test -- --run
  npm run build
)

python3 scripts/ci/extension_dist_smoke.py

git diff --check
