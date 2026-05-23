from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
from typing import Any

import httpx
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from . import __version__
from .acquisition import AcquisitionError
from .auth import run_web_login
from .client import DiscoveryError, MdteroClient
from .config import MdteroConfig, config_path, load_config, save_config
from .projects import (
    PaperRecord,
    add_paper,
    bind_server_project,
    import_bib,
    init_project,
    load_project,
    paper_to_document,
    paper_from_submission,
    project_path,
    project_pending_papers,
    project_task_ids,
    remove_paper,
    save_project,
    update_paper_submission,
    update_task,
)
from .workflow import parse_trace_from_route, status_trace, upload_trace

ACADEMIC_OPTIONS = [
    {
        "index": "1",
        "label": "Elsevier key",
        "url": "https://dev.elsevier.com/apikey/manage",
        "field": "elsevier_api_key",
        "prompt": "Elsevier API key",
    },
    {
        "index": "2",
        "label": "Wiley TDM",
        "url": "https://onlinelibrary.wiley.com/library-info/resources/text-and-datamining",
        "field": "wiley_tdm_token",
        "prompt": "Wiley TDM token",
    },
    {
        "index": "3",
        "label": "Semantic Scholar API Key",
        "url": "https://www.semanticscholar.org/product/api#api-key-form",
        "field": "semantic_scholar_api_key",
        "prompt": "Semantic Scholar API key",
    },
]


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    result = args.func(args)
    return int(result or 0)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mdtero")
    parser.add_argument("--version", action="version", version=f"mdtero {__version__}")
    sub = parser.add_subparsers(dest="command")

    setup = _cmd(sub, "setup", "Run the onboarding wizard.", cmd_setup)
    setup.add_argument("--api-key", default="", help="Save an API key during setup for headless servers.")
    _cmd(sub, "doctor", "Check local Mdtero configuration.", cmd_doctor)
    login = _cmd(sub, "login", "Configure OAuth or API-key login.", cmd_login)
    login.add_argument("--api-key", default="")
    login.add_argument("--no-browser", action="store_true", help="Print the loopback web-login URL instead of opening a browser.")
    login.add_argument("--timeout", type=float, default=180.0, help="Seconds to wait for the browser login callback.")

    config = sub.add_parser("config")
    config_sub = config.add_subparsers(dest="config_command")
    _cmd(config_sub, "academic", "Configure optional academic resource keys.", cmd_config_academic)
    zotero_config = _cmd(config_sub, "zotero", "Configure Zotero library credentials.", cmd_config_zotero)
    zotero_config.add_argument("--library-id")
    zotero_config.add_argument("--library-type", choices=["user", "group"], default=None)
    zotero_config.add_argument("--api-key")

    parse = _cmd(sub, "parse", "Parse one DOI/URL or upload files.", cmd_parse)
    parse.add_argument("input", nargs="?")
    parse.add_argument("--file", type=Path)
    parse.add_argument("--batch", type=Path)
    parse.add_argument("--json", action="store_true")
    parse.add_argument("--wait", action="store_true")
    parse.add_argument("--trace", action="store_true")

    discover = _cmd(sub, "discover", "Search papers.", cmd_discover)
    discover.add_argument("query")
    discover.add_argument("--limit", type=int, default=10)
    discover.add_argument("--add", action="store_true", help="Add selected discovery results to the current project.")
    discover.add_argument("--select", default="", help="Result numbers to add, for example `1 3`, `1,3`, or `all`. Defaults to all with --add.")
    discover.add_argument("--interactive", action="store_true", help="Show results and prompt for numbers to add to the current project.")
    discover.add_argument("--json", action="store_true")

    project = sub.add_parser("project")
    project_sub = project.add_subparsers(dest="project_command")
    project_init = _cmd(project_sub, "init", "Initialize a local Mdtero project.", cmd_project_init)
    project_init.add_argument("--name")
    project_init.add_argument("--json", action="store_true")
    project_add = _cmd(project_sub, "add", "Add one DOI/URL/file to the current project.", cmd_project_add)
    project_add.add_argument("input")
    project_add.add_argument("--json", action="store_true")
    project_link = _cmd(project_sub, "link", "Bind this local project to an existing server project id.", cmd_project_link)
    project_link.add_argument("--server-project-id", required=True)
    project_link.add_argument("--json", action="store_true")
    project_create_server = _cmd(project_sub, "create-server", "Create and bind a server project for RAG.", cmd_project_create_server)
    project_create_server.add_argument("--name")
    project_create_server.add_argument("--description")
    project_create_server.add_argument("--json", action="store_true")
    project_remove = _cmd(project_sub, "remove", "Remove one project paper by input or task id.", cmd_project_remove)
    project_remove.add_argument("input")
    project_remove.add_argument("--json", action="store_true")
    project_bib = _cmd(project_sub, "import-bib", "Import DOI/URL entries from one or more BibTeX files.", cmd_project_import_bib)
    project_bib.add_argument("paths", nargs="+", type=Path)
    project_bib.add_argument("--json", action="store_true")
    project_parse = _cmd(project_sub, "parse", "Submit pending project papers to Mdtero.", cmd_project_parse)
    project_parse.add_argument("--limit", type=int, default=0)
    project_parse.add_argument("--include-failed", action="store_true")
    project_parse.add_argument("--wait", action="store_true")
    project_parse.add_argument("--json", action="store_true")
    project_refresh = _cmd(project_sub, "refresh", "Refresh task status for project papers.", cmd_project_refresh)
    project_refresh.add_argument("--wait", action="store_true")
    project_refresh.add_argument("--json", action="store_true")
    project_download = _cmd(project_sub, "download", "Download completed project artifacts.", cmd_project_download)
    project_download.add_argument("--artifact", default="paper_md")
    project_download.add_argument("--output-dir", type=Path, default=Path("mdtero-output"))
    project_download.add_argument("--json", action="store_true")
    project_ingest = _cmd(project_sub, "ingest", "Import succeeded parse tasks into the linked server project for RAG.", cmd_project_ingest)
    project_ingest.add_argument("--json", action="store_true")
    project_list = _cmd(project_sub, "list", "List papers in the current project.", cmd_project_status)
    project_list.add_argument("--json", action="store_true")
    project_status = _cmd(project_sub, "status", "Show current project status.", cmd_project_status)
    project_status.add_argument("--json", action="store_true")

    parse_bib = _cmd(sub, "parse-bib", "Import BibTeX DOI/URL entries into the current project.", cmd_project_import_bib)
    parse_bib.add_argument("paths", nargs="+", type=Path)

    zotero = sub.add_parser("zotero")
    zotero_sub = zotero.add_subparsers(dest="zotero_command")
    zotero_import = _cmd(zotero_sub, "import", "Import a Zotero collection into the current project.", cmd_zotero_import)
    zotero_import.add_argument("--collection")
    zotero_import.add_argument("--limit", type=int, default=50)
    zotero_import.add_argument("--library-id")
    zotero_import.add_argument("--library-type", choices=["user", "group"])
    zotero_import.add_argument("--api-key")
    zotero_import.add_argument("--json", action="store_true")
    zotero_sync = _cmd(zotero_sub, "sync", "Sync Mdtero parse state back to Zotero notes/tags.", cmd_zotero_sync)
    zotero_sync.add_argument("--json", action="store_true")

    translate = _cmd(sub, "translate", "Request server-side translation.", cmd_translate)
    translate.add_argument("task_or_file")
    translate.add_argument("--to", default="zh-CN")
    translate.add_argument("--json", action="store_true")

    rag = sub.add_parser("rag")
    rag_sub = rag.add_subparsers(dest="rag_command")
    rag_build = _cmd(rag_sub, "build", "Request server-side project RAG build.", cmd_rag_build)
    rag_build.add_argument("--project-id")
    rag_build.add_argument("--json", action="store_true")
    rag_query = _cmd(rag_sub, "query", "Query server-side project RAG.", cmd_rag_query)
    rag_query.add_argument("question")
    rag_query.add_argument("--project-id")
    rag_query.add_argument("--json", action="store_true")
    rag_status = _cmd(rag_sub, "status", "Show RAG status.", cmd_rag_status)
    rag_status.add_argument("--project-id")
    rag_status.add_argument("--json", action="store_true")

    mcp = sub.add_parser("mcp")
    mcp_sub = mcp.add_subparsers(dest="mcp_command")
    _cmd(mcp_sub, "serve", "Serve local project context over FastMCP.", cmd_mcp_serve)

    status = _cmd(sub, "status", "Poll one task and update the current project.", cmd_status)
    status.add_argument("task_id")
    status.add_argument("--wait", action="store_true")
    status.add_argument("--json", action="store_true")
    status.add_argument("--trace", action="store_true")

    download = _cmd(sub, "download", "Download one task artifact.", cmd_download)
    download.add_argument("task_id")
    download.add_argument("artifact", nargs="?", default="paper_md")
    download.add_argument("--output-dir", type=Path, default=Path.cwd())
    download.add_argument("--json", action="store_true")

    agent = sub.add_parser("agent")
    agent_sub = agent.add_subparsers(dest="agent_command")
    agent_detect = _cmd(agent_sub, "detect", "Detect local agent workspaces before installing skills.", cmd_agent_detect)
    agent_detect.add_argument("--root", type=Path)
    agent_detect.add_argument("--json", action="store_true")
    agent_install = _cmd(agent_sub, "install", "Detect local agents and install Mdtero skills.", cmd_agent_install)
    agent_install.add_argument("--target", action="append", choices=["codex", "claude_code", "gemini_cli", "hermes", "opencode"])
    agent_install.add_argument("--root", type=Path)
    agent_install.add_argument("--all", action="store_true")
    agent_install.add_argument("--dry-run", action="store_true")
    agent_install.add_argument("--json", action="store_true")
    agent_install.add_argument("--interactive", action="store_true", help="Interactively select detected agent workspaces to configure.")
    agent_uninstall = _cmd(agent_sub, "uninstall", "Remove Mdtero skills from selected agents.", cmd_agent_uninstall)
    agent_uninstall.add_argument("--target", action="append", required=True, choices=["codex", "claude_code", "gemini_cli", "hermes", "opencode"])
    agent_uninstall.add_argument("--root", type=Path)
    agent_uninstall.add_argument("--dry-run", action="store_true")
    agent_uninstall.add_argument("--json", action="store_true")

    _cmd(sub, "tui", "Open the Textual dashboard.", cmd_tui)
    return parser


def _cmd(subparsers: Any, name: str, help_text: str, func: Any) -> argparse.ArgumentParser:
    parser = subparsers.add_parser(name, help=help_text)
    parser.set_defaults(func=func)
    return parser


def cmd_setup(_args: argparse.Namespace) -> int:
    console = Console()
    console.rule("[bold]Mdtero setup")
    cfg = load_config()
    if getattr(_args, "api_key", ""):
        cfg.api_key = _normalize_api_key_arg(str(_args.api_key), console=console)
        if not cfg.api_key:
            return 2
        save_config(cfg)
        console.print("Step 1: saved API-key login for this machine.")
    elif cfg.is_authenticated:
        console.print(f"Step 1: using existing API-key login from {cfg.api_key_source}.")
    else:
        console.print("Step 1: authenticate.")
        if Confirm.ask("Use API-key login for this machine?", default=True):
            cfg.api_key = _normalize_api_key_arg(Prompt.ask("Paste Mdtero API key", password=True), console=console)
            if not cfg.api_key:
                return 2
            save_config(cfg)
        else:
            _login_with_browser(cfg, console, timeout_seconds=180.0, no_browser=False)
    _configure_academic(cfg, console)
    console.print("\n[bold green]Configuration complete.[/bold green]")
    _print_next_steps(console)
    return 0


def cmd_login(args: argparse.Namespace) -> int:
    cfg = load_config()
    console = Console()
    if args.api_key is not None and str(args.api_key) != "":
        cfg.api_key = _normalize_api_key_arg(str(args.api_key), console=console)
        if not cfg.api_key:
            return 2
        path = save_config(cfg)
        console.print(f"Saved API key to {path}")
        return 0
    _login_with_browser(cfg, console, timeout_seconds=args.timeout, no_browser=args.no_browser)
    return 0


def _normalize_api_key_arg(value: str, *, console: Console) -> str | None:
    key = str(value or "").strip()
    if not key:
        console.print("[red]API key cannot be empty.[/red]")
        return None
    return key


def _login_with_browser(cfg: MdteroConfig, console: Console, *, timeout_seconds: float, no_browser: bool) -> None:
    if no_browser:
        console.print("Printing a loopback web-login URL instead of opening a browser.")
        console.print("Use `mdtero login --api-key <key>` for remote/headless servers where 127.0.0.1 cannot receive the browser callback.")
        console.print("Open the URL below from a browser that can reach this machine's loopback callback. Waiting for the callback...")
        opener = lambda url: console.print(f"  {url}")
    else:
        console.print(f"Opening {cfg.site_base_url}/auth for Mdtero web login...")
        opener = None
    result = run_web_login(cfg.site_base_url, timeout_seconds=timeout_seconds, open_browser=opener) if opener else run_web_login(cfg.site_base_url, timeout_seconds=timeout_seconds)
    cfg.api_key = result.api_key
    path = save_config(cfg)
    if result.prefix:
        console.print(f"Saved web login API key ({result.prefix}) to {path}")
    else:
        console.print(f"Saved web login API key to {path}")


def cmd_doctor(_args: argparse.Namespace) -> int:
    cfg = load_config()
    console = Console()
    table = Table("Check", "Status", "Detail")
    table.add_row("API key", "ok" if cfg.is_authenticated else "missing", cfg.api_key_source)
    table.add_row("Config", "ok" if config_path().exists() else "not created", str(config_path()))
    table.add_row("API base", "ok", cfg.api_base_url)
    table.add_row(*_dependency_check_row("curl_cffi", import_name="curl_cffi.requests", ok_detail="local route acquisition", missing_detail="httpx fallback only"))
    table.add_row(*_dependency_check_row("FastMCP", import_name="fastmcp", ok_detail="MCP server available", missing_detail="install mdtero with FastMCP support"))
    table.add_row(*_dependency_check_row("pyzotero", import_name="pyzotero", ok_detail="Zotero client available", missing_detail="Zotero import/sync unavailable"))
    table.add_row("Semantic Scholar", "ok" if cfg.has_semantic_scholar_key else "optional", "local discovery" if cfg.has_semantic_scholar_key else "server OpenAlex fallback")
    table.add_row("Zotero config", "ok" if _zotero_configured(cfg) else "optional", _zotero_config_detail(cfg))
    current_project = project_path(Path.cwd())
    table.add_row("Project", "ok" if current_project.exists() else "not initialized", str(current_project))
    console.print(table)
    return 0 if cfg.is_authenticated else 1


def _dependency_check_row(label: str, *, import_name: str, ok_detail: str, missing_detail: str) -> tuple[str, str, str]:
    try:
        available = importlib.util.find_spec(import_name) is not None
    except (ImportError, AttributeError, ValueError):
        available = False
    return (label, "ok" if available else "missing", ok_detail if available else missing_detail)


def _zotero_configured(cfg: MdteroConfig) -> bool:
    return bool(cfg.zotero.library_id and cfg.zotero.api_key)


def _zotero_config_detail(cfg: MdteroConfig) -> str:
    if not cfg.zotero.library_id and not cfg.zotero.api_key:
        return "run mdtero config zotero"
    if not cfg.zotero.library_id:
        return "missing library id"
    if not cfg.zotero.api_key:
        return "missing API key"
    return f"{cfg.zotero.library_type}:{cfg.zotero.library_id}"


def cmd_config_academic(_args: argparse.Namespace) -> int:
    cfg = load_config()
    _configure_academic(cfg, Console())
    return 0


def cmd_config_zotero(args: argparse.Namespace) -> int:
    cfg = load_config()
    console = Console()
    cfg.zotero.library_id = args.library_id or Prompt.ask("Zotero library id", default=cfg.zotero.library_id or "")
    cfg.zotero.library_type = args.library_type or Prompt.ask("Zotero library type", choices=["user", "group"], default=cfg.zotero.library_type or "user")
    cfg.zotero.api_key = args.api_key or Prompt.ask("Zotero API key", password=True, default=cfg.zotero.api_key or "")
    path = save_config(cfg)
    console.print(f"Saved Zotero config to {path}")
    return 0


def cmd_parse(args: argparse.Namespace) -> int:
    client = MdteroClient()
    submissions: list[tuple[dict[str, Any], str, str]] = []
    traces = []
    if args.batch:
        for path in sorted(args.batch.iterdir()):
            if path.suffix.lower() in {".pdf", ".epub", ".html", ".htm", ".xml"}:
                result = client.upload(path)
                submissions.append((result, str(path), f"file:{path.suffix.lower().lstrip('.')}"))
                traces.append(upload_trace(path, result).to_dict())
    elif args.file:
        result = client.upload(args.file, source_input=args.input)
        submissions.append((result, args.input or str(args.file), f"file:{args.file.suffix.lower().lstrip('.')}"))
        traces.append(upload_trace(args.file, result).to_dict())
    else:
        if not args.input:
            raise SystemExit("parse requires <doi-or-url>, --file, or --batch")
        try:
            route, result, acquisition = client.parse_with_route(args.input)
        except AcquisitionError as exc:
            failure = {
                "status": "failed",
                "reason_code": exc.reason_code,
                "action_hint": exc.action_hint,
                "diagnostics": exc.diagnostics,
            }
            _print_result(failure, json_output=args.json or args.trace)
            return 2
        submissions.append((result, args.input, "manual"))
        traces.append(parse_trace_from_route(args.input, route, result).to_dict())
    for result, input_value, source in submissions:
        if result.get("task_id"):
            add_paper(Path.cwd(), paper_from_submission(input_value, result, source=source))
            if args.wait:
                task = client.wait(str(result["task_id"]))
                update_task(Path.cwd(), task)
                result["final_task"] = task
    results = [result for result, _, _ in submissions]
    payload = results[0] if len(results) == 1 else {"items": results}
    if args.trace:
        payload = {"result": payload, "workflow": traces[0] if len(traces) == 1 else traces}
    _print_result(payload, json_output=args.json or args.trace)
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    try:
        result = MdteroClient().discover(args.query, limit=args.limit)
    except DiscoveryError as exc:
        if args.json:
            print(json.dumps(exc.payload, indent=2, ensure_ascii=False))
        else:
            Console().print(f"Discovery failed: {exc.payload.get('error_code')}")
            Console().print(str(exc.payload.get("action_hint") or ""))
        return 2
    project_add = None
    if args.interactive:
        selection = _prompt_discovery_selection(result)
        try:
            project_add = _add_discovery_results_to_project(result, selection=selection)
        except ValueError as exc:
            if args.json:
                print(json.dumps({"status": "failed", "error_code": "invalid_discovery_selection", "message": str(exc)}, indent=2, ensure_ascii=False))
            else:
                Console().print(f"Invalid selection: {exc}")
            return 2
        result["project_add"] = project_add
    elif args.add:
        try:
            project_add = _add_discovery_results_to_project(result, selection=args.select or "all")
        except ValueError as exc:
            if args.json:
                print(json.dumps({"status": "failed", "error_code": "invalid_discovery_selection", "message": str(exc)}, indent=2, ensure_ascii=False))
            else:
                Console().print(f"Invalid selection: {exc}")
            return 2
        result["project_add"] = project_add
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    _print_discovery_table(result)
    if project_add is not None:
        Console().print(f"Added {project_add['added_count']} discovery result(s) to project; skipped {project_add['skipped_count']}.")
    return 0


def _prompt_discovery_selection(result: dict[str, Any]) -> str:
    console = Console(stderr=True)
    _print_discovery_table(result, console=console)
    console.print("Select result numbers to add to the current project. Use spaces for multi-select, `all` for all results, or Enter to skip.")
    return Prompt.ask("Add papers", default="", console=console).strip()


def _print_discovery_table(result: dict[str, Any], *, console: Console | None = None) -> None:
    table = Table("No", "Year", "Title", "DOI", "Source")
    for index, item in enumerate(result.get("items") or [], start=1):
        table.add_row(str(index), str(item.get("year") or ""), str(item.get("title") or ""), str(item.get("doi") or ""), str(item.get("source") or "openalex"))
    (console or Console()).print(table)


def _add_discovery_results_to_project(result: dict[str, Any], *, selection: str) -> dict[str, Any]:
    items = [item for item in result.get("items") or [] if isinstance(item, dict)]
    selected_indices = _parse_result_selection(selection, max_count=len(items))
    state = load_project(Path.cwd()) if project_path(Path.cwd()).exists() else None
    existing_inputs = {paper.input for paper in state.papers} if state else set()
    added: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for index in selected_indices:
        item = items[index - 1]
        target = _discovery_parse_target(item)
        if not target:
            skipped.append({"index": index, "reason_code": "missing_doi_or_url", "title": item.get("title")})
            continue
        if target in existing_inputs:
            skipped.append({"index": index, "reason_code": "already_in_project", "input": target})
            continue
        add_paper(
            Path.cwd(),
            PaperRecord(
                input=target,
                title=str(item.get("title") or "") or None,
                doi=str(item.get("doi") or "") or None,
                source=f"discover:{item.get('source') or result.get('source') or 'unknown'}",
            ),
        )
        existing_inputs.add(target)
        added.append({"index": index, "input": target, "title": item.get("title"), "doi": item.get("doi")})
    return {
        "added_count": len(added),
        "skipped_count": len(skipped),
        "added": added,
        "skipped": skipped,
    }


def _parse_result_selection(selection: str, *, max_count: int) -> list[int]:
    if max_count <= 0:
        return []
    cleaned = str(selection or "").strip().lower()
    if not cleaned:
        return []
    if cleaned in {"all", "a", "*"}:
        return list(range(1, max_count + 1))
    values: list[int] = []
    for token in cleaned.replace(",", " ").split():
        try:
            value = int(token)
        except ValueError as exc:
            raise ValueError(f"selection `{token}` is not a number") from exc
        if value < 1 or value > max_count:
            raise ValueError(f"selection `{value}` is outside 1..{max_count}")
        if value not in values:
            values.append(value)
    return values


def _discovery_parse_target(item: dict[str, Any]) -> str | None:
    doi = str(item.get("doi") or "").strip()
    if doi:
        return doi
    url = str(item.get("url") or "").strip()
    return url or None


def _project_payload(state: Any) -> dict[str, Any]:
    succeeded = [paper for paper in state.papers if paper.status == "succeeded" and paper.task_id]
    pending = [paper for paper in state.papers if paper.status in {"pending", "created"} and not paper.task_id]
    failed = [paper for paper in state.papers if paper.status == "failed"]
    running = [paper for paper in state.papers if paper.task_id and paper.status not in {"succeeded", "failed", "cancelled"}]
    return {
        "name": state.name,
        "server_project_id": state.server_project_id,
        "paper_count": len(state.papers),
        "pending_count": len(pending),
        "running_count": len(running),
        "succeeded_count": len(succeeded),
        "failed_count": len(failed),
        "ready_for_ingest_count": len(succeeded),
        "papers": [paper_to_document(paper).to_dict() for paper in state.papers],
    }


def cmd_project_init(args: argparse.Namespace) -> int:
    path = init_project(Path.cwd(), name=args.name)
    state = load_project(Path.cwd())
    payload = _project_payload(state)
    payload["project_path"] = str(path)
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        Console().print(f"Initialized Mdtero project at {path}")
    return 0


def cmd_project_status(args: argparse.Namespace) -> int:
    state = load_project(Path.cwd())
    if getattr(args, "json", False):
        print(json.dumps(_project_payload(state), indent=2, ensure_ascii=False))
        return 0
    table = Table("Input", "Task", "Status", "Reason")
    for paper in state.papers:
        table.add_row(paper.input, paper.task_id or "", paper.status, paper.reason_code or "")
    Console().print(f"Project: {state.name}")
    Console().print(f"Server project: {state.server_project_id or 'not linked'}")
    Console().print(table)
    return 0


def cmd_project_add(args: argparse.Namespace) -> int:
    state = add_paper(Path.cwd(), PaperRecord(input=args.input, source="manual"))
    if args.json:
        print(json.dumps({"status": "added", "input": args.input, "project": _project_payload(state)}, indent=2, ensure_ascii=False))
    else:
        Console().print(f"Added {args.input} to project {state.name}")
    return 0


def cmd_project_link(args: argparse.Namespace) -> int:
    state = bind_server_project(Path.cwd(), args.server_project_id)
    if args.json:
        print(json.dumps({"status": "linked", "server_project_id": state.server_project_id, "project": _project_payload(state)}, indent=2, ensure_ascii=False))
    else:
        Console().print(f"Project {state.name} linked to server project {state.server_project_id}")
    return 0


def cmd_project_create_server(args: argparse.Namespace) -> int:
    root = Path.cwd()
    state = load_project(root)
    name = args.name or state.name
    result = MdteroClient().create_project(name, description=args.description or f"Mdtero local project: {state.name}")
    server_project_id = str(result.get("id") or "").strip()
    if not server_project_id:
        raise SystemExit("Server did not return a project id")
    state = bind_server_project(root, server_project_id)
    payload = {"server_project_id": state.server_project_id, "project": result}
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        Console().print(f"Created server project {state.server_project_id} for {state.name}")
    return 0


def cmd_project_remove(args: argparse.Namespace) -> int:
    state = remove_paper(Path.cwd(), args.input)
    if args.json:
        print(json.dumps({"status": "removed", "input": args.input, "project": _project_payload(state)}, indent=2, ensure_ascii=False))
    else:
        Console().print(f"Project {state.name}: {len(state.papers)} paper(s) remain")
    return 0


def cmd_project_import_bib(args: argparse.Namespace) -> int:
    summary = import_bib(Path.cwd(), args.paths)
    if getattr(args, "json", False):
        summary["project"] = _project_payload(load_project(Path.cwd()))
        print(json.dumps(summary, indent=2, ensure_ascii=False))
    else:
        Console().print(
            f"Imported {summary['imported_count']} BibTeX target(s); skipped {summary['skipped_count']}; project now has {summary['paper_count']} paper(s)."
        )
    return 0


def cmd_project_parse(args: argparse.Namespace) -> int:
    root = Path.cwd()
    state = load_project(root)
    pending = project_pending_papers(state, include_failed=args.include_failed)
    if args.limit and args.limit > 0:
        pending = pending[: args.limit]
    client = MdteroClient()
    results = []
    for paper in pending:
        result = _submit_project_paper(client, paper)
        update_paper_submission(root, paper.input, result)
        if args.wait and result.get("task_id"):
            task = client.wait(str(result["task_id"]))
            update_task(root, task)
            result["final_task"] = task
        results.append({"input": paper.input, "task": result})
    payload = {"submitted_count": len(results), "items": results}
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        table = Table("Input", "Task", "Status", "Reason")
        for item in results:
            task = item["task"]
            table.add_row(item["input"], str(task.get("task_id") or ""), str(task.get("status") or ""), str(task.get("reason_code") or ""))
        Console().print(table)
    return 0


def cmd_project_refresh(args: argparse.Namespace) -> int:
    root = Path.cwd()
    state = load_project(root)
    client = MdteroClient()
    results = []
    for task_id in project_task_ids(state):
        task = client.wait(task_id) if args.wait else client.task(task_id)
        update_task(root, task)
        results.append(task)
    payload = {"refreshed_count": len(results), "items": results}
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        table = Table("Task", "Status", "Reason")
        for task in results:
            table.add_row(str(task.get("task_id") or ""), str(task.get("status") or ""), str(task.get("reason_code") or ""))
        Console().print(table)
    return 0


def cmd_project_download(args: argparse.Namespace) -> int:
    state = load_project(Path.cwd())
    client = MdteroClient()
    downloaded = []
    for paper in state.papers:
        if paper.status != "succeeded" or not paper.task_id:
            continue
        artifact = paper.artifact or args.artifact
        path = client.download(paper.task_id, artifact, args.output_dir)
        downloaded.append({"input": paper.input, "task_id": paper.task_id, "artifact": artifact, "path": str(path)})
    payload = {"downloaded_count": len(downloaded), "items": downloaded}
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        table = Table("Input", "Artifact", "Path")
        for item in downloaded:
            table.add_row(item["input"], item["artifact"], item["path"])
        Console().print(table)
    return 0


def cmd_project_ingest(args: argparse.Namespace) -> int:
    root = Path.cwd()
    state = load_project(root)
    project_id = _server_project_id(args)
    client = MdteroClient()
    ingest = _import_succeeded_tasks_to_server_project(client, state, project_id)
    results = ingest["items"]
    failures = ingest["failures"]
    payload = {
        "server_project_id": project_id,
        "imported_count": len(results),
        "failed_count": len(failures),
        "items": results,
        "failures": failures,
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        table = Table("Input", "Task", "Document", "Status")
        for item in results:
            result = item["result"]
            table.add_row(item["input"], item["task_id"], str(result.get("document_id") or ""), str(result.get("import_status") or ""))
        for item in failures:
            table.add_row(item["input"], item["task_id"], "", f"failed: {item['error_code']}")
        Console().print(table)
        if not results:
            Console().print("No succeeded project tasks are ready to import.")
        for item in failures:
            Console().print(f"Hint for {item['task_id']}: {item['action_hint']}")
    return 1 if failures else 0


def cmd_status(args: argparse.Namespace) -> int:
    client = MdteroClient()
    task = client.wait(args.task_id) if args.wait else client.task(args.task_id)
    update_task(Path.cwd(), task)
    payload = {"task": task, "workflow": status_trace(task).to_dict()} if args.trace else task
    _print_result(payload, json_output=args.json or args.trace)
    return 0


def cmd_download(args: argparse.Namespace) -> int:
    path = MdteroClient().download(args.task_id, args.artifact, args.output_dir)
    payload = {
        "status": "downloaded",
        "task_id": args.task_id,
        "artifact": args.artifact,
        "path": str(path),
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        Console().print(f"Downloaded {args.artifact} to {path}")
    return 0


def cmd_translate(args: argparse.Namespace) -> int:
    target = Path(args.task_or_file)
    client = MdteroClient()
    try:
        if target.exists():
            result = client.translate_text(target.read_text(encoding="utf-8"), filename=target.name, target_language=args.to)
        else:
            result = client.translate_task(args.task_or_file, target_language=args.to)
    except ValueError as exc:
        if str(exc) == "translation_source_artifact_missing":
            payload = {
                "status": "failed",
                "error_code": "translation_source_artifact_missing",
                "task_id": args.task_or_file,
                "action_hint": "The parse task does not expose a server-side paper_md path for translation. Run `mdtero status <task-id> --json`; if only a download artifact is available, download paper_md and run `mdtero translate <paper.md> --to zh-CN --json`.",
                "next_commands": [f"mdtero status {args.task_or_file} --json", f"mdtero download {args.task_or_file} paper_md --output-dir ./mdtero-output --json"],
            }
            _print_result(payload, json_output=args.json)
            return 1
        raise
    _print_result(result, json_output=args.json)
    return 0


def cmd_zotero_import(args: argparse.Namespace) -> int:
    from .config import load_config
    from .zotero import list_zotero_items, make_zotero_client, paper_from_zotero_item

    cfg = load_config()
    if args.library_id:
        cfg.zotero.library_id = args.library_id
    if args.library_type:
        cfg.zotero.library_type = args.library_type
    if args.api_key:
        cfg.zotero.api_key = args.api_key
    client = make_zotero_client(cfg)
    imported = 0
    skipped = 0
    for item in list_zotero_items(client, collection_id=args.collection, limit=args.limit):
        paper = paper_from_zotero_item(item)
        if paper is None:
            skipped += 1
            continue
        add_paper(Path.cwd(), paper)
        imported += 1
    payload = {"imported_count": imported, "skipped_count": skipped}
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        Console().print(f"Imported {imported} Zotero item(s); skipped {skipped}.")
    return 0


def cmd_zotero_sync(_args: argparse.Namespace) -> int:
    from .zotero import make_zotero_client, sync_project_to_zotero

    cfg = load_config()
    state = load_project(Path.cwd())
    client = make_zotero_client(cfg)
    payload = sync_project_to_zotero(client, state.papers)
    save_project(Path.cwd(), state)
    if _args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        Console().print(f"Synced {payload['synced_count']} Zotero item(s); skipped {payload['skipped_count']}.")
    return 0


def cmd_rag_build(_args: argparse.Namespace) -> int:
    root = Path.cwd()
    state = load_project(root)
    client = MdteroClient()
    try:
        project_id, bootstrap = _ensure_server_project_for_rag(client, root, state, getattr(_args, "project_id", None))
    except Exception as exc:
        payload = _rag_bootstrap_failure("build", exc)
        _print_rag_command_failure(payload, json_output=_args.json)
        return 1
    ingest = _import_succeeded_tasks_to_server_project(client, state, project_id)
    if ingest["failures"]:
        payload = {
            "status": "failed",
            "command": "rag_build",
            "reason_code": "server_project_import_failed",
            "error_code": "rag_precondition_failed",
            "server_project_id": project_id,
            "bootstrap": bootstrap,
            "ingest": ingest,
            "action_hint": "Some succeeded parse tasks could not be imported into the server project. Fix the import failures, rerun `mdtero project ingest --json`, then rerun `mdtero rag build --json`.",
            "next_commands": ["mdtero project ingest --json", "mdtero rag status --json", "mdtero rag build --json"],
        }
        _print_rag_command_failure(payload, json_output=_args.json)
        return 1
    try:
        result = client.rag_build(project_id)
    except Exception as exc:
        payload = _rag_command_failure("build", project_id, exc)
        payload["bootstrap"] = bootstrap
        payload["ingest"] = ingest
        _print_rag_command_failure(payload, json_output=_args.json)
        return 1
    result.setdefault("server_project_id", project_id)
    result.setdefault("bootstrap", bootstrap)
    result.setdefault("ingest", ingest)
    _print_result(result, json_output=_args.json)
    return 0


def cmd_rag_query(args: argparse.Namespace) -> int:
    project_id = _server_project_id_or_report(args, command="query")
    if project_id is None:
        return 1
    try:
        result = MdteroClient().rag_query(project_id, args.question)
    except Exception as exc:
        payload = _rag_command_failure("query", project_id, exc)
        _print_rag_command_failure(payload, json_output=args.json)
        return 1
    _print_result(result, json_output=args.json)
    return 0


def cmd_rag_status(args: argparse.Namespace) -> int:
    state = load_project(Path.cwd())
    indexed = sum(1 for paper in state.papers if paper.status == "succeeded" and paper.artifact)
    console = Console()
    project_id = args.project_id or state.server_project_id
    if project_id:
        try:
            result = MdteroClient().rag_status(project_id)
        except Exception as exc:
            http_status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
            next_commands = ["mdtero project ingest --json", "mdtero rag status --json"]
            if indexed:
                next_commands.append("mdtero rag build --json")
            payload = {
                "status": "unavailable",
                "reason_code": "server_rag_status_unavailable",
                "project": state.name,
                "server_project_id": project_id,
                "local_ready_for_ingest_count": indexed,
                "local_paper_count": len(state.papers),
                "error_type": exc.__class__.__name__,
                "http_status": http_status,
                "action_hint": "Server RAG status is unavailable. Deploy the backend /api/v1 project RAG routes, then rerun `mdtero project ingest --json` and `mdtero rag status --json`.",
                "next_commands": next_commands,
            }
            if args.json:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                console.print(f"Project {state.name}: {indexed}/{len(state.papers)} local paper(s) have downloadable artifacts for server RAG.")
                console.print(f"Server project: {project_id}; status unavailable ({exc.__class__.__name__}).")
                console.print(f"Hint: {payload['action_hint']}")
                console.print("Next:")
                for command in next_commands:
                    console.print(f"  {command}")
            return 1
        summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
        result.setdefault("project", state.name)
        result.setdefault("server_project_id", str(project_id))
        result.setdefault("local_ready_for_ingest_count", indexed)
        result.setdefault("local_paper_count", len(state.papers))
        if args.json:
            print(json.dumps(result, indent=2, ensure_ascii=False))
            return 0
        console.print(
            f"Project {state.name}: server RAG {result.get('status')} ({result.get('reason_code')}); "
            f"{summary.get('embedded_count', 0)}/{summary.get('chunk_count', 0)} chunk(s) embedded."
        )
        console.print(f"Server project: {project_id}; provider: {result.get('selected_provider')}; model: {summary.get('embedding_model') or 'unknown'}")
        action_hint = str(result.get("action_hint") or "").strip()
        if action_hint:
            console.print(f"Hint: {action_hint}")
        next_commands = [str(command).strip() for command in result.get("next_commands") or [] if str(command).strip()]
        if next_commands:
            console.print("Next:")
            for command in next_commands:
                console.print(f"  {command}")
        return 0
    payload = {
        "status": "not_ready",
        "reason_code": "server_project_not_linked",
        "project": state.name,
        "server_project_id": None,
        "local_ready_for_ingest_count": indexed,
        "local_paper_count": len(state.papers),
        "action_hint": "Run `mdtero rag build --json` to create and bind a server project, import succeeded parse tasks, and start server-side Voyage RAG.",
        "next_commands": ["mdtero rag build --json", "mdtero rag status --json", "mdtero rag query \"<question>\" --json"],
    }
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    console.print(f"Project {state.name}: {indexed}/{len(state.papers)} local paper(s) have downloadable artifacts for server RAG.")
    console.print(f"Server project: not linked. Hint: {payload['action_hint']}")
    console.print("Next:")
    for command in payload["next_commands"]:
        console.print(f"  {command}")
    return 0


def cmd_mcp_serve(_args: argparse.Namespace) -> int:
    from .mcp import serve_project_context

    serve_project_context(Path.cwd())
    return 0


def cmd_agent_detect(_args: argparse.Namespace) -> int:
    from .agent import detect_target_status, detections_to_json

    results = detect_target_status(root=_args.root)
    if _args.json:
        print(detections_to_json(results))
        return 0
    table = Table("Agent", "Detected", "Installed", "Workspace", "Install command")
    for result in results:
        table.add_row(
            result.label,
            "yes" if result.detected else "no",
            "yes" if result.installed else "no",
            result.workspace_path,
            result.install_command,
        )
    Console().print(table)
    return 0


def cmd_agent_install(_args: argparse.Namespace) -> int:
    from .agent import detect_target_status, install_targets, results_to_json

    try:
        target_names = _args.target
        if _args.interactive:
            detections = detect_target_status(root=_args.root)
            target_names = _prompt_agent_targets(detections)
            if not target_names:
                raise ValueError("No agent target selected. Pass --target <target> or create an agent workspace directory first.")
        results = install_targets(target_names, root=_args.root, install_all=_args.all, dry_run=_args.dry_run)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if _args.json:
        print(results_to_json(results))
        return 0
    console = Console()
    table = Table("Agent", "Action", "Path")
    for result in results:
        table.add_row(result.label, result.action, result.path)
    console.print(table)
    console.print("Agent skill install uses the Python mdtero package; npm is no longer required for this path.")
    return 0


def _prompt_agent_targets(detections: list[Any]) -> list[str]:
    from .agent import default_interactive_targets, parse_agent_selection

    console = Console(stderr=True)
    table = Table("No", "Agent", "Detected", "Installed", "Workspace")
    for item in detections:
        table.add_row(
            str(item.selection_index),
            item.label,
            "yes" if item.detected else "no",
            "yes" if item.installed else "no",
            item.workspace_path,
        )
    console.print(table)
    defaults = default_interactive_targets(detections)
    default_hint = ",".join(defaults) if defaults else ""
    console.print("Select agent workspaces by number or target name. Use spaces for multi-select; Enter installs detected pending targets.")
    while True:
        selection = Prompt.ask("Agents", default=default_hint, console=console).strip()
        try:
            return parse_agent_selection(selection, detections)
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")


def cmd_agent_uninstall(_args: argparse.Namespace) -> int:
    from .agent import results_to_json, uninstall_targets

    try:
        results = uninstall_targets(_args.target, root=_args.root, dry_run=_args.dry_run)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    if _args.json:
        print(results_to_json(results))
        return 0
    table = Table("Agent", "Action", "Path")
    for result in results:
        table.add_row(result.label, result.action, result.path)
    Console().print(table)
    return 0


def cmd_tui(_args: argparse.Namespace) -> int:
    from .tui import MdteroTui

    MdteroTui().run()
    return 0


def _submit_project_paper(client: MdteroClient, paper: PaperRecord) -> dict[str, Any]:
    path = Path(paper.input).expanduser()
    if path.exists() and path.is_file():
        return client.upload(path, source_input=paper.doi or paper.title)
    _route, result, _acquisition = client.parse_with_route(paper.input)
    return result


def _ensure_server_project_for_rag(client: MdteroClient, root: Path, state: Any, project_id: str | None) -> tuple[str, dict[str, Any]]:
    explicit_project_id = str(project_id or "").strip()
    if explicit_project_id:
        return explicit_project_id, {"created_server_project": False, "bound_local_project": False, "used_explicit_project_id": True}
    if state.server_project_id:
        return state.server_project_id, {"created_server_project": False, "bound_local_project": True, "used_explicit_project_id": False}
    result = client.create_project(state.name, description=f"Mdtero local project: {state.name}")
    server_project_id = str(result.get("id") or "").strip()
    if not server_project_id:
        raise RuntimeError("server_project_id_missing")
    bind_server_project(root, server_project_id)
    return server_project_id, {
        "created_server_project": True,
        "bound_local_project": True,
        "used_explicit_project_id": False,
        "project": result,
    }


def _import_succeeded_tasks_to_server_project(client: MdteroClient, state: Any, project_id: str) -> dict[str, Any]:
    results = []
    failures = []
    for paper in state.papers:
        if paper.status != "succeeded" or not paper.task_id:
            continue
        try:
            result = client.import_task_to_project(project_id, paper.task_id)
        except httpx.HTTPStatusError as exc:
            failures.append(_project_ingest_failure(project_id, paper, exc))
            continue
        results.append({"input": paper.input, "task_id": paper.task_id, "result": result})
    return {
        "server_project_id": project_id,
        "imported_count": len(results),
        "failed_count": len(failures),
        "items": results,
        "failures": failures,
    }


def _project_ingest_failure(project_id: str, paper: PaperRecord, exc: httpx.HTTPStatusError) -> dict[str, Any]:
    status_code = exc.response.status_code
    error_code = "server_project_import_unavailable" if status_code == 404 else "server_project_import_failed"
    action_hint = (
        "The backend did not expose the project task import endpoint yet. Deploy the backend branch with "
        "POST /api/v1/projects/{id}/tasks/{task_id}/import, then rerun `mdtero project ingest --json`; "
        "use `mdtero rag status --json` to verify the linked server project."
        if status_code == 404
        else "Check the server project id, API key permissions, and task ownership, then rerun `mdtero project ingest --json`."
    )
    return {
        "input": paper.input,
        "task_id": paper.task_id,
        "status": "failed",
        "error_code": error_code,
        "http_status": status_code,
        "server_project_id": project_id,
        "action_hint": action_hint,
    }


def _rag_command_failure(command: str, project_id: str, exc: Exception) -> dict[str, Any]:
    detail = _http_error_detail(exc)
    reason_code = str(detail.get("reason_code") or "server_rag_command_failed")
    action_hint = str(detail.get("action_hint") or _rag_action_hint(command, reason_code))
    return {
        "status": "failed",
        "command": f"rag_{command}",
        "reason_code": reason_code,
        "error_code": str(detail.get("error_code") or "server_rag_failed"),
        "server_project_id": project_id,
        "http_status": exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None,
        "error_type": exc.__class__.__name__,
        "action_hint": action_hint,
        "next_commands": _rag_failure_next_commands(command, reason_code),
    }


def _rag_bootstrap_failure(command: str, exc: Exception) -> dict[str, Any]:
    detail = _http_error_detail(exc)
    reason_code = str(detail.get("reason_code") or detail.get("error_code") or exc)
    if reason_code == "server_project_id_missing":
        action_hint = "The server project creation response did not include an id. Check the backend project API contract, then rerun `mdtero rag build --json`."
    else:
        action_hint = str(detail.get("action_hint") or "Create or link a server project before running server-side Voyage RAG.")
    return {
        "status": "failed",
        "command": f"rag_{command}",
        "reason_code": reason_code,
        "error_code": str(detail.get("error_code") or "rag_bootstrap_failed"),
        "server_project_id": None,
        "http_status": exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None,
        "error_type": exc.__class__.__name__,
        "action_hint": action_hint,
        "next_commands": ["mdtero project create-server --json", "mdtero project ingest --json", "mdtero rag status --json", f"mdtero rag {command} --json"],
    }


def _http_error_detail(exc: Exception) -> dict[str, Any]:
    if not isinstance(exc, httpx.HTTPStatusError):
        return {}
    try:
        payload = exc.response.json()
    except ValueError:
        return {}
    detail = payload.get("detail") if isinstance(payload, dict) else None
    return detail if isinstance(detail, dict) else {}


def _rag_action_hint(command: str, reason_code: str) -> str:
    if reason_code == "voyage_not_configured":
        return "Server Voyage RAG is not configured. Configure VOYAGE_API_KEY on the backend, then rerun `mdtero rag build --json`."
    if reason_code == "rag_index_not_built":
        return "Build this server project RAG index before querying."
    if reason_code == "project_has_no_chunks":
        return "Import succeeded parse tasks first with `mdtero project ingest --json`, then run `mdtero rag build --json`."
    if reason_code == "forbidden":
        return "Use credentials for the owner of this server project."
    if reason_code == "project_not_found":
        return "Check the server project id or run `mdtero project create-server --json`."
    if command == "query":
        return "Check `mdtero rag status --json`, then run `mdtero rag build --json` if the project is not ready."
    return "Check `mdtero rag status --json`, fix the reported precondition, then retry."


def _rag_failure_next_commands(command: str, reason_code: str) -> list[str]:
    if reason_code == "project_has_no_chunks":
        return ["mdtero project ingest --json", "mdtero rag status --json", "mdtero rag build --json"]
    if command == "query" and reason_code == "rag_index_not_built":
        return ["mdtero rag status --json", "mdtero rag build --json", "mdtero rag query \"<question>\" --json"]
    if reason_code in {"voyage_not_configured", "forbidden", "project_not_found"}:
        return ["mdtero rag status --json"]
    return ["mdtero rag status --json", "mdtero rag build --json"]


def _print_rag_command_failure(payload: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    console = Console()
    console.print(f"RAG {payload['command'].removeprefix('rag_')} failed: {payload['reason_code']}")
    console.print(f"Hint: {payload['action_hint']}")
    next_commands = [str(command) for command in payload.get("next_commands") or [] if str(command).strip()]
    if next_commands:
        console.print("Next:")
        for command in next_commands:
            console.print(f"  {command}")


def _server_project_id(args: argparse.Namespace) -> str:
    value = getattr(args, "project_id", None)
    if value:
        return str(value)
    state = load_project(Path.cwd())
    if state.server_project_id:
        return state.server_project_id
    raise SystemExit("No server project is linked. Run `mdtero rag build --json` to create, bind, import, and build server-side Voyage RAG.")


def _server_project_id_or_report(args: argparse.Namespace, *, command: str) -> str | None:
    value = getattr(args, "project_id", None)
    if value:
        return str(value)
    state = load_project(Path.cwd())
    if state.server_project_id:
        return state.server_project_id
    payload = _unlinked_server_project_payload(command, state)
    if getattr(args, "json", False):
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        console = Console()
        console.print(f"RAG {command} not ready: {payload['reason_code']}")
        console.print(f"Hint: {payload['action_hint']}")
        console.print("Next:")
        for next_command in payload["next_commands"]:
            console.print(f"  {next_command}")
    return None


def _unlinked_server_project_payload(command: str, state: Any) -> dict[str, Any]:
    return {
        "status": "not_ready",
        "command": f"rag_{command}",
        "reason_code": "server_project_not_linked",
        "error_code": "rag_precondition_failed",
        "server_project_id": None,
        "project": state.name,
        "local_ready_for_ingest_count": sum(1 for paper in state.papers if paper.status == "succeeded" and paper.task_id),
        "local_paper_count": len(state.papers),
        "action_hint": "Run `mdtero rag build --json` to create and bind a server project, import succeeded parse tasks, and start server-side Voyage RAG.",
        "next_commands": ["mdtero rag build --json", "mdtero rag status --json", "mdtero rag query \"<question>\" --json"],
    }


def _configure_academic(cfg: MdteroConfig, console: Console) -> None:
    console.print("\nStep 2: optional academic resource keys.")
    for option in ACADEMIC_OPTIONS:
        console.print(f"  ({option['index']}) {option['label']}: {option['url']}")
    console.print("Press Enter to skip. Choose one or more numbers, for example `1 3`.")
    while True:
        selection = Prompt.ask("Configure optional keys", default="").strip()
        try:
            selected = _parse_academic_selection(selection)
            break
        except ValueError as exc:
            console.print(f"[red]{exc}[/red]")
    for option in ACADEMIC_OPTIONS:
        if str(option["index"]) not in selected:
            continue
        value = Prompt.ask(str(option["prompt"]), password=True).strip()
        if value:
            setattr(cfg.academic, str(option["field"]), value)
    path = save_config(cfg)
    console.print(f"Saved config to {path}")
    if cfg.academic.semantic_scholar_api_key:
        console.print("Discover will use local Semantic Scholar first, with server OpenAlex as fallback.")
    else:
        console.print("Discover will use server OpenAlex. Add Semantic Scholar later with `mdtero config academic` if needed.")


def _parse_academic_selection(selection: str) -> set[str]:
    cleaned = selection.strip().lower()
    if not cleaned:
        return set()
    if cleaned in {"all", "a", "*"}:
        return {str(option["index"]) for option in ACADEMIC_OPTIONS}
    allowed = {str(option["index"]) for option in ACADEMIC_OPTIONS}
    tokens = [token for token in cleaned.replace(",", " ").split() if token]
    invalid = [token for token in tokens if token not in allowed]
    if invalid:
        raise ValueError(f"Unknown academic key option(s): {', '.join(invalid)}. Choose 1, 2, 3, all, or Enter to skip.")
    return set(tokens)


def _print_next_steps(console: Console) -> None:
    console.print("\n[bold]Next commands[/bold]")
    sections = [
        (
            "Start a local project",
            [
                "mdtero project init --name literature-review",
                "mdtero discover \"graph neural networks\" --limit 5 --add --select 1,3",
                "mdtero project import-bib references.bib",
            ],
        ),
        (
            "Parse papers and files",
            [
                "mdtero parse 10.48550/arXiv.1706.03762 --wait --json",
                "mdtero parse https://example.org/open-paper --trace --json",
                "mdtero parse --file paper.pdf --wait --json",
                "mdtero parse --batch ./papers --wait --json",
                "mdtero project parse --wait --json",
                "mdtero project refresh --wait --json",
                "mdtero project download --output-dir ./mdtero-output --json",
            ],
        ),
        (
            "Zotero",
            [
                "mdtero config zotero",
                "mdtero zotero import --limit 20",
                "mdtero zotero sync",
            ],
        ),
        (
            "Server RAG and local agents",
            [
                "mdtero rag build --json",
                "mdtero rag status --json",
                "mdtero rag query \"What are the key claims and methods?\" --json",
                "mdtero mcp serve",
                "mdtero agent install",
                "mdtero tui",
            ],
        ),
    ]
    for title, commands in sections:
        console.print(f"\n[bold]{title}[/bold]")
        for command in commands:
            console.print(f"  {command}")


def _print_result(payload: dict[str, Any], *, json_output: bool) -> None:
    if json_output:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    console = Console()
    if "task_id" in payload:
        console.print(f"Task: {payload.get('task_id')} ({payload.get('status')})")
        reason = payload.get("reason_code") or payload.get("action_hint")
        if reason:
            console.print(str(reason))
    else:
        console.print(payload)


if __name__ == "__main__":
    raise SystemExit(main())
