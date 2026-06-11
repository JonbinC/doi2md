#!/usr/bin/env bash
set -euo pipefail

command="${1:-draft-all}"
case "$command" in
  chrome-draft|edge-draft|draft-all) ;;
  *)
    printf 'Usage: %s [chrome-draft|edge-draft|draft-all]\n' "$0" >&2
    exit 64
    ;;
esac

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
extension_dir="$(cd "$script_dir/.." && pwd)"

infisical_host="${MDTERO_INFISICAL_HOST:-gcp-sg-arm}"
infisical_project_id="${MDTERO_EXTENSION_STORE_INFISICAL_PROJECT_ID:-df34fed4-1403-4a12-bcde-dbc59caf6d1b}"
infisical_env="${MDTERO_EXTENSION_STORE_INFISICAL_ENV:-prod}"
infisical_path="${MDTERO_EXTENSION_STORE_INFISICAL_PATH:-/extension-store}"

tmp_env="$(mktemp /tmp/mdtero-extension-store.XXXXXX.env)"
cleanup() {
  rm -f "$tmp_env"
}
trap cleanup EXIT
chmod 600 "$tmp_env"

ssh "$infisical_host" \
  "sudo docker exec infisical sh -lc 'tmp=\$(mktemp); trap \"rm -f \\\"\$tmp\\\"\" EXIT; infisical export --domain=http://127.0.0.1:8080 --projectId=$infisical_project_id --env=$infisical_env --path=$infisical_path --format=dotenv --output-file=\"\$tmp\" >/dev/null; cat \"\$tmp\"'" \
  > "$tmp_env"

if ! grep -q '^EDGE_API_KEY=' "$tmp_env" || ! grep -q '^CHROME_WEBSTORE_REFRESH_TOKEN=' "$tmp_env"; then
  printf 'Infisical export did not include the expected store credentials.\n' >&2
  exit 70
fi

set -a
# shellcheck disable=SC1090
. "$tmp_env"
set +a

cd "$extension_dir"
npm test
npm run package:webstore
node scripts/store-draft.mjs "$command"
