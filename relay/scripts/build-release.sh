#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${MDTERO_RELAY_VERSION:-0.1.6}"
OUT="$ROOT/dist/v$VERSION"

mkdir -p "$OUT"

build_one() {
  local goos="$1"
  local goarch="$2"
  local archive="$3"
  local output="$OUT/mdtero-relay"
  if [[ "$goos" == "windows" ]]; then
    output="$OUT/mdtero-relay.exe"
  fi
  echo "Building $archive ..."
  GOOS="$goos" GOARCH="$goarch" go build -trimpath -ldflags "-s -w -X main.version=$VERSION" -o "$output" "$ROOT/cmd/mdtero-relay"
	if [[ "$goos" == "windows" ]]; then
		tar -C "$OUT" -czf "$OUT/$archive.tgz" mdtero-relay.exe browser_worker
	else
		tar -C "$OUT" -czf "$OUT/$archive.tgz" mdtero-relay browser_worker
  fi
  if [[ "$goos" == "windows" ]] && command -v zip >/dev/null 2>&1; then
    (cd "$OUT" && zip -q "$archive.zip" mdtero-relay.exe)
  fi
	rm -f "$output"
}

cd "$ROOT"
go mod tidy

# The worker is shipped as data beside the native binary.  Keeping the
# Python source in its own small directory lets the CLI install Playwright
# only on supported desktop machines; headless servers never unpack it.
mkdir -p "$OUT/browser_worker"
cp "$ROOT/browser_worker/mdtero_browser_worker.py" "$OUT/browser_worker/"
cp "$ROOT/browser_worker/requirements.txt" "$OUT/browser_worker/"

build_one darwin arm64 mdtero-relay-darwin-arm64
build_one darwin amd64 mdtero-relay-darwin-amd64
build_one linux arm64 mdtero-relay-linux-arm64
build_one linux amd64 mdtero-relay-linux-amd64
build_one windows amd64 mdtero-relay-windows-amd64
build_one windows arm64 mdtero-relay-windows-arm64

rm -rf "$OUT/browser_worker"

echo "Release artifacts written to $OUT"
