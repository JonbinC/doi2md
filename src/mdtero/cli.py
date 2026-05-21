from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from .client import MdteroClient
from .config import MdteroConfig, config_path, load_config, save_config
from .projects import (
    PaperRecord,
    add_paper,
    import_bib,
    init_project,
    load_project,
    project_path,
    project_pending_papers,
    project_task_ids,
    remove_paper,
    update_paper_submission,
    update_task,
)
from .workflow import parse_trace_from_route, status_trace, upload_trace

ACADEMIC_LINKS = {
    "Elsevier key": "https://dev.elsevier.com/apikey/manage",
    "Wiley TDM": "https://onlinelibrary.wiley.com/library-info/resources/text-and-datamining",
    "Semantic Scholar API Key": "https://www.semanticscholar.org/product/api#api-key-form",
}


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
    sub = parser.add_subparsers(dest="command")

    _cmd(sub, "setup", "Run the onboarding wizard.", cmd_setup)
    _cmd(sub, "doctor", "Check local Mdtero configuration.", cmd_doctor)
    login = _cmd(sub, "login", "Configure OAuth or API-key login.", cmd_login)
    login.add_argument("--api-key", default="")

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
    discover.add_argument("--json", action="store_true")

    project = sub.add_parser("project")
    project_sub = project.add_subparsers(dest="project_command")
    project_init = _cmd(project_sub, "init", "Initialize a local Mdtero project.", cmd_project_init)
    project_init.add_argument("--name")
    project_add = _cmd(project_sub, "add", "Add one DOI/URL/file to the current project.", cmd_project_add)
    project_add.add_argument("input")
    project_remove = _cmd(project_sub, "remove", "Remove one project paper by input or task id.", cmd_project_remove)
    project_remove.add_argument("input")
    project_bib = _cmd(project_sub, "import-bib", "Import DOI/URL entries from one or more BibTeX files.", cmd_project_import_bib)
    project_bib.add_argument("paths", nargs="+", type=Path)
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
    _cmd(project_sub, "list", "List papers in the current project.", cmd_project_status)
    _cmd(project_sub, "status", "Show current project status.", cmd_project_status)

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
    _cmd(zotero_sub, "sync", "Sync Mdtero parse state back to Zotero notes/tags.", cmd_zotero_sync)

    translate = _cmd(sub, "translate", "Request server-side translation.", cmd_translate)
    translate.add_argument("task_or_file")
    translate.add_argument("--to", default="zh-CN")

    rag = sub.add_parser("rag")
    rag_sub = rag.add_subparsers(dest="rag_command")
    rag_build = _cmd(rag_sub, "build", "Request server-side project RAG build.", cmd_rag_build)
    rag_build.add_argument("--project-id")
    rag_query = _cmd(rag_sub, "query", "Query server-side project RAG.", cmd_rag_query)
    rag_query.add_argument("question")
    rag_query.add_argument("--project-id")
    _cmd(rag_sub, "status", "Show RAG status.", cmd_rag_status)

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

    agent = sub.add_parser("agent")
    agent_sub = agent.add_subparsers(dest="agent_command")
    agent_install = _cmd(agent_sub, "install", "Detect local agents and install Mdtero skills.", cmd_agent_install)
    agent_install.add_argument("--target", action="append", choices=["codex", "claude_code", "gemini_cli", "hermes", "opencode"])
    agent_install.add_argument("--root", type=Path)
    agent_install.add_argument("--all", action="store_true")
    agent_install.add_argument("--dry-run", action="store_true")
    agent_install.add_argument("--json", action="store_true")
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
    if not cfg.api_key:
        console.print("Step 1: authenticate.")
        if Confirm.ask("Use API-key login for this machine?", default=True):
            cfg.api_key = Prompt.ask("Paste Mdtero API key", password=True)
            save_config(cfg)
        else:
            console.print(f"Open {cfg.site_base_url}/auth and run `mdtero login --api-key <key>` on headless servers.")
    _configure_academic(cfg, console)
    console.print("\n[bold green]Configuration complete.[/bold green]")
    _print_next_steps(console)
    return 0


def cmd_login(args: argparse.Namespace) -> int:
    cfg = load_config()
    console = Console()
    if args.api_key:
        cfg.api_key = args.api_key.strip()
        path = save_config(cfg)
        console.print(f"Saved API key to {path}")
        return 0
    console.print(f"Open {cfg.site_base_url}/auth, create an API key, then run:")
    console.print("  mdtero login --api-key <key>")
    return 0


def cmd_doctor(_args: argparse.Namespace) -> int:
    cfg = load_config()
    console = Console()
    table = Table("Check", "Status", "Detail")
    key_source = "saved config" if cfg.api_key else "missing"
    if os.environ.get("MDTERO_API_KEY"):
        key_source = "MDTERO_API_KEY"
    table.add_row("API key", "ok" if cfg.api_key else "missing", key_source)
    table.add_row("Config", "ok" if config_path().exists() else "not created", str(config_path()))
    table.add_row("API base", "ok", cfg.api_base_url)
    current_project = project_path(Path.cwd())
    table.add_row("Project", "ok" if current_project.exists() else "not initialized", str(current_project))
    console.print(table)
    return 0 if cfg.api_key else 1


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
    results = []
    traces = []
    if args.batch:
        for path in sorted(args.batch.iterdir()):
            if path.suffix.lower() in {".pdf", ".epub", ".html", ".htm", ".xml"}:
                result = client.upload(path)
                results.append(result)
                traces.append(upload_trace(path, result).to_dict())
    elif args.file:
        result = client.upload(args.file, source_input=args.input)
        results.append(result)
        traces.append(upload_trace(args.file, result).to_dict())
    else:
        if not args.input:
            raise SystemExit("parse requires <doi-or-url>, --file, or --batch")
        route = client.route(args.input)
        result = client.parse(args.input)
        result["route"] = route
        results.append(result)
        traces.append(parse_trace_from_route(args.input, route, result).to_dict())
    for result in results:
        if result.get("task_id"):
            add_paper(
                Path.cwd(),
                PaperRecord(
                    input=args.input or str(args.file or args.batch or ""),
                    task_id=str(result.get("task_id")),
                    status=str(result.get("status") or "queued"),
                ),
            )
            if args.wait:
                task = client.wait(str(result["task_id"]))
                update_task(Path.cwd(), task)
                result["final_task"] = task
    payload = results[0] if len(results) == 1 else {"items": results}
    if args.trace:
        payload = {"result": payload, "workflow": traces[0] if len(traces) == 1 else traces}
    _print_result(payload, json_output=args.json or args.trace)
    return 0


def cmd_discover(args: argparse.Namespace) -> int:
    result = MdteroClient().discover(args.query, limit=args.limit)
    if args.json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    table = Table("Year", "Title", "DOI", "Source")
    for item in result.get("items") or []:
        table.add_row(str(item.get("year") or ""), str(item.get("title") or ""), str(item.get("doi") or ""), str(item.get("source") or "openalex"))
    Console().print(table)
    return 0


def cmd_project_init(args: argparse.Namespace) -> int:
    path = init_project(Path.cwd(), name=args.name)
    Console().print(f"Initialized Mdtero project at {path}")
    return 0


def cmd_project_status(_args: argparse.Namespace) -> int:
    state = load_project(Path.cwd())
    table = Table("Input", "Task", "Status", "Reason")
    for paper in state.papers:
        table.add_row(paper.input, paper.task_id or "", paper.status, paper.reason_code or "")
    Console().print(f"Project: {state.name}")
    Console().print(table)
    return 0


def cmd_project_add(args: argparse.Namespace) -> int:
    state = add_paper(Path.cwd(), PaperRecord(input=args.input, source="manual"))
    Console().print(f"Added {args.input} to project {state.name}")
    return 0


def cmd_project_remove(args: argparse.Namespace) -> int:
    state = remove_paper(Path.cwd(), args.input)
    Console().print(f"Project {state.name}: {len(state.papers)} paper(s) remain")
    return 0


def cmd_project_import_bib(args: argparse.Namespace) -> int:
    summary = import_bib(Path.cwd(), args.paths)
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


def cmd_status(args: argparse.Namespace) -> int:
    client = MdteroClient()
    task = client.wait(args.task_id) if args.wait else client.task(args.task_id)
    update_task(Path.cwd(), task)
    payload = {"task": task, "workflow": status_trace(task).to_dict()} if args.trace else task
    _print_result(payload, json_output=args.json or args.trace)
    return 0


def cmd_download(args: argparse.Namespace) -> int:
    path = MdteroClient().download(args.task_id, args.artifact, args.output_dir)
    Console().print(f"Downloaded {args.artifact} to {path}")
    return 0


def cmd_translate(args: argparse.Namespace) -> int:
    target = Path(args.task_or_file)
    if target.exists():
        result = MdteroClient().translate_text(target.read_text(encoding="utf-8"), filename=target.name, target_language=args.to)
    else:
        raise SystemExit("translate currently accepts a local markdown file in the Python client")
    _print_result(result, json_output=False)
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
    Console().print("Zotero sync command is wired in the public CLI; reverse sync metadata is the next migration slice.")
    return 0


def cmd_rag_build(_args: argparse.Namespace) -> int:
    project_id = _server_project_id(_args)
    result = MdteroClient().rag_build(project_id)
    _print_result(result, json_output=False)
    return 0


def cmd_rag_query(args: argparse.Namespace) -> int:
    project_id = _server_project_id(args)
    result = MdteroClient().rag_query(project_id, args.question)
    _print_result(result, json_output=False)
    return 0


def cmd_rag_status(_args: argparse.Namespace) -> int:
    state = load_project(Path.cwd())
    indexed = sum(1 for paper in state.papers if paper.status == "succeeded" and paper.artifact)
    Console().print(f"Project {state.name}: {indexed}/{len(state.papers)} paper(s) have downloadable artifacts for server RAG.")
    return 0


def cmd_mcp_serve(_args: argparse.Namespace) -> int:
    from .mcp import serve_project_context

    serve_project_context(Path.cwd())
    return 0


def cmd_agent_install(_args: argparse.Namespace) -> int:
    from .agent import install_targets, results_to_json

    try:
        results = install_targets(_args.target, root=_args.root, install_all=_args.all, dry_run=_args.dry_run)
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
    route = client.route(paper.input)
    result = client.parse(paper.input)
    result["route"] = route
    return result


def _server_project_id(args: argparse.Namespace) -> str:
    value = getattr(args, "project_id", None)
    if value:
        return str(value)
    state = load_project(Path.cwd())
    return state.name


def _configure_academic(cfg: MdteroConfig, console: Console) -> None:
    console.print("\nStep 2: optional academic resource keys.")
    for label, url in ACADEMIC_LINKS.items():
        console.print(f"{label}: {url}")
    if Confirm.ask("Configure Elsevier API key?", default=False):
        cfg.academic.elsevier_api_key = Prompt.ask("Elsevier API key", password=True)
    if Confirm.ask("Configure Wiley TDM token?", default=False):
        cfg.academic.wiley_tdm_token = Prompt.ask("Wiley TDM token", password=True)
    if Confirm.ask("Configure Semantic Scholar API key for local discover?", default=False):
        cfg.academic.semantic_scholar_api_key = Prompt.ask("Semantic Scholar API key", password=True)
    path = save_config(cfg)
    console.print(f"Saved config to {path}")


def _print_next_steps(console: Console) -> None:
    commands = [
        "mdtero project init",
        "mdtero parse 10.1000/example",
        "mdtero parse --file paper.pdf",
        "mdtero parse --batch ./papers",
        "mdtero discover \"graph neural networks\"",
        "mdtero project import-bib references.bib",
        "mdtero config zotero",
        "mdtero zotero import",
        "mdtero rag build",
        "mdtero mcp serve",
        "mdtero agent install",
        "mdtero tui",
    ]
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
