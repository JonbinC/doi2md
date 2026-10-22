"""Debug artifact collection must verify payloads and tie them to source."""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "connect/native/collect_artifacts.py"
SPEC = importlib.util.spec_from_file_location("connect_native_collect", SCRIPT)
assert SPEC and SPEC.loader
collector = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(collector)


@pytest.fixture
def provenance(monkeypatch):
    checksums = {"connect/native/src-tauri/src/main.rs": "c" * 64}
    monkeypatch.setattr(collector, "source_provenance", lambda repository: ("a" * 40, checksums, "b" * 64))
    return checksums


def _prepared_runtime(repository, target, edition="full"):
    runtime = repository / "connect/native/src-tauri/resources/runtime"
    exe = ".exe" if "windows" in target else ""
    files = [runtime / "relay" / f"mdtero-relay{exe}"]
    if edition == "full":
        files.extend([runtime / "node" / f"node{exe}", runtime / "agent/worker.mjs"])
        package = runtime / "agent/node_modules/@earendil-works/pi-coding-agent/package.json"
        package.parent.mkdir(parents=True)
        package.write_text(json.dumps({"version": "1.3.0"}))
    for path in files:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"synthetic runtime asset")
    manifest = {
        "protocol": 1, "product": "mdtero-connect-desktop", "target": target,
        "edition": edition, "commit": "a" * 40, "relay_included": True,
        "node_version": "22.19.0" if edition == "full" else None,
        "pi_sdk_version": "1.3.0" if edition == "full" else None,
    }
    (runtime / "manifest.json").write_text(json.dumps(manifest))
    return runtime


def test_mac_dmg_is_collected_and_records_payload(tmp_path, provenance):
    bundle = tmp_path / "bundle"
    dmg = bundle / "dmg/Mdtero Connect_0.1.0_aarch64.dmg"
    dmg.parent.mkdir(parents=True)
    dmg.write_bytes(b"UDIF debug disk image")
    _prepared_runtime(tmp_path, "aarch64-apple-darwin")
    output = tmp_path / "artifacts"
    index = collector.collect(target="aarch64-apple-darwin", source=bundle, output=output, edition="full", repository=tmp_path)
    payload = output / index["payloads"][0]["name"]
    assert payload.name == "mdtero-connect-aarch64-apple-darwin.dmg"
    assert payload.read_bytes() == dmg.read_bytes()
    assert index["payloads"][0]["sha256"] == hashlib.sha256(payload.read_bytes()).hexdigest()
    assert index["commit"] == "a" * 40
    assert index["source_digest"] == "b" * 64
    assert index["human_acceptance"] == "pending"
    assert not index["developer_identity_signed"]
    assert json.loads((output / "source-checksums.json").read_text()) == provenance
    for line in (output / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split("  ", 1)
        assert digest == hashlib.sha256((output / name).read_bytes()).hexdigest()


def test_windows_collects_installer_without_mutating_it(tmp_path, provenance):
    bundle = tmp_path / "bundle"
    installer = bundle / "nsis/Mdtero Connect_0.1.0_x64-setup.exe"
    installer.parent.mkdir(parents=True)
    installer.write_bytes(b"MZdebug installer")
    _prepared_runtime(tmp_path, "x86_64-pc-windows-msvc", "basic")
    output = tmp_path / "artifacts"
    index = collector.collect(target="x86_64-pc-windows-msvc", source=bundle, output=output, edition="basic", repository=tmp_path)
    assert (output / index["payloads"][0]["name"]).read_bytes() == installer.read_bytes()
    assert index["edition"] == "basic"
    assert not index["notarized"]


@pytest.mark.parametrize("mutation", ["target", "edition", "commit", "node", "pi", "missing-worker", "missing-relay"])
def test_full_artifact_rejects_mismatched_or_incomplete_runtime(tmp_path, provenance, mutation):
    target = "x86_64-pc-windows-msvc"
    runtime = _prepared_runtime(tmp_path, target)
    manifest_path = runtime / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    if mutation == "target":
        manifest["target"] = "aarch64-apple-darwin"
    elif mutation == "edition":
        manifest["edition"] = "basic"
    elif mutation == "commit":
        manifest["commit"] = "f" * 40
    elif mutation == "node":
        manifest["node_version"] = "22.18.0"
    elif mutation == "pi":
        (runtime / "agent/node_modules/@earendil-works/pi-coding-agent/package.json").write_text('{"version":"9.9.9"}')
    elif mutation == "missing-worker":
        (runtime / "agent/worker.mjs").unlink()
    elif mutation == "missing-relay":
        (runtime / "relay/mdtero-relay.exe").unlink()
    manifest_path.write_text(json.dumps(manifest))
    bundle = tmp_path / "bundle"
    (bundle / "nsis").mkdir(parents=True)
    (bundle / "nsis/debug-setup.exe").write_bytes(b"MZ")
    output = tmp_path / "artifacts"
    with pytest.raises(ValueError):
        collector.collect(target=target, source=bundle, output=output, edition="full", repository=tmp_path)
    assert not output.exists()


def test_full_windows_artifact_records_matching_bundled_runtime(tmp_path, provenance):
    target = "x86_64-pc-windows-msvc"
    runtime = _prepared_runtime(tmp_path, target)
    bundle = tmp_path / "bundle"
    (bundle / "nsis").mkdir(parents=True)
    (bundle / "nsis/debug-setup.exe").write_bytes(b"MZ")
    output = tmp_path / "artifacts"
    index = collector.collect(target=target, source=bundle, output=output, edition="full", repository=tmp_path)
    assert (output / "runtime-manifest.json").read_bytes() == (runtime / "manifest.json").read_bytes()
    assert index["edition"] == "full"


@pytest.mark.parametrize(("target", "bundle_type", "suffix"), [
    ("x86_64-pc-windows-msvc", "nsis", "exe"),
    ("aarch64-apple-darwin", "dmg", "dmg"),
])
@pytest.mark.parametrize("count", [0, 2])
def test_missing_or_ambiguous_native_payload_fails_without_output(tmp_path, provenance, target, bundle_type, suffix, count):
    bundle = tmp_path / "bundle" / bundle_type
    bundle.mkdir(parents=True)
    for number in range(count):
        (bundle / f"{number}-setup.{suffix}").write_bytes(b"native debug payload")
    output = tmp_path / "artifacts"
    with pytest.raises(ValueError, match=f"expected one {bundle_type} payload"):
        collector.collect(target=target, source=bundle.parent, output=output, edition="full", repository=tmp_path)
    assert not output.exists()


def test_existing_artifacts_are_not_silently_mixed(tmp_path, provenance):
    bundle = tmp_path / "bundle"
    (bundle / "nsis").mkdir(parents=True)
    (bundle / "nsis/debug-setup.exe").write_bytes(b"MZ")
    output = tmp_path / "artifacts"
    output.mkdir()
    (output / "previous-build").write_bytes(b"retain me")
    with pytest.raises(ValueError, match="output directory must be empty"):
        collector.collect(target="x86_64-pc-windows-msvc", source=bundle, output=output, edition="full", repository=tmp_path)
    assert (output / "previous-build").read_bytes() == b"retain me"


def test_source_digest_matches_canonical_checksum_map(tmp_path, monkeypatch):
    (tmp_path / "source.py").write_text("print('source')\n")
    tracked = b"source.py\0"
    try:
        (tmp_path / "shortcut.py").symlink_to(tmp_path / "source.py")
        tracked += b"shortcut.py\0"
    except OSError:
        # Windows may prohibit symlinks for this account; checksum collection
        # still needs to run there without claiming its symlink case passed.
        pass

    def fake_git(arguments, **kwargs):
        if arguments[1] == "rev-parse":
            return "d" * 40 + "\n"
        return tracked

    monkeypatch.setattr(collector.subprocess, "check_output", fake_git)
    commit, checksums, digest = collector.source_provenance(tmp_path)
    assert commit == "d" * 40
    assert checksums == {"source.py": hashlib.sha256((tmp_path / "source.py").read_bytes()).hexdigest()}
    canonical = json.dumps(checksums, sort_keys=True, separators=(",", ":")).encode()
    assert digest == hashlib.sha256(canonical).hexdigest()
