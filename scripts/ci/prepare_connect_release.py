#!/usr/bin/env python3
"""Validate and assemble Connect preview assets produced by release jobs."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path


TARGETS = {
    "macos-arm64": ("aarch64-apple-darwin", ".dmg"),
    "macos-x64": ("x86_64-apple-darwin", ".dmg"),
    "windows-x64": ("x86_64-pc-windows-msvc", "-setup.exe"),
}
METADATA_FILES = ("artifact-index.json", "runtime-manifest.json", "source-checksums.json")
TAG_PATTERN = re.compile(r"connect-v\d+\.\d+\.\d+(?:-(?:preview|beta|rc)\.\d+)?\Z")
SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
COMMIT_PATTERN = re.compile(r"[0-9a-f]{40}\Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError(f"invalid JSON metadata: {path.name}") from error
    if not isinstance(value, dict):
        raise ValueError(f"JSON metadata must be an object: {path.name}")
    return value


def _verify_checksums(directory: Path) -> None:
    checksum_file = directory / "SHA256SUMS"
    try:
        lines = checksum_file.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        raise ValueError(f"missing checksums for {directory.name}") from error

    checksums: dict[str, str] = {}
    for line in lines:
        try:
            digest, name = line.split("  ", 1)
        except ValueError as error:
            raise ValueError(f"malformed checksum line in {checksum_file}") from error
        if not SHA256_PATTERN.fullmatch(digest) or Path(name).name != name or name == "SHA256SUMS":
            raise ValueError(f"unsafe or malformed checksum entry in {checksum_file}")
        if name in checksums:
            raise ValueError(f"duplicate checksum entry: {name}")
        checksums[name] = digest

    files = {
        path.name
        for path in directory.iterdir()
        if path.is_file() and not path.is_symlink() and path.name != "SHA256SUMS"
    }
    if set(checksums) != files:
        raise ValueError(f"checksum file does not cover the exact files in {directory.name}")
    for name, expected in checksums.items():
        path = directory / name
        if path.is_symlink() or not path.is_file() or _sha256(path) != expected:
            raise ValueError(f"checksum mismatch: {directory.name}/{name}")


def prepare_release(
    *, artifacts: Path, output: Path, tag: str, commit: str
) -> dict:
    """Validate each platform artifact and make one checksummed release directory."""
    if not TAG_PATTERN.fullmatch(tag):
        raise ValueError("tag must be connect-vMAJOR.MINOR.PATCH[-preview.N|-beta.N|-rc.N]")
    if not COMMIT_PATTERN.fullmatch(commit):
        raise ValueError("expected commit must be a full lowercase Git SHA")
    if not artifacts.is_dir():
        raise ValueError("downloaded artifact directory is missing")
    if output.exists() and any(output.iterdir()):
        raise ValueError("release output directory must be empty")

    validated: list[tuple[str, Path, dict]] = []
    for artifact_id, (target, suffix) in TARGETS.items():
        directory = artifacts / f"mdtero-connect-release-{artifact_id}"
        if not directory.is_dir():
            raise ValueError(f"missing platform artifact: {artifact_id}")
        _verify_checksums(directory)
        index = _read_json(directory / "artifact-index.json")
        if (
            index.get("schema_version") != 1
            or index.get("channel") != "debug-artifacts"
            or index.get("commit") != commit
            or index.get("target") != target
            or index.get("edition") != "full"
            or index.get("developer_identity_signed") is not False
            or index.get("notarized") is not False
            or index.get("human_acceptance") != "pending"
        ):
            raise ValueError(f"artifact index does not match this full preview build: {artifact_id}")

        runtime = _read_json(directory / "runtime-manifest.json")
        if (
            runtime.get("target") != target
            or runtime.get("edition") != "full"
            or runtime.get("commit") != commit
        ):
            raise ValueError(f"runtime manifest does not match this build: {artifact_id}")

        payloads = index.get("payloads")
        expected_name = f"mdtero-connect-debug-{target}{suffix}"
        if not isinstance(payloads, list) or len(payloads) != 1:
            raise ValueError(f"expected exactly one payload in {artifact_id}")
        payload = payloads[0]
        if not isinstance(payload, dict) or payload.get("name") != expected_name:
            raise ValueError(f"unexpected payload name in {artifact_id}")
        payload_path = directory / expected_name
        if (
            payload_path.is_symlink()
            or not payload_path.is_file()
            or payload.get("sha256") != _sha256(payload_path)
            or payload.get("bytes") != payload_path.stat().st_size
        ):
            raise ValueError(f"payload metadata does not match bytes in {artifact_id}")
        for metadata in METADATA_FILES:
            if not (directory / metadata).is_file() or (directory / metadata).is_symlink():
                raise ValueError(f"missing release metadata: {artifact_id}/{metadata}")
        validated.append((artifact_id, directory, index))

    output.mkdir(parents=True, exist_ok=True)
    release_payloads: list[dict[str, str | int]] = []
    for artifact_id, directory, index in validated:
        payload_name = index["payloads"][0]["name"]
        shutil.copy2(directory / payload_name, output / payload_name)
        release_payloads.append({
            "target": index["target"],
            "name": payload_name,
            "sha256": index["payloads"][0]["sha256"],
            "bytes": index["payloads"][0]["bytes"],
        })
        for metadata in METADATA_FILES:
            path = directory / metadata
            shutil.copy2(path, output / f"{path.stem}-{artifact_id}{path.suffix}")

    manifest = {
        "schema_version": 1,
        "channel": "debug-preview",
        "release_tag": tag,
        "source_commit": commit,
        "developer_identity_signed": False,
        "notarized": False,
        "human_acceptance": "pending",
        "payloads": release_payloads,
    }
    (output / "release-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    checksum_lines = [
        f"{_sha256(path)}  {path.name}\n"
        for path in sorted(output.iterdir())
        if path.is_file() and path.name != "SHA256SUMS"
    ]
    (output / "SHA256SUMS").write_text("".join(checksum_lines), encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    args = parser.parse_args()
    try:
        result = prepare_release(artifacts=args.artifacts, output=args.output, tag=args.tag, commit=args.commit)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Connect release preparation failed: {error}\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
