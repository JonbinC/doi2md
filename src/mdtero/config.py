from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_API_BASE = "https://api.mdtero.com"
DEFAULT_SITE_BASE = "https://mdtero.com"


def config_dir() -> Path:
    override = os.environ.get("MDTERO_CONFIG_DIR")
    if override:
        return Path(override).expanduser().resolve()
    return Path(os.environ.get("XDG_CONFIG_HOME", "~/.config")).expanduser() / "mdtero"


def config_path() -> Path:
    return config_dir() / "config.json"


@dataclass
class AcademicKeys:
    elsevier_api_key: str | None = None
    wiley_tdm_token: str | None = None
    semantic_scholar_api_key: str | None = None


@dataclass
class ZoteroConfig:
    library_id: str | None = None
    library_type: str = "user"
    api_key: str | None = None


@dataclass
class MdteroConfig:
    api_base_url: str = DEFAULT_API_BASE
    site_base_url: str = DEFAULT_SITE_BASE
    api_key: str | None = None
    academic: AcademicKeys = field(default_factory=AcademicKeys)
    zotero: ZoteroConfig = field(default_factory=ZoteroConfig)
    default_project: str | None = None
    proxy_url: str | None = None
    require_campus_proxy: bool = False

    @property
    def has_semantic_scholar_key(self) -> bool:
        return bool((self.academic.semantic_scholar_api_key or "").strip())

    @property
    def effective_api_key(self) -> str | None:
        return (self.api_key or os.environ.get("MDTERO_API_KEY") or "").strip() or None

    @property
    def api_key_source(self) -> str:
        if (self.api_key or "").strip():
            return "saved config"
        if os.environ.get("MDTERO_API_KEY"):
            return "MDTERO_API_KEY"
        return "missing"

    @property
    def is_authenticated(self) -> bool:
        return self.effective_api_key is not None

    @property
    def effective_proxy_url(self) -> str | None:
        return (self.proxy_url or os.environ.get("MDTERO_PROXY_URL") or os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or "").strip() or None

    @property
    def campus_proxy_required(self) -> bool:
        value = str(os.environ.get("MDTERO_REQUIRE_CAMPUS_PROXY") or "").strip().lower()
        return self.require_campus_proxy or value in {"1", "true", "yes", "on"}


def load_config(path: Path | None = None) -> MdteroConfig:
    target = path or config_path()
    academic_env = _academic_keys_from_env()
    if not target.exists():
        return MdteroConfig(
            api_base_url=os.environ.get("MDTERO_API_URL", DEFAULT_API_BASE),
            site_base_url=os.environ.get("MDTERO_SITE_URL", DEFAULT_SITE_BASE),
            api_key=None,
            academic=academic_env,
            proxy_url=os.environ.get("MDTERO_PROXY_URL") or None,
            require_campus_proxy=str(os.environ.get("MDTERO_REQUIRE_CAMPUS_PROXY") or "").strip().lower() in {"1", "true", "yes", "on"},
        )
    payload = json.loads(target.read_text(encoding="utf-8"))
    academic = payload.get("academic") or {}
    zotero = payload.get("zotero") or {}
    cfg = MdteroConfig(
        api_base_url=str(payload.get("api_base_url") or os.environ.get("MDTERO_API_URL") or DEFAULT_API_BASE),
        site_base_url=str(payload.get("site_base_url") or os.environ.get("MDTERO_SITE_URL") or DEFAULT_SITE_BASE),
        api_key=payload.get("api_key") or None,
        default_project=payload.get("default_project") or None,
        proxy_url=payload.get("proxy_url") or os.environ.get("MDTERO_PROXY_URL") or None,
        require_campus_proxy=bool(payload.get("require_campus_proxy")) or str(os.environ.get("MDTERO_REQUIRE_CAMPUS_PROXY") or "").strip().lower() in {"1", "true", "yes", "on"},
        academic=AcademicKeys(
            elsevier_api_key=academic.get("elsevier_api_key") or academic_env.elsevier_api_key or None,
            wiley_tdm_token=academic.get("wiley_tdm_token") or academic_env.wiley_tdm_token or None,
            semantic_scholar_api_key=academic.get("semantic_scholar_api_key") or academic_env.semantic_scholar_api_key or None,
        ),
        zotero=ZoteroConfig(
            library_id=zotero.get("library_id") or os.environ.get("ZOTERO_LIBRARY_ID") or None,
            library_type=str(zotero.get("library_type") or os.environ.get("ZOTERO_LIBRARY_TYPE") or "user"),
            api_key=zotero.get("api_key") or os.environ.get("ZOTERO_API_KEY") or None,
        ),
    )
    return cfg


def _academic_keys_from_env() -> AcademicKeys:
    return AcademicKeys(
        elsevier_api_key=os.environ.get("MDTERO_ELSEVIER_API_KEY") or os.environ.get("ELSEVIER_API_KEY") or None,
        wiley_tdm_token=os.environ.get("MDTERO_WILEY_TDM_TOKEN") or os.environ.get("WILEY_TDM_TOKEN") or None,
        semantic_scholar_api_key=(
            os.environ.get("MDTERO_SEMANTIC_SCHOLAR_API_KEY")
            or os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
            or os.environ.get("S2_API_KEY")
            or None
        ),
    )


def save_config(config: MdteroConfig, path: Path | None = None) -> Path:
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = asdict(config)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    target.chmod(0o600)
    return target
