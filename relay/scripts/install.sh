#!/usr/bin/env bash
set -euo pipefail

MDTERO_RELAY_VERSION="${MDTERO_RELAY_VERSION:-0.1.0}"
MDTERO_RELAY_BASE_URL="${MDTERO_RELAY_BASE_URL:-https://mdtero.com/releases/relay}"
INSTALL_DIR="${MDTERO_RELAY_INSTALL_DIR:-${HOME}/.local/bin}"

usage() {
  cat <<EOF
Mdtero campus relay installer

Usage:
  curl -fsSL https://mdtero.com/relay | bash
  curl -fsSL https://mdtero.com/relay | bash -s -- --api-key <key>

Options:
  --api-key <key>   Save your Mdtero API key during install
  --label <name>    Optional relay label
  --dir <path>      Install directory (default: ~/.local/bin)
EOF
}

API_KEY=""
LABEL=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --api-key)
      API_KEY="${2:-}"
      shift 2
      ;;
    --label)
      LABEL="${2:-}"
      shift 2
      ;;
    --dir)
      INSTALL_DIR="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 2
      ;;
  esac
done

OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"
case "$ARCH" in
  x86_64|amd64) ARCH="amd64" ;;
  arm64|aarch64) ARCH="arm64" ;;
  *)
    echo "Unsupported architecture: $ARCH" >&2
    exit 1
    ;;
esac

case "$OS" in
  darwin) PLATFORM="darwin" ;;
  linux) PLATFORM="linux" ;;
  *)
    echo "Unsupported OS: $OS" >&2
    echo "For Windows, run: irm https://mdtero.com/relay.ps1 | iex" >&2
    exit 1
    ;;
esac

mkdir -p "$INSTALL_DIR"
TARGET="$INSTALL_DIR/mdtero-relay"
ARCHIVE="$TARGET.tgz"
URL="$MDTERO_RELAY_BASE_URL/v$MDTERO_RELAY_VERSION/mdtero-relay-$PLATFORM-$ARCH.tgz"

echo "Installing mdtero-relay $MDTERO_RELAY_VERSION for $PLATFORM/$ARCH ..."
if command -v curl >/dev/null 2>&1; then
  curl -fsSL "$URL" -o "$ARCHIVE"
else
  wget -qO "$ARCHIVE" "$URL"
fi

TMP_DIR="$(mktemp -d)"
tar -xzf "$ARCHIVE" -C "$TMP_DIR"
install -m 0755 "$TMP_DIR/mdtero-relay" "$TARGET"
rm -rf "$TMP_DIR" "$ARCHIVE"

case ":$PATH:" in
  *":$INSTALL_DIR:"*) ;;
  *)
    SHELL_RC="${HOME}/.zshrc"
    if [[ "${SHELL:-}" == *"bash"* ]]; then
      SHELL_RC="${HOME}/.bashrc"
    fi
    echo "export PATH=\"$INSTALL_DIR:\$PATH\"" >> "$SHELL_RC"
    export PATH="$INSTALL_DIR:$PATH"
    echo "Added $INSTALL_DIR to PATH in $SHELL_RC"
    ;;
esac

INSTALL_ARGS=()
if [[ -n "$API_KEY" ]]; then
  INSTALL_ARGS+=(--api-key "$API_KEY")
fi
if [[ -n "$LABEL" ]]; then
  INSTALL_ARGS+=(--label "$LABEL")
fi

echo "Setting up background service ..."
"$TARGET" install "${INSTALL_ARGS[@]}"

echo
echo "Done. Campus relay is installed."
echo "Check status: mdtero-relay status"
echo "Logs (macOS): ~/Library/Logs/mdtero-relay.log"
