#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION="${MDTERO_RELAY_VERSION:-0.1.0}"
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
  GOOS="$goos" GOARCH="$goarch" go build -trimpath -ldflags "-s -w" -o "$output" "$ROOT/cmd/mdtero-relay"
  if [[ "$goos" == "windows" ]]; then
    tar -C "$OUT" -czf "$OUT/$archive.tgz" mdtero-relay.exe
  else
    tar -C "$OUT" -czf "$OUT/$archive.tgz" mdtero-relay
  fi
  if [[ "$goos" == "windows" ]] && command -v zip >/dev/null 2>&1; then
    (cd "$OUT" && zip -q "$archive.zip" mdtero-relay.exe)
  fi
  rm -f "$output"
}

cd "$ROOT"
go mod tidy

build_one darwin arm64 mdtero-relay-darwin-arm64
build_one darwin amd64 mdtero-relay-darwin-amd64
build_one linux arm64 mdtero-relay-linux-arm64
build_one linux amd64 mdtero-relay-linux-amd64
build_one windows amd64 mdtero-relay-windows-amd64
build_one windows arm64 mdtero-relay-windows-arm64

echo "Release artifacts written to $OUT"
