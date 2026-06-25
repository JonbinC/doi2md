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

infisical_host="${MDTERO_INFISICAL_HOST:-jumbo-sg-arm}"
infisical_domain="${INFISICAL_DOMAIN:-http://127.0.0.1:8080}"
infisical_project_id="${MDTERO_EXTENSION_STORE_INFISICAL_PROJECT_ID:-df34fed4-1403-4a12-bcde-dbc59caf6d1b}"
infisical_env="${MDTERO_EXTENSION_STORE_INFISICAL_ENV:-prod}"
infisical_path="${MDTERO_EXTENSION_STORE_INFISICAL_PATH:-/extension-store}"
infisical_token_file="${INFISICAL_TOKEN_FILE:-/home/ubuntu/infisical/.admin_jwt}"

tmp_env="$(mktemp /tmp/mdtero-extension-store.XXXXXX.env)"
cleanup() {
  rm -f "$tmp_env"
}
trap cleanup EXIT
chmod 600 "$tmp_env"

resolve_infisical_token() {
  if [[ -n "${INFISICAL_TOKEN:-}" ]]; then
    printf '%s' "$INFISICAL_TOKEN"
    return 0
  fi
  if [[ -f "$infisical_token_file" ]]; then
    tr -d '\n' <"$infisical_token_file"
    return 0
  fi
  return 1
}

export_infisical_store_env() {
  local token="${1:-}"
  local docker_env=()
  if [[ -n "$token" ]]; then
    docker_env=(-e "INFISICAL_TOKEN=$token")
  fi

  sudo docker exec "${docker_env[@]}" infisical bash -lc "
    tmp=\$(mktemp)
    trap 'rm -f \"\$tmp\"' EXIT
    if [[ -n \"\${INFISICAL_TOKEN:-}\" ]]; then
      infisical export \
        --token=\"\$INFISICAL_TOKEN\" \
        --domain=$infisical_domain \
        --projectId=$infisical_project_id \
        --env=$infisical_env \
        --path=$infisical_path \
        --format=dotenv \
        --silent \
        --output-file=\"\$tmp\"
    else
      infisical export \
        --domain=$infisical_domain \
        --projectId=$infisical_project_id \
        --env=$infisical_env \
        --path=$infisical_path \
        --format=dotenv \
        --silent \
        --output-file=\"\$tmp\"
    fi >/dev/null
    cat \"\$tmp\"
  "
}

token=""
if ! token="$(resolve_infisical_token)"; then
  printf 'Missing Infisical token. Set INFISICAL_TOKEN or refresh %s on %s.\n' \
    "$infisical_token_file" "$infisical_host" >&2
fi

current_host="$(hostname -s 2>/dev/null || hostname)"
if [[ "$current_host" == "$infisical_host" || "$current_host" == "jumbo-sg-arm" || "$current_host" == "gcp-sg-arm" ]]; then
  export_infisical_store_env "$token" >"$tmp_env"
else
  ssh "$infisical_host" bash -s -- "$token" "$infisical_domain" "$infisical_project_id" "$infisical_env" "$infisical_path" <<'REMOTE'
set -euo pipefail
token="$1"
domain="$2"
project_id="$3"
env_name="$4"
secret_path="$5"
docker_env=()
if [[ -n "$token" ]]; then
  docker_env=(-e "INFISICAL_TOKEN=$token")
fi
sudo docker exec "${docker_env[@]}" infisical bash -lc "
  tmp=\$(mktemp)
  trap 'rm -f \"\$tmp\"' EXIT
  if [[ -n \"\${INFISICAL_TOKEN:-}\" ]]; then
    infisical export \
      --token=\"\$INFISICAL_TOKEN\" \
      --domain=$domain \
      --projectId=$project_id \
      --env=$env_name \
      --path=$secret_path \
      --format=dotenv \
      --silent \
      --output-file=\"\$tmp\"
  else
    infisical export \
      --domain=$domain \
      --projectId=$project_id \
      --env=$env_name \
      --path=$secret_path \
      --format=dotenv \
      --silent \
      --output-file=\"\$tmp\"
  fi >/dev/null
  cat \"\$tmp\"
"
REMOTE
  >"$tmp_env"
fi

if ! grep -q '^EDGE_API_KEY=' "$tmp_env" || ! grep -q '^CHROME_WEBSTORE_REFRESH_TOKEN=' "$tmp_env"; then
  printf 'Infisical export did not include the expected store credentials.\n' >&2
  printf 'Infisical runs on %s (%s), not on jumbo-pi. Refresh %s if the admin token expired.\n' \
    "$infisical_host" "$infisical_domain" "$infisical_token_file" >&2
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
