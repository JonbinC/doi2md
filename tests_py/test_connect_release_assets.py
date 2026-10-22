"""Connect release assembly must match the tagged full-build artifacts."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/ci/prepare_connect_release.py"
SPEC = importlib.util.spec_from_file_location("connect_release_assets", SCRIPT)
assert SPEC and SPEC.loader
release_assets = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release_assets)


COMMIT = "a" * 40
BUILDS = {
    "macos-arm64": ("aarch64-apple-darwin", ".dmg"),
    "macos-x64": ("x86_64-apple-darwin", ".dmg"),
    "windows-x64": ("x86_64-pc-windows-msvc", "-setup.exe"),
}


def _write_artifact(root: Path, artifact_id: str, *, commit: str = COMMIT) -> Path:
    target, suffix = BUILDS[artifact_id]
    directory = root / f"mdtero-connect-release-{artifact_id}"
    directory.mkdir(parents=True)
    payload_name = f"mdtero-connect-debug-{target}{suffix}"
    payload_bytes = f"synthetic {artifact_id} payload".encode()
    (directory / payload_name).write_bytes(payload_bytes)
    (directory / "runtime-manifest.json").write_text(json.dumps({
        "protocol": 1,
        "product": "mdtero-connect-debug",
        "target": target,
        "edition": "full",
        "commit": commit,
        "relay_included": True,
        "node_version": "22.19.0",
        "pi_sdk_version": "1.3.0",
    }))
    (directory / "source-checksums.json").write_text(json.dumps({"README.md": "b" * 64}))
    (directory / "artifact-index.json").write_text(json.dumps({
        "schema_version": 1,
        "channel": "debug-artifacts",
        "commit": commit,
        "target": target,
        "edition": "full",
        "developer_identity_signed": False,
        "notarized": False,
        "human_acceptance": "pending",
        "payloads": [{
            "name": payload_name,
            "sha256": hashlib.sha256(payload_bytes).hexdigest(),
            "bytes": len(payload_bytes),
        }],
    }))
    for name, contents in (("DEBUGGING.md", b"preview docs"), ("support-matrix.json", b"{}\n")):
        (directory / name).write_bytes(contents)
    lines = [
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n"
        for path in sorted(directory.iterdir())
    ]
    (directory / "SHA256SUMS").write_text("".join(lines))
    return directory


def _all_artifacts(root: Path, *, mismatch: str | None = None) -> None:
    root.mkdir()
    for artifact_id in BUILDS:
        commit = "f" * 40 if mismatch == artifact_id else COMMIT
        _write_artifact(root, artifact_id, commit=commit)


def test_release_assets_validate_all_targets_and_build_one_checksum_manifest(tmp_path):
    artifacts = tmp_path / "artifacts"
    _all_artifacts(artifacts)
    output = tmp_path / "release"

    result = release_assets.prepare_release(
        artifacts=artifacts,
        output=output,
        tag="connect-v0.1.1-preview.1",
        commit=COMMIT,
    )

    assert result["release_tag"] == "connect-v0.1.1-preview.1"
    assert result["source_commit"] == COMMIT
    assert result["human_acceptance"] == "pending"
    assert len(result["payloads"]) == 3
    assert (output / "mdtero-connect-debug-aarch64-apple-darwin.dmg").is_file()
    assert (output / "mdtero-connect-debug-x86_64-apple-darwin.dmg").is_file()
    assert (output / "mdtero-connect-debug-x86_64-pc-windows-msvc-setup.exe").is_file()
    assert (output / "artifact-index-windows-x64.json").is_file()
    for line in (output / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ", 1)
        assert digest == hashlib.sha256((output / name).read_bytes()).hexdigest()


def test_release_assets_reject_a_build_from_another_commit(tmp_path):
    artifacts = tmp_path / "artifacts"
    _all_artifacts(artifacts, mismatch="macos-x64")

    with pytest.raises(ValueError, match="artifact index does not match"):
        release_assets.prepare_release(
            artifacts=artifacts,
            output=tmp_path / "release",
            tag="connect-v0.1.1-preview.1",
            commit=COMMIT,
        )


def test_release_assets_reject_tampered_platform_payload(tmp_path):
    artifacts = tmp_path / "artifacts"
    _all_artifacts(artifacts)
    payload = artifacts / "mdtero-connect-release-macos-arm64" / "mdtero-connect-debug-aarch64-apple-darwin.dmg"
    payload.write_bytes(b"changed after upload")

    with pytest.raises(ValueError, match="checksum mismatch"):
        release_assets.prepare_release(
            artifacts=artifacts,
            output=tmp_path / "release",
            tag="connect-v0.1.1-preview.1",
            commit=COMMIT,
        )


@pytest.mark.parametrize("tag", ["v0.1.1", "connect-v1", "connect-v0.1.1-preview"])
def test_release_assets_reject_non_connect_or_incomplete_tags(tmp_path, tag):
    artifacts = tmp_path / "artifacts"
    _all_artifacts(artifacts)
    with pytest.raises(ValueError, match="tag must be"):
        release_assets.prepare_release(
            artifacts=artifacts,
            output=tmp_path / "release",
            tag=tag,
            commit=COMMIT,
        )
