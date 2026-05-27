#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

remote_name="${MDTERO_FORGEJO_REMOTE:-forgejo}"
if ! git remote get-url "$remote_name" >/dev/null 2>&1; then
  origin_url="$(git remote get-url origin 2>/dev/null || true)"
  case "$origin_url" in
    http://100.97.234.105:3020/*)
      remote_name="origin"
      ;;
    *)
      printf 'public_private_platform_preflight: Forgejo remote %s is not configured and origin is not the private Forgejo remote.\n' "$remote_name" >&2
      exit 65
      ;;
  esac
fi

scripts/ci/forgejo-remote-doctor.sh "$remote_name"

if [[ -x "$repo_root/.venv/bin/python" ]]; then
  python_bin="$repo_root/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  python_bin="python3"
elif command -v python >/dev/null 2>&1; then
  python_bin="python"
else
  printf 'public_private_platform_preflight: python runtime not found.\n' >&2
  exit 69
fi

"$python_bin" scripts/ci/secret_guard.py
"$python_bin" scripts/ci/forgejo_workflow_policy.py
npm --prefix extension test -- --run
"$python_bin" scripts/ci/extension_dist_smoke.py >/dev/null

printf 'public_private_platform_preflight: status=ok remote=%s forgejo_policy=ok extension_tests=ok extension_dist=ok\n' "$remote_name"
