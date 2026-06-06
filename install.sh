#!/bin/sh
set -eu

TARGET=""
DRY_RUN="0"

usage() {
  cat <<'EOF'
Usage:
  install.sh [--agent <claude_code|codex|gemini_cli|hermes|opencode>] [--dry-run]

Installs uv when needed, installs the Python Mdtero runtime, then installs the matching agent
skill bundle through `mdtero agent install`. No Node package manager is
required for this path. During the alpha, the script installs the known-good
public GitHub client because the old PyPI package name is still being replaced.

Examples:
  curl -Ls https://mdtero.com/install.sh | sh
  curl -Ls https://mdtero.com/install.sh | sh -s -- --agent codex
  sh install.sh --dry-run
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
    "") return 0 ;;
    *) fail "Unsupported agent '$1'. Use claude_code, codex, gemini_cli, hermes, or opencode." ;;
  esac
}

run() {
  printf '+ %s\n' "$*"
  if [ "$DRY_RUN" = "0" ]; then
    "$@"
  fi
}

run_sh() {
  printf '+ %s\n' "$*"
  if [ "$DRY_RUN" = "0" ]; then
    sh -c "$*"
  fi
}

refresh_uv_path() {
  if [ -n "${HOME:-}" ]; then
    PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    export PATH
  fi
}

ensure_uv() {
  if command_exists uv; then
    return 0
  fi

  printf '%s\n' "uv is not installed; installing uv first."
  if command_exists curl; then
    run_sh "curl -LsSf https://astral.sh/uv/install.sh | sh"
  elif command_exists wget; then
    run_sh "wget -qO- https://astral.sh/uv/install.sh | sh"
  else
    fail "uv is required and neither curl nor wget is available. Install uv first: https://docs.astral.sh/uv/getting-started/installation/"
  fi
  refresh_uv_path
  if ! command_exists uv; then
    fail "uv was installed but is not on PATH. Open a new shell or add \$HOME/.local/bin to PATH, then rerun this installer."
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

if [ -n "$TARGET" ]; then
  printf '%s\n' "Installing Mdtero for agent: $TARGET"
else
  printf '%s\n' "Installing Mdtero CLI"
fi
ensure_uv
run uv tool install --force --reinstall git+https://github.com/JonbinC/doi2md.git
if [ -n "$TARGET" ]; then
  run mdtero agent install --target "$TARGET"
fi

cat <<'EOF'

Mdtero is installed. Next steps:
  mdtero setup
  mdtero agent install --interactive

For headless agents, create an API key in Mdtero Account and paste the dashboard install prompt into the agent.
EOF
