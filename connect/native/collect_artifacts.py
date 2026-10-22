#!/usr/bin/env python3
"""Collect native debug payloads without publishing or claiming OS acceptance."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[2]
TARGET_FORMATS = {
    "aarch64-apple-darwin": "dmg",
    "x86_64-apple-darwin": "dmg",
    "x86_64-pc-windows-msvc": "nsis",
}
SOURCE_ROOTS = (
    "src/mdtero",
    "connect/app",
    "connect/agent",
    "connect/native",
    "relay",
    "pyproject.toml",
    "uv.lock",
    ".github/workflows/connect-native-debug.yml",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def source_provenance(repository: Path) -> tuple[str, dict[str, str], str]:
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=repository, text=True
    ).strip()
    tracked = subprocess.check_output(
        ["git", "ls-files", "-z", "--", *SOURCE_ROOTS], cwd=repository
    ).decode("utf-8").split("\0")
    checksums = {
        relative: sha256(repository / relative)
        for relative in sorted(filter(None, tracked))
        if (repository / relative).is_file() and not (repository / relative).is_symlink()
    }
    canonical = json.dumps(checksums, sort_keys=True, separators=(",", ":")).encode()
    return commit, checksums, hashlib.sha256(canonical).hexdigest()


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def validate_runtime(repository: Path, target: str, edition: str, commit: str) -> Path:
    """Reject missing/wrong build inputs before labeling an artifact full."""
    runtime = repository / "connect/native/src-tauri/resources/runtime"
    manifest_path = runtime / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise ValueError("a valid prepared runtime manifest is required") from error
    required = {
        "protocol": 1,
        "product": "mdtero-connect-debug",
        "target": target,
        "edition": edition,
        "commit": commit,
        "relay_included": True,
    }
    if not isinstance(manifest, dict) or any(manifest.get(key) != value for key, value in required.items()):
        raise ValueError("prepared runtime manifest does not match the artifact target, edition or commit")
    exe = ".exe" if "windows" in target else ""
    required_files = [runtime / "relay" / f"mdtero-relay{exe}"]
    if edition == "full":
        version = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", str(manifest.get("node_version", "")))
        if version is None or tuple(map(int, version.groups())) < (22, 19, 0) or manifest.get("pi_sdk_version") != "1.3.0":
            raise ValueError("full debug artifacts require bundled Node 22.19+ and pinned Pi 1.3.0")
        package = runtime / "agent/node_modules/@earendil-works/pi-coding-agent/package.json"
        required_files.extend([runtime / "node" / f"node{exe}", runtime / "agent/worker.mjs", package])
        try:
            if json.loads(package.read_text(encoding="utf-8")).get("version") != "1.3.0":
                raise ValueError("wrong bundled Pi SDK version")
        except (OSError, ValueError, AttributeError) as error:
            raise ValueError("the pinned Pi SDK must be present in a full debug artifact") from error
    if any(not path.is_file() or not path.resolve().is_relative_to(runtime.resolve()) for path in required_files):
        raise ValueError("prepared runtime files are missing or resolve outside the runtime directory")
    return manifest_path


def collect(
    *,
    target: str,
    source: Path,
    output: Path,
    edition: str,
    repository: Path = REPOSITORY,
) -> dict:
    if target not in TARGET_FORMATS:
        raise ValueError(f"unsupported debug artifact target: {target}")
    if edition not in {"basic", "full"}:
        raise ValueError("edition must be basic or full")
    bundle_format = TARGET_FORMATS[target]
    pattern = "dmg/*.dmg" if bundle_format == "dmg" else "nsis/*.exe"
    candidates = sorted(source.glob(pattern))
    candidates = [
        path
        for path in candidates
        if not path.is_symlink()
        and path.is_file()
    ]
    if len(candidates) != 1:
        raise ValueError(f"expected one {bundle_format} payload under {source}; found {len(candidates)}")
    if output.exists() and any(output.iterdir()):
        raise ValueError(f"output directory must be empty: {output}")
    commit, checksums, source_digest = source_provenance(repository)
    runtime_manifest = validate_runtime(repository, target, edition, commit)
    output.mkdir(parents=True, exist_ok=True)
    payload = candidates[0]
    if bundle_format == "dmg":
        payload_output = output / f"mdtero-connect-debug-{target}.dmg"
        shutil.copy2(payload, payload_output)
    else:
        payload_output = output / f"mdtero-connect-debug-{target}-setup.exe"
        shutil.copy2(payload, payload_output)

    _write_json(output / "source-checksums.json", checksums)
    for document in ("DEBUGGING.md", "support-matrix.json"):
        source_document = repository / "connect" / "native" / document
        if source_document.is_file():
            shutil.copy2(source_document, output / document)
    shutil.copy2(runtime_manifest, output / "runtime-manifest.json")

    index = {
        "schema_version": 1,
        "channel": "debug-artifacts",
        "commit": commit,
        "target": target,
        "edition": edition,
        "source_digest": source_digest,
        "source_digest_algorithm": "sha256-of-sorted-compact-source-checksums-json",
        "developer_identity_signed": False,
        "notarized": False,
        "human_acceptance": "pending",
        "payloads": [
            {
                "name": payload_output.name,
                "sha256": sha256(payload_output),
                "bytes": payload_output.stat().st_size,
            }
        ],
    }
    _write_json(output / "artifact-index.json", index)
    checksum_lines = [
        f"{sha256(path)}  {path.name}\n"
        for path in sorted(output.iterdir())
        if path.is_file() and path.name != "SHA256SUMS"
    ]
    (output / "SHA256SUMS").write_text("".join(checksum_lines), encoding="utf-8")
    return index


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=TARGET_FORMATS, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--edition", choices=("basic", "full"), default="full")
    arguments = parser.parse_args()
    source = arguments.source or REPOSITORY / "connect/native/src-tauri/target" / arguments.target / "release/bundle"
    output = arguments.output or REPOSITORY / "connect/native/dist" / arguments.target
    try:
        index = collect(target=arguments.target, source=source, output=output, edition=arguments.edition)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"native artifact collection failed: {error}\n")
    print(json.dumps(index, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
