"""Synthetic-only browser fixture; never reads local credentials or contacts upstream.

The product UI and /connect/v1 requests use the real ConnectBridge security and
LibraryClient. Only the MdteroClient upstream, Relay diagnostic and local Zotero
providers are replaced. A separate loopback-only control port resets fixtures
and exposes request receipts to Playwright; it is not a shipped application API.
"""
from __future__ import annotations

import copy
import io
import json
import os
import signal
import threading
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import httpx

# Do not inherit a real key or use the operator's persisted CLI configuration.
os.environ.pop("MDTERO_API_KEY", None)

from mdtero.client import MdteroApiError, MdteroClient  # noqa: E402
from mdtero.config import MdteroConfig  # noqa: E402
import mdtero.connect.bridge as bridge_module  # noqa: E402
from mdtero.connect.bridge import ConnectBridge  # noqa: E402

APP_DIR = Path(__file__).resolve().parents[1] / "app"
SYNTHETIC_KEY = "synthetic-browser-fixture-not-a-credential"
INITIAL_PAPERS = [
    {"document_id": 11, "title": "Cycling stability of synthetic cells", "authors": ["Ada Example"], "year": 2025,
     "venue": "Synthetic Journal", "doi": "10.0000/synthetic.11", "tags": ["Batteries"], "has_saved_text": True},
    {"document_id": 22, "title": "Metadata only synthetic review", "authors": ["Bo Example"], "year": 2024,
     "venue": "Fixture Review", "doi": "10.0000/synthetic.22", "tags": ["Review"], "has_saved_text": False},
    {"document_id": 33, "title": "An untagged synthetic experiment", "authors": ["Cy Example"], "year": 2023,
     "venue": "Fixture Letters", "doi": "10.0000/synthetic.33", "tags": [], "has_saved_text": True},
]


def markdown(document_id: int) -> bytes:
    return f"# Synthetic document {document_id}\n\nText-only fixture. No images.\n".encode()


class SyntheticClient(MdteroClient):
    def __init__(self) -> None:
        super().__init__(MdteroConfig(api_key=SYNTHETIC_KEY, api_base_url="https://synthetic.invalid"))
        self.lock = threading.RLock()
        self.reset()

    def reset(self, settings: dict[str, Any] | None = None) -> None:
        with self.lock:
            self.papers = copy.deepcopy(INITIAL_PAPERS)
            self.calls: list[dict[str, Any]] = []
            self.settings = {"authenticated": True, "invalid_credentials": False, "fail_next": None, **(settings or {})}
            self.config.api_key = SYNTHETIC_KEY if self.settings["authenticated"] else None

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return copy.deepcopy({"papers": self.papers, "calls": self.calls})

    def _record(self, method: str, path: str, kwargs: dict[str, Any]) -> None:
        self.calls.append({"method": method, "path": path, "body": copy.deepcopy(kwargs.get("json"))})
        if self.settings.get("invalid_credentials") or not self.config.effective_api_key:
            raise MdteroApiError({"status_code": 401, "reason_code": "unauthorized", "action_hint": "Synthetic key rejected; run mdtero login."})
        if self.settings.get("fail_next") == path:
            self.settings["fail_next"] = None
            raise MdteroApiError({"status_code": 503, "reason_code": "synthetic_unavailable", "action_hint": "Synthetic service unavailable; retry."})

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        with self.lock:
            self._record(method, path, kwargs)
            if method == "GET" and path == "/api/v1/documents":
                return {"items": copy.deepcopy(self.papers)}
            if method == "GET" and path == "/api/v1/library/tags":
                return {"items": [{"name": tag} for tag in sorted({t for p in self.papers for t in p["tags"]})]}
            if method == "POST" and path == "/api/v1/library/tags/batch":
                body = kwargs["json"]
                # Fail loudly if the client ever relies on the backend's false default.
                assert isinstance(body.get("dry_run"), bool), "dry_run must be explicit"
                candidates = [p for p in self.papers if p["document_id"] in body["document_ids"]]
                changes = []
                for paper in candidates:
                    tags = sorted((set(paper["tags"]) | set(body["add"])) - set(body["remove"]))
                    if tags != sorted(paper["tags"]):
                        changes.append((paper, tags))
                if not body["dry_run"]:
                    for paper, tags in changes:
                        paper["tags"] = tags
                return {"dry_run": body["dry_run"], "changed_count": len(changes), "document_ids": body["document_ids"]}
            if path == "/api/v1/library/import":
                assert kwargs["json"]["dry_run"] is True
                return {"dry_run": True, "metadata_only": True, "created_count": 1}
            raise AssertionError(f"Unexpected synthetic upstream request: {method} {path}")

    def _raw_request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        with self.lock:
            self._record(method, path, kwargs)
            assert method == "POST" and path == "/api/v1/library/export"
            body = kwargs["json"]
            ids = body["document_ids"]
            kind = body["format"]
            if kind == "bibtex":
                data = b"@article{synthetic11,\n  title={Cycling stability of synthetic cells},\n}\n"
                filename, media, label = "synthetic-references.bib", "application/x-bibtex", "bibtex"
            elif kind == "csl_json":
                data = json.dumps([{"id": str(i), "type": "article-journal", "title": f"Synthetic document {i}"} for i in ids]).encode()
                filename, media, label = "synthetic-references.json", "application/json", "csl_json"
            elif kind == "markdown":
                assert len(ids) == 1
                data = markdown(ids[0])
                filename, media, label = f"synthetic-{ids[0]}.md", "text/markdown; charset=utf-8", "markdown-text-only"
            elif kind == "markdown_zip":
                output = io.BytesIO()
                with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
                    for document_id in ids:
                        info = zipfile.ZipInfo(f"synthetic-{document_id}.md", date_time=(2026, 1, 1, 0, 0, 0))
                        archive.writestr(info, markdown(document_id))
                data = output.getvalue()
                filename, media, label = "synthetic-markdown-text-only.zip", "application/zip", "markdown-text-only"
            else:
                raise AssertionError(f"Unexpected export format {kind}")
            return httpx.Response(200, content=data, request=httpx.Request(method, "https://synthetic.invalid" + path),
                                  headers={"content-type": media, "content-disposition": f'attachment; filename="{filename}"', "x-mdtero-export": label})


client = SyntheticClient()
bridge_module.diagnose_relay = lambda _: {
    "transport_online": True, "browser_ready": False, "article_entitlement": None,
    "cloud_status": {"connected": True, "egress_ip": "192.0.2.10"},
    "notes": ["Synthetic transport only; full text must be checked per article."],
}
bridge_module.probe_article_entitlement = lambda *_args, **_kwargs: {
    "status": "unverified", "reason_code": "article_entitlement_unverified", "action_hint": "Synthetic fixture has no full-text authorization.",
}
bridge_module.connector_status = lambda: {"available": False, "reason_code": "synthetic_zotero_not_running"}
bridge_module.list_collections = lambda: {"available": True, "collections": [{"key": "SYNTH001", "name": "Synthetic collection"}]}
bridge_module.collection_items_preview = lambda _key: {"items": [{"raw": {"key": "ITEM0001", "itemType": "journalArticle", "title": "Synthetic import", "DOI": "10.0000/synthetic.import"}}]}


class ControlHandler(BaseHTTPRequestHandler):
    def log_message(self, *_args: Any) -> None:
        return

    def do_GET(self) -> None:  # noqa: N802
        if self.path not in {"/health", "/state"}:
            self.send_error(404)
            return
        self._json({"fixture": "synthetic-only"} if self.path == "/health" else client.snapshot())

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/reset":
            self.send_error(404)
            return
        settings = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
        client.reset(settings)
        self._json({"reset": True})

    def _json(self, payload: dict[str, Any]) -> None:
        data = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    stopped = threading.Event()
    for event in (signal.SIGTERM, signal.SIGINT):
        signal.signal(event, lambda *_args: stopped.set())
    control = ThreadingHTTPServer(("127.0.0.1", 18742), ControlHandler)
    with ConnectBridge(host="127.0.0.1", port=18741, client=client, static_dir=APP_DIR) as bridge:
        threading.Thread(target=control.serve_forever, daemon=True).start()
        print(f"Synthetic-only Connect fixture at {bridge.base_url}", flush=True)
        stopped.wait()
    control.shutdown()
    control.server_close()
