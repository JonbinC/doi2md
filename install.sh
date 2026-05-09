#!/bin/sh
set -eu

TARGET=""
DRY_RUN="0"
UV_INSTALL_URL="https://astral.sh/uv/install.sh"

usage() {
  cat <<'EOF'
Usage:
  install.sh --agent <claude_code|codex|gemini_cli|hermes|opencode> [--dry-run]

Installs the Mdtero Python CLI with uv, then asks the CLI to install the
matching agent skill bundle.

Examples:
  curl -Ls https://mdtero.com/install.sh | sh -s -- --agent codex
  sh install.sh --agent claude_code --dry-run
EOF
}

fail() {
  printf '%s\n' "Error: $*" >&2
  exit 1
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

validate_target() {
  case "$1" in
    claude_code|codex|gemini_cli|hermes|opencode) return 0 ;;
    openclaw) fail "OpenClaw uses the dedicated ClawHub route: clawhub install mdtero" ;;
    "") fail "Missing --agent. Run with --agent codex, claude_code, gemini_cli, hermes, or opencode." ;;
    *) fail "Unsupported agent '$1'. Use claude_code, codex, gemini_cli, hermes, or opencode." ;;
  esac
}

run() {
  printf '+ %s\n' "$*"
  if [ "$DRY_RUN" = "0" ]; then
    "$@"
  fi
}

ensure_uv() {
  if command_exists uv; then
    return 0
  fi

  if ! command_exists curl; then
    fail "uv is not installed and curl is unavailable. Install uv first: https://docs.astral.sh/uv/getting-started/installation/"
  fi

  printf '%s\n' "uv was not found. Installing uv from $UV_INSTALL_URL ..."
  run sh -c "curl -LsSf '$UV_INSTALL_URL' | sh"
  export PATH="$HOME/.local/bin:$PATH"

  if [ "$DRY_RUN" = "0" ] && ! command_exists uv; then
    fail "uv installation finished, but uv is still not on PATH. Add $HOME/.local/bin to PATH and rerun this installer."
  fi
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --agent)
      [ "$#" -ge 2 ] || fail "--agent requires a value"
      TARGET="$2"
      shift 2
      ;;
    --agent=*)
      TARGET="${1#--agent=}"
      shift
      ;;
    --dry-run)
      DRY_RUN="1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      fail "Unknown argument: $1"
      ;;
  esac
done

validate_target "$TARGET"

printf '%s\n' "Installing Mdtero for agent: $TARGET"
ensure_uv
run uv tool install mdtero
export PATH="$HOME/.local/bin:$PATH"
run mdtero setup --agent "$TARGET"

cat <<'EOF'

Mdtero is installed. Next steps:
  mdtero login
  mdtero doctor

For headless agents, create an API key in Mdtero Account and paste the dashboard install prompt into the agent.
EOF
