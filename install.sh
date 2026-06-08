#!/bin/sh
set -eu

TARGET=""
DRY_RUN="0"

usage() {
  cat <<'EOF'
Usage:
  install.sh [--agent <claude_code|codex|gemini_cli|hermes|opencode>] [--dry-run]

Installs the Python Mdtero runtime, then installs the matching agent skill
bundle through `mdtero agent install`. During the alpha, the script installs
the known-good public GitHub client because the old PyPI package name is still
being replaced. It prefers uv, then pipx, then Python's user-site pip fallback.

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

python_cmd() {
  if command_exists python3; then
    printf '%s\n' python3
  elif command_exists python; then
    printf '%s\n' python
  else
    fail "Python 3 is required. Install Python 3.10+ first, then rerun this installer."
  fi
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

refresh_user_path() {
  if [ -n "${HOME:-}" ]; then
    PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
    export PATH
  fi
}

try_install_uv() {
  if command_exists uv; then
    return 0
  fi

  if ! command_exists curl && ! command_exists wget; then
    return 1
  fi

  printf '%s\n' "uv is not installed; trying to install uv first."
  if command_exists curl; then
    run_sh "curl -LsSf https://astral.sh/uv/install.sh | sh"
  else
    run_sh "wget -qO- https://astral.sh/uv/install.sh | sh"
  fi
  refresh_user_path
  command_exists uv
}

install_mdtero_runtime() {
  GITHUB_SPEC="git+https://github.com/JonbinC/doi2md.git"
  if command_exists uv || try_install_uv; then
    run uv tool install --force --reinstall "$GITHUB_SPEC"
  elif command_exists pipx; then
    run pipx install --force "$GITHUB_SPEC"
  else
    PYTHON="$(python_cmd)"
    printf '%s\n' "uv and pipx are unavailable; falling back to Python user-site install."
    run "$PYTHON" -m pip install --user --force-reinstall "$GITHUB_SPEC"
    refresh_user_path
  fi

  if ! command_exists mdtero; then
    fail "mdtero was installed but is not on PATH. Add \$HOME/.local/bin to PATH or open a new shell, then rerun mdtero setup."
  fi
  run mdtero --version
  if mdtero doctor --json >/dev/null 2>&1; then
    printf '%s\n' "mdtero doctor completed."
  else
    printf '%s\n' "mdtero is installed; run mdtero setup, then mdtero doctor --json."
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
refresh_user_path
install_mdtero_runtime
if [ -n "$TARGET" ]; then
  run mdtero agent install --target "$TARGET"
fi

cat <<'EOF'

Mdtero is installed. Next steps:
  mdtero setup
  mdtero agent install --interactive

For headless agents, create an API key in Mdtero Account and paste the dashboard install prompt into the agent.
EOF
