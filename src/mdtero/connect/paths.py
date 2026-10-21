"""Resolve Connect static UI assets for repo checkouts and installed wheels."""

from __future__ import annotations

import os
from pathlib import Path


def app_static_dir() -> Path:
    override = str(os.environ.get("MDTERO_CONNECT_APP_DIR") or "").strip()
    if override:
        path = Path(override).expanduser().resolve()
        if (path / "index.html").is_file():
            return path
        raise FileNotFoundError(f"MDTERO_CONNECT_APP_DIR has no index.html: {path}")

    here = Path(__file__).resolve()
    candidates = [
        here.parent / "static",
        # src/mdtero/connect -> repo/connect/app
        here.parents[3] / "connect" / "app" if len(here.parents) >= 4 else None,
        Path.cwd() / "connect" / "app",
    ]
    for candidate in candidates:
        if candidate is None:
            continue
        if (candidate / "index.html").is_file():
            return candidate.resolve()
    raise FileNotFoundError(
        "Connect UI not found. Expected connect/app/index.html in the repository or packaged static assets."
    )
