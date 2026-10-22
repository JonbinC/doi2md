from __future__ import annotations

import json
from unittest.mock import Mock

import httpx
import pytest

from mdtero.config import AcademicKeys, MdteroConfig
from mdtero.connect.providers import ProviderError, ProviderStore


class Keyring:
    """In-memory stand-in for an explicitly trusted OS backend."""

    __module__ = "keyring.backends.SecretService"
    priority = 5

    def __init__(self):
        self.values = {}
        self.error = None

    def get_password(self, service, username):
        if self.error:
            raise RuntimeError(self.error)
        return self.values.get((service, username))

    def set_password(self, service, username, password):
        if self.error:
            raise RuntimeError(self.error)
        self.values[(service, username)] = password

    def delete_password(self, service, username):
        if self.error:
            raise RuntimeError(self.error)
        self.values.pop((service, username), None)


def _store(**kwargs):
    kwargs.setdefault("environ", {})
    kwargs.setdefault("keyring_backend", None)
    kwargs.setdefault("http_get", Mock(side_effect=AssertionError("Unexpected provider request")))
    return ProviderStore(**kwargs)


def _row(store, provider="openalex"):
    return next(row for row in store.status()["providers"] if row["id"] == provider)


def _openalex_response(status=200, payload=None):
    return httpx.Response(
        status,
        json=payload if payload is not None else {"id": "https://openalex.org/W2741809807"},
    )


def test_session_is_default_without_writing_account_config_or_probing(tmp_path, monkeypatch):
    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path))
    config = MdteroConfig(api_key="account-only-secret", academic=AcademicKeys(openalex_api_key="legacy-secret"))
    probe = Mock()
    store = _store(config=config, http_get=probe)
    result = store.set_key("openalex", "session-provider-secret")

    assert result["source"] == "session"
    assert result["configured"] is True
    assert result["verification"] == "not_checked"
    assert config.api_key == "account-only-secret"
    assert config.academic.openalex_api_key == "legacy-secret"
    assert list(tmp_path.iterdir()) == []
    assert probe.call_count == 0
    public = json.dumps([result, store.status()])
    for secret in ("account-only-secret", "legacy-secret", "session-provider-secret"):
        assert secret not in public
    assert not any(key in result for key in ("key", "fingerprint", "prefix", "suffix"))


def test_empty_environment_and_disabled_keyring_isolate_ambient_keys(monkeypatch):
    monkeypatch.setenv("OPENALEX_API_KEY", "ambient-provider-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "ambient-ai-secret")
    store = _store()
    assert not any(row["configured"] for row in store.status()["providers"])
    assert store.status()["storage"] == {
        "session": True,
        "os": False,
        "os_reason_code": "os_keyring_unavailable",
        "default": "session",
        "plaintext_fallback": False,
    }


@pytest.mark.parametrize(
    ("provider", "env_name"),
    [
        ("openalex", "MDTERO_OPENALEX_API_KEY"),
        ("openalex", "OPENALEX_API_KEY"),
        ("mineru", "MINERU_API_TOKEN"),
        ("voyage", "VOYAGE_API_KEY"),
        ("openai", "OPENAI_API_KEY"),
        ("anthropic", "ANTHROPIC_API_KEY"),
        ("google", "GEMINI_API_KEY"),
        ("google", "GOOGLE_API_KEY"),
        ("openrouter", "OPENROUTER_API_KEY"),
    ],
)
def test_environment_resolution(provider, env_name):
    store = _store(environ={env_name: "environment-secret"})
    assert store.get_key(provider) == "environment-secret"
    assert _row(store, provider)["source"] == "environment"
    assert "environment-secret" not in json.dumps(store.status())


def test_source_priority_and_clear_reveal_lower_priority_credentials():
    backend = Keyring()
    store = _store(
        config=MdteroConfig(academic=AcademicKeys(openalex_api_key="legacy-secret")),
        environ={"MDTERO_OPENALEX_API_KEY": "prefixed-env-secret", "OPENALEX_API_KEY": "env-secret"},
        keyring_backend=backend,
    )
    assert store.get_key("openalex") == "prefixed-env-secret"
    assert store.set_key("openalex", "os-secret", storage="os")["source"] == "os"
    assert store.set_key("openalex", "session-secret")["source"] == "session"
    assert store.get_key("openalex") == "session-secret"
    assert store.clear_key("openalex")["source"] == "os"
    assert store.get_key("openalex") == "os-secret"
    assert store.clear_key("openalex", storage="os")["source"] == "environment"
    assert store.get_key("openalex") == "prefixed-env-secret"
    assert store.clear_key("openalex", storage="os")["source"] == "environment"


def test_legacy_openalex_is_read_only_and_explicitly_labeled():
    store = _store(config=MdteroConfig(academic=AcademicKeys(openalex_api_key="legacy-secret")))
    assert _row(store)["source"] == "legacy_config"
    assert store.clear_key("openalex")["configured"] is True
    assert store.get_key("openalex") == "legacy-secret"


def test_os_write_clears_session_override_and_is_available_to_new_store():
    backend = Keyring()
    store = _store(keyring_backend=backend)
    store.set_key("openai", "temporary-secret")
    saved = store.set_key("openai", "persistent-secret", storage="os")
    assert saved["source"] == "os"
    assert store.status()["storage"]["os"] is True
    assert _store(keyring_backend=backend).get_key("openai") == "persistent-secret"
    store.clear_session()
    assert store.get_key("openai") == "persistent-secret"


@pytest.mark.parametrize(
    ("module", "name", "priority"),
    [
        ("keyring.backends.fail", "Keyring", 0),
        ("keyring.backends.null", "Keyring", 1),
        ("keyring.backends.chainer", "ChainerBackend", 10),
        ("keyrings.alt.file", "PlaintextKeyring", 100),
        ("keyrings.alt.file", "EncryptedKeyring", 100),
        ("keyring.backends.SecretService", "Keyring", 0),
    ],
)
def test_unsupported_keyrings_never_receive_credentials(module, name, priority):
    get_password = Mock(side_effect=AssertionError("Untrusted backend was read"))
    set_password = Mock(side_effect=AssertionError("Untrusted backend was written"))
    backend_type = type(name, (), {"__module__": module, "priority": priority})
    backend = backend_type()
    backend.get_password = get_password
    backend.set_password = set_password
    store = _store(keyring_backend=backend)
    with pytest.raises(ProviderError) as caught:
        store.set_key("voyage", "must-never-persist", storage="os")
    assert caught.value.reason_code == "os_keyring_unavailable"
    assert "must-never-persist" not in str(caught.value)
    assert store.get_key("voyage") is None
    assert not store.status()["storage"]["os"]
    get_password.assert_not_called()
    set_password.assert_not_called()


def test_os_errors_are_sanitized_and_never_create_a_session_or_file_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("MDTERO_CONFIG_DIR", str(tmp_path))
    backend = Keyring()
    backend.error = "Backend error echoing leaked-provider-secret"
    store = _store(keyring_backend=backend, environ={"VOYAGE_API_KEY": "env-secret"})
    with pytest.raises(ProviderError) as caught:
        store.set_key("voyage", "submitted-secret", storage="os")
    assert caught.value.reason_code == "os_keyring_write_failed"
    assert "leaked-provider-secret" not in str(caught.value)
    assert "submitted-secret" not in str(caught.value)
    assert store.get_key("voyage") == "env-secret"
    status = store.status()
    assert status["storage"]["os"] is False
    assert status["storage"]["os_reason_code"] == "os_keyring_locked_or_unavailable"
    assert list(tmp_path.iterdir()) == []
    assert "secret" not in json.dumps(status)


@pytest.mark.parametrize("provider", ["not-a-provider", "OPENAI", None, [], {}])
def test_unsupported_provider_errors_do_not_echo_user_input(provider):
    with pytest.raises(ProviderError) as caught:
        _store().get_key(provider)
    assert caught.value.reason_code == "provider_not_supported"


@pytest.mark.parametrize("key", ["", "  ", "line\nbreak", "header\rinjection", "embedded space", "\x00", "x" * 8193, None, {}])
def test_invalid_keys_are_rejected_without_echoing_them(key):
    store = _store()
    with pytest.raises(ProviderError) as caught:
        store.set_key("openalex", key)
    assert caught.value.reason_code == "invalid_provider_key"
    assert store.get_key("openalex") is None


@pytest.mark.parametrize("storage", ["file", "plaintext", "SESSION", None, {}])
def test_storage_must_be_explicit_supported_choice(storage):
    with pytest.raises(ProviderError) as caught:
        _store().set_key("openalex", "secret", storage=storage)
    assert caught.value.reason_code == "invalid_provider_storage"


def test_openalex_check_is_fixed_free_singleton_with_bearer_and_no_redirects():
    probe = Mock(return_value=_openalex_response())
    store = _store(http_get=probe)
    store.set_key("openalex", "openalex-private-secret")
    assert probe.call_count == 0
    result = store.check("openalex")
    assert result["verification"] == "verified"
    assert result["scope"] == "credential"
    assert result["checked_at"]
    assert _row(store)["verification"] == "verified"
    args, kwargs = probe.call_args
    assert args == ("https://api.openalex.org/works/W2741809807",)
    assert kwargs["headers"]["Authorization"] == "Bearer openalex-private-secret"
    assert kwargs["params"] == {"select": "id"}
    assert kwargs["follow_redirects"] is False
    assert kwargs["trust_env"] is False
    assert kwargs["timeout"] <= 10
    assert "openalex-private-secret" not in json.dumps(result)
    store.status()
    assert probe.call_count == 1
    assert store.set_key("openalex", "rotated-secret")["verification"] == "not_checked"
    assert store.clear_key("openalex")["verification"] == "not_checked"


@pytest.mark.parametrize(
    ("status", "reason"),
    [(401, "provider_auth_failed"), (403, "provider_auth_failed"), (429, "provider_rate_limited"), (302, "provider_check_failed"), (500, "provider_check_failed")],
)
def test_openalex_failures_do_not_return_response_bodies(status, reason):
    probe = Mock(return_value=_openalex_response(status, {"error": "echoed-private-secret"}))
    store = _store(http_get=probe)
    store.set_key("openalex", "echoed-private-secret")
    result = store.check("openalex")
    assert result["verification"] == "failed"
    assert result["reason_code"] == reason
    assert "echoed-private-secret" not in json.dumps([result, store.status()])


@pytest.mark.parametrize("payload", [{}, {"id": "wrong-id"}, [], "echoed-private-secret"])
def test_openalex_invalid_payload_is_not_treated_as_verified(payload):
    store = _store(http_get=Mock(return_value=_openalex_response(payload=payload)))
    store.set_key("openalex", "echoed-private-secret")
    result = store.check("openalex")
    assert result["verification"] == "failed"
    assert result["reason_code"] == "provider_response_invalid"
    assert "echoed-private-secret" not in json.dumps(result)


def test_openalex_network_exceptions_do_not_expose_secret_in_error():
    store = _store(http_get=Mock(side_effect=RuntimeError("Authorization: Bearer echoed-private-secret")))
    store.set_key("openalex", "echoed-private-secret")
    result = store.check("openalex")
    assert result["verification"] == "failed"
    assert result["reason_code"] == "provider_check_unavailable"
    assert "echoed-private-secret" not in json.dumps(result)


@pytest.mark.parametrize("provider", ["mineru", "voyage", "openai", "anthropic", "google", "openrouter"])
def test_configuration_checks_never_submit_parse_embedding_or_generation(provider):
    probe = Mock(side_effect=AssertionError("Paid provider request attempted"))
    store = _store(http_get=probe)
    store.set_key(provider, "configured-secret")
    result = store.check(provider)
    assert result["configured"] is True
    assert result["verification"] == "not_checked"
    assert result["scope"] == "configuration_only"
    assert result["reason_code"] == "remote_check_not_available"
    assert _row(store, provider)["verification"] == "not_checked"
    probe.assert_not_called()


def test_no_check_without_a_key_and_no_remote_request():
    probe = Mock()
    with pytest.raises(ProviderError) as caught:
        _store(http_get=probe).check("openalex")
    assert caught.value.reason_code == "provider_key_missing"
    probe.assert_not_called()


def test_key_changed_while_check_runs_cannot_inherit_old_verification():
    store = _store()

    def rotate_while_checking(*args, **kwargs):
        store.set_key("openalex", "new-secret")
        return _openalex_response()

    store._http_get = rotate_while_checking
    store.set_key("openalex", "original-secret")
    with pytest.raises(ProviderError) as caught:
        store.check("openalex")
    assert caught.value.reason_code == "provider_key_changed"
    assert store.get_key("openalex") == "new-secret"
    assert _row(store)["verification"] == "not_checked"


def test_os_rotation_outside_connect_invalidates_old_verification():
    backend = Keyring()
    store = _store(keyring_backend=backend, http_get=Mock(return_value=_openalex_response()))
    store.set_key("openalex", "original-secret", storage="os")
    store.check("openalex")
    assert _row(store)["verification"] == "verified"
    backend.set_password("mdtero-connect.providers", "openalex", "external-rotation-secret")
    assert _row(store)["verification"] == "not_checked"


def test_stop_cleanup_removes_session_credentials_and_verification():
    store = _store(http_get=Mock(return_value=_openalex_response()))
    store.set_key("openalex", "session-secret")
    store.set_key("openai", "ai-secret")
    store.check("openalex")
    store.clear_session()
    assert store.get_key("openalex") is None
    assert store.get_key("openai") is None
    assert _row(store)["verification"] == "not_checked"
    assert store._checks == {}


def test_catalog_distinguishes_credential_only_from_functional_adapters():
    store = _store()
    assert _row(store, "mineru")["capability"] == "credential_only"
    assert "does not consume" in _row(store, "mineru")["usage_hint"]
    assert _row(store, "voyage")["capability"] == "credential_only"
    assert "does not consume" in _row(store, "voyage")["usage_hint"]
    assert _row(store, "openalex")["capability"] == "local_discovery"
    assert _row(store, "openai")["capability"] == "pi"
