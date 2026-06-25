#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
RELAY_ROOT="$ROOT/relay"
VERSION="${1:-}"
SITE_ROOT="${MDTERO_SITE_ROOT:-$(cd "$ROOT/../nextmdtero" && pwd)}"

if [[ -z "$VERSION" ]]; then
  echo "Usage: publish-site-assets.sh <version>" >&2
  echo "Example: publish-site-assets.sh 0.1.0" >&2
  exit 2
fi

DIST="$RELAY_ROOT/dist/v$VERSION"
if [[ ! -d "$DIST" ]]; then
  echo "Missing release artifacts at $DIST" >&2
  echo "Run: bash relay/scripts/build-release.sh" >&2
  exit 1
fi

TARGET_RELEASES="$SITE_ROOT/public/releases/relay/v$VERSION"
mkdir -p "$TARGET_RELEASES"
cp "$DIST"/*.tgz "$TARGET_RELEASES/"

install -m 0755 "$RELAY_ROOT/scripts/install.sh" "$SITE_ROOT/public/relay"
install -m 0644 "$RELAY_ROOT/scripts/install.ps1" "$SITE_ROOT/public/relay.ps1"

MANIFEST="$SITE_ROOT/public/releases/relay/manifest.json"
cat > "$MANIFEST" <<EOF
{
  "product": "mdtero-relay",
  "latest_version": "$VERSION",
  "install_script_url": "https://mdtero.com/relay",
  "install_script_url_windows": "https://mdtero.com/relay.ps1",
  "release_base_url": "https://mdtero.com/releases/relay/v$VERSION",
  "artifacts": {
    "darwin-arm64": "https://mdtero.com/releases/relay/v$VERSION/mdtero-relay-darwin-arm64.tgz",
    "darwin-amd64": "https://mdtero.com/releases/relay/v$VERSION/mdtero-relay-darwin-amd64.tgz",
    "linux-arm64": "https://mdtero.com/releases/relay/v$VERSION/mdtero-relay-linux-arm64.tgz",
    "linux-amd64": "https://mdtero.com/releases/relay/v$VERSION/mdtero-relay-linux-amd64.tgz",
    "windows-amd64": "https://mdtero.com/releases/relay/v$VERSION/mdtero-relay-windows-amd64.tgz",
    "windows-arm64": "https://mdtero.com/releases/relay/v$VERSION/mdtero-relay-windows-arm64.tgz"
  },
  "one_line_install": {
    "macos": "curl -fsSL https://mdtero.com/relay | bash",
    "windows": "irm https://mdtero.com/relay.ps1 | iex"
  }
}
EOF

echo "Published relay v$VERSION site assets to:"
echo "  $TARGET_RELEASES"
echo "  $SITE_ROOT/public/relay"
echo "  $SITE_ROOT/public/relay.ps1"
echo "  $MANIFEST"
