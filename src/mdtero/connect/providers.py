"""Device-local BYOK credentials, separate from Mdtero account authentication.

Saving a credential does not verify it or make cloud tasks use it. Session
storage is the default; persistent writes require a working OS credential
store. This module never falls back to a plaintext file.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from mdtero.config import MdteroConfig


_AUTO_KEYRING = object()
_KEYRING_SERVICE = "mdtero-connect.providers"
_OPENALEX_WORK_ID = "https://openalex.org/W2741809807"
_OPENALEX_CHECK_URL = "https://api.openalex.org/works/W2741809807"
# Reject fail/null/chainer and third-party file backends, even when keyring has
# selected one as the machine's default. Backend discovery is not proof that
# the backend is an OS credential store.
_OS_BACKENDS = frozenset(
    {
        ("keyring.backends.macOS", "Keyring"),
        ("keyring.backends.Windows", "WinVaultKeyring"),
        ("keyring.backends.SecretService", "Keyring"),
        ("keyring.backends.kwallet", "DBusKeyring"),
        ("keyring.backends.kwallet", "DBusKeyringKWallet4"),
        ("keyring.backends.kwallet", "DBusKeyringKWallet5"),
        ("keyring.backends.kwallet", "DBusKeyringKWallet6"),
        ("keyring.backends.libsecret", "Keyring"),
    }
)


class ProviderError(ValueError):
    """A safe error to expose through the loopback API; never carries a key."""

    def __init__(self, reason_code: str, hint: str) -> None:
        super().__init__(hint)
        self.reason_code = reason_code
        self.hint = hint
        self.action_hint = hint


@dataclass(frozen=True)
class _Provider:
    id: str
    name: str
    category: str
    capability: str
    env_names: tuple[str, ...]
    usage_hint: str


_PROVIDERS = (
    _Provider(
        "openalex", "OpenAlex", "discovery", "local_discovery",
        ("MDTERO_OPENALEX_API_KEY", "OPENALEX_API_KEY"),
        "Local literature discovery. Cloud discovery fallback uses the deployment's credentials.",
    ),
    _Provider(
        "mineru", "MinerU", "parser", "credential_only", ("MINERU_API_TOKEN",),
        "Credential storage only. Cloud parsing does not consume this local key yet.",
    ),
    _Provider(
        "voyage", "Voyage AI", "retrieval", "credential_only", ("VOYAGE_API_KEY",),
        "Credential storage only. Cloud RAG does not consume this local key yet.",
    ),
    _Provider(
        "openai", "OpenAI", "ai", "pi", ("OPENAI_API_KEY",),
        "For the optional local Pi runtime. Cloud AI tasks do not use this key.",
    ),
    _Provider(
        "anthropic", "Anthropic", "ai", "pi", ("ANTHROPIC_API_KEY",),
        "For the optional local Pi runtime. Cloud AI tasks do not use this key.",
    ),
    _Provider(
        "google", "Google AI (Gemini)", "ai", "pi", ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
        "For the optional local Pi runtime. Cloud AI tasks do not use this key.",
    ),
    _Provider(
        "openrouter", "OpenRouter", "ai", "pi", ("OPENROUTER_API_KEY",),
        "For the optional local Pi runtime. Cloud AI tasks do not use this key.",
    ),
)
_BY_ID = {provider.id: provider for provider in _PROVIDERS}


def _default_keyring() -> Any | None:
    try:
        import keyring

        return keyring.get_keyring()
    except Exception:
        return None


class ProviderStore:
    """Resolve local keys without exposing secrets in browser-facing status.

    ``environ={}`` and ``keyring_backend=None`` disable ambient credentials in
    tests. Omitting those arguments uses a snapshot of the environment and
    discovers the installed keyring backend. A passed config is read only for
    legacy OpenAlex compatibility; this class never writes ``config.json``.
    """

    def __init__(
        self,
        config: MdteroConfig | None = None,
        *,
        environ: Mapping[str, str] | None = None,
        keyring_backend: Any = _AUTO_KEYRING,
        http_get: Callable[..., httpx.Response] | None = None,
    ) -> None:
        self._config = config or MdteroConfig()
        self._environ = dict(os.environ if environ is None else environ)
        self._keyring = _default_keyring() if keyring_backend is _AUTO_KEYRING else keyring_backend
        self._http_get = http_get or httpx.get
        self._session: dict[str, str] = {}
        # The checked key remains in memory only to avoid reporting a stale
        # verification after an OS keyring item is changed outside Connect.
        self._checks: dict[str, tuple[str, dict[str, Any]]] = {}
        self._lock = threading.RLock()
        self._os_reason: str | None = None

    @staticmethod
    def _provider(provider: str) -> _Provider:
        if not isinstance(provider, str) or provider not in _BY_ID:
            raise ProviderError("provider_not_supported", "Choose a supported BYOK provider.")
        return _BY_ID[provider]

    def _os_available(self) -> bool:
        backend = self._keyring
        if backend is None or (type(backend).__module__, type(backend).__name__) not in _OS_BACKENDS:
            self._os_reason = "os_keyring_unavailable"
            return False
        try:
            available = float(backend.priority) > 0
        except Exception:
            available = False
        if not available:
            self._os_reason = "os_keyring_unavailable"
        return available

    def _require_os(self) -> None:
        if not self._os_available():
            raise ProviderError(
                "os_keyring_unavailable",
                "The OS credential store is unavailable. Use session storage or configure an OS keyring.",
            )

    def _os_key(self, provider: str) -> str | None:
        if not self._os_available():
            return None
        try:
            value = self._keyring.get_password(_KEYRING_SERVICE, provider)
        except Exception:
            self._os_reason = "os_keyring_locked_or_unavailable"
            return None
        return value.strip() or None if isinstance(value, str) else None

    def _resolve(self, provider: _Provider) -> tuple[str | None, str]:
        if value := self._session.get(provider.id):
            return value, "session"
        if value := self._os_key(provider.id):
            return value, "os"
        for name in provider.env_names:
            if value := str(self._environ.get(name) or "").strip():
                return value, "environment"
        if provider.id == "openalex":
            if value := str(getattr(self._config.academic, "openalex_api_key", None) or "").strip():
                return value, "legacy_config"
        return None, "missing"

    def get_key(self, provider: str) -> str | None:
        """Internal runtime access only; do not serialize the return value."""
        spec = self._provider(provider)
        with self._lock:
            return self._resolve(spec)[0]

    def _status(self, spec: _Provider) -> dict[str, Any]:
        key, source = self._resolve(spec)
        checked = self._checks.get(spec.id)
        result = checked[1] if checked and checked[0] == key else {}
        if checked and checked[0] != key:
            self._checks.pop(spec.id, None)
        return {
            "id": spec.id,
            "name": spec.name,
            "category": spec.category,
            "capability": spec.capability,
            "configured": bool(key),
            "source": source,
            "verification": result.get("verification", "not_checked"),
            "checked_at": result.get("checked_at"),
            "usage_hint": spec.usage_hint,
        }

    def status(self) -> dict[str, Any]:
        """No provider requests, credential fragments, or fingerprints."""
        with self._lock:
            self._os_reason = None
            providers = [self._status(spec) for spec in _PROVIDERS]
            available = self._os_available() and self._os_reason != "os_keyring_locked_or_unavailable"
            return {
                "providers": providers,
                "storage": {
                    "session": True,
                    "os": available,
                    "os_reason_code": None if available else self._os_reason,
                    "default": "session",
                    "plaintext_fallback": False,
                },
            }

    @staticmethod
    def _storage(storage: str) -> None:
        if not isinstance(storage, str) or storage not in {"session", "os"}:
            raise ProviderError("invalid_provider_storage", "Choose session or OS credential storage.")

    def set_key(self, provider: str, key: str, storage: str = "session") -> dict[str, Any]:
        spec = self._provider(provider)
        self._storage(storage)
        if not isinstance(key, str):
            raise ProviderError("invalid_provider_key", "Enter a non-empty API key.")
        value = key.strip()
        if not value or len(value) > 8192 or any(ord(char) < 33 or ord(char) > 126 for char in value):
            raise ProviderError("invalid_provider_key", "Enter an API key without spaces or control characters.")
        with self._lock:
            if storage == "os":
                self._require_os()
                try:
                    self._keyring.set_password(_KEYRING_SERVICE, spec.id, value)
                    if self._keyring.get_password(_KEYRING_SERVICE, spec.id) != value:
                        raise RuntimeError("Keyring write did not persist")
                except Exception:
                    raise ProviderError(
                        "os_keyring_write_failed",
                        "The OS credential-store write could not be confirmed. No file fallback was used.",
                    ) from None
                self._os_reason = None
                self._session.pop(spec.id, None)
            else:
                self._session[spec.id] = value
            self._checks.pop(spec.id, None)
            return self._status(spec)

    def clear_key(self, provider: str, storage: str = "session") -> dict[str, Any]:
        spec = self._provider(provider)
        self._storage(storage)
        with self._lock:
            if storage == "os":
                self._require_os()
                try:
                    if self._keyring.get_password(_KEYRING_SERVICE, spec.id) is not None:
                        self._keyring.delete_password(_KEYRING_SERVICE, spec.id)
                except Exception:
                    raise ProviderError(
                        "os_keyring_delete_failed", "The key could not be removed from the OS credential store."
                    ) from None
            else:
                self._session.pop(spec.id, None)
            self._checks.pop(spec.id, None)
            return self._status(spec)

    def clear_session(self) -> None:
        with self._lock:
            self._session.clear()
            self._checks.clear()

    def check(self, provider: str) -> dict[str, Any]:
        """Check OpenAlex with a free singleton GET; never submit paid work.

        Other providers have no supported zero-usage auth check here. Their
        result is explicitly a configuration check, not remote verification.
        """
        spec = self._provider(provider)
        with self._lock:
            key, _ = self._resolve(spec)
        if not key:
            raise ProviderError("provider_key_missing", "Configure this provider's local key first.")
        if spec.id != "openalex":
            with self._lock:
                return {
                    **self._status(spec),
                    "verification": "not_checked",
                    "scope": "configuration_only",
                    "reason_code": "remote_check_not_available",
                    "action_hint": "The key is configured locally. No parsing, embedding, reranking or generation request was sent.",
                }

        result: dict[str, Any] = {
            "verification": "failed",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "scope": "credential",
        }
        try:
            response = self._http_get(
                _OPENALEX_CHECK_URL,
                params={"select": "id"},
                headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
                timeout=10.0,
                follow_redirects=False,
                trust_env=False,
            )
            if response.status_code == 200:
                if response.json().get("id") != _OPENALEX_WORK_ID:
                    result["reason_code"] = "provider_response_invalid"
                else:
                    result.update(verification="verified", reason_code="provider_key_verified")
            elif response.status_code in {401, 403}:
                result["reason_code"] = "provider_auth_failed"
            elif response.status_code == 429:
                result["reason_code"] = "provider_rate_limited"
            else:
                result["reason_code"] = "provider_check_failed"
        except (ValueError, AttributeError):
            result["reason_code"] = "provider_response_invalid"
        except Exception:
            # Provider and HTTP exceptions can contain URLs, authorization
            # headers, or a response body that echoes a submitted key.
            result["reason_code"] = "provider_check_unavailable"
        result["action_hint"] = (
            "OpenAlex accepted the key for a free single-entity lookup."
            if result["verification"] == "verified"
            else "OpenAlex verification did not succeed. Check the key and network, then retry."
        )
        with self._lock:
            # A user can rotate or clear a key while the request is in flight.
            # Never attach the old response to the newly effective credential.
            if self._resolve(spec)[0] != key:
                raise ProviderError("provider_key_changed", "The key changed during the check. Check the current key again.")
            self._checks[spec.id] = (key, result)
            return {**self._status(spec), **result}
