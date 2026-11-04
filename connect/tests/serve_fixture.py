"""Synthetic-only browser fixture; never reads local credentials or contacts upstream.

The product UI and /connect/v1 requests use real bridge security, ProviderStore,
LibraryClient, and AgentRuntime approval controls. Only upstream data, provider
HTTP, Pi dependency discovery/model execution, Relay and Zotero are synthetic.
A separate loopback-only control port resets fixtures and exposes sanitized
request receipts to Playwright; it is not a shipped application API.
"""
from __future__ import annotations

import copy
import io
import json
import os
import re
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
from mdtero.connect.agent_runtime import AgentRuntime  # noqa: E402
from mdtero.connect.library import LibraryClient  # noqa: E402
from mdtero.connect.providers import ProviderStore  # noqa: E402
from mdtero.connect.relay_runtime import RelayError  # noqa: E402

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


def _parse_synthetic_import(content: str, fmt: str) -> list[dict[str, Any]]:
    stripped = content.strip()
    if not stripped:
        return []
    if fmt == "auto":
        if stripped.startswith("@"):
            fmt = "bibtex"
        elif "TY  -" in stripped or stripped.startswith("TY  -"):
            fmt = "ris"
        elif stripped.startswith(("[", "{")):
            fmt = "json"
        else:
            fmt = "bibtex"

    items: list[dict[str, Any]] = []
    if fmt == "bibtex":
        entry_pattern = re.compile(r"@(\w+)\s*\{\s*([^,]+),\s*(.*?)(?:\r?\n\s*\}|\}\s*$)", re.DOTALL)
        field_pattern = re.compile(r"(\w+)\s*=\s*[\"{](.*?)[\"}],?", re.DOTALL)
        matches = list(entry_pattern.finditer(content))
        if not matches:
            matches = list(re.finditer(r"@(\w+)\s*\{\s*([^,]+),", content))
            for i, m in enumerate(matches):
                items.append({
                    "index": i + 1,
                    "outcome": "will_import",
                    "metadata": {
                        "title": f"BibTeX Entry {m.group(2).strip()}",
                        "authors": ["Synthetic Author"],
                        "year": 2025,
                        "venue": "Synthetic Venue",
                        "doi": f"10.0000/bibtex.{i + 1}",
                    },
                    "warnings": [],
                    "reason_code": None,
                })
        else:
            for i, m in enumerate(matches):
                fields = dict(field_pattern.findall(m.group(3)))
                title = fields.get("title", f"BibTeX Entry {m.group(2).strip()}")
                author_str = fields.get("author", "Synthetic Author")
                authors = [a.strip() for a in re.split(r"\s+and\s+", author_str) if a.strip()]
                year = int(fields.get("year", 2025)) if fields.get("year", "").isdigit() else 2025
                venue = fields.get("journal", fields.get("booktitle", "Synthetic Venue"))
                doi = fields.get("doi", f"10.0000/bibtex.{i + 1}")
                items.append({
                    "index": i + 1,
                    "outcome": "will_import",
                    "metadata": {
                        "title": title,
                        "authors": authors,
                        "year": year,
                        "venue": venue,
                        "doi": doi,
                    },
                    "warnings": [],
                    "reason_code": None,
                })
    elif fmt == "ris":
        records = [r for r in re.split(r"\nER\s{2}-|\r\nER\s{2}-", content) if r.strip()]
        for i, rec in enumerate(records):
            title_m = re.search(r"^(?:TI|T1)\s{2}-\s*(.*)$", rec, re.MULTILINE)
            author_m = re.findall(r"^(?:AU|A1)\s{2}-\s*(.*)$", rec, re.MULTILINE)
            year_m = re.search(r"^(?:PY|Y1)\s{2}-\s*(\d{4})", rec, re.MULTILINE)
            venue_m = re.search(r"^(?:JO|JF|JA)\s{2}-\s*(.*)$", rec, re.MULTILINE)
            doi_m = re.search(r"^DO\s{2}-\s*(.*)$", rec, re.MULTILINE)
            title = title_m.group(1).strip() if title_m else f"RIS Entry {i + 1}"
            authors = [a.strip() for a in author_m] or ["Synthetic Author"]
            year = int(year_m.group(1)) if year_m else 2025
            venue = venue_m.group(1).strip() if venue_m else "Synthetic Journal"
            doi = doi_m.group(1).strip() if doi_m else f"10.0000/ris.{i + 1}"
            items.append({
                "index": i + 1,
                "outcome": "will_import",
                "metadata": {
                    "title": title,
                    "authors": authors,
                    "year": year,
                    "venue": venue,
                    "doi": doi,
                },
                "warnings": [],
                "reason_code": None,
            })
    else:
        try:
            data = json.loads(content)
            if isinstance(data, dict):
                data = data.get("items") or [data]
            if isinstance(data, list):
                for i, entry in enumerate(data):
                    raw = entry.get("data") if isinstance(entry.get("data"), dict) else entry
                    title = str(raw.get("title") or f"Imported Entry {i + 1}")
                    creators = raw.get("creators") or raw.get("author") or []
                    authors = []
                    if isinstance(creators, list):
                        for c in creators:
                            if isinstance(c, dict):
                                name = c.get("name") or f"{c.get('given', '')} {c.get('family', '')}".strip() or f"{c.get('lastName', '')}"
                                if name:
                                    authors.append(name)
                            elif isinstance(c, str):
                                authors.append(c)
                    else:
                        authors = [str(creators)]
                    year = 2025
                    date = str(raw.get("date") or raw.get("issued") or "")
                    dm = re.search(r"\d{4}", date)
                    if dm:
                        year = int(dm.group(0))
                    venue = str(raw.get("publicationTitle") or raw.get("container-title") or "Synthetic Venue")
                    doi = str(raw.get("DOI") or raw.get("doi") or f"10.0000/json.{i + 1}")
                    items.append({
                        "index": i + 1,
                        "outcome": "will_import",
                        "metadata": {
                            "title": title,
                            "authors": authors or ["Synthetic Author"],
                            "year": year,
                            "venue": venue,
                            "doi": doi,
                        },
                        "warnings": [],
                        "reason_code": None,
                    })
        except Exception:
            pass
    return items


class SyntheticRelayRuntime:
    """Offline process boundary for UI tests; never starts a campus transport."""

    def __init__(self, owner: "SyntheticClient", *, available: bool = False) -> None:
        self.owner = owner
        self.available = available
        self.running = False

    def status(self) -> dict[str, Any]:
        return {"available": self.available, "running": self.running,
                "state": "running" if self.running else "stopped" if self.available else "unavailable",
                "managed_by_connect": self.running, "browser_enabled": False, "auto_start": False, "confirmation_required": True,
                "reason_code": None if self.available else "relay_not_bundled",
                "action_hint": "Synthetic managed Relay; no network transport is started." if self.available else
                               "This synthetic basic client has no bundled Relay runtime."}

    def _activate(self, operation: str, allow_campus_transport: bool) -> dict[str, Any]:
        if allow_campus_transport is not True:
            raise RelayError("relay_confirmation_required", "Allow this computer's network transport before starting Relay.")
        if not self.available:
            raise RelayError("relay_not_bundled", "This client has no bundled Relay runtime.")
        if not self.owner.config.effective_api_key:
            raise RelayError("relay_account_required", "Log in to the local Mdtero account first.")
        with self.owner.lock:
            self.owner.relay_runtime_calls.append({"operation": operation, "allow_campus_transport": True})
            self.running = True
            return self.status()

    def start(self, *, allow_campus_transport: bool) -> dict[str, Any]:
        return self._activate("start", allow_campus_transport)

    def restart(self, *, allow_campus_transport: bool) -> dict[str, Any]:
        return self._activate("restart", allow_campus_transport)

    def stop(self) -> dict[str, Any]:
        with self.owner.lock:
            self.owner.relay_runtime_calls.append({"operation": "stop"})
            self.running = False
            return self.status()

    def close(self) -> None:
        self.running = False


class SyntheticClient(MdteroClient):
    def __init__(self) -> None:
        super().__init__(MdteroConfig(api_key=SYNTHETIC_KEY, api_base_url="https://synthetic.invalid"))
        self.lock = threading.RLock()
        self.reset()

    def reset(self, settings: dict[str, Any] | None = None) -> None:
        with self.lock:
            self.papers = copy.deepcopy(INITIAL_PAPERS)
            self.committed_imports: dict[str, dict[str, Any]] = {}
            self.calls: list[dict[str, Any]] = []
            self.provider_calls: list[dict[str, Any]] = []
            self.agent_calls: list[dict[str, Any]] = []
            self.discovery_calls: list[dict[str, Any]] = []
            self.relay_runtime_calls: list[dict[str, Any]] = []
            self.settings = {"authenticated": True, "invalid_credentials": False, "fail_next": None, **(settings or {})}
            self.config.api_key = SYNTHETIC_KEY if self.settings["authenticated"] else None
            self.relay_runtime = SyntheticRelayRuntime(self, available=bool(self.settings.get("relay_runtime_available", False)))

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return copy.deepcopy({"papers": self.papers, "calls": self.calls,
                                  "provider_calls": self.provider_calls, "agent_calls": self.agent_calls,
                                  "discovery_calls": self.discovery_calls, "relay_runtime_calls": self.relay_runtime_calls,
                                  "relay_runtime": self.relay_runtime.status()})

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
                body = kwargs["json"]
                assert isinstance(body.get("dry_run"), bool), "dry_run must be explicit"
                dry_run = body["dry_run"]
                request_id = str(body.get("request_id") or "")
                if not dry_run and request_id and request_id in self.committed_imports:
                    return copy.deepcopy(self.committed_imports[request_id])
                content = str(body.get("content") or "")
                fmt = str(body.get("format") or "auto").lower()

                if len(content.encode("utf-8")) > 1024 * 1024:
                    raise MdteroApiError({
                        "status_code": 413,
                        "reason_code": "import_too_large",
                        "action_hint": "Bibliography content exceeds the 1 MiB limit.",
                    })

                if fmt in {"rdf", "zotero_rdf"} or "rdf:RDF" in content:
                    raise MdteroApiError({
                        "status_code": 400,
                        "reason_code": "unsupported_format",
                        "action_hint": "Zotero RDF is not supported. Please export as BibTeX, RIS, or CSL JSON.",
                    })

                parsed_items = _parse_synthetic_import(content, fmt)
                if not parsed_items:
                    # Fallback for connector or minimal test payload
                    parsed_items = [{
                        "index": 1,
                        "outcome": "will_import" if dry_run else "imported",
                        "metadata": {
                            "title": "Synthetic import",
                            "authors": ["Ada Example"],
                            "year": 2025,
                            "venue": "Synthetic Journal",
                            "doi": "10.0000/synthetic.import",
                        },
                        "warnings": [],
                        "reason_code": None,
                    }]

                if len(parsed_items) > 500:
                    raise MdteroApiError({
                        "status_code": 413,
                        "reason_code": "too_many_items",
                        "action_hint": "Import up to 500 items at a time.",
                    })

                existing_titles = {p["title"].strip().lower() for p in self.papers}
                existing_count = 0
                duplicate_count = 0
                for item in parsed_items:
                    item_title = item["metadata"]["title"].strip().lower()
                    if item_title in existing_titles or "existing" in item_title:
                        item["outcome"] = "existing"
                        existing_count += 1
                    elif "duplicate" in item_title:
                        item["outcome"] = "duplicate"
                        duplicate_count += 1
                    else:
                        item["outcome"] = "will_import" if dry_run else "imported"

                importable_count = (len(parsed_items) - existing_count - duplicate_count) if dry_run else 0
                imported_count = (len(parsed_items) - existing_count - duplicate_count) if not dry_run else 0

                if not dry_run:
                    for item in parsed_items:
                        if item["outcome"] == "imported":
                            doc_id = max([p["document_id"] for p in self.papers] or [100]) + 11
                            new_paper = {
                                "document_id": doc_id,
                                "title": item["metadata"]["title"],
                                "authors": item["metadata"]["authors"],
                                "year": item["metadata"]["year"],
                                "venue": item["metadata"]["venue"],
                                "doi": item["metadata"]["doi"],
                                "tags": ["Imported"],
                                "has_saved_text": False,
                            }
                            self.papers.append(new_paper)

                result = {
                    "schema_version": 1,
                    "format": fmt,
                    "dry_run": dry_run,
                    "metadata_only": True,
                    "request_id": body.get("request_id"),
                    "limits": {"max_bytes": 1048576, "max_items": 500},
                    "summary": {
                        "total": len(parsed_items),
                        "importable": importable_count,
                        "imported": imported_count,
                        "existing": existing_count,
                        "duplicates": duplicate_count,
                        "skipped": 0,
                        "attached": 0,
                    },
                    "items": parsed_items,
                    "created_count": imported_count,
                }
                if not dry_run and request_id:
                    self.committed_imports[request_id] = copy.deepcopy(result)
                return result
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


def synthetic_provider_http(url: str, **_kwargs: Any) -> httpx.Response:
    # Never record kwargs: the production check attaches a private key there.
    with client.lock:
        client.provider_calls.append({"method": "GET", "url": url})
    assert url == "https://api.openalex.org/works/W2741809807"
    return httpx.Response(200, json={"id": "https://openalex.org/W2741809807"}, request=httpx.Request("GET", url))


class SyntheticAgentRuntime(AgentRuntime):
    """Keep real approval/run controls; replace just the SDK boundary offline."""

    def _dependency_info(self) -> dict[str, Any]:
        return {"available": True, "node_version": "v22.19.0", "sdk_version": "1.3.0", "models": {
            "openai": [{"id": "gpt-4.1-mini", "name": "Synthetic model", "max_output_tokens": 4096}],
            "anthropic": [{"id": "claude-sonnet-4-5", "name": "Synthetic model", "max_output_tokens": 4096}],
            "google": [{"id": "gemini-2.5-flash", "name": "Synthetic model", "max_output_tokens": 4096}],
            "openrouter": [{"id": "openai/gpt-4.1-mini", "name": "Synthetic model", "max_output_tokens": 4096}],
        }}

    def _execute_worker(self, payload: dict[str, Any], cancel_event: threading.Event, run_id: str) -> dict[str, Any]:
        # Receipts intentionally exclude api_key and any SDK implementation state.
        with client.lock:
            client.agent_calls.append({"run_id": run_id, "payload": copy.deepcopy({
                key: value for key, value in payload.items() if key != "api_key"
            })})
            delay = float(client.settings.get("agent_delay_seconds", 0.05))
        cancel_event.wait(delay)
        return {"text": 'Synthetic metadata summary [11]. <img src=x onerror="window.agentXss=true">',
                "usage": {"input": 50, "output": 20, "totalTokens": 70}, "engine": "pi", "sdk_version": "1.3.0",
                "provider": payload["provider"], "model": payload["model"], "scope": "selected_metadata",
                "full_text_included": False, "model_requests": 1, "max_output_tokens": payload["max_output_tokens"]}


def local_services(settings: dict[str, Any] | None = None) -> tuple[ProviderStore, SyntheticAgentRuntime]:
    providers = ProviderStore(config=client.config, environ={}, keyring_backend=None, http_get=synthetic_provider_http)
    runtime = SyntheticAgentRuntime(full_mode=bool((settings or {}).get("full_mode", False)),
                                    providers=providers, library=LibraryClient(client))
    return providers, runtime


bridge: ConnectBridge | None = None


def synthetic_discovery(query: str, **kwargs: Any) -> dict[str, Any]:
    # Verify local selection without ever exposing the supplied OpenAlex key.
    with client.lock:
        client.discovery_calls.append({"query": query, "providers": kwargs.get("providers"),
                                       "enrich": kwargs.get("enrich"), "key_configured": bool(kwargs.get("openalex_api_key"))})
    return {"provider": "openalex", "source": "local_multi_source", "query": query,
            "items": [{"title": 'Synthetic local discovery <script>window.discoveryXss=true</script>',
                       "doi": "10.0000/synthetic.discovery", "authors": ["Synthetic Author"], "year": 2025}],
            "result_count": 1, "meta": {"local": True}, "discovery_diagnostics": {"server_openalex_attempted": False}}


bridge_module.search_local_discovery = synthetic_discovery
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
        assert bridge is not None
        bridge.agent_runtime.close()
        bridge.relay_runtime.close()
        bridge.providers.clear_session()
        client.reset(settings)
        bridge.providers, bridge.agent_runtime = local_services(settings)
        bridge.relay_runtime = client.relay_runtime
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
    origin_port = int(os.environ.get("MDTERO_CONNECT_TEST_ORIGIN_PORT", "18741"))
    control_port = int(os.environ.get("MDTERO_CONNECT_TEST_CONTROL_PORT", "18742"))
    control = ThreadingHTTPServer(("127.0.0.1", control_port), ControlHandler)
    providers, runtime = local_services()
    with ConnectBridge(host="127.0.0.1", port=origin_port, client=client, static_dir=APP_DIR,
                       providers=providers, agent_runtime=runtime, relay_runtime=client.relay_runtime) as bridge:
        threading.Thread(target=control.serve_forever, daemon=True).start()
        print(f"Synthetic-only Connect fixture at {bridge.base_url}", flush=True)
        stopped.wait()
    control.shutdown()
    control.server_close()
