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
    openalex_api_key: str | None = None
    unpaywall_email: str | None = None
    core_api_key: str | None = None
    doaj_api_key: str | None = None
    zenodo_access_token: str | None = None
    ieee_api_key: str | None = None
    acm_api_key: str | None = None
    # Sci-Hub is download-only and disabled by default.
    enable_scihub: bool = False
    scihub_base_url: str | None = None


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
            semantic_scholar_api_key=(
                academic.get("semantic_scholar_api_key") or academic_env.semantic_scholar_api_key or None
            ),
            openalex_api_key=academic.get("openalex_api_key") or academic_env.openalex_api_key or None,
            unpaywall_email=academic.get("unpaywall_email") or academic_env.unpaywall_email or None,
            core_api_key=academic.get("core_api_key") or academic_env.core_api_key or None,
            doaj_api_key=academic.get("doaj_api_key") or academic_env.doaj_api_key or None,
            zenodo_access_token=academic.get("zenodo_access_token") or academic_env.zenodo_access_token or None,
            ieee_api_key=academic.get("ieee_api_key") or academic_env.ieee_api_key or None,
            acm_api_key=academic.get("acm_api_key") or academic_env.acm_api_key or None,
            enable_scihub=_as_bool(academic.get("enable_scihub"), default=academic_env.enable_scihub),
            scihub_base_url=academic.get("scihub_base_url") or academic_env.scihub_base_url or None,
        ),
        zotero=ZoteroConfig(
            library_id=zotero.get("library_id") or os.environ.get("ZOTERO_LIBRARY_ID") or None,
            library_type=str(zotero.get("library_type") or os.environ.get("ZOTERO_LIBRARY_TYPE") or "user"),
            api_key=zotero.get("api_key") or os.environ.get("ZOTERO_API_KEY") or None,
        ),
    )
    return cfg


def _as_bool(value: Any, *, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _academic_keys_from_env() -> AcademicKeys:
    return AcademicKeys(
        elsevier_api_key=os.environ.get("MDTERO_ELSEVIER_API_KEY") or os.environ.get("ELSEVIER_API_KEY") or None,
        wiley_tdm_token=os.environ.get("MDTERO_WILEY_TDM_TOKEN") or os.environ.get("WILEY_TDM_TOKEN") or None,
        semantic_scholar_api_key=(
            os.environ.get("MDTERO_SEMANTIC_SCHOLAR_API_KEY")
            or os.environ.get("SEMANTIC_SCHOLAR_API_KEY")
            or os.environ.get("PAPER_SEARCH_MCP_SEMANTIC_SCHOLAR_API_KEY")
            or None
        ),
        openalex_api_key=os.environ.get("MDTERO_OPENALEX_API_KEY") or os.environ.get("OPENALEX_API_KEY") or None,
        unpaywall_email=(
            os.environ.get("MDTERO_UNPAYWALL_EMAIL")
            or os.environ.get("UNPAYWALL_EMAIL")
            or os.environ.get("PAPER_SEARCH_MCP_UNPAYWALL_EMAIL")
            or None
        ),
        core_api_key=(
            os.environ.get("MDTERO_CORE_API_KEY")
            or os.environ.get("CORE_API_KEY")
            or os.environ.get("PAPER_SEARCH_MCP_CORE_API_KEY")
            or None
        ),
        doaj_api_key=(
            os.environ.get("MDTERO_DOAJ_API_KEY")
            or os.environ.get("DOAJ_API_KEY")
            or os.environ.get("PAPER_SEARCH_MCP_DOAJ_API_KEY")
            or None
        ),
        zenodo_access_token=(
            os.environ.get("MDTERO_ZENODO_ACCESS_TOKEN")
            or os.environ.get("ZENODO_ACCESS_TOKEN")
            or os.environ.get("PAPER_SEARCH_MCP_ZENODO_ACCESS_TOKEN")
            or None
        ),
        ieee_api_key=(
            os.environ.get("MDTERO_IEEE_API_KEY")
            or os.environ.get("IEEE_API_KEY")
            or os.environ.get("PAPER_SEARCH_MCP_IEEE_API_KEY")
            or None
        ),
        acm_api_key=(
            os.environ.get("MDTERO_ACM_API_KEY")
            or os.environ.get("ACM_API_KEY")
            or os.environ.get("PAPER_SEARCH_MCP_ACM_API_KEY")
            or None
        ),
        enable_scihub=str(os.environ.get("MDTERO_ENABLE_SCIHUB") or "").strip().lower() in {"1", "true", "yes", "on"},
        scihub_base_url=os.environ.get("MDTERO_SCIHUB_BASE_URL") or None,
    )


def save_config(config: MdteroConfig, path: Path | None = None) -> Path:
    target = path or config_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = asdict(config)
    # Preserve any pre-existing academic keys that older clients wrote under unknown fields.
    if target.exists():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}
        existing_academic = existing.get("academic") if isinstance(existing.get("academic"), dict) else {}
        academic_payload = payload.setdefault("academic", {})
        if isinstance(academic_payload, dict):
            for key, value in existing_academic.items():
                if key not in academic_payload or academic_payload.get(key) in {None, ""}:
                    academic_payload[key] = value
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    target.chmod(0o600)
    return target
