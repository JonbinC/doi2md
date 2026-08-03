from __future__ import annotations

from pathlib import Path

from mdtero.config import MdteroConfig
from mdtero.local_access import ensure_local_access, local_access_status


def test_local_access_skips_headless_environment(monkeypatch):
    monkeypatch.setenv("MDTERO_HEADLESS", "1")
    monkeypatch.delenv("MDTERO_FORCE_LOCAL_ACCESS", raising=False)

    payload = ensure_local_access(MdteroConfig(api_key="mdt_live_test"))

    assert payload["status"] == "not_applicable"
    assert payload["desktop"] is False


def test_local_access_can_be_disabled_without_network(monkeypatch):
    monkeypatch.setenv("MDTERO_DISABLE_LOCAL_ACCESS", "1")

    payload = local_access_status()

    assert payload["status"] == "disabled"
    assert payload["browser_extension_fallback"] is True


def test_local_access_service_key_is_passed_through_environment(monkeypatch, tmp_path: Path):
    import mdtero.local_access as local_access

    binary = tmp_path / "mdtero-relay"
    binary.write_text("stub", encoding="utf-8")
    seen: dict[str, object] = {}

    def fake_run(command, *, env, **kwargs):
        seen["command"] = command
        seen["env"] = env

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr(local_access.subprocess, "run", fake_run)

    ready, reason = local_access._install_service(binary, MdteroConfig(api_key="mdt_live_secret", api_base_url="https://api.example"))

    assert ready is True
    assert reason is None
    assert seen["command"] == [str(binary), "install", "--browser=false"]
    assert seen["env"]["MDTERO_API_KEY"] == "mdt_live_secret"
    assert seen["env"]["MDTERO_API_URL"] == "https://api.example"
