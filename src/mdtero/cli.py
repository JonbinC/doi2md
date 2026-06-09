from __future__ import annotations

import argparse
import csv
import importlib.util
import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

import httpx
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from . import __version__
from .acquisition import AcquisitionError
from .auth import run_web_login
from .client import DiscoveryError, MdteroApiError, MdteroClient, api_failure_payload
from .config import MdteroConfig, config_path, load_config, save_config
from .network import ProxyValidationError, proxy_settings_from_config
from .onboarding import (
    ACADEMIC_OPTIONS,
    GENERIC_RAG_QUERY_COMMAND,
    ONE_COMMAND_RAG_BOOTSTRAP,
    build_academic_onboarding_summary,
    build_input_route_contract,
    build_next_step_command_groups,
    build_onboarding_checklist,
)
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
from .rag_contract import ensure_rag_contract
from .redact import redact_sensitive_payload, redact_sensitive_text
from .workflow import parse_trace_from_route, status_trace, upload_trace

DEFAULT_WAIT_TIMEOUT_SECONDS = 600.0
DEFAULT_WAIT_INTERVAL_SECONDS = 2.0
SUPPORTED_PARSE_FILE_SUFFIXES = {".pdf", ".epub", ".html", ".htm", ".xml"}
SUPPORTED_PARSE_FILE_EXTENSIONS = ["pdf", "epub", "html", "xml"]
API_KEY_PROMPT_SENTINEL = "__mdtero_prompt_for_api_key__"
RAG_STATUS_COMMAND = "mdtero rag status --json"
RAG_BUILD_COMMAND = "mdtero rag build --wait --json"
RAG_INGEST_COMMAND = "mdtero project ingest --json"
RAG_MCP_BRIEFING_COMMAND = "mdtero mcp briefing --json"
RAG_MCP_SERVE_COMMAND = "mdtero mcp serve"


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    result = args.func(args)
    return int(result or 0)


def _print_nested_help(parser: argparse.ArgumentParser) -> Any:
    def _handler(_args: argparse.Namespace) -> int:
        parser.print_help()
        return 2

    return _handler


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mdtero")
    parser.add_argument("--version", action="version", version=f"mdtero {__version__}")
    sub = parser.add_subparsers(dest="command")

    setup = _cmd(sub, "setup", "Run the onboarding wizard.", cmd_setup)
    setup.add_argument("--api-key", nargs="?", const=API_KEY_PROMPT_SENTINEL, default=None, help="Save an API key during setup for headless servers; omit the value to paste it securely.")
    setup.add_argument("--json", action="store_true", help="Print a non-interactive, secret-safe setup summary for agents/headless environments.")
    doctor = _cmd(sub, "doctor", "Check local Mdtero configuration.", cmd_doctor)
    doctor.add_argument("--json", action="store_true", help="Print a machine-readable safe diagnostic summary without echoing secrets.")
    login = _cmd(sub, "login", "Configure OAuth or API-key login.", cmd_login)
    login.add_argument("--api-key", nargs="?", const=API_KEY_PROMPT_SENTINEL, default=None, help="Save an API key for headless login; omit the value to paste it securely.")
    login.add_argument("--no-browser", action="store_true", help="Print the loopback web-login URL instead of opening a browser.")
    login.add_argument("--timeout", type=float, default=180.0, help="Seconds to wait for the browser login callback.")

    smoke = _cmd(sub, "smoke", "Run a deploy-ready CLI smoke test against Mdtero APIs.", cmd_smoke)
    smoke.add_argument("--api-base", help="Override the Mdtero API base URL for this smoke run.")
    smoke.add_argument("--workdir", type=Path, help="Project directory for smoke state and downloads. Defaults to a temporary directory.")
    smoke.add_argument("--doi", default="10.48550/arXiv.1706.03762", help="DOI or URL to parse during smoke.")
    smoke.add_argument("--query", default="retrieval augmented generation scientific papers", help="Discovery query to run during smoke.")
    smoke.add_argument("--limit", type=int, default=3, help="Discovery result limit.")
    smoke.add_argument("--question", default="What are the paper's main contribution and method?", help="RAG question for the parsed paper.")
    smoke.add_argument("--project-id", help="Use an existing server project id for RAG instead of creating one.")
    smoke.add_argument("--translate-to", default="zh-CN", help="Target language for the translation smoke step.")
    smoke.add_argument("--skip-discovery", action="store_true")
    smoke.add_argument("--skip-download", action="store_true")
    smoke.add_argument("--skip-translate", action="store_true")
    smoke.add_argument("--skip-rag", action="store_true")
    smoke.add_argument("--wait", action="store_true", help="Accepted for copy-paste consistency; smoke already waits for parse, translation, and RAG steps.")
    _add_wait_options(smoke)
    smoke.add_argument("--json", action="store_true")

    config = sub.add_parser("config")
    config.set_defaults(func=_print_nested_help(config))
    config_sub = config.add_subparsers(dest="config_command")
    academic_config = _cmd(config_sub, "academic", "Configure optional academic resource keys.", cmd_config_academic)
    academic_config.add_argument("--elsevier-key", help="Save an Elsevier API key without opening the interactive prompt.")
    academic_config.add_argument("--wiley-tdm-token", help="Save a Wiley TDM token without opening the interactive prompt.")
    academic_config.add_argument("--semantic-scholar-key", help="Save a Semantic Scholar API key without opening the interactive prompt.")
    academic_config.add_argument("--json", action="store_true", help="Print a machine-readable safe summary without echoing secrets.")
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
    _add_wait_options(parse)
    parse.add_argument("--trace", action="store_true")

    parse_batch = _cmd(sub, "parse-batch", "Parse DOI/URL targets from a text file, optionally wait and download Markdown.", cmd_parse_batch)
    parse_batch.add_argument("path", type=Path, help="Text file with one DOI or URL per line; blank lines and # comments are ignored.")
    parse_batch.add_argument("--download", nargs="?", const="paper_md", default=None, help="Download an artifact after each succeeded parse. Defaults to paper_md when the flag is present.")
    parse_batch.add_argument("--output-dir", type=Path, default=Path("mdtero-output"))
    parse_batch.add_argument("--filename-template", default="{author}_{year}_{shorttitle}", help="Download filename template using {author}, {year}, {shorttitle}, {title}, {doi}, {task_id}, and {artifact}.")
    parse_batch.add_argument("--manifest", action=argparse.BooleanOptionalAction, default=True, help="Write manifest.csv and failed.csv in the output directory.")
    parse_batch.add_argument("--json", action="store_true")
    parse_batch.add_argument("--wait", action="store_true")
    _add_wait_options(parse_batch)

    discover = _cmd(sub, "discover", "Search papers.", cmd_discover)
    discover.add_argument("query", nargs="+")
    discover.add_argument("--limit", type=int, default=10)
    discover.add_argument("--add", action="store_true", help="Add selected discovery results to the current project.")
    discover.add_argument("--select", default="", help="Result numbers to add, for example `1 3`, `1,3`, or `all`. Defaults to all with --add.")
    discover.add_argument("--interactive", action="store_true", help="Show results and prompt for numbers to add to the current project.")
    discover.add_argument("--json", action="store_true")

    project = sub.add_parser("project")
    project.set_defaults(func=_print_nested_help(project))
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
    _add_wait_options(project_parse)
    project_parse.add_argument("--json", action="store_true")
    project_refresh = _cmd(project_sub, "refresh", "Refresh task status for project papers.", cmd_project_refresh)
    project_refresh.add_argument("--wait", action="store_true")
    _add_wait_options(project_refresh)
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
    zotero.set_defaults(func=_print_nested_help(zotero))
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
    translate.add_argument("--wait", action="store_true", help="Wait for the translation task to finish and include final_task in the output.")
    _add_wait_options(translate)
    translate.add_argument("--json", action="store_true")

    rag = sub.add_parser("rag")
    rag.set_defaults(func=_print_nested_help(rag))
    rag_sub = rag.add_subparsers(dest="rag_command")
    rag_build = _cmd(rag_sub, "build", "Request server-side project RAG build.", cmd_rag_build)
    rag_build.add_argument("--project-id")
    rag_build.add_argument("--wait", action="store_true", help="Poll RAG status until the backend build is query-ready or times out.")
    _add_wait_options(rag_build)
    rag_build.add_argument("--json", action="store_true")
    rag_query = _cmd(rag_sub, "query", "Query server-side project RAG.", cmd_rag_query)
    rag_query.add_argument("question")
    rag_query.add_argument("--project-id")
    rag_query.add_argument("--build-if-needed", action="store_true", help="Create/bind/import/build server RAG before querying when the local project is not ready.")
    _add_wait_options(rag_query)
    rag_query.add_argument("--json", action="store_true")
    rag_status = _cmd(rag_sub, "status", "Show RAG status.", cmd_rag_status)
    rag_status.add_argument("--project-id")
    rag_status.add_argument("--json", action="store_true")

    mcp = sub.add_parser("mcp")
    mcp.set_defaults(func=_print_nested_help(mcp))
    mcp_sub = mcp.add_subparsers(dest="mcp_command")
    mcp_briefing = _cmd(mcp_sub, "briefing", "Print the local MCP agent briefing without starting a server.", cmd_mcp_briefing)
    mcp_briefing.add_argument("--json", action="store_true")
    _cmd(mcp_sub, "serve", "Serve local project context over FastMCP.", cmd_mcp_serve)

    status = _cmd(sub, "status", "Poll one task and update the current project.", cmd_status)
    status.add_argument("task_id")
    status.add_argument("--wait", action="store_true")
    _add_wait_options(status)
    status.add_argument("--json", action="store_true")
    status.add_argument("--trace", action="store_true")

    download = _cmd(sub, "download", "Download one task artifact.", cmd_download)
    download.add_argument("task_id")
    download.add_argument("artifact", nargs="?", default="paper_md")
    download.add_argument("--output-dir", type=Path, default=Path.cwd())
    download.add_argument("--filename-template", default="{author}_{year}_{shorttitle}", help="Prefer a metadata-based filename for Markdown artifacts. Use an empty string to keep the server filename.")
    download.add_argument("--manifest", action=argparse.BooleanOptionalAction, default=True, help="Write/update manifest.csv in the output directory.")
    download.add_argument("--json", action="store_true")

    agent = sub.add_parser("agent")
    agent.set_defaults(func=_print_nested_help(agent))
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


def _add_wait_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--timeout", type=float, default=DEFAULT_WAIT_TIMEOUT_SECONDS, help="Seconds to wait for a task to finish when --wait is set.")
    parser.add_argument("--interval", type=float, default=DEFAULT_WAIT_INTERVAL_SECONDS, help="Seconds between task polls when --wait is set.")


def cmd_smoke(args: argparse.Namespace) -> int:
    cfg = load_config()
    if getattr(args, "api_base", None):
        cfg.api_base_url = str(args.api_base).rstrip("/")
    workdir = (args.workdir or Path(tempfile.mkdtemp(prefix="mdtero-smoke-"))).expanduser().resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "status": "running",
        "command": "smoke",
        "api_base_url": cfg.api_base_url,
        "workdir": str(workdir),
        "doi": args.doi,
        "query": args.query,
        "steps": [],
        "task_ids": [],
        "translation_task_ids": [],
        "downloaded_paths": [],
        "translated_paths": [],
        "server_project_id": str(args.project_id or "").strip() or None,
        "coverage_contract": _smoke_coverage_contract(args),
        "next_commands": [
            "mdtero doctor --json",
            f"mdtero parse {args.doi} --trace --wait --timeout {int(args.timeout)} --json",
            f"mdtero translate <task-id-or-paper.md> --to {args.translate_to} --wait --timeout {int(args.timeout)} --json",
            "mdtero rag status --json",
            "mdtero mcp briefing --json",
        ],
    }

    if not cfg.is_authenticated:
        payload.update(
            {
                "status": "not_ready",
                "reason_code": "auth_missing",
                "action_hint": "Configure Mdtero auth before running production smoke. Use browser OAuth with `mdtero login` or headless API-key login with `mdtero login --api-key`.",
                "next_commands": ["mdtero login", "mdtero login --api-key", "mdtero doctor --json"],
            }
        )
        _print_smoke_result(payload, json_output=args.json)
        return 1

    init_project(workdir, name="mdtero-smoke")
    client = MdteroClient(config=cfg, timeout=max(float(args.timeout or DEFAULT_WAIT_TIMEOUT_SECONDS), 1.0))
    terminal_failures = 0
    parse_task: dict[str, Any] | None = None

    if args.skip_discovery:
        _smoke_add_step(payload, "discover", "skipped", reason_code="skipped")
    else:
        try:
            discovery = client.discover(args.query, limit=max(int(args.limit or 1), 1))
            items = discovery.get("items") if isinstance(discovery.get("items"), list) else []
            _smoke_add_step(payload, "discover", "succeeded", source=discovery.get("source"), items_count=len(items), result=discovery)
        except Exception as exc:
            terminal_failures += 1
            _smoke_add_step(payload, "discover", "failed", **_smoke_exception_payload(exc, default_reason="discovery_failed"))

    try:
        route, submission, acquisition = client.parse_with_route(args.doi)
        _enrich_parse_submission(submission)
        task_id = str(submission.get("task_id") or "").strip()
        if not task_id:
            raise RuntimeError("parse_task_id_missing")
        payload["task_ids"].append(task_id)
        add_paper(workdir, paper_from_submission(args.doi, submission, source="smoke"))
        parse_task = _wait_for_task(client, task_id, args=args)
        _enrich_task_status(parse_task)
        if parse_task.get("status") != "timeout":
            update_task(workdir, parse_task)
        _merge_waited_task_into_submission(submission, parse_task)
        parse_status = "succeeded" if parse_task.get("status") == "succeeded" else "failed"
        if parse_status != "succeeded":
            terminal_failures += 1
        _smoke_add_step(
            payload,
            "parse",
            parse_status,
            task_id=task_id,
            route_kind=route.get("route_kind"),
            acquisition_mode=route.get("acquisition_mode"),
            client_acquisition=acquisition,
            selected_provider=submission.get("selected_provider"),
            parser_strategy=submission.get("parser_strategy"),
            reason_code=submission.get("reason_code") or submission.get("error_code"),
            result=submission,
        )
    except Exception as exc:
        terminal_failures += 1
        _smoke_add_step(payload, "parse", "failed", **_smoke_exception_payload(exc, default_reason="parse_failed"))

    if args.skip_download:
        _smoke_add_step(payload, "download", "skipped", reason_code="skipped")
    elif parse_task and parse_task.get("status") == "succeeded":
        task_id = str(parse_task.get("task_id") or payload["task_ids"][-1])
        artifact = str(parse_task.get("preferred_artifact") or _preferred_parse_artifact(parse_task) or "paper_md")
        try:
            path = client.download(task_id, artifact, workdir / "downloads")
            payload["downloaded_paths"].append(str(path))
            _smoke_add_step(payload, "download", "succeeded", task_id=task_id, artifact=artifact, path=str(path))
        except Exception as exc:
            terminal_failures += 1
            _smoke_add_step(payload, "download", "failed", task_id=task_id, artifact=artifact, **_smoke_exception_payload(exc, default_reason="download_failed"))
    else:
        _smoke_add_step(payload, "download", "skipped", reason_code="parse_not_succeeded")

    if args.skip_translate:
        _smoke_add_step(payload, "translate", "skipped", reason_code="skipped")
    elif parse_task and parse_task.get("status") == "succeeded":
        task_id = str(parse_task.get("task_id") or payload["task_ids"][-1])
        try:
            translation = client.translate_task(task_id, target_language=args.translate_to)
            _enrich_translate_submission(translation)
            translation_task_id = str(translation.get("task_id") or "").strip()
            if not translation_task_id:
                raise RuntimeError("translation_task_id_missing")
            payload["translation_task_ids"].append(translation_task_id)
            final_translation = _wait_for_task(client, translation_task_id, args=args)
            _enrich_task_status(final_translation)
            translation["final_task"] = final_translation
            translation_status = "succeeded" if final_translation.get("status") == "succeeded" else "failed"
            translated_path = None
            if translation_status == "succeeded":
                translated_path = client.download(translation_task_id, "translated_md", workdir / "translations")
                payload["translated_paths"].append(str(translated_path))
            else:
                terminal_failures += 1
            _smoke_add_step(
                payload,
                "translate",
                translation_status,
                source_task_id=task_id,
                task_id=translation_task_id,
                target_language=args.translate_to,
                reason_code=final_translation.get("reason_code") or final_translation.get("error_code") or translation.get("reason_code"),
                path=str(translated_path) if translated_path else None,
                result=translation,
            )
        except Exception as exc:
            terminal_failures += 1
            _smoke_add_step(payload, "translate", "failed", task_id=task_id, target_language=args.translate_to, **_smoke_exception_payload(exc, default_reason="translate_failed"))
    else:
        _smoke_add_step(payload, "translate", "skipped", reason_code="parse_not_succeeded")

    if args.skip_rag:
        _smoke_add_step(payload, "rag", "skipped", reason_code="skipped")
    elif parse_task and parse_task.get("status") == "succeeded":
        try:
            state = load_project(workdir)
            project_id, bootstrap = _ensure_server_project_for_rag(client, workdir, state, getattr(args, "project_id", None))
            payload["server_project_id"] = project_id
            ingest = _import_succeeded_tasks_to_server_project(client, load_project(workdir), project_id)
            if ingest["failures"]:
                raise RuntimeError("server_project_import_failed")
            build = client.rag_build(project_id)
            rag_status = _wait_for_rag_ready(client, project_id, args=args)
            query = _normalize_rag_query_payload(client.rag_query(project_id, args.question), project_id=project_id, question=args.question)
            _smoke_add_step(
                payload,
                "rag",
                "succeeded",
                server_project_id=project_id,
                bootstrap=bootstrap,
                ingest=ingest,
                build=build,
                rag_status=rag_status,
                query=query,
                reason_code=query.get("reason_code") or rag_status.get("reason_code"),
            )
        except Exception as exc:
            terminal_failures += 1
            _smoke_add_step(payload, "rag", "failed", server_project_id=payload.get("server_project_id"), **_smoke_exception_payload(exc, default_reason="rag_failed"))
    else:
        _smoke_add_step(payload, "rag", "skipped", reason_code="parse_not_succeeded")

    if args.skip_rag:
        _smoke_add_step(payload, "mcp_briefing", "skipped", reason_code="rag_skipped")
    elif parse_task and parse_task.get("status") == "succeeded":
        try:
            from .mcp import build_agent_briefing

            briefing = build_agent_briefing(workdir)
            mcp_tools = briefing.get("mcp_tools") if isinstance(briefing.get("mcp_tools"), list) else []
            missing_tools = [tool for tool in ("agent_briefing", "server_rag_status", "server_rag_build", "rag_query") if tool not in mcp_tools]
            if missing_tools:
                raise RuntimeError(f"mcp_briefing_missing_tools:{','.join(missing_tools)}")
            _smoke_add_step(
                payload,
                "mcp_briefing",
                "succeeded",
                server_project_id=payload.get("server_project_id"),
                reason_code=briefing.get("health", {}).get("rag_reason_code") if isinstance(briefing.get("health"), dict) else None,
                project_bridge=briefing.get("project_bridge"),
                rag=briefing.get("rag"),
                mcp_tools=mcp_tools,
                mcp_tool_plan=briefing.get("mcp_tool_plan"),
                recommended_next_commands=briefing.get("recommended_next_commands"),
            )
        except Exception as exc:
            terminal_failures += 1
            _smoke_add_step(payload, "mcp_briefing", "failed", server_project_id=payload.get("server_project_id"), **_smoke_exception_payload(exc, default_reason="mcp_briefing_failed"))
    else:
        _smoke_add_step(payload, "mcp_briefing", "skipped", reason_code="parse_not_succeeded")

    payload["status"] = "succeeded" if terminal_failures == 0 else "failed"
    payload["failed_count"] = terminal_failures
    if terminal_failures == 0:
        payload["reason_code"] = "smoke_succeeded"
        payload["action_hint"] = "Smoke completed."
    else:
        _enrich_smoke_failure_summary(payload)
    _print_smoke_result(payload, json_output=args.json)
    return 0 if terminal_failures == 0 else 1


def cmd_setup(_args: argparse.Namespace) -> int:
    json_output = bool(getattr(_args, "json", False))
    console = Console()
    if json_output:
        return _cmd_setup_json(_args)
    console.rule("[bold]Mdtero setup")
    cfg = load_config()
    headless_auth = False
    api_key_arg = getattr(_args, "api_key", None)
    if api_key_arg is not None:
        headless_auth = True
        cfg.api_key = _api_key_from_arg_or_prompt(api_key_arg, console=console)
        if not cfg.api_key:
            return 2
        save_config(cfg)
        console.print("Step 1: saved API-key login for this machine.")
    elif cfg.is_authenticated:
        console.print(f"Step 1: using existing API-key login from {cfg.api_key_source}.")
        headless_auth = cfg.api_key_source == "MDTERO_API_KEY"
    else:
        console.print("Step 1: authenticate.")
        if Confirm.ask("Open browser OAuth login for this machine?", default=True):
            _login_with_browser(cfg, console, timeout_seconds=180.0, no_browser=False)
        else:
            console.print("Use API-key login for headless servers or remote shells where browser OAuth cannot call back to this machine.")
            cfg.api_key = _normalize_api_key_arg(Prompt.ask("Paste Mdtero API key", password=True), console=console)
            if not cfg.api_key:
                return 2
            save_config(cfg)
            headless_auth = True
    _configure_academic(cfg, console)
    _configure_detected_agent_skills(console, skip_prompt=headless_auth)
    console.print("\n[bold green]Configuration complete.[/bold green]")
    _print_next_steps(console)
    return 0


def _cmd_setup_json(_args: argparse.Namespace) -> int:
    cfg = load_config()
    api_key_arg = getattr(_args, "api_key", None)
    auth_mode = "existing"
    saved_config = False
    if api_key_arg is not None:
        prompt_console = Console(stderr=True)
        raw_key = api_key_arg
        if api_key_arg == API_KEY_PROMPT_SENTINEL:
            raw_key = Prompt.ask("Paste Mdtero API key", password=True, console=prompt_console)
        key = _normalize_api_key_arg(str(raw_key or ""), console=prompt_console)
        if not key:
            payload = _setup_summary_payload(cfg, auth_mode="api_key", headless=True, saved_config=False)
            payload.update({"status": "failed", "reason_code": "api_key_empty", "action_hint": "Rerun `mdtero setup --api-key --json` and paste a non-empty Mdtero API key."})
            print(json.dumps(redact_sensitive_payload(payload), indent=2, ensure_ascii=False))
            return 2
        cfg.api_key = key
        save_config(cfg)
        auth_mode = "api_key"
        saved_config = True
    elif not cfg.is_authenticated:
        payload = _setup_summary_payload(cfg, auth_mode="missing", headless=False, saved_config=False)
        payload.update({
            "status": "missing_auth",
            "reason_code": "auth_missing",
            "action_hint": "Run `mdtero setup` for browser OAuth, or `mdtero setup --api-key --json` for a headless/API-key setup.",
        })
        print(json.dumps(redact_sensitive_payload(payload), indent=2, ensure_ascii=False))
        return 1
    headless = api_key_arg is not None or cfg.api_key_source == "MDTERO_API_KEY"
    payload = _setup_summary_payload(cfg, auth_mode=auth_mode, headless=headless, saved_config=saved_config)
    print(json.dumps(redact_sensitive_payload(payload), indent=2, ensure_ascii=False))
    return 0


def _setup_summary_payload(cfg: MdteroConfig, *, auth_mode: str, headless: bool, saved_config: bool) -> dict[str, Any]:
    academic = _academic_config_summary(cfg, path=config_path(), saved=False)
    dependencies = _local_dependency_summary()
    agent_status: list[dict[str, Any]] = []
    agent_detection_skipped = bool(headless)
    if not agent_detection_skipped:
        from .agent import detect_target_status

        agent_status = [
            {
                "target": item.target,
                "label": item.label,
                "detected": item.detected,
                "installed": item.installed,
                "install_command": item.install_command,
                "selection_index": item.selection_index,
            }
            for item in detect_target_status()
        ]
    configured_academic = academic["configured"]
    next_command_groups = _next_step_command_groups()
    return {
        "status": "configured" if cfg.is_authenticated else "missing_auth",
        "reason_code": "setup_configured" if cfg.is_authenticated else "auth_missing",
        "config_path": str(config_path()),
        "saved_config": saved_config,
        "authenticated": cfg.is_authenticated,
        "auth_source": cfg.api_key_source,
        "auth_mode": auth_mode,
        "headless": headless,
        "academic": {
            "configured": configured_academic,
            "discover_source": academic["discover_source"],
            "application_links": academic["application_links"],
        },
        "dependencies": dependencies,
        "agents": {
            "detection_skipped": agent_detection_skipped,
            "status": agent_status,
            "detected_count": sum(1 for item in agent_status if item["detected"]),
            "installed_count": sum(1 for item in agent_status if item["installed"]),
            "next_commands": ["mdtero agent detect --json", "mdtero agent install --interactive"],
        },
        "input_routes": build_input_route_contract(),
        "next_commands": [
            "mdtero doctor --json",
            "mdtero config academic --json",
            "mdtero discover \"<topic>\" --limit 5 --json",
            "mdtero parse 10.48550/arXiv.1706.03762 --trace --wait --timeout 300 --json",
            "mdtero rag query \"<question>\" --build-if-needed --json",
            "mdtero mcp briefing --json",
        ],
        "next_command_groups": next_command_groups,
        "onboarding_checklist": build_onboarding_checklist(
            authenticated=cfg.is_authenticated,
            headless=headless,
            academic=academic,
            dependencies=dependencies,
            agent_status=agent_status,
            agent_detection_skipped=agent_detection_skipped,
        ),
    }


def _local_dependency_summary() -> dict[str, Any]:
    modules = {
        "curl_cffi": {
            "import_name": "curl_cffi.requests",
            "capability": "local publisher route acquisition",
        },
        "fastmcp": {
            "import_name": "fastmcp",
            "capability": "local MCP server for agents",
        },
        "pyzotero": {
            "import_name": "pyzotero",
            "capability": "Zotero import and sync",
        },
    }
    checks: dict[str, Any] = {}
    missing: list[str] = []
    for name, meta in modules.items():
        import_name = str(meta["import_name"])
        try:
            available = importlib.util.find_spec(import_name) is not None
        except (ImportError, AttributeError, ValueError):
            available = False
        checks[name] = {
            "status": "ok" if available else "missing",
            "import_name": import_name,
            "capability": meta["capability"],
        }
        if not available:
            missing.append(name)
    return {
        "ready": not missing,
        "missing": missing,
        "checks": checks,
        "install_command": "uv tool install --force --reinstall git+https://github.com/JonbinC/doi2md.git",
        "installer_command": "curl -Ls https://mdtero.com/install.sh | sh",
        "pipx_install_command": "pipx install --force git+https://github.com/JonbinC/doi2md.git",
        "pip_user_install_command": "python3 -m pip install --user --force-reinstall git+https://github.com/JonbinC/doi2md.git",
        "pypi_install_command": "uv tool install mdtero",
        "doctor_command": "mdtero doctor --json",
    }


def _install_boundary_summary() -> dict[str, Any]:
    service_spec = None
    try:
        service_spec = importlib.util.find_spec("service")
    except (ImportError, AttributeError, ValueError):
        service_spec = None
    service_origin = getattr(service_spec, "origin", None) if service_spec is not None else None
    mdtero_executable = shutil.which("mdtero")
    status = "ok"
    action_hint = "Public Mdtero CLI package is active."
    if service_origin:
        status = "mixed_environment"
        action_hint = "A top-level backend `service` package is importable in this Python environment. Reinstall the public CLI with `uv tool install --force --reinstall git+https://github.com/JonbinC/doi2md.git` or `curl -Ls https://mdtero.com/install.sh | sh`; avoid the old PyPI package until it is republished."
    return {
        "status": status,
        "package": "mdtero",
        "version": __version__,
        "entrypoint": mdtero_executable,
        "backend_service_importable": bool(service_origin),
        "backend_service_origin": str(service_origin) if service_origin else None,
        "action_hint": action_hint,
        "next_commands": [
            "uv tool install --force --reinstall git+https://github.com/JonbinC/doi2md.git",
            "curl -Ls https://mdtero.com/install.sh | sh",
            "mdtero doctor --json",
        ],
    }


def cmd_login(args: argparse.Namespace) -> int:
    cfg = load_config()
    console = Console()
    if args.api_key is not None:
        cfg.api_key = _api_key_from_arg_or_prompt(args.api_key, console=console)
        if not cfg.api_key:
            return 2
        path = save_config(cfg)
        console.print(f"Saved API key to {path}")
        return 0
    _login_with_browser(cfg, console, timeout_seconds=args.timeout, no_browser=args.no_browser)
    return 0


def _api_key_from_arg_or_prompt(value: str | None, *, console: Console) -> str | None:
    if value == API_KEY_PROMPT_SENTINEL:
        value = Prompt.ask("Paste Mdtero API key", password=True, console=console)
    return _normalize_api_key_arg(str(value or ""), console=console)


def _normalize_api_key_arg(value: str, *, console: Console) -> str | None:
    key = str(value or "").strip()
    if not key:
        console.print("[red]API key cannot be empty.[/red]")
        return None
    return key


def _login_with_browser(cfg: MdteroConfig, console: Console, *, timeout_seconds: float, no_browser: bool) -> None:
    if no_browser:
        console.print("Printing a loopback web-login URL instead of opening a browser.")
        console.print("Use `mdtero setup --api-key --json` for remote/headless servers where 127.0.0.1 cannot receive the browser callback.")
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
    remote_auth = _doctor_remote_auth(cfg)
    root = Path.cwd()
    server_rag_status = _doctor_server_rag_status(cfg, root, remote_auth=remote_auth)
    rows = _doctor_rows(cfg, root, remote_auth=remote_auth, server_rag_status=server_rag_status)
    if getattr(_args, "json", False):
        payload = _doctor_payload(cfg, root, rows, remote_auth=remote_auth, server_rag_status=server_rag_status)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0 if payload["status"] == "ok" else 1
    console = Console()
    table = Table("Check", "Status", "Detail")
    for row in rows:
        table.add_row(*row)
    console.print(table)
    return 0 if cfg.is_authenticated and remote_auth.get("status") != "failed" else 1


def _doctor_rows(cfg: MdteroConfig, root: Path, *, remote_auth: dict[str, Any] | None = None, server_rag_status: dict[str, Any] | None = None) -> list[tuple[str, str, str]]:
    remote_auth = remote_auth or _doctor_remote_auth(cfg)
    install_boundary = _install_boundary_summary()
    api_key_status = "ok" if cfg.is_authenticated else "missing"
    api_key_detail = cfg.api_key_source
    if remote_auth.get("status") == "failed":
        api_key_status = "invalid"
        api_key_detail = str(remote_auth.get("reason_code") or remote_auth.get("error_code") or "authentication_failed")
    rows = [
        ("API key", api_key_status, api_key_detail),
        ("Config", "ok" if config_path().exists() else "not created", str(config_path())),
        ("API base", "ok", cfg.api_base_url),
        ("Proxy", "required" if cfg.campus_proxy_required else ("configured" if cfg.effective_proxy_url else "optional"), _proxy_config_detail(cfg)),
        ("Install boundary", str(install_boundary["status"]), str(install_boundary["action_hint"])),
        _dependency_check_row("curl_cffi", import_name="curl_cffi.requests", ok_detail="local route acquisition", missing_detail="httpx fallback only"),
        _dependency_check_row("FastMCP", import_name="fastmcp", ok_detail="MCP server available", missing_detail="install mdtero with FastMCP support"),
        _dependency_check_row("pyzotero", import_name="pyzotero", ok_detail="Zotero client available", missing_detail="Zotero import/sync unavailable"),
        ("Semantic Scholar", "ok" if cfg.has_semantic_scholar_key else "optional", "local discovery" if cfg.has_semantic_scholar_key else "server OpenAlex fallback"),
        ("Zotero config", "ok" if _zotero_configured(cfg) else "optional", _zotero_config_detail(cfg)),
    ]
    current_project = project_path(root)
    rows.append(("Project", "ok" if current_project.exists() else "not initialized", str(current_project)))
    if current_project.exists():
        rows.extend(_doctor_project_rows(root, server_rag_status=server_rag_status))
    return rows


def _doctor_payload(cfg: MdteroConfig, root: Path, rows: list[tuple[str, str, str]], *, remote_auth: dict[str, Any] | None = None, server_rag_status: dict[str, Any] | None = None) -> dict[str, Any]:
    row_payload = [{"check": check, "status": status, "detail": detail} for check, status, detail in rows]
    remote_auth = remote_auth or _doctor_remote_auth(cfg)
    status = "ok" if cfg.is_authenticated else "missing_auth"
    if remote_auth.get("status") == "failed":
        status = "invalid_auth"
    payload: dict[str, Any] = {
        "status": status,
        "authenticated": cfg.is_authenticated and remote_auth.get("status") != "failed",
        "api_key_source": cfg.api_key_source,
        "remote_auth": remote_auth,
        "config_path": str(config_path()),
        "api_base_url": cfg.api_base_url,
        "proxy": _proxy_config_payload(cfg),
        "install_boundary": _install_boundary_summary(),
        "checks": row_payload,
        "dependencies": {
            "curl_cffi": _doctor_row_status(rows, "curl_cffi"),
            "fastmcp": _doctor_row_status(rows, "FastMCP"),
            "pyzotero": _doctor_row_status(rows, "pyzotero"),
        },
        "academic": {
            "elsevier_api_key": bool((cfg.academic.elsevier_api_key or "").strip()),
            "wiley_tdm_token": bool((cfg.academic.wiley_tdm_token or "").strip()),
            "semantic_scholar_api_key": bool((cfg.academic.semantic_scholar_api_key or "").strip()),
            "discover_source": "local_semantic_scholar" if cfg.has_semantic_scholar_key else "server_openalex",
        },
        "zotero": {
            "configured": _zotero_configured(cfg),
            "library_id": cfg.zotero.library_id,
            "library_type": cfg.zotero.library_type,
        },
        "project": _doctor_project_payload(root, server_rag_status=server_rag_status),
        "next_commands": _doctor_auth_next_commands(cfg, remote_auth),
    }
    project_next = payload["project"].get("next_commands") if isinstance(payload.get("project"), dict) else None
    if status != "invalid_auth" and isinstance(project_next, list):
        payload["next_commands"] = _dedupe_string_list([*payload["next_commands"], *project_next])
    return payload


def _doctor_remote_auth(cfg: MdteroConfig) -> dict[str, Any]:
    if not cfg.is_authenticated:
        return {
            "status": "missing",
            "action_hint": "Run `mdtero setup` for browser OAuth, or `mdtero setup --api-key --json` for headless environments.",
            "next_commands": ["mdtero setup", "mdtero setup --api-key --json"],
        }
    try:
        usage = MdteroClient(config=cfg, timeout=10.0).usage()
    except MdteroApiError as exc:
        return {**exc.payload, "status": "failed"}
    except httpx.HTTPError as exc:
        return {
            "status": "unverified",
            "error_code": "api_connectivity_failed",
            "reason_code": "api_connectivity_failed",
            "detail": str(exc),
            "action_hint": "API key exists locally, but Mdtero could not verify it against the server. Check connectivity and rerun `mdtero doctor --json`.",
            "next_commands": ["mdtero doctor --json"],
        }
    return {
        "status": "ok",
        "email": usage.get("email"),
        "wallet_balance_display": usage.get("wallet_balance_display"),
    }


def _doctor_server_rag_status(cfg: MdteroConfig, root: Path, *, remote_auth: dict[str, Any]) -> dict[str, Any] | None:
    if not cfg.is_authenticated or remote_auth.get("status") == "failed":
        return None
    try:
        state = load_project(root)
    except Exception:
        return None
    project_id = str(state.server_project_id or "").strip()
    if not project_id:
        return None
    try:
        status = MdteroClient(config=cfg, timeout=10.0).rag_status(project_id)
    except (MdteroApiError, httpx.HTTPError) as exc:
        return {
            "status": "unavailable",
            "reason_code": "server_rag_status_unavailable",
            "server_project_id": project_id,
            "error_type": exc.__class__.__name__,
            "action_hint": "Server RAG status could not be fetched during doctor. Rerun `mdtero rag status --json` or check API connectivity.",
            "next_commands": ["mdtero rag status --json"],
        }
    sanitized = redact_sensitive_payload(status)
    if isinstance(sanitized, dict):
        sanitized.setdefault("server_project_id", project_id)
        return ensure_rag_contract(sanitized)
    return None


def _doctor_auth_next_commands(cfg: MdteroConfig, remote_auth: dict[str, Any]) -> list[str]:
    if not cfg.is_authenticated:
        return ["mdtero setup"]
    if remote_auth.get("status") == "failed":
        return [str(command) for command in remote_auth.get("next_commands") or ["mdtero setup --api-key --json", "mdtero doctor --json"]]
    return ["mdtero doctor --json"]


def _proxy_config_payload(cfg: MdteroConfig) -> dict[str, Any]:
    settings = proxy_settings_from_config(cfg)
    return {
        "configured": bool(settings.proxy_url),
        "proxy_url_present": bool(settings.proxy_url),
        "require_campus_proxy": settings.require_campus_proxy,
        "outlet_check": "required_before_network" if settings.require_campus_proxy else "not_required",
        "action_hint": (
            "Campus proxy is required; Mdtero will verify AS786/Jisc/Nottingham before discovery or route acquisition."
            if settings.require_campus_proxy
            else "Proxy is optional. Set MDTERO_PROXY_URL and MDTERO_REQUIRE_CAMPUS_PROXY=1 for guarded campus-network paper acquisition."
        ),
    }


def _proxy_config_detail(cfg: MdteroConfig) -> str:
    payload = _proxy_config_payload(cfg)
    if payload["require_campus_proxy"]:
        return "campus outlet check required; proxy configured" if payload["configured"] else "campus outlet check required; proxy missing"
    if payload["configured"]:
        return "proxy configured"
    return "set MDTERO_PROXY_URL to route local acquisition/discovery through a proxy"


def _doctor_row_status(rows: list[tuple[str, str, str]], check: str) -> dict[str, str] | None:
    for row_check, status, detail in rows:
        if row_check == check:
            return {"status": status, "detail": detail}
    return None


def _doctor_project_payload(root: Path, *, server_rag_status: dict[str, Any] | None = None) -> dict[str, Any]:
    target = project_path(root)
    if not target.exists():
        return {
            "initialized": False,
            "path": str(target),
            "next_commands": ["mdtero project init --name <name>", "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json"],
        }
    try:
        state = load_project(root)
    except Exception as exc:
        return {
            "initialized": True,
            "path": str(target),
            "readable": False,
            "error_type": exc.__class__.__name__,
            "next_commands": ["mdtero project status --json"],
        }
    pending = sum(1 for paper in state.papers if paper.status in {"pending", "created"} and not paper.task_id)
    running = sum(1 for paper in state.papers if paper.task_id and paper.status not in {"succeeded", "failed"})
    succeeded = sum(1 for paper in state.papers if paper.status == "succeeded")
    failed = sum(1 for paper in state.papers if paper.status == "failed")
    ready_for_ingest = sum(1 for paper in state.papers if paper.status == "succeeded" and paper.task_id)
    if server_rag_status:
        readiness = server_rag_status.get("readiness") if isinstance(server_rag_status.get("readiness"), dict) else {}
        ready_for_query = bool(readiness.get("ready_for_query"))
        provider_blocked = bool(readiness.get("provider_blocked"))
        needs_build = bool(readiness.get("needs_build"))
        needs_ingest = bool(readiness.get("needs_ingest"))
        if ready_for_query:
            rag_status = "ready"
        elif provider_blocked:
            rag_status = "provider_blocked"
        elif needs_build:
            rag_status = "needs_build"
        elif needs_ingest:
            rag_status = "needs_ingest"
        else:
            rag_status = str(server_rag_status.get("status") or "check")
        rag_next = [str(command) for command in server_rag_status.get("next_commands") or ["mdtero rag status --json"]]
    elif state.server_project_id and ready_for_ingest:
        rag_next = ["mdtero project ingest --json", ONE_COMMAND_RAG_BOOTSTRAP, "mdtero rag status --json", "mdtero rag build --wait --json"]
        rag_status = "check"
    elif state.server_project_id:
        rag_next = ["mdtero project parse --wait --timeout 300 --json", "mdtero project ingest --json"]
        rag_status = "needs_papers"
    elif ready_for_ingest:
        rag_next = [ONE_COMMAND_RAG_BOOTSTRAP, "mdtero rag status --json", "mdtero rag build --wait --json", "mdtero rag query \"<question>\" --build-if-needed --json"]
        rag_status = "not_linked"
    else:
        rag_next = ["mdtero discover \"<topic>\" --interactive", "mdtero project parse --wait --timeout 300 --json"]
        rag_status = "not_ready"
    return {
        "initialized": True,
        "readable": True,
        "path": str(target),
        "name": state.name,
        "server_project_id": state.server_project_id,
        "paper_count": len(state.papers),
        "pending_count": pending,
        "running_count": running,
        "succeeded_count": succeeded,
        "failed_count": failed,
        "ready_for_ingest_count": ready_for_ingest,
        "rag_status": rag_status,
        "server_rag_status": server_rag_status,
        "next_commands": rag_next,
    }


def _dedupe_string_list(values: list[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        cleaned = str(value or "").strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def _doctor_project_rows(root: Path, *, server_rag_status: dict[str, Any] | None = None) -> list[tuple[str, str, str]]:
    try:
        state = load_project(root)
    except Exception as exc:
        return [("Project state", "unreadable", f"{exc.__class__.__name__}: {exc}")]
    pending = sum(1 for paper in state.papers if paper.status in {"pending", "created"} and not paper.task_id)
    running = sum(1 for paper in state.papers if paper.task_id and paper.status not in {"succeeded", "failed"})
    succeeded = sum(1 for paper in state.papers if paper.status == "succeeded")
    failed = sum(1 for paper in state.papers if paper.status == "failed")
    ready_for_ingest = sum(1 for paper in state.papers if paper.status == "succeeded" and paper.task_id)
    rows = [
        (
            "Project papers",
            "ok" if state.papers else "empty",
            f"{len(state.papers)} total / {pending} pending / {running} running / {succeeded} succeeded / {failed} failed",
        ),
        (
            "Server project",
            "ok" if state.server_project_id else "not linked",
            state.server_project_id or f"run {ONE_COMMAND_RAG_BOOTSTRAP}",
        ),
    ]
    if server_rag_status:
        reason_code = str(server_rag_status.get("reason_code") or "unknown")
        readiness = server_rag_status.get("readiness") if isinstance(server_rag_status.get("readiness"), dict) else {}
        agent_summary = server_rag_status.get("agent_summary") if isinstance(server_rag_status.get("agent_summary"), dict) else {}
        if readiness.get("ready_for_query"):
            rows.append(("RAG readiness", "ready", f"{reason_code}; query with mdtero rag query \"<question>\" --build-if-needed --json"))
        elif readiness.get("provider_blocked"):
            rows.append(("RAG readiness", "blocked", f"{reason_code}; {server_rag_status.get('action_hint') or 'check backend RAG provider'}"))
        else:
            next_step = str(readiness.get("next_step") or "inspect_status")
            next_commands = server_rag_status.get("next_commands") if isinstance(server_rag_status.get("next_commands"), list) else ["mdtero rag status --json"]
            rows.append(("RAG readiness", next_step, f"{reason_code}; next: {next_commands[0]}"))
        provider = str(agent_summary.get("selected_provider") or server_rag_status.get("selected_provider") or "unknown")
        provider_state = str(agent_summary.get("provider_state") or server_rag_status.get("provider_state") or "unknown")
        embedding_model = str(agent_summary.get("embedding_model") or server_rag_status.get("embedding_model") or "unknown")
        rows.append(("Server RAG provider", provider_state, f"{provider} / {embedding_model}"))
    elif state.server_project_id and ready_for_ingest:
        rows.append(("RAG readiness", "check", "run mdtero project ingest --json, then mdtero rag status --json"))
    elif state.server_project_id:
        rows.append(("RAG readiness", "needs papers", "parse papers before mdtero project ingest --json"))
    elif ready_for_ingest:
        rows.append(("RAG readiness", "not linked", f"run {ONE_COMMAND_RAG_BOOTSTRAP}"))
    else:
        rows.append(("RAG readiness", "not ready", "add and parse papers before RAG"))
    return rows


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
    explicit = {
        "elsevier_api_key": getattr(_args, "elsevier_key", None),
        "wiley_tdm_token": getattr(_args, "wiley_tdm_token", None),
        "semantic_scholar_api_key": getattr(_args, "semantic_scholar_key", None),
    }
    provided = {field: str(value).strip() for field, value in explicit.items() if value is not None and str(value).strip()}
    if provided or getattr(_args, "json", False):
        path = config_path()
        if provided:
            for field, value in provided.items():
                setattr(cfg.academic, field, value)
            path = save_config(cfg)
        payload = _academic_config_summary(cfg, path=path, saved=bool(provided))
        if getattr(_args, "json", False):
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            console = Console()
            console.print(f"Saved academic config to {path}")
            console.print(payload["discover_source"])
        return 0
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
        batch_files, failure = _validated_parse_batch_files(args.batch)
        if failure:
            _print_result(failure, json_output=args.json or args.trace)
            return 2
        for path in batch_files:
            result = client.upload(path)
            submissions.append((result, str(path), f"file:{path.suffix.lower().lstrip('.')}"))
            traces.append(upload_trace(path, result).to_dict())
    elif args.file:
        failure = _validated_parse_file_failure(args.file)
        if failure:
            _print_result(failure, json_output=args.json or args.trace)
            return 2
        result = client.upload(args.file, source_input=args.input)
        submissions.append((result, args.input or str(args.file), f"file:{args.file.suffix.lower().lstrip('.')}"))
        traces.append(upload_trace(args.file, result).to_dict())
    else:
        if not args.input:
            failure = _parse_input_failure(
                "parse_input_missing",
                action_hint="Provide one DOI/URL, one local PDF/EPUB/XML/HTML file, or a directory of supported files.",
            )
            _print_result(failure, json_output=args.json or args.trace)
            return 2
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
        except ProxyValidationError as exc:
            _print_result(exc.payload, json_output=args.json or args.trace)
            return 2
        except MdteroApiError as exc:
            _print_result(exc.payload, json_output=args.json or args.trace)
            return 2
        except httpx.HTTPStatusError as exc:
            _print_result(api_failure_payload(exc, method=exc.request.method, path=exc.request.url.path), json_output=args.json or args.trace)
            return 2
        submissions.append((result, args.input, "manual"))
        traces.append(parse_trace_from_route(args.input, route, result).to_dict())
    for result, input_value, source in submissions:
        _enrich_parse_submission(result)
        if result.get("task_id"):
            add_paper(Path.cwd(), paper_from_submission(input_value, result, source=source))
            if args.wait:
                task = _wait_for_task(client, str(result["task_id"]), args=args)
                _enrich_task_status(task)
                if task.get("status") != "timeout":
                    update_task(Path.cwd(), task)
                _merge_waited_task_into_submission(result, task)
    results = [result for result, _, _ in submissions]
    payload = results[0] if len(results) == 1 else {"items": results}
    if args.trace:
        payload = {"result": payload, "workflow": traces[0] if len(traces) == 1 else traces}
    _print_result(payload, json_output=args.json or args.trace)
    return 2 if any((result.get("final_task") or {}).get("status") == "timeout" for result in results) else 0


def cmd_parse_batch(args: argparse.Namespace) -> int:
    targets, failure = _validated_parse_batch_targets(args.path)
    if failure:
        _print_result(failure, json_output=args.json)
        return 2
    client = MdteroClient()
    items: list[dict[str, Any]] = []
    for index, target in enumerate(targets, start=1):
        item: dict[str, Any] = {"index": index, "input": target, "status": "submitted"}
        try:
            route, result, acquisition = client.parse_with_route(target)
            _enrich_parse_submission(result)
            item.update({"task_id": result.get("task_id"), "route_kind": route.get("route_kind")})
            if acquisition:
                item["client_acquisition"] = acquisition
            if result.get("task_id"):
                add_paper(Path.cwd(), paper_from_submission(target, result, source="parse-batch"))
            if args.wait and result.get("task_id"):
                task = _wait_for_task(client, str(result["task_id"]), args=args)
                _enrich_task_status(task)
                if task.get("status") != "timeout":
                    update_task(Path.cwd(), task)
                _merge_waited_task_into_submission(result, task)
                item.update(_batch_item_summary(target, result))
                if args.download and task.get("status") == "succeeded":
                    download = _download_task_artifact(
                        client,
                        str(result["task_id"]),
                        str(args.download),
                        args.output_dir,
                        task=task,
                        filename_template=args.filename_template,
                    )
                    item["download"] = download
                    item["path"] = download.get("path")
            else:
                item.update(_batch_item_summary(target, result))
        except Exception as exc:
            item.update(_batch_exception_payload(target, exc))
        items.append(item)
    failed_rows = [_failed_manifest_row(item) for item in items if item.get("status") in {"failed", "cancelled", "timeout"}]
    payload = {
        "status": "completed" if not failed_rows else "completed_with_failures",
        "input_path": str(args.path),
        "total_count": len(items),
        "succeeded_count": sum(1 for item in items if item.get("status") == "succeeded"),
        "failed_count": len(failed_rows),
        "downloaded_count": sum(1 for item in items if item.get("download")),
        "items": items,
        "failures": failed_rows,
    }
    if args.manifest:
        payload["manifest"] = _write_batch_manifests(args.output_dir, items)
    if args.json:
        print(json.dumps(redact_sensitive_payload(payload), indent=2, ensure_ascii=False))
    else:
        _print_parse_batch_summary(payload)
    return 1 if failed_rows else 0


def _validated_parse_batch_targets(path: Path) -> tuple[list[str], dict[str, Any] | None]:
    if not path.exists():
        return [], _parse_input_failure("batch_path_not_found", path=path, action_hint="Create the DOI/URL text file or pass the correct path.")
    if not path.is_file():
        return [], _parse_input_failure("batch_path_not_file", path=path, action_hint="Pass a text file with one DOI or URL per line. For local files use `mdtero parse --batch <directory>`.")
    targets = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        targets.append(line)
    if not targets:
        return [], _parse_input_failure("batch_no_targets", path=path, action_hint="Add one DOI or URL per line, then rerun `mdtero parse-batch <dois.txt> --wait --download paper_md --json`.")
    return targets, None


def _batch_item_summary(input_value: str, result: dict[str, Any]) -> dict[str, Any]:
    task = result.get("final_task") if isinstance(result.get("final_task"), dict) else result
    parse_outcome = _task_parse_outcome(task)
    route_summary = _task_quality_route_summary(task)
    return {
        "input": input_value,
        "task_id": result.get("task_id") or task.get("task_id"),
        "status": result.get("status") or task.get("status"),
        "quality_label": _task_quality_label(task),
        "reason_code": result.get("reason_code") or task.get("reason_code") or task.get("error_code"),
        "action_hint": result.get("action_hint") or task.get("action_hint"),
        "selected_provider": task.get("selected_provider") or _task_result(task).get("selected_provider"),
        "parser_strategy": task.get("parser_strategy") or _task_result(task).get("parser_strategy"),
        "parse_outcome": parse_outcome.get("outcome_code") if parse_outcome else None,
        "parse_billable": parse_outcome.get("billable") if parse_outcome else None,
        "parse_reason_codes": _join_values(parse_outcome.get("reason_codes") if parse_outcome else []),
        "route_best_connector": route_summary.get("best_connector") if route_summary else None,
        "route_best_quality_label": route_summary.get("best_quality_label") if route_summary else None,
        "route_needs_followup": route_summary.get("needs_followup") if route_summary else None,
        "title": _task_title(task),
        "doi": _task_doi(task) or _doi_from_input(input_value),
        "preferred_artifact": _preferred_parse_artifact(task),
    }


def _batch_exception_payload(input_value: str, exc: Exception) -> dict[str, Any]:
    if isinstance(exc, ProxyValidationError):
        payload = dict(exc.payload)
        payload.setdefault("input", input_value)
        payload.setdefault("status", "failed")
        return payload
    if isinstance(exc, AcquisitionError):
        return {"input": input_value, "status": "failed", "reason_code": exc.reason_code, "action_hint": exc.action_hint, "diagnostics": exc.diagnostics}
    if isinstance(exc, MdteroApiError):
        payload = dict(exc.payload)
        payload.setdefault("input", input_value)
        payload.setdefault("status", "failed")
        payload.setdefault("reason_code", payload.get("error_code") or "api_request_failed")
        return payload
    if isinstance(exc, httpx.HTTPStatusError):
        payload = api_failure_payload(exc, method=exc.request.method, path=exc.request.url.path)
        payload["input"] = input_value
        return payload
    return {
        "input": input_value,
        "status": "failed",
        "reason_code": exc.__class__.__name__,
        "action_hint": "Check the target with `mdtero parse <doi-or-url> --trace --wait --timeout 300 --json`, then retry the batch.",
        "message": str(exc),
    }


def _failed_manifest_row(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "input": item.get("input"),
        "task_id": item.get("task_id"),
        "status": item.get("status"),
        "quality_label": item.get("quality_label"),
        "reason_code": item.get("reason_code") or item.get("error_code"),
        "parse_outcome": item.get("parse_outcome"),
        "parse_reason_codes": item.get("parse_reason_codes"),
        "action_hint": item.get("action_hint"),
    }


def _enrich_parse_submission(result: dict[str, Any]) -> dict[str, Any]:
    task_id = str(result.get("task_id") or result.get("id") or "").strip()
    if not task_id:
        return result
    result.setdefault("task_id", task_id)
    result.setdefault("task_api", "/api/v1/tasks/{task_id}")
    result.setdefault("download_api", "/api/v1/tasks/{task_id}/download/{artifact}")
    _apply_quality_label(result)
    preferred_artifact = _preferred_parse_artifact(result)
    result.setdefault("preferred_artifact", preferred_artifact)
    next_commands = [str(command).strip() for command in result.get("next_commands") or [] if str(command).strip()]
    defaults = [
        f"mdtero status {task_id} --wait --timeout 300 --json",
        f"mdtero download {task_id} {preferred_artifact} --output-dir ./mdtero-output --json",
    ]
    for command in defaults:
        if command not in next_commands:
            next_commands.append(command)
    result["next_commands"] = next_commands
    return result


def _validated_parse_batch_files(batch_path: Path) -> tuple[list[Path], dict[str, Any] | None]:
    if not batch_path.exists():
        return [], _parse_input_failure(
            "batch_path_not_found",
            path=batch_path,
            action_hint="Create the directory or pass the correct path to a folder containing PDF, EPUB, XML, or HTML files.",
        )
    if not batch_path.is_dir():
        return [], _parse_input_failure(
            "batch_path_not_directory",
            path=batch_path,
            action_hint="Pass a directory to `--batch`, or use `--file` for a single PDF, EPUB, XML, or HTML file.",
        )
    files = [path for path in sorted(batch_path.iterdir()) if path.is_file() and path.suffix.lower() in SUPPORTED_PARSE_FILE_SUFFIXES]
    if not files:
        return [], _parse_input_failure(
            "batch_no_supported_files",
            path=batch_path,
            action_hint="Add PDF, EPUB, XML, or HTML files to the batch directory, or parse one supported file with `--file`.",
        )
    return files, None


def _validated_parse_file_failure(file_path: Path) -> dict[str, Any] | None:
    if not file_path.exists():
        return _parse_input_failure(
            "file_path_not_found",
            path=file_path,
            action_hint="Pass an existing PDF, EPUB, XML, or HTML file path, or use a DOI/URL without `--file`.",
        )
    if not file_path.is_file():
        return _parse_input_failure(
            "file_path_not_file",
            path=file_path,
            action_hint="Pass a file to `--file`; for directories use `mdtero parse --batch <directory> --wait --timeout 300 --json`.",
        )
    if file_path.suffix.lower() not in SUPPORTED_PARSE_FILE_SUFFIXES:
        return _parse_input_failure(
            "file_type_not_supported",
            path=file_path,
            action_hint="Mdtero upload parse currently accepts PDF, EPUB, XML, HTML, or HTM files. Convert or export the source first, then retry.",
        )
    return None


def _parse_input_failure(reason_code: str, *, path: Path | None = None, action_hint: str) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "failed",
        "error_code": reason_code,
        "reason_code": reason_code,
        "action_hint": action_hint,
        "supported_extensions": SUPPORTED_PARSE_FILE_EXTENSIONS,
        "next_commands": [
            "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json",
            "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json",
            "mdtero parse --batch <directory> --wait --timeout 300 --json",
        ],
    }
    if path is not None:
        payload["path"] = str(path)
    return payload


def _merge_waited_task_into_submission(result: dict[str, Any], task: dict[str, Any]) -> dict[str, Any]:
    _promote_task_result_fields(task)
    submission_status = str(result.get("status") or "").strip()
    if submission_status:
        result.setdefault("submission_status", submission_status)
    result["final_task"] = task
    for key in (
        "status",
        "stage",
        "reason_code",
        "error_code",
        "error_message",
        "selected_provider",
        "parser_strategy",
        "client_acquisition",
        "parse_outcome",
        "download_artifacts",
        "quality_label",
        "quality_warning",
        "result",
        "preferred_artifact",
        "next_commands",
    ):
        if key in task:
            result[key] = task[key]
    if "task_id" in task:
        result["task_id"] = task["task_id"]
    result.setdefault("task_api", "/api/v1/tasks/{task_id}")
    result.setdefault("download_api", "/api/v1/tasks/{task_id}/download/{artifact}")
    return result


def _preferred_parse_artifact(result: dict[str, Any]) -> str:
    nested = result.get("result") if isinstance(result.get("result"), dict) else {}
    task_kind = str(result.get("task_kind") or nested.get("task_kind") if isinstance(nested, dict) else "").strip()
    candidates = [
        result.get("preferred_artifact"),
        nested.get("preferred_artifact") if isinstance(nested, dict) else None,
        result.get("artifact"),
        nested.get("artifact") if isinstance(nested, dict) else None,
    ]
    artifacts = nested.get("artifacts") if isinstance(nested, dict) and isinstance(nested.get("artifacts"), dict) else {}
    if isinstance(artifacts, dict):
        candidates.extend([
            "translated_md" if "translated_md" in artifacts else None,
            "paper_md" if "paper_md" in artifacts else None,
            "paper_bundle" if "paper_bundle" in artifacts else None,
        ])
    for candidate in candidates:
        cleaned = str(candidate or "").strip()
        if cleaned:
            return cleaned
    if task_kind == "translate":
        return "translated_md"
    return "paper_md"


def cmd_discover(args: argparse.Namespace) -> int:
    query = _discover_query(args.query)
    try:
        result = MdteroClient().discover(query, limit=args.limit)
    except ProxyValidationError as exc:
        if args.json:
            print(json.dumps(exc.payload, indent=2, ensure_ascii=False))
        else:
            Console().print(f"Discovery failed: {exc.payload.get('reason_code')}")
            Console().print(str(exc.payload.get("action_hint") or ""))
        return 2
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
    _print_discovery_fallback_notice(result)
    _print_discovery_table(result)
    if project_add is not None:
        Console().print(f"Added {project_add['added_count']} discovery result(s) to project; skipped {project_add['skipped_count']}.")
    return 0


def _discover_query(value: Any) -> str:
    if isinstance(value, list):
        return " ".join(str(part).strip() for part in value if str(part).strip()).strip()
    return str(value or "").strip()


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


def _print_discovery_fallback_notice(result: dict[str, Any], *, console: Console | None = None) -> None:
    fallback = result.get("discovery_fallback") if isinstance(result.get("discovery_fallback"), dict) else None
    if not fallback:
        return
    target = console or Console()
    reason = str(fallback.get("reason_code") or "semantic_scholar_local_failed")
    hint = str(fallback.get("action_hint") or "Using server OpenAlex fallback for this query.")
    target.print(f"Semantic Scholar local discovery failed ({reason}); using server OpenAlex fallback.")
    target.print(hint)


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
    source = str(result.get("source") or "unknown")
    fallback = result.get("discovery_fallback") if isinstance(result.get("discovery_fallback"), dict) else None
    summary = {
        "selection": selected_indices,
        "source": source,
        "source_mode": "semantic_scholar_local" if source == "semantic_scholar_local" else "openalex_server",
        "fallback_reason_code": fallback.get("reason_code") if fallback else None,
        "added_count": len(added),
        "skipped_count": len(skipped),
        "added": added,
        "skipped": skipped,
        "next_commands": _discovery_project_next_commands(len(added)),
    }
    if state is not None:
        summary["project"] = _project_payload(load_project(Path.cwd()))
    return summary


def _discovery_project_next_commands(added_count: int) -> list[str]:
    if added_count <= 0:
        return ["mdtero project status --json", "mdtero discover \"<topic>\" --limit 5 --interactive", "mdtero discover \"<topic>\" --limit 5 --add --select 1,3 --json"]
    return ["mdtero project parse --wait --timeout 300 --json", "mdtero project refresh --wait --timeout 300 --json", "mdtero project download --output-dir ./mdtero-output --json"]


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
    client = MdteroClient()
    try:
        result, reused = _find_or_create_server_project(client, name, description=args.description or f"Mdtero local project: {state.name}")
    except Exception as exc:
        payload = _project_create_server_failure(state, exc)
        _print_project_create_server_failure(payload, json_output=args.json)
        return 1
    server_project_id = str(result.get("id") or "").strip()
    if not server_project_id:
        payload = _project_create_server_failure(state, RuntimeError("server_project_id_missing"), project=result)
        _print_project_create_server_failure(payload, json_output=args.json)
        return 1
    state = bind_server_project(root, server_project_id)
    payload = {"server_project_id": state.server_project_id, "project": result, "reused_server_project": reused}
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        verb = "Linked existing" if reused else "Created"
        Console().print(f"{verb} server project {state.server_project_id} for {state.name}")
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
        _enrich_parse_submission(result)
        update_paper_submission(root, paper.input, result)
        if args.wait and result.get("task_id"):
            task = _wait_for_task(client, str(result["task_id"]), args=args)
            _enrich_task_status(task)
            if task.get("status") != "timeout":
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
    return 2 if any((item["task"].get("final_task") or {}).get("status") == "timeout" for item in results) else 0


def cmd_project_refresh(args: argparse.Namespace) -> int:
    root = Path.cwd()
    state = load_project(root)
    client = MdteroClient()
    results = []
    for task_id in project_task_ids(state):
        task = _wait_for_task(client, task_id, args=args) if args.wait else client.task(task_id)
        _enrich_task_status(task)
        if task.get("status") != "timeout":
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
    return 2 if any(task.get("status") == "timeout" for task in results) else 0


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
    project_id = _server_project_id_or_report(args, command="project_ingest")
    if project_id is None:
        return 1
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
        print(json.dumps(redact_sensitive_payload(payload), indent=2, ensure_ascii=False))
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
    task = _wait_for_task(client, args.task_id, args=args) if args.wait else client.task(args.task_id)
    _enrich_task_status(task)
    if task.get("status") != "timeout":
        update_task(Path.cwd(), task)
    payload = {"task": task, "workflow": status_trace(task).to_dict()} if args.trace else task
    _print_result(payload, json_output=args.json or args.trace)
    return 2 if task.get("status") == "timeout" else 0


def _wait_for_task(client: MdteroClient, task_id: str, *, args: argparse.Namespace) -> dict[str, Any]:
    interval = max(0.25, float(getattr(args, "interval", DEFAULT_WAIT_INTERVAL_SECONDS) or DEFAULT_WAIT_INTERVAL_SECONDS))
    timeout = max(0.25, float(getattr(args, "timeout", DEFAULT_WAIT_TIMEOUT_SECONDS) or DEFAULT_WAIT_TIMEOUT_SECONDS))
    try:
        return client.wait(task_id, interval=interval, timeout=timeout)
    except TimeoutError:
        return _task_wait_timeout_payload(task_id, timeout=timeout, interval=interval)


def _task_wait_timeout_payload(task_id: str, *, timeout: float, interval: float) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "status": "timeout",
        "stage": "waiting",
        "reason_code": "task_wait_timeout",
        "action_hint": "The task is still running or queued after the local wait timeout. Poll again later or use a larger --timeout value.",
        "wait": {"timeout_seconds": timeout, "interval_seconds": interval},
        "task_api": "/api/v1/tasks/{task_id}",
        "download_api": "/api/v1/tasks/{task_id}/download/{artifact}",
        "next_commands": [
            f"mdtero status {task_id} --wait --timeout {int(timeout)} --json",
            f"mdtero status {task_id} --json",
        ],
    }


def _enrich_task_status(task: dict[str, Any]) -> dict[str, Any]:
    task_id = str(task.get("task_id") or task.get("id") or "").strip()
    if not task_id:
        return task
    _promote_task_result_fields(task)
    _apply_quality_label(task)
    task.setdefault("task_id", task_id)
    task.setdefault("task_api", "/api/v1/tasks/{task_id}")
    task.setdefault("download_api", "/api/v1/tasks/{task_id}/download/{artifact}")
    status = str(task.get("status") or "").strip().lower()
    preferred_artifact = _preferred_parse_artifact(task)
    if status == "succeeded":
        selected_artifact = str(task.get("preferred_artifact") or preferred_artifact or "").strip()
        if selected_artifact:
            task.setdefault("preferred_artifact", selected_artifact)
            result = task.get("result") if isinstance(task.get("result"), dict) else {}
            result.setdefault("preferred_artifact", selected_artifact)
            task["result"] = result
    next_commands = [str(command).strip() for command in task.get("next_commands") or [] if str(command).strip()]
    if next_commands:
        task["next_commands"] = next_commands
        return task
    defaults: list[str]
    if status == "succeeded":
        defaults = [f"mdtero download {task_id} {preferred_artifact} --output-dir ./mdtero-output --json"]
    elif status in {"failed", "cancelled"}:
        is_translation = str(task.get("task_kind") or "").strip() == "translate" or bool(task.get("translation_attempts"))
        defaults = [f"mdtero status {task_id} --json"]
        if is_translation:
            defaults.extend([
                "mdtero translate <parse-task-id-or-paper.md> --to zh-CN --wait --timeout 600 --json",
                "mdtero smoke --skip-translate --json",
            ])
        else:
            defaults.append("mdtero project parse --include-failed --wait --timeout 300 --json")
    else:
        defaults = [f"mdtero status {task_id} --wait --timeout 300 --json"]
    for command in defaults:
        if command not in next_commands:
            next_commands.append(command)
    task["next_commands"] = next_commands
    return task


def _promote_task_result_fields(task: dict[str, Any]) -> dict[str, Any]:
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    if not isinstance(result, dict):
        return task
    quality = result.get("quality") if isinstance(result.get("quality"), dict) else {}
    parse_outcome = result.get("parse_outcome") if isinstance(result.get("parse_outcome"), dict) else None
    promotions = {
        "selected_provider": result.get("selected_provider") or quality.get("selected_pdf_provider") or quality.get("provider"),
        "parser_strategy": result.get("parser_strategy") or quality.get("parser_strategy"),
        "reason_code": result.get("reason_code"),
        "action_hint": result.get("action_hint"),
        "next_commands": result.get("next_commands"),
        "client_acquisition": result.get("client_acquisition"),
        "parse_outcome": parse_outcome,
        "download_artifacts": result.get("download_artifacts"),
        "translation_attempts": result.get("translation_attempts"),
    }
    for key, value in promotions.items():
        if value not in (None, "", [], {}):
            task.setdefault(key, value)
    return task


def cmd_download(args: argparse.Namespace) -> int:
    client = MdteroClient()
    task: dict[str, Any] | None = None
    try:
        task = client.task(args.task_id)
        _enrich_task_status(task)
    except Exception:
        task = None
    filename_template = getattr(args, "filename_template", "{author}_{year}_{shorttitle}")
    download = _download_task_artifact(client, args.task_id, args.artifact, args.output_dir, task=task, filename_template=filename_template)
    payload = {
        "status": "downloaded",
        "task_id": args.task_id,
        "artifact": args.artifact,
        "path": download["path"],
        "original_filename": download.get("original_filename"),
        "quality_label": download.get("quality_label"),
        "quality_warning_code": download.get("quality_warning_code"),
        "quality_warning": download.get("quality_warning"),
        "parse_outcome": download.get("parse_outcome"),
        "parse_billable": download.get("parse_billable"),
        "parse_reason_codes": download.get("parse_reason_codes") or [],
    }
    if task:
        payload["task"] = _download_task_summary(task)
    if getattr(args, "manifest", False):
        payload["manifest"] = _append_download_manifest(args.output_dir, _manifest_row_from_task(task or {}, artifact=args.artifact, path=download["path"], input_value=None, original_filename=download.get("original_filename"), download=download))
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        Console().print(f"Downloaded {args.artifact} to {download['path']}")
        warning = download.get("quality_warning") or _quality_warning(str(download.get("quality_label") or ""))
        if warning or download.get("parse_billable") is False:
            Console().print(f"Warning: {warning or 'downloaded artifact is not marked billable full text; verify before citing it.'}")
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
                "action_hint": "The parse task does not expose a server-side paper_md path for translation. Run `mdtero status <task-id> --json`; if only a download artifact is available, download paper_md and run `mdtero translate <paper.md> --to zh-CN --wait --timeout 600 --json`.",
                "next_commands": [
                    f"mdtero status {args.task_or_file} --json",
                    f"mdtero download {args.task_or_file} paper_md --output-dir ./mdtero-output --json",
                    "mdtero translate <paper.md> --to zh-CN --wait --timeout 600 --json",
                ],
            }
            _print_result(payload, json_output=args.json)
            return 1
        raise
    _enrich_translate_submission(result)
    if getattr(args, "wait", False) and result.get("task_id"):
        final_task = _wait_for_task(client, str(result["task_id"]), args=args)
        _enrich_task_status(final_task)
        result["final_task"] = final_task
    _print_result(result, json_output=args.json)
    final_status = str((result.get("final_task") or {}).get("status") or "").lower()
    if final_status == "timeout":
        return 2
    if final_status in {"failed", "cancelled"}:
        return 1
    return 0


def _enrich_translate_submission(result: dict[str, Any]) -> dict[str, Any]:
    task_id = str(result.get("task_id") or result.get("id") or "").strip()
    if not task_id:
        return result
    result.setdefault("task_id", task_id)
    result.setdefault("task_api", "/api/v1/tasks/{task_id}")
    result.setdefault("download_api", "/api/v1/tasks/{task_id}/download/{artifact}")
    result.setdefault("preferred_artifact", "translated_md")
    next_commands = [str(command).strip() for command in result.get("next_commands") or [] if str(command).strip()]
    defaults = [
        f"mdtero status {task_id} --wait --timeout 300 --json",
        f"mdtero download {task_id} translated_md --output-dir ./mdtero-output --json",
    ]
    for command in defaults:
        if command not in next_commands:
            next_commands.append(command)
    result["next_commands"] = next_commands
    return result


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
    local_ready_count = _local_ready_for_rag_count(state)
    if local_ready_count == 0:
        payload = _rag_no_succeeded_tasks_payload(state, command="build")
        _print_rag_command_failure(payload, json_output=_args.json)
        return 1
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
            "action_hint": f"Some succeeded parse tasks could not be imported into the server project. Fix the import failures, rerun `{RAG_INGEST_COMMAND}`, then retry `{ONE_COMMAND_RAG_BOOTSTRAP}`.",
            "next_commands": [RAG_INGEST_COMMAND, ONE_COMMAND_RAG_BOOTSTRAP, RAG_STATUS_COMMAND, RAG_BUILD_COMMAND],
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
    if getattr(_args, "wait", False):
        status_after_build = _wait_for_rag_ready(client, project_id, args=_args)
        result.setdefault("status_after_build", status_after_build)
        if _rag_status_payload_is_ready(status_after_build):
            result.setdefault("status", status_after_build.get("status", "ready"))
            result.setdefault("reason_code", status_after_build.get("reason_code", "indexed"))
        else:
            result.setdefault("action_hint", "RAG build was submitted, but it did not become query-ready within the local wait timeout. Poll `mdtero rag status --json`, then retry `mdtero rag query \"<question>\" --build-if-needed --json`.")
            result.setdefault("next_commands", [RAG_STATUS_COMMAND, ONE_COMMAND_RAG_BOOTSTRAP, RAG_BUILD_COMMAND, GENERIC_RAG_QUERY_COMMAND])
    _print_result(redact_sensitive_payload(result), json_output=_args.json)
    return 0


def cmd_rag_query(args: argparse.Namespace) -> int:
    bootstrap: dict[str, Any] | None = None
    if getattr(args, "build_if_needed", False):
        client = MdteroClient()
        root = Path.cwd()
        state = load_project(root)
        if _local_ready_for_rag_count(state) == 0:
            payload = _rag_no_succeeded_tasks_payload(state, command="query", question=args.question)
            _print_rag_command_failure(payload, json_output=args.json)
            return 1
        try:
            project_id, bootstrap_meta = _ensure_server_project_for_rag(client, root, state, getattr(args, "project_id", None))
        except Exception as exc:
            payload = _rag_bootstrap_failure("query", exc)
            payload["question"] = args.question
            _print_rag_command_failure(payload, json_output=args.json)
            return 1
        ingest = _import_succeeded_tasks_to_server_project(client, load_project(root), project_id)
        bootstrap = {"bootstrap": bootstrap_meta, "ingest": ingest}
        if ingest["failures"]:
            payload = _rag_query_bootstrap_not_ready(project_id, args.question, bootstrap, reason_code="server_project_import_failed")
            _print_rag_command_failure(payload, json_output=args.json)
            return 1
        try:
            build = client.rag_build(project_id)
        except Exception as exc:
            payload = _rag_command_failure("build", project_id, exc)
            payload["command"] = "rag_query"
            payload["question"] = args.question
            payload["bootstrap"] = bootstrap
            _print_rag_command_failure(payload, json_output=args.json)
            return 1
        bootstrap["build"] = build
        if not _rag_status_payload_is_ready(build):
            status_after_build = _wait_for_rag_ready(client, project_id, args=args)
            bootstrap["status_after_build"] = status_after_build
            if not _rag_status_payload_is_ready(status_after_build):
                reason_code = str(status_after_build.get("reason_code") or "rag_index_not_ready")
                payload = _rag_query_build_not_ready(project_id, args.question, bootstrap, reason_code=reason_code)
                payload["status_after_build"] = status_after_build
                _print_rag_command_failure(payload, json_output=args.json)
                return 1
    else:
        client = MdteroClient()
        project_id = _server_project_id_or_report(args, command="query")
    if project_id is None:
        return 1
    try:
        result = client.rag_query(project_id, args.question)
    except Exception as exc:
        payload = _rag_command_failure("query", project_id, exc)
        if bootstrap is not None:
            payload["bootstrap"] = bootstrap
            payload.setdefault("question", args.question)
        _print_rag_command_failure(payload, json_output=args.json)
        return 1
    result = _normalize_rag_query_payload(result, project_id=project_id, question=args.question)
    if bootstrap is not None:
        result.setdefault("bootstrap", bootstrap)
    _print_rag_query_result(result, json_output=args.json)
    return 0


def _rag_query_bootstrap_not_ready(project_id: str, question: str, bootstrap: dict[str, Any], *, reason_code: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "command": "rag_query",
        "reason_code": reason_code,
        "error_code": "rag_precondition_failed",
        "server_project_id": project_id,
        "question": question,
        "bootstrap": bootstrap,
        "action_hint": f"RAG query bootstrap could not import every succeeded parse task. Fix the import failures, rerun `{RAG_INGEST_COMMAND}`, then retry `{ONE_COMMAND_RAG_BOOTSTRAP}`.",
        "next_commands": [RAG_INGEST_COMMAND, ONE_COMMAND_RAG_BOOTSTRAP, RAG_STATUS_COMMAND, RAG_BUILD_COMMAND, GENERIC_RAG_QUERY_COMMAND],
    }


def _rag_query_build_not_ready(project_id: str, question: str, bootstrap: dict[str, Any], *, reason_code: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "command": "rag_query",
        "reason_code": reason_code,
        "error_code": "rag_precondition_failed",
        "server_project_id": project_id,
        "question": question,
        "bootstrap": bootstrap,
        "action_hint": "Server-side Voyage RAG build has not become query-ready yet. Keep polling `mdtero rag status --json`, then retry the one-command RAG query.",
        "next_commands": [RAG_STATUS_COMMAND, ONE_COMMAND_RAG_BOOTSTRAP, RAG_BUILD_COMMAND, GENERIC_RAG_QUERY_COMMAND],
    }


def _rag_status_payload_is_ready(payload: dict[str, Any]) -> bool:
    status = str(payload.get("status") or "").lower()
    reason_code = str(payload.get("reason_code") or "").lower()
    return status in {"ready", "succeeded", "indexed"} or reason_code in {"indexed", "rag_index_ready", "rag_ready"}


def _local_ready_for_rag_count(state: Any) -> int:
    return sum(1 for paper in state.papers if paper.status == "succeeded" and paper.task_id)


def _rag_recovery_commands() -> list[str]:
    return [
        "mdtero parse 10.48550/arXiv.1706.03762 --trace --wait --timeout 300 --json",
        "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 600 --json",
        "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json",
        "mdtero project refresh --wait --timeout 300 --json",
        "mdtero rag query \"<question>\" --build-if-needed --json",
    ]


def _smoke_add_step(payload: dict[str, Any], name: str, status: str, **fields: Any) -> dict[str, Any]:
    step = {
        "name": name,
        "status": status,
        "duration_ms": fields.pop("duration_ms", None),
    }
    step.update({key: value for key, value in fields.items() if value not in (None, "", [], {})})
    payload.setdefault("steps", []).append(redact_sensitive_payload(step))
    return step


def _smoke_coverage_contract(args: argparse.Namespace) -> dict[str, Any]:
    timeout = int(float(getattr(args, "timeout", DEFAULT_WAIT_TIMEOUT_SECONDS) or DEFAULT_WAIT_TIMEOUT_SECONDS))
    translate_to = str(getattr(args, "translate_to", "zh-CN") or "zh-CN")
    skipped = []
    if getattr(args, "skip_discovery", False):
        skipped.append("discovery")
    if getattr(args, "skip_download", False):
        skipped.append("artifact_download")
    if getattr(args, "skip_translate", False):
        skipped.append("translation")
    if getattr(args, "skip_rag", False):
        skipped.extend(["rag", "mcp_briefing"])
    return {
        "schema_version": "2026-05-27",
        "goal": "production_cli_smoke",
        "covered_by_this_command": [
            "auth_config_presence",
            "server_openalex_or_local_semantic_scholar_discovery" if not getattr(args, "skip_discovery", False) else "discovery_skipped",
            "doi_or_url_route_parse_status",
            "artifact_download" if not getattr(args, "skip_download", False) else "artifact_download_skipped",
            "translation_task" if not getattr(args, "skip_translate", False) else "translation_skipped",
            "server_voyage_rag_build_query" if not getattr(args, "skip_rag", False) else "rag_skipped",
            "mcp_agent_briefing_contract" if not getattr(args, "skip_rag", False) else "mcp_briefing_skipped",
        ],
        "requires_separate_smoke": [
            {
                "id": "pdf_mineru_urlapi",
                "command": f"mdtero parse --file <paper.pdf> --trace --wait --timeout {timeout} --json",
                "reason": "PDF/MinerU URL API requires a user-selected local PDF and should not be implied by DOI smoke.",
            },
            {
                "id": "epub_upload",
                "command": f"mdtero parse --file <paper.epub> --trace --wait --timeout {timeout} --json",
                "reason": "EPUB upload is a separate raw-file path from DOI/native-source parsing.",
            },
            {
                "id": "browser_extension_mv3",
                "command": "npm --prefix extension test -- --run && npm --prefix extension run build && python3 scripts/ci/extension_dist_smoke.py",
                "reason": "Extension OAuth, current-page capture, PDF/EPUB upload UI, polling, translation, and download are packaged in the MV3 bundle.",
            },
        ],
        "post_success_next_commands": _dedupe_string_list([
            "mdtero doctor --json",
            f"mdtero parse --file <paper.pdf> --trace --wait --timeout {timeout} --json",
            f"mdtero translate <task-id-or-paper.md> --to {translate_to} --wait --timeout {timeout} --json",
            "mdtero rag query \"<question>\" --build-if-needed --json",
            "mdtero mcp briefing --json",
            "mdtero mcp serve",
        ]),
        "skipped_by_flags": skipped,
        "artifact_expectations": {
            "parse": ["paper_md", "paper_bundle"],
            "translate": ["translated_md"],
            "source": ["paper_pdf", "paper_xml"],
        },
        "evidence_fields": ["reason_code", "action_hint", "download_artifacts", "selected_provider", "parser_strategy", "client_acquisition", "citation_contract", "citations", "source_nodes"],
    }


def _enrich_smoke_failure_summary(payload: dict[str, Any]) -> dict[str, Any]:
    failed_steps = [
        step
        for step in payload.get("steps") or []
        if isinstance(step, dict) and str(step.get("status") or "").lower() == "failed"
    ]
    payload["reason_code"] = "smoke_failed"
    payload["failed_steps"] = [_smoke_failed_step_summary(step) for step in failed_steps]
    first_failed = failed_steps[0] if failed_steps else {}
    first_name = str(first_failed.get("name") or "unknown")
    first_reason = _smoke_step_reason_code(first_failed)
    first_hint = _smoke_step_action_hint(first_failed, first_reason)
    payload["primary_failure"] = {
        "step": first_name,
        "reason_code": first_reason,
        "action_hint": first_hint,
    }
    payload["action_hint"] = (
        f"Smoke failed at `{first_name}` with `{first_reason}`. "
        f"{payload['primary_failure']['action_hint']}"
    )
    recovery_commands: list[str] = []
    for step in failed_steps:
        recovery_commands.extend(_smoke_step_next_commands(step))
    if not recovery_commands:
        recovery_commands = _smoke_failure_next_commands(first_reason)
    payload["next_commands"] = _dedupe_string_list([*recovery_commands, *payload.get("next_commands", [])])
    return payload


def _smoke_failed_step_summary(step: dict[str, Any]) -> dict[str, Any]:
    reason_code = _smoke_step_reason_code(step)
    summary: dict[str, Any] = {
        "name": step.get("name"),
        "reason_code": reason_code,
        "action_hint": _smoke_step_action_hint(step, reason_code),
        "next_commands": _smoke_step_next_commands(step),
    }
    for key in ("task_id", "http_status", "server_project_id"):
        if step.get(key) not in (None, "", [], {}):
            summary[key] = step.get(key)
    return summary


def _smoke_step_reason_code(step: dict[str, Any]) -> str:
    result = step.get("result") if isinstance(step.get("result"), dict) else {}
    final_task = result.get("final_task") if isinstance(result.get("final_task"), dict) else {}
    return str(
        step.get("reason_code")
        or step.get("error_code")
        or final_task.get("reason_code")
        or final_task.get("error_code")
        or result.get("reason_code")
        or result.get("error_code")
        or "step_failed"
    )


def _smoke_step_action_hint(step: dict[str, Any], reason_code: str) -> str:
    result = step.get("result") if isinstance(step.get("result"), dict) else {}
    final_task = result.get("final_task") if isinstance(result.get("final_task"), dict) else {}
    hint = str(step.get("action_hint") or final_task.get("action_hint") or result.get("action_hint") or "").strip()
    return hint or _smoke_action_hint(reason_code)


def _smoke_step_next_commands(step: dict[str, Any]) -> list[str]:
    reason_code = _smoke_step_reason_code(step)
    result = step.get("result") if isinstance(step.get("result"), dict) else {}
    final_task = result.get("final_task") if isinstance(result.get("final_task"), dict) else {}
    if reason_code.startswith("translation_provider"):
        return _smoke_failure_next_commands(reason_code)
    commands = _detail_next_commands(step) or _detail_next_commands(result)
    if commands:
        return commands
    return _dedupe_string_list([*_smoke_failure_next_commands(reason_code), *_detail_next_commands(final_task)])


def _smoke_exception_payload(exc: Exception, *, default_reason: str) -> dict[str, Any]:
    detail = _http_error_detail(exc)
    message = str(detail.get("message") or exc)
    reason_code = str(detail.get("reason_code") or detail.get("error_code") or default_reason)
    if default_reason == "mcp_briefing_failed" and message.startswith("mcp_briefing_missing_tools"):
        reason_code = message
    status_code = _exception_status_code(exc)
    if status_code in {401, 403} or reason_code in {"authentication_required", "missing_or_invalid_credentials"}:
        reason_code = "authentication_required" if status_code != 403 else "forbidden"
    action_hint = str(detail.get("action_hint") or _smoke_action_hint(reason_code))
    payload = {
        "reason_code": reason_code,
        "error_code": reason_code,
        "error_type": exc.__class__.__name__,
        "http_status": status_code,
        "message": message,
        "action_hint": action_hint,
        "next_commands": _detail_next_commands(detail) or _smoke_failure_next_commands(reason_code),
    }
    return redact_sensitive_payload(payload)


def _smoke_action_hint(reason_code: str) -> str:
    if reason_code in {"auth_missing", "authentication_required", "unauthorized", "forbidden"}:
        return "Production auth failed. Configure a valid Mdtero API key, verify with `mdtero doctor --json`, then rerun smoke."
    if reason_code in {"rag_index_not_built", "project_has_no_chunks", "server_project_import_failed"}:
        return "Check server RAG with `mdtero rag status --json`, then rerun `mdtero smoke --json`."
    if reason_code.startswith("translation_provider") or reason_code in {"translate_failed", "translation_task_id_missing"}:
        return "Check backend translation provider diagnostics, quota, and API keys, then rerun `mdtero smoke --json`."
    if reason_code in {"task_wait_timeout", "rag_wait_timeout"}:
        return "The backend is still processing. Rerun smoke with a larger --timeout, or poll the task/RAG status directly."
    if reason_code == "mcp_briefing_failed" or reason_code.startswith("mcp_briefing_missing_tools"):
        return "Check local project state with `mdtero mcp briefing --json`; the CLI should expose agent_briefing, server_rag_status, server_rag_build, and rag_query before launch."
    return "Inspect this smoke step and rerun after fixing the reported backend or client path."


def _smoke_failure_next_commands(reason_code: str) -> list[str]:
    if reason_code in {"auth_missing", "authentication_required", "unauthorized", "forbidden"}:
        return ["mdtero setup --api-key --json", "mdtero doctor --json", "mdtero smoke --json --timeout 600 --interval 2"]
    if reason_code in {"rag_index_not_built", "project_has_no_chunks", "server_project_import_failed", "rag_failed"}:
        return [ONE_COMMAND_RAG_BOOTSTRAP, RAG_STATUS_COMMAND, RAG_BUILD_COMMAND, GENERIC_RAG_QUERY_COMMAND, RAG_MCP_BRIEFING_COMMAND, RAG_MCP_SERVE_COMMAND]
    if reason_code == "mcp_briefing_failed" or reason_code.startswith("mcp_briefing_missing_tools"):
        return ["mdtero mcp briefing --json", "mdtero rag status --json", "mdtero mcp serve"]
    if reason_code in {"parse_failed", "task_wait_timeout"}:
        return ["mdtero parse 10.48550/arXiv.1706.03762 --trace --wait --timeout 600 --json", "mdtero status <task-id> --json"]
    if reason_code.startswith("translation_provider") or reason_code in {"translate_failed", "translation_task_id_missing"}:
        return [
            "mdtero status <translation-task-id> --json",
            "mdtero translate <task-id-or-paper.md> --to zh-CN --wait --timeout 600 --json",
            "mdtero smoke --skip-translate --json",
        ]
    return ["mdtero doctor --json", "mdtero smoke --json"]


def _wait_for_rag_ready(client: MdteroClient, project_id: str, *, args: argparse.Namespace) -> dict[str, Any]:
    interval = max(0.5, float(getattr(args, "interval", DEFAULT_WAIT_INTERVAL_SECONDS) or DEFAULT_WAIT_INTERVAL_SECONDS))
    timeout = max(0.5, float(getattr(args, "timeout", DEFAULT_WAIT_TIMEOUT_SECONDS) or DEFAULT_WAIT_TIMEOUT_SECONDS))
    deadline = time.monotonic() + timeout
    last_status: dict[str, Any] = {}
    while True:
        last_status = client.rag_status(project_id)
        status = str(last_status.get("status") or "").lower()
        reason_code = str(last_status.get("reason_code") or "").lower()
        if status in {"ready", "succeeded", "indexed"} or reason_code in {"indexed", "rag_index_ready", "rag_ready"}:
            return last_status
        if status in {"failed", "cancelled", "error"}:
            return last_status
        if time.monotonic() >= deadline:
            last_status.setdefault("status", "timeout")
            last_status.setdefault("reason_code", "rag_wait_timeout")
            last_status.setdefault("action_hint", "RAG build did not become ready within the local wait timeout. Poll again later with `mdtero rag status --json`.")
            last_status.setdefault("next_commands", ["mdtero rag status --json", "mdtero rag query \"<question>\" --build-if-needed --json"])
            return last_status
        time.sleep(interval)


def _print_smoke_result(payload: dict[str, Any], *, json_output: bool) -> None:
    payload = redact_sensitive_payload(payload)
    if json_output:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    console = Console()
    console.print(f"Smoke: {payload.get('status')} ({payload.get('reason_code')})")
    console.print(f"Workdir: {payload.get('workdir')}")
    table = Table("Step", "Status", "Reason")
    for step in payload.get("steps") or []:
        table.add_row(str(step.get("name") or ""), str(step.get("status") or ""), str(step.get("reason_code") or step.get("error_code") or ""))
    console.print(table)
    action_hint = str(payload.get("action_hint") or "").strip()
    if action_hint:
        console.print(f"Hint: {action_hint}")
    next_commands = [str(command).strip() for command in payload.get("next_commands") or [] if str(command).strip()]
    if next_commands:
        console.print("Next:")
        for command in next_commands:
            console.print(f"  {command}")


def _rag_no_succeeded_tasks_payload(state: Any, *, command: str, question: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "not_ready",
        "command": f"rag_{command}",
        "reason_code": "no_succeeded_tasks",
        "error_code": "rag_precondition_failed",
        "server_project_id": state.server_project_id,
        "project": state.name,
        "local_ready_for_ingest_count": 0,
        "local_paper_count": len(state.papers),
        "action_hint": "Parse at least one paper successfully before building or querying server-side Voyage RAG. Use the arXiv smoke DOI, direct file upload, or browser-extension handoff, then refresh the local project.",
        "next_commands": _rag_recovery_commands(),
    }
    if question is not None:
        payload["question"] = question
        payload["answer"] = None
    return payload


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
            next_commands = [RAG_INGEST_COMMAND]
            if indexed:
                next_commands.append(ONE_COMMAND_RAG_BOOTSTRAP)
            next_commands.append(RAG_STATUS_COMMAND)
            if indexed:
                next_commands.append(RAG_BUILD_COMMAND)
            payload = {
                "status": "unavailable",
                "reason_code": "server_rag_status_unavailable",
                "project": state.name,
                "server_project_id": project_id,
                "local_ready_for_ingest_count": indexed,
                "local_paper_count": len(state.papers),
                "error_type": exc.__class__.__name__,
                "http_status": http_status,
                "action_hint": f"Server RAG status is unavailable. Deploy the backend /api/v1 project RAG routes, then rerun `{ONE_COMMAND_RAG_BOOTSTRAP}` or inspect with `{RAG_STATUS_COMMAND}`.",
                "next_commands": next_commands,
            }
            ensure_rag_contract(payload)
            payload = redact_sensitive_payload(payload)
            if args.json:
                print(json.dumps(payload, indent=2, ensure_ascii=False))
            else:
                console.print(f"Project {state.name}: {indexed}/{len(state.papers)} local paper(s) have downloadable artifacts for server RAG.")
                console.print(f"Server project: {project_id}; status unavailable ({exc.__class__.__name__}).")
                console.print(f"Hint: {payload['action_hint']}")
                console.print("Next:")
                for command in next_commands:
                    console.print(f"  {command}")
                _print_rag_agent_tool_plan(payload, console=console)
            return 1
        summary = result.get("summary") if isinstance(result.get("summary"), dict) else {}
        result.setdefault("project", state.name)
        result.setdefault("server_project_id", str(project_id))
        result.setdefault("local_ready_for_ingest_count", indexed)
        result.setdefault("local_paper_count", len(state.papers))
        ensure_rag_contract(result)
        if args.json:
            print(json.dumps(redact_sensitive_payload(result), indent=2, ensure_ascii=False))
            return 0
        console.print(
            f"Project {state.name}: server RAG {result.get('status')} ({result.get('reason_code')}); "
            f"{summary.get('embedded_count', 0)}/{summary.get('chunk_count', 0)} chunk(s) embedded."
        )
        console.print(f"Server project: {project_id}; provider: {result.get('selected_provider')}; model: {summary.get('embedding_model') or 'unknown'}")
        action_hint = redact_sensitive_text(result.get("action_hint")).strip()
        if action_hint:
            console.print(f"Hint: {action_hint}")
        next_commands = [str(command).strip() for command in result.get("next_commands") or [] if str(command).strip()]
        if next_commands:
            console.print("Next:")
            for command in next_commands:
                console.print(f"  {command}")
        _print_rag_agent_tool_plan(redact_sensitive_payload(result), console=console)
        return 0
    payload = {
        "status": "not_ready",
        "reason_code": "server_project_not_linked",
        "project": state.name,
        "server_project_id": None,
        "local_ready_for_ingest_count": indexed,
        "local_paper_count": len(state.papers),
        "action_hint": f"Run `{ONE_COMMAND_RAG_BOOTSTRAP}` to create and bind a server project, import succeeded parse tasks, build server-side Voyage RAG, and query without copying a server project id.",
        "next_commands": [ONE_COMMAND_RAG_BOOTSTRAP, RAG_STATUS_COMMAND, RAG_BUILD_COMMAND, GENERIC_RAG_QUERY_COMMAND],
    }
    ensure_rag_contract(payload)
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    console.print(f"Project {state.name}: {indexed}/{len(state.papers)} local paper(s) have downloadable artifacts for server RAG.")
    console.print(f"Server project: not linked. Hint: {payload['action_hint']}")
    console.print("Next:")
    for command in payload["next_commands"]:
        console.print(f"  {command}")
    _print_rag_agent_tool_plan(payload, console=console)
    return 0


def cmd_mcp_serve(_args: argparse.Namespace) -> int:
    from .mcp import serve_project_context

    serve_project_context(Path.cwd())
    return 0


def cmd_mcp_briefing(args: argparse.Namespace) -> int:
    from .mcp import build_agent_briefing

    payload = build_agent_briefing(Path.cwd())
    if args.json:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        console = Console()
        console.print(f"Project: {payload['project']['name']}")
        console.print(f"RAG: {payload['rag']['status']} ({payload['rag']['reason_code']})")
        console.print("Next:")
        for command in payload.get("recommended_next_commands", [])[:8]:
            console.print(f"  {command}")
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


def _prompt_agent_targets(detections: list[Any], *, console: Console | None = None) -> list[str]:
    from .agent import default_interactive_targets, parse_agent_selection

    console = console or Console(stderr=True)
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


def _configure_detected_agent_skills(console: Console, *, skip_prompt: bool = False) -> None:
    if skip_prompt:
        console.print("\nStep 3: agent skill detection skipped for headless setup.")
        console.print("Run `mdtero agent install --interactive` later to detect and configure local agent workspaces.")
        return
    from .agent import detect_target_status, install_targets

    detections = detect_target_status()
    detected = [item for item in detections if item.detected]
    pending = [item for item in detections if item.detected and not item.installed]
    console.print("\nStep 3: local agent workspaces.")
    if not detected:
        console.print("No Codex, Claude Code, Gemini CLI, Hermes, or OpenCode workspace was detected.")
        console.print("Create an agent workspace, then run `mdtero agent install --interactive`.")
        return
    labels = ", ".join(item.label for item in detected)
    console.print(f"Detected: {labels}")
    if not pending:
        console.print("Mdtero skills are already installed for detected workspaces.")
        return
    if not Confirm.ask("Install Mdtero skills for detected agent workspaces now?", default=True):
        console.print("Skipped agent skill install. Run `mdtero agent install --interactive` later.")
        return
    targets = _prompt_agent_targets(detections, console=console)
    if not targets:
        console.print("No agent target selected. Run `mdtero agent install --interactive` later.")
        return
    results = install_targets(targets)
    table = Table("Agent", "Action", "Path")
    for result in results:
        table.add_row(result.label, result.action, result.path)
    console.print(table)


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
    result, reused = _find_or_create_server_project(client, state.name, description=f"Mdtero local project: {state.name}")
    server_project_id = str(result.get("id") or "").strip()
    if not server_project_id:
        raise RuntimeError("server_project_id_missing")
    bind_server_project(root, server_project_id)
    return server_project_id, {
        "created_server_project": not reused,
        "reused_server_project": reused,
        "bound_local_project": True,
        "used_explicit_project_id": False,
        "project": result,
    }


def _find_or_create_server_project(client: MdteroClient, name: str, *, description: str | None = None) -> tuple[dict[str, Any], bool]:
    normalized_name = str(name or "").strip()
    try:
        list_projects = getattr(client, "list_projects")
        projects = list_projects()
    except (AttributeError, httpx.HTTPStatusError, httpx.RequestError, MdteroApiError):
        projects = {}
    items = projects.get("items") if isinstance(projects, dict) else []
    if isinstance(items, list):
        for item in items:
            if isinstance(item, dict) and str(item.get("name") or "").strip() == normalized_name and str(item.get("id") or "").strip():
                return item, True
    return client.create_project(normalized_name, description=description), False


def _project_create_server_failure(state: Any, exc: Exception, *, project: dict[str, Any] | None = None) -> dict[str, Any]:
    detail = _http_error_detail(exc)
    status_code = _exception_status_code(exc)
    raw_reason = detail.get("reason_code") or detail.get("error_code")
    if raw_reason:
        reason_code = str(raw_reason)
    elif str(exc) == "server_project_id_missing":
        reason_code = "server_project_id_missing"
    elif status_code == 404:
        reason_code = "server_project_endpoint_missing"
    else:
        reason_code = "server_project_create_failed"
    if reason_code == "server_project_id_missing":
        action_hint = "The backend project creation response did not include an id. Check the /api/v1/projects contract, then rerun `mdtero project create-server --json`."
    elif status_code == 404:
        action_hint = "The backend /api/v1/projects endpoint is not deployed yet. Deploy the backend project/RAG routes, then rerun `mdtero project create-server --json`."
    else:
        action_hint = str(detail.get("action_hint") or "Check Mdtero API connectivity, authentication, and project permissions, then rerun `mdtero project create-server --json`.")
    payload: dict[str, Any] = {
        "status": "failed",
        "command": "project_create_server",
        "reason_code": reason_code,
        "error_code": str(detail.get("error_code") or "server_project_create_failed"),
        "project": state.name,
        "server_project_id": None,
        "http_status": status_code,
        "error_type": exc.__class__.__name__,
        "action_hint": action_hint,
        "next_commands": ["mdtero doctor --json", "mdtero project create-server --json", ONE_COMMAND_RAG_BOOTSTRAP, "mdtero rag status --json", "mdtero rag build --wait --json"],
    }
    if project is not None:
        payload["server_response"] = project
    return redact_sensitive_payload(payload)


def _print_project_create_server_failure(payload: dict[str, Any], *, json_output: bool) -> None:
    payload = redact_sensitive_payload(payload)
    if json_output:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    console = Console()
    console.print(f"Server project create failed: {payload['reason_code']}")
    console.print(f"Hint: {payload['action_hint']}")
    console.print("Next:")
    for command in payload.get("next_commands") or []:
        console.print(f"  {command}")


def _import_succeeded_tasks_to_server_project(client: MdteroClient, state: Any, project_id: str) -> dict[str, Any]:
    results = []
    failures = []
    for paper in state.papers:
        if paper.status != "succeeded" or not paper.task_id:
            continue
        try:
            result = client.import_task_to_project(project_id, paper.task_id)
        except (httpx.HTTPStatusError, MdteroApiError) as exc:
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


def _project_ingest_failure(project_id: str, paper: PaperRecord, exc: Exception) -> dict[str, Any]:
    status_code = _exception_status_code(exc)
    detail = _http_error_detail(exc)
    reason_code = str(detail.get("reason_code") or detail.get("error_code") or "server_project_import_failed")
    error_code = "server_project_import_unavailable" if status_code == 404 else "server_project_import_failed"
    action_hint = (
        "The backend did not expose the project task import endpoint yet. Deploy the backend branch with "
        "POST /api/v1/projects/{id}/tasks/{task_id}/import, then rerun `mdtero project ingest --json`; "
        "use `mdtero rag status --json` to verify the linked server project."
        if status_code == 404
        else str(detail.get("action_hint") or "Check the server project id, API key permissions, and task ownership, then rerun `mdtero project ingest --json`.")
    )
    return {
        "input": paper.input,
        "task_id": paper.task_id,
        "status": "failed",
        "error_code": error_code,
        "reason_code": reason_code,
        "http_status": status_code,
        "error_type": exc.__class__.__name__,
        "server_project_id": project_id,
        "action_hint": action_hint,
    }


def _rag_command_failure(command: str, project_id: str, exc: Exception) -> dict[str, Any]:
    detail = _http_error_detail(exc)
    reason_code = str(detail.get("reason_code") or "server_rag_command_failed")
    action_hint = _public_rag_action_hint(command, reason_code, detail.get("action_hint"))
    next_commands = _detail_next_commands(detail) or _rag_failure_next_commands(command, reason_code)
    return {
        "status": "failed",
        "command": f"rag_{command}",
        "reason_code": reason_code,
        "error_code": str(detail.get("error_code") or "server_rag_failed"),
        "server_project_id": project_id,
        "http_status": exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None,
        "error_type": exc.__class__.__name__,
        "action_hint": action_hint,
        "next_commands": next_commands,
    }


def _rag_bootstrap_failure(command: str, exc: Exception) -> dict[str, Any]:
    detail = _http_error_detail(exc)
    reason_code = str(detail.get("reason_code") or detail.get("error_code") or exc)
    if reason_code == "server_project_id_missing":
        action_hint = f"The server project creation response did not include an id. Check the backend project API contract, then rerun `{ONE_COMMAND_RAG_BOOTSTRAP}`."
    else:
        action_hint = str(detail.get("action_hint") or f"Retry `{ONE_COMMAND_RAG_BOOTSTRAP}` so the CLI can create or link a server project before running server-side Voyage RAG.")
    next_commands = _detail_next_commands(detail) or [ONE_COMMAND_RAG_BOOTSTRAP, "mdtero project create-server --json", RAG_INGEST_COMMAND, RAG_STATUS_COMMAND, RAG_BUILD_COMMAND]
    return {
        "status": "failed",
        "command": f"rag_{command}",
        "reason_code": reason_code,
        "error_code": str(detail.get("error_code") or "rag_bootstrap_failed"),
        "server_project_id": None,
        "http_status": exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None,
        "error_type": exc.__class__.__name__,
        "action_hint": action_hint,
        "next_commands": next_commands,
    }


def _public_rag_action_hint(command: str, reason_code: str, server_hint: object | None = None) -> str:
    if reason_code == "voyage_not_configured":
        return (
            "Server-side Voyage RAG is not available for this Mdtero deployment yet. "
            "This is a Mdtero backend operations issue, not a user-side API key setup step; "
            "rerun `mdtero rag status --json` after the backend RAG service is configured."
        )
    hint = redact_sensitive_text(server_hint).strip()
    if hint:
        return hint
    return _rag_action_hint(command, reason_code)


def _detail_next_commands(detail: dict[str, Any]) -> list[str]:
    return [str(command).strip() for command in detail.get("next_commands") or [] if str(command).strip()]


def _http_error_detail(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, ProxyValidationError):
        return redact_sensitive_payload(exc.payload) if isinstance(exc.payload, dict) else {}
    if isinstance(exc, DiscoveryError):
        return redact_sensitive_payload(exc.payload) if isinstance(exc.payload, dict) else {}
    if isinstance(exc, MdteroApiError):
        detail = exc.payload.get("detail") if isinstance(exc.payload, dict) else None
        if isinstance(detail, dict):
            nested = detail.get("detail") if isinstance(detail.get("detail"), dict) else detail
            return redact_sensitive_payload(nested if isinstance(nested, dict) else detail)
        return redact_sensitive_payload(exc.payload) if isinstance(exc.payload, dict) else {}
    if not isinstance(exc, httpx.HTTPStatusError):
        return {}
    try:
        payload = exc.response.json()
    except ValueError:
        return {}
    detail = payload.get("detail") if isinstance(payload, dict) else None
    return redact_sensitive_payload(detail) if isinstance(detail, dict) else {}


def _exception_status_code(exc: Exception) -> int | None:
    if isinstance(exc, DiscoveryError):
        value = exc.payload.get("status_code") if isinstance(exc.payload, dict) else None
        return int(value) if isinstance(value, int) else None
    if isinstance(exc, MdteroApiError):
        value = exc.payload.get("status_code") if isinstance(exc.payload, dict) else None
        return int(value) if isinstance(value, int) else None
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code
    return None


def _rag_action_hint(command: str, reason_code: str) -> str:
    if reason_code == "voyage_not_configured":
        return _public_rag_action_hint(command, reason_code)
    if reason_code == "rag_index_not_built":
        return f"Run `{ONE_COMMAND_RAG_BOOTSTRAP}` from the local project so the CLI can build server-side Voyage RAG and query in one step."
    if reason_code == "project_has_no_chunks":
        return f"Import succeeded parse tasks with `{RAG_INGEST_COMMAND}`, then retry `{ONE_COMMAND_RAG_BOOTSTRAP}`."
    if reason_code == "forbidden":
        return "Use credentials for the owner of this server project."
    if reason_code in {"project_not_found", "invalid_project_id"}:
        return f"Run `{ONE_COMMAND_RAG_BOOTSTRAP}` from the local Mdtero project so the CLI can create or bind the correct server project without copying ids by hand."
    if command == "query":
        return f"Check `{RAG_STATUS_COMMAND}`, then retry `{ONE_COMMAND_RAG_BOOTSTRAP}` if the project is not ready."
    return f"Check `{RAG_STATUS_COMMAND}`, fix the reported precondition, then retry."


def _rag_failure_next_commands(command: str, reason_code: str) -> list[str]:
    if reason_code == "project_has_no_chunks":
        return [RAG_INGEST_COMMAND, ONE_COMMAND_RAG_BOOTSTRAP, RAG_STATUS_COMMAND, RAG_BUILD_COMMAND]
    if command == "query" and reason_code == "rag_index_not_built":
        return [ONE_COMMAND_RAG_BOOTSTRAP, RAG_STATUS_COMMAND, RAG_BUILD_COMMAND, GENERIC_RAG_QUERY_COMMAND]
    if reason_code in {"project_not_found", "invalid_project_id"}:
        return [ONE_COMMAND_RAG_BOOTSTRAP, RAG_STATUS_COMMAND, RAG_BUILD_COMMAND, GENERIC_RAG_QUERY_COMMAND]
    if reason_code in {"voyage_not_configured", "forbidden"}:
        return [RAG_STATUS_COMMAND]
    return [RAG_STATUS_COMMAND, ONE_COMMAND_RAG_BOOTSTRAP, RAG_BUILD_COMMAND]


def _print_rag_command_failure(payload: dict[str, Any], *, json_output: bool) -> None:
    ensure_rag_contract(payload)
    payload = redact_sensitive_payload(payload)
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
    _print_rag_agent_tool_plan(payload, console=console)


def _print_rag_query_result(payload: dict[str, Any], *, json_output: bool) -> None:
    ensure_rag_contract(payload)
    payload = redact_sensitive_payload(payload)
    if json_output:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    console = Console()
    console.print(f"RAG query: {payload.get('status', 'succeeded')} ({payload.get('reason_code', 'rag_query_succeeded')})")
    answer = str(payload.get("answer") or "").strip()
    if answer:
        console.print("\n[bold]Answer[/bold]")
        console.print(answer)
    citations = payload.get("citations") if isinstance(payload.get("citations"), list) else []
    if citations:
        console.print("\n[bold]Citations[/bold]")
        for citation in citations[:5]:
            title = str(citation.get("document_title") or citation.get("document_id") or "document").strip()
            order = citation.get("citation_order") or "-"
            line_start = citation.get("line_start")
            line_end = citation.get("line_end")
            line_ref = f":{line_start}-{line_end}" if line_start is not None and line_end is not None else ""
            source_ref = str(citation.get("doi") or citation.get("source_url") or "").strip()
            suffix = f" · {source_ref}" if source_ref else ""
            console.print(f"  [{order}] {title}{line_ref}{suffix}")
    citation_contract = payload.get("citation_contract") if isinstance(payload.get("citation_contract"), dict) else {}
    required_fields = citation_contract.get("required_for_final_answer") if isinstance(citation_contract.get("required_for_final_answer"), list) else []
    agent_instruction = str(citation_contract.get("agent_instruction") or "").strip()
    if required_fields or agent_instruction:
        console.print("\n[bold]Citation contract[/bold]")
        if required_fields:
            console.print(f"  Final answers must preserve: {', '.join(str(field) for field in required_fields)}")
        if agent_instruction:
            console.print(f"  {agent_instruction}")
    next_commands = [str(command) for command in payload.get("next_commands") or [] if str(command).strip()]
    if next_commands:
        console.print("\n[bold]Next[/bold]")
        for command in next_commands:
            console.print(f"  {command}")
    _print_rag_agent_tool_plan(payload, console=console)


def _print_rag_agent_tool_plan(payload: dict[str, Any], *, console: Console) -> None:
    plan = payload.get("agent_tool_plan") if isinstance(payload.get("agent_tool_plan"), list) else []
    if not plan:
        return
    console.print("\n[bold]Agent plan[/bold]")
    for step in plan[:4]:
        if not isinstance(step, dict):
            continue
        step_name = str(step.get("step") or "").strip()
        tool = str(step.get("tool") or "").strip()
        if step_name and tool:
            console.print(f"  {step_name} -> {tool}")
        elif step_name:
            console.print(f"  {step_name}")


def _normalize_rag_query_payload(payload: dict[str, Any], *, project_id: str, question: str) -> dict[str, Any]:
    if not isinstance(payload, dict):
        payload = {"answer": str(payload)}
    matches = payload.get("matches") if isinstance(payload.get("matches"), list) else []
    source_nodes = payload.get("source_nodes") if isinstance(payload.get("source_nodes"), list) else _rag_source_nodes_from_matches(matches)
    citations = payload.get("citations") if isinstance(payload.get("citations"), list) else _rag_citations_from_matches(matches)
    payload.setdefault("project_id", project_id)
    payload.setdefault("server_project_id", str(project_id))
    payload.setdefault("question", question)
    payload.setdefault("status", "succeeded")
    payload.setdefault("reason_code", "rag_query_succeeded" if matches or payload.get("answer") else "no_matches")
    payload.setdefault("answer_kind", "extractive_evidence_pack")
    payload.setdefault("answer", _extract_rag_answer(matches))
    payload.setdefault("citations", citations)
    payload.setdefault("source_nodes", source_nodes)
    payload.setdefault("evidence_pack", _rag_evidence_pack(question=question, source_nodes=source_nodes, citations=citations))
    payload.setdefault("action_hint", "RAG query completed. Review the returned answer, citations, and matches.")
    payload.setdefault(
        "next_commands",
        ["mdtero rag status --json", "mdtero rag query \"<question>\" --build-if-needed --json", "mdtero mcp briefing --json", "mdtero mcp serve"],
    )
    ensure_rag_contract(payload)
    return redact_sensitive_payload(payload)


def _extract_rag_answer(matches: list[Any]) -> str | None:
    snippets: list[str] = []
    for index, match in enumerate(matches[:3], start=1):
        if not isinstance(match, dict):
            continue
        snippet = " ".join(str(match.get("snippet") or "").split())
        if snippet:
            snippets.append(f"[{index}] {snippet}")
    return "\n\n".join(snippets) if snippets else None


def _rag_citations_from_matches(matches: list[Any]) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    for index, match in enumerate(matches, start=1):
        if not isinstance(match, dict):
            continue
        citations.append({
            "citation_order": match.get("citation_order") or index,
            "document_id": match.get("document_id"),
            "document_title": match.get("document_title"),
            "chunk_id": match.get("chunk_id"),
            "line_start": match.get("line_start"),
            "line_end": match.get("line_end"),
            "doi": match.get("doi"),
            "source_url": match.get("source_url"),
        })
    return citations


def _rag_source_nodes_from_matches(matches: list[Any]) -> list[dict[str, Any]]:
    source_nodes: list[dict[str, Any]] = []
    for index, match in enumerate(matches, start=1):
        if not isinstance(match, dict):
            continue
        document_id = match.get("document_id")
        chunk_id = match.get("chunk_id")
        source_nodes.append({
            "node_id": f"doc-{document_id}:chunk-{chunk_id}",
            "score": match.get("score"),
            "text": str(match.get("snippet") or ""),
            "metadata": {
                "citation_order": match.get("citation_order") or index,
                "document_id": document_id,
                "document_title": match.get("document_title"),
                "chunk_id": chunk_id,
                "line_start": match.get("line_start"),
                "line_end": match.get("line_end"),
                "doi": match.get("doi"),
                "source_url": match.get("source_url"),
                "year": match.get("year"),
                "venue": match.get("venue"),
                "external_source": match.get("external_source"),
                "external_key": match.get("external_key"),
            },
        })
    return source_nodes


def _rag_evidence_pack(*, question: str, source_nodes: list[dict[str, Any]], citations: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "question": question,
        "answer_kind": "extractive_evidence_pack",
        "source_nodes": source_nodes,
        "citations": citations,
        "context_markdown": _rag_context_markdown(source_nodes),
        "agent_instruction": (
            "Use source_nodes and citations as grounded evidence. Treat answer as an extractive summary, "
            "not a generated final synthesis, unless a downstream LLM rewrites it with citations preserved."
        ),
    }


def _rag_context_markdown(source_nodes: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for node in source_nodes:
        metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
        order = metadata.get("citation_order") or "?"
        title = str(metadata.get("document_title") or "Untitled document").strip()
        doi = str(metadata.get("doi") or metadata.get("source_url") or "").strip()
        location = ""
        if metadata.get("line_start") is not None and metadata.get("line_end") is not None:
            location = f":{metadata['line_start']}-{metadata['line_end']}"
        suffix = f" ({doi})" if doi else ""
        text = " ".join(str(node.get("text") or "").split())
        blocks.append(f"[{order}] {title}{location}{suffix}\n{text}")
    return "\n\n".join(blocks)


def _server_project_id(args: argparse.Namespace) -> str:
    value = getattr(args, "project_id", None)
    if value:
        return str(value)
    state = load_project(Path.cwd())
    if state.server_project_id:
        return state.server_project_id
    raise SystemExit(f"No server project is linked. Run `{ONE_COMMAND_RAG_BOOTSTRAP}` to create, bind, import, build, and query server-side Voyage RAG.")


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
        "command": command if command.startswith("project_") else f"rag_{command}",
        "reason_code": "server_project_not_linked",
        "error_code": "rag_precondition_failed",
        "server_project_id": None,
        "project": state.name,
        "local_ready_for_ingest_count": sum(1 for paper in state.papers if paper.status == "succeeded" and paper.task_id),
        "local_paper_count": len(state.papers),
        "action_hint": f"Run `{ONE_COMMAND_RAG_BOOTSTRAP}` to create and bind a server project, import succeeded parse tasks, build server-side Voyage RAG, and query without copying a server project id.",
        "next_commands": [ONE_COMMAND_RAG_BOOTSTRAP, RAG_STATUS_COMMAND, RAG_BUILD_COMMAND, GENERIC_RAG_QUERY_COMMAND],
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


def _academic_config_summary(cfg: MdteroConfig, *, path: Path, saved: bool) -> dict[str, Any]:
    return build_academic_onboarding_summary(cfg, path=path, saved=saved)


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
    for group in _next_step_command_groups():
        console.print(f"\n[bold]{group['title']}[/bold]")
        for command in group["commands"]:
            console.print(f"  {command}")


def _next_step_command_groups() -> list[dict[str, Any]]:
    return build_next_step_command_groups()


def _apply_quality_label(task: dict[str, Any]) -> dict[str, Any]:
    label = _task_quality_label(task)
    task["quality_label"] = label
    task["quality_warning"] = _quality_warning(label)
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    if result is not task:
        result.setdefault("quality_label", label)
        warning = _quality_warning(label)
        if warning:
            result.setdefault("quality_warning", warning)
        if result:
            task["result"] = result
    return task


def _task_quality_label(task: dict[str, Any]) -> str:
    outcome_label = _quality_label_from_parse_outcome(task)
    if outcome_label:
        return outcome_label
    for value in _quality_candidates(task):
        cleaned = str(value or "").strip().lower()
        if not cleaned:
            continue
        normalized = _normalize_quality_label(cleaned)
        if normalized in _known_quality_labels():
            return normalized
    status = str(task.get("status") or "").strip().lower()
    if status == "succeeded":
        return "full_text_good"
    if status in {"failed", "cancelled", "timeout"}:
        return "unavailable"
    return "unknown"


def _quality_label_from_parse_outcome(task: dict[str, Any]) -> str | None:
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    parse_outcome = task.get("parse_outcome") if isinstance(task.get("parse_outcome"), dict) else result.get("parse_outcome") if isinstance(result.get("parse_outcome"), dict) else {}
    outcome_code = str(parse_outcome.get("outcome_code") or "").strip().lower()
    reason_codes = {
        str(item).strip().lower()
        for item in (parse_outcome.get("reason_codes") or [])
        if str(item).strip()
    }
    if outcome_code == "fulltext_accepted":
        return None
    if outcome_code == "content_incomplete":
        if "metadata_only" in reason_codes or "doi_resolver_html_metadata_only" in reason_codes:
            return "metadata_only"
        if "abstract_only" in reason_codes:
            return "abstract_only"
        if "section_only_fulltext" in reason_codes:
            return "section_only_fulltext"
        return "low_confidence_parse"
    if outcome_code in {"artifact_rejected", "parser_failure"}:
        return "unavailable"
    return None


def _quality_candidates(task: dict[str, Any]) -> list[Any]:
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    quality = result.get("quality") if isinstance(result.get("quality"), dict) else {}
    parse_outcome = task.get("parse_outcome") if isinstance(task.get("parse_outcome"), dict) else result.get("parse_outcome") if isinstance(result.get("parse_outcome"), dict) else {}
    return [
        task.get("quality_label"),
        result.get("quality_label"),
        quality.get("quality_label"),
        quality.get("label"),
        parse_outcome.get("quality_label") if isinstance(parse_outcome, dict) else None,
        parse_outcome.get("outcome_code") if isinstance(parse_outcome, dict) else None,
        task.get("reason_code"),
        result.get("reason_code"),
        quality.get("reason_code"),
    ]


def _normalize_quality_label(value: str) -> str:
    if value in {"full_text_good", "fulltext_accepted", "full_text", "complete", "succeeded"}:
        return "full_text_good"
    if value in {"metadata_only", "no_fulltext", "no_full_text"}:
        return "metadata_only"
    if value in {"abstract_only", "abstract", "abstract_only_fulltext"}:
        return "abstract_only"
    if value in {"section_only_fulltext", "section_only", "sections_only"}:
        return "section_only_fulltext"
    if value in {"low_confidence_parse", "low_quality", "weak_fulltext", "weak_xml", "elsevier_xml_weak"}:
        return "low_confidence_parse"
    if "abstract" in value and "only" in value:
        return "abstract_only"
    if "metadata" in value and "only" in value:
        return "metadata_only"
    if "section_only" in value or "sections_only" in value:
        return "section_only_fulltext"
    if "low" in value or "weak" in value:
        return "low_confidence_parse"
    return value


def _known_quality_labels() -> set[str]:
    return {"full_text_good", "metadata_only", "abstract_only", "section_only_fulltext", "low_confidence_parse", "unavailable", "unknown"}


def _quality_warning(label: str) -> str | None:
    if label == "full_text_good":
        return None
    if label in {"metadata_only", "abstract_only", "section_only_fulltext", "low_confidence_parse", "unavailable"}:
        return f"Artifact quality is {label}; verify the source before citing it as full text."
    return None


def _is_low_quality_label(label: str) -> bool:
    return bool(_quality_warning(_normalize_quality_label(label)))


def _download_task_artifact(client: MdteroClient, task_id: str, artifact: str, output_dir: Path, *, task: dict[str, Any] | None, filename_template: str) -> dict[str, Any]:
    filename = _download_filename(task, artifact=artifact, filename_template=filename_template) if task else None
    try:
        result = client.download(task_id, artifact, output_dir, filename=filename)
    except TypeError:
        result = client.download(task_id, artifact, output_dir)
    path = Path(os.fspath(result))
    return {
        "artifact": artifact,
        "path": str(path),
        "filename": path.name,
        "original_filename": getattr(result, "filename", path.name),
        "content_type": getattr(result, "content_type", None),
        "content_length": getattr(result, "content_length", None),
        "quality_label": getattr(result, "quality_label", None) or _task_quality_label(task or {}),
        "quality_warning_code": getattr(result, "quality_warning_code", None),
        "quality_warning": getattr(result, "quality_warning", None),
        "parse_outcome": getattr(result, "parse_outcome", None),
        "parse_billable": getattr(result, "parse_billable", None),
        "parse_reason_codes": list(getattr(result, "parse_reason_codes", ()) or ()),
    }


def _download_filename(task: dict[str, Any], *, artifact: str, filename_template: str) -> str | None:
    template = str(filename_template or "").strip()
    if not template:
        return None
    extension = ".md" if artifact.endswith("_md") or artifact == "paper_md" else ".zip" if "bundle" in artifact else ""
    label = _task_quality_label(task)
    values = {
        "author": _first_author(task) or "unknown",
        "year": _task_year(task) or "n.d.",
        "shorttitle": _short_title(_task_title(task)) or artifact,
        "title": _slug(_task_title(task)) or artifact,
        "doi": _slug(_task_doi(task)) or "no-doi",
        "task_id": _slug(str(task.get("task_id") or task.get("id") or "")) or "task",
        "artifact": _slug(artifact) or artifact,
    }
    try:
        stem = template.format(**values)
    except (KeyError, ValueError):
        stem = "{author}_{year}_{shorttitle}".format(**values)
    stem = _slug(stem) or values["task_id"]
    if _is_low_information_download_stem(stem, artifact=artifact):
        return None
    if artifact.endswith("_md") and _is_low_quality_label(label):
        stem = f"{stem}.low_quality"
    return f"{stem}{extension}"


def _is_low_information_download_stem(stem: str, *, artifact: str) -> bool:
    normalized = _slug(stem)
    artifact_slug = _slug(artifact) or artifact
    low_information = {
        artifact_slug,
        f"unknown_n_d_{artifact_slug}",
        f"unknown_nd_{artifact_slug}",
        f"unknown_{artifact_slug}",
        f"n_d_{artifact_slug}",
    }
    return normalized in low_information or normalized.startswith(f"unknown_n_d_{artifact_slug}.")


def _append_download_manifest(output_dir: Path, row: dict[str, Any]) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "manifest.csv"
    _append_csv_rows(path, [row], _manifest_fieldnames())
    return {"manifest_csv": str(path)}


def _write_batch_manifests(output_dir: Path, items: list[dict[str, Any]]) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.csv"
    failed_path = output_dir / "failed.csv"
    rows = [_manifest_row_from_batch_item(item) for item in items if item.get("download")]
    failures = [_failed_manifest_row(item) for item in items if item.get("status") in {"failed", "cancelled", "timeout"}]
    _write_csv_rows(manifest_path, rows, _manifest_fieldnames())
    _write_csv_rows(failed_path, failures, ["input", "task_id", "status", "quality_label", "reason_code", "parse_outcome", "parse_reason_codes", "action_hint"])
    return {"manifest_csv": str(manifest_path), "failed_csv": str(failed_path)}


def _manifest_row_from_batch_item(item: dict[str, Any]) -> dict[str, Any]:
    download = item.get("download") if isinstance(item.get("download"), dict) else {}
    return {
        "input": item.get("input"),
        "doi": item.get("doi") or _doi_from_input(str(item.get("input") or "")),
        "title": item.get("title"),
        "task_id": item.get("task_id"),
        "status": item.get("status"),
        "quality_label": item.get("quality_label"),
        "reason_code": item.get("reason_code"),
        "action_hint": item.get("action_hint"),
        "selected_provider": item.get("selected_provider"),
        "parser_strategy": item.get("parser_strategy"),
        "parse_outcome": download.get("parse_outcome") or item.get("parse_outcome"),
        "parse_billable": download.get("parse_billable") if download.get("parse_billable") is not None else item.get("parse_billable"),
        "parse_reason_codes": _join_values(download.get("parse_reason_codes") or item.get("parse_reason_codes")),
        "quality_warning_code": download.get("quality_warning_code"),
        "quality_warning": download.get("quality_warning"),
        "route_best_connector": item.get("route_best_connector"),
        "route_best_quality_label": item.get("route_best_quality_label"),
        "route_needs_followup": item.get("route_needs_followup"),
        "artifact": str(download.get("artifact") or item.get("preferred_artifact") or ""),
        "path": download.get("path") or item.get("path"),
        "original_filename": download.get("original_filename"),
    }


def _manifest_row_from_task(task: dict[str, Any], *, artifact: str, path: str, input_value: str | None, original_filename: str | None, download: dict[str, Any] | None = None) -> dict[str, Any]:
    download = download or {}
    parse_outcome = _task_parse_outcome(task)
    route_summary = _task_quality_route_summary(task)
    return {
        "input": input_value or task.get("paper_input") or task.get("input_summary") or _task_doi(task),
        "doi": _task_doi(task),
        "title": _task_title(task),
        "task_id": task.get("task_id") or task.get("id"),
        "status": task.get("status"),
        "quality_label": _task_quality_label(task),
        "reason_code": task.get("reason_code") or task.get("error_code"),
        "action_hint": task.get("action_hint"),
        "selected_provider": task.get("selected_provider") or _task_result(task).get("selected_provider"),
        "parser_strategy": task.get("parser_strategy") or _task_result(task).get("parser_strategy"),
        "parse_outcome": download.get("parse_outcome") or (parse_outcome.get("outcome_code") if parse_outcome else None),
        "parse_billable": download.get("parse_billable") if download.get("parse_billable") is not None else (parse_outcome.get("billable") if parse_outcome else None),
        "parse_reason_codes": _join_values(download.get("parse_reason_codes") or (parse_outcome.get("reason_codes") if parse_outcome else [])),
        "quality_warning_code": download.get("quality_warning_code"),
        "quality_warning": download.get("quality_warning"),
        "route_best_connector": route_summary.get("best_connector") if route_summary else None,
        "route_best_quality_label": route_summary.get("best_quality_label") if route_summary else None,
        "route_needs_followup": route_summary.get("needs_followup") if route_summary else None,
        "artifact": artifact,
        "path": path,
        "original_filename": original_filename,
    }


def _download_task_summary(task: dict[str, Any]) -> dict[str, Any]:
    quality_label = _task_quality_label(task)
    return {
        "task_id": task.get("task_id") or task.get("id"),
        "status": task.get("status"),
        "title": _task_title(task),
        "doi": _task_doi(task),
        "quality_label": quality_label,
        "quality_warning": _quality_warning(quality_label),
        "reason_code": task.get("reason_code") or task.get("error_code"),
        "action_hint": task.get("action_hint"),
    }


def _task_result(task: dict[str, Any]) -> dict[str, Any]:
    return task.get("result") if isinstance(task.get("result"), dict) else {}


def _task_parse_outcome(task: dict[str, Any]) -> dict[str, Any]:
    result = _task_result(task)
    if isinstance(task.get("parse_outcome"), dict):
        return task["parse_outcome"]
    if isinstance(result.get("parse_outcome"), dict):
        return result["parse_outcome"]
    return {}


def _task_quality_route_summary(task: dict[str, Any]) -> dict[str, Any]:
    result = _task_result(task)
    if isinstance(task.get("quality_route_summary"), dict):
        return task["quality_route_summary"]
    if isinstance(result.get("quality_route_summary"), dict):
        return result["quality_route_summary"]
    return {}


def _join_values(values: Any) -> str:
    if isinstance(values, str):
        return values
    return ",".join(str(value).strip() for value in (values or []) if str(value).strip())


def _manifest_fieldnames() -> list[str]:
    return [
        "input",
        "doi",
        "title",
        "task_id",
        "status",
        "quality_label",
        "reason_code",
        "action_hint",
        "selected_provider",
        "parser_strategy",
        "parse_outcome",
        "parse_billable",
        "parse_reason_codes",
        "quality_warning_code",
        "quality_warning",
        "route_best_connector",
        "route_best_quality_label",
        "route_needs_followup",
        "artifact",
        "path",
        "original_filename",
    ]


def _write_csv_rows(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _append_csv_rows(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerows(rows)


def _task_title(task: dict[str, Any]) -> str:
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    for value in (task.get("title"), result.get("title"), metadata.get("title"), task.get("paper_title")):
        cleaned = str(value or "").strip()
        if cleaned:
            return cleaned
    return ""


def _task_doi(task: dict[str, Any]) -> str:
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    for value in (task.get("doi"), result.get("doi"), metadata.get("doi"), task.get("paper_input"), task.get("input_summary")):
        doi = _doi_from_input(str(value or ""))
        if doi:
            return doi
    return ""


def _doi_from_input(value: str) -> str:
    match = re.search(r"(10\.\d{4,9}/\S+)", value, flags=re.I)
    if not match:
        return ""
    return match.group(1).rstrip(".,;)")


def _task_year(task: dict[str, Any]) -> str:
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    for value in (task.get("year"), result.get("year"), metadata.get("year"), metadata.get("published_year"), metadata.get("publication_year")):
        match = re.search(r"(19|20)\d{2}", str(value or ""))
        if match:
            return match.group(0)
    return ""


def _first_author(task: dict[str, Any]) -> str:
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    metadata = result.get("metadata") if isinstance(result.get("metadata"), dict) else {}
    authors = task.get("authors") or result.get("authors") or metadata.get("authors")
    first: Any = None
    if isinstance(authors, list) and authors:
        first = authors[0]
    elif isinstance(authors, str):
        first = authors.split(",", 1)[0].split(";", 1)[0]
    if isinstance(first, dict):
        first = first.get("family") or first.get("last") or first.get("name")
    cleaned = str(first or "").strip()
    if not cleaned:
        return ""
    return _slug(cleaned.split()[-1])


def _short_title(title: str, *, words: int = 6) -> str:
    tokens = re.findall(r"[A-Za-z0-9]+", title.lower())
    return "_".join(tokens[:words])


def _slug(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", str(value or "").strip().lower())
    return cleaned.strip("_")


def _print_parse_batch_summary(payload: dict[str, Any]) -> None:
    console = Console()
    console.print(
        f"Parse batch: {payload.get('succeeded_count')}/{payload.get('total_count')} succeeded; "
        f"{payload.get('downloaded_count')} downloaded; {payload.get('failed_count')} failed."
    )
    table = Table("Input", "Task", "Status", "Quality", "Path")
    for item in payload.get("items") or []:
        table.add_row(
            str(item.get("input") or ""),
            str(item.get("task_id") or ""),
            str(item.get("status") or ""),
            str(item.get("quality_label") or ""),
            str(item.get("path") or ""),
        )
    console.print(table)


def _print_result(payload: dict[str, Any], *, json_output: bool) -> None:
    payload = redact_sensitive_payload(payload)
    if json_output:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return
    console = Console()
    if "task_id" in payload:
        console.print(f"Task: {payload.get('task_id')} ({payload.get('status')})")
        quality_label = str(payload.get("quality_label") or "").strip()
        if quality_label:
            console.print(f"Quality: {quality_label}")
        warning = payload.get("quality_warning") or _quality_warning(quality_label)
        if warning:
            console.print(f"Warning: {warning}")
        reason = payload.get("reason_code") or payload.get("action_hint")
        if reason:
            console.print(str(reason))
        _print_translation_attempts(payload, console)
    else:
        console.print(payload)


def _print_translation_attempts(payload: dict[str, Any], console: Console) -> None:
    attempts = payload.get("translation_attempts")
    if attempts is None and isinstance(payload.get("result"), dict):
        attempts = payload["result"].get("translation_attempts")
    if not isinstance(attempts, list) or not attempts:
        return
    table = Table("Provider", "Reason", "Status", "Message")
    for attempt in attempts:
        if not isinstance(attempt, dict):
            continue
        status = ""
        if attempt.get("provider_status_code") is not None:
            status = str(attempt.get("provider_status_code"))
        elif attempt.get("status"):
            status = str(attempt.get("status"))
        table.add_row(
            redact_sensitive_text(attempt.get("provider") or "provider"),
            redact_sensitive_text(attempt.get("reason_code") or attempt.get("provider_error_code") or "failed"),
            status,
            redact_sensitive_text(attempt.get("message") or ""),
        )
    console.print(table)


if __name__ == "__main__":
    raise SystemExit(main())
