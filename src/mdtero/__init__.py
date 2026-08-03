"""Public Python client for Mdtero."""

from __future__ import annotations

from typing import Any

__version__ = "0.2.0a27"

__all__ = [
    "ArtifactRef",
    "MdteroClient",
    "MdteroConfig",
    "PaperChunk",
    "PaperDocument",
    "ProviderResult",
    "WorkflowStep",
    "__version__",
    "load_config",
]


def __getattr__(name: str) -> Any:
    if name == "MdteroClient":
        from .client import MdteroClient

        return MdteroClient
    if name == "MdteroConfig":
        from .config import MdteroConfig

        return MdteroConfig
    if name == "load_config":
        from .config import load_config

        return load_config
    if name in {"ArtifactRef", "PaperChunk", "PaperDocument", "ProviderResult", "WorkflowStep"}:
        from . import core

        return getattr(core, name)
    raise AttributeError(f"module 'mdtero' has no attribute {name!r}")
