from __future__ import annotations

from pathlib import Path
from typing import Any

from .agent import detect_target_status
from .client import MdteroClient
from .config import MdteroConfig, load_config
from .projects import add_paper, bind_server_project, load_project, paper_from_submission, paper_to_document, project_documents, project_path, update_task
from .rag_contract import ensure_rag_contract
from .redact import redact_sensitive_payload, redact_sensitive_text


def build_project_status(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path.cwd()
    state = _load_project_or_none(root)
    if state is None:
        commands = build_agent_commands(root)
        return {
            "status": "not_initialized",
            "reason_code": "project_not_initialized",
            "name": root.resolve().name,
            "root": str(root.resolve()),
            "server_project_id": None,
            "paper_count": 0,
            "ready_for_ingest_count": 0,
            "pending_count": 0,
            "running_count": 0,
            "failed_count": 0,
            "papers": [],
            "action_hint": "Run `mdtero project init --name <name>` before project, RAG, or MCP workflows.",
            "next_commands": [
                commands["commands"]["project_init_named"],
                commands["commands"]["discover"],
                commands["commands"]["project_add"],
                commands["commands"]["parse_doi_or_url"],
            ],
            "next_actions": commands,
        }
    succeeded = [paper for paper in state.papers if paper.status == "succeeded" and paper.task_id]
    pending = [paper for paper in state.papers if paper.status in {"pending", "created"} and not paper.task_id]
    running = [paper for paper in state.papers if paper.task_id and paper.status not in {"succeeded", "failed"}]
    failed = [paper for paper in state.papers if paper.status == "failed"]
    commands = build_agent_commands(root)
    if failed:
        status = "needs_attention"
        reason_code = "project_has_failed_items"
        action_hint = "Inspect failed items and rerun them with `mdtero project parse --include-failed --wait --timeout 300 --json` before building RAG."
        next_commands = ["mdtero project parse --include-failed --wait --timeout 300 --json", commands["commands"]["refresh"]]
    elif running:
        status = "running"
        reason_code = "project_has_running_tasks"
        action_hint = "Wait for running tasks to finish before ingesting or querying RAG."
        next_commands = [commands["commands"]["refresh"], commands["commands"]["rag_status"]]
    elif pending:
        status = "pending"
        reason_code = "project_has_pending_items"
        action_hint = "Submit pending papers, refresh task status, then build or query server-side Voyage RAG."
        next_commands = [commands["commands"]["parse_pending"], commands["commands"]["refresh"], commands["commands"]["rag_build"]]
    elif succeeded:
        status = "ready"
        reason_code = "project_ready_for_rag"
        action_hint = "Project has succeeded parse tasks. Ingest/build/query server-side Voyage RAG or expose context through MCP."
        next_commands = [commands["commands"].get("ingest_for_rag", "mdtero project ingest --json"), commands["commands"]["rag_build"], commands["commands"]["rag_query"], commands["commands"]["mcp_briefing"]]
    else:
        status = "empty"
        reason_code = "project_empty"
        action_hint = "Add a DOI, URL, BibTeX import, Zotero import, or local file before parsing."
        next_commands = [commands["commands"]["discover"], commands["commands"]["project_add"], commands["commands"]["parse_doi_or_url"]]

    return redact_sensitive_payload({
        "status": status,
        "reason_code": reason_code,
        "name": state.name,
        "server_project_id": state.server_project_id,
        "paper_count": len(state.papers),
        "ready_for_ingest_count": len(succeeded),
        "pending_count": len(pending),
        "running_count": len(running),
        "failed_count": len(failed),
        "papers": [document.to_dict() for document in project_documents(root)],
        "action_hint": action_hint,
        "next_commands": _dedupe_commands(next_commands),
        "next_actions": commands,
    })


def build_paper_context(input_or_task_id: str, project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path.cwd()
    state = _load_project_or_none(root)
    if state is None:
        return {
            "error": "project_not_initialized",
            "input_or_task_id": input_or_task_id,
            "action_hint": "Run `mdtero project init --name <name>` before asking for paper context.",
            "next_commands": ["mdtero project init --name <name>", "mdtero project add <doi-or-url> --json"],
        }
    for paper in state.papers:
        if paper.input == input_or_task_id or paper.task_id == input_or_task_id:
            payload = paper_to_document(paper).to_dict()
            payload["recommended_commands"] = _paper_commands(paper)
            return redact_sensitive_payload(payload)
    return {"error": "paper_not_found", "input_or_task_id": input_or_task_id}


def build_agent_commands(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path.cwd()
    state = _load_project_or_none(root)
    project_name = state.name if state is not None else root.resolve().name
    server_project_id = state.server_project_id if state is not None else None
    commands: dict[str, Any] = {
        "setup": "mdtero setup",
        "login_api_key": "mdtero setup --api-key <key>",
        "doctor": "mdtero doctor --json",
        "discover": "mdtero discover \"<topic>\" --interactive",
        "parse_doi_or_url": "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json",
        "parse_file": "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 300 --json",
        "parse_batch": "mdtero parse --batch <directory> --wait --timeout 300 --json",
        "extension_handoff_url": "mdtero parse <doi-or-url> --trace --wait --timeout 300 --json",
        "extension_handoff_file": "mdtero parse --file <paper.pdf|paper.epub|paper.html|paper.xml> --trace --wait --timeout 300 --json",
        "project_init": "mdtero project init --name <name>",
        "project_add": "mdtero project add <doi-or-url> --json",
        "import_bib": "mdtero project import-bib <refs.bib> --json",
        "parse_pending": "mdtero project parse --wait --timeout 300 --json",
        "refresh": "mdtero project refresh --wait --timeout 300 --json",
        "download_artifact": "mdtero download <task-id> <artifact> --output-dir ./mdtero-output --json",
        "download_markdown": "mdtero project download --output-dir ./mdtero-output --json",
        "translate": "mdtero translate <task-id-or-markdown-file> --to zh-CN --wait --timeout 600 --json",
        "zotero_import": "mdtero zotero import --json",
        "zotero_sync": "mdtero zotero sync --json",
        "rag_status": "mdtero rag status --json",
        "rag_build": "mdtero rag build --json",
        "rag_query": "mdtero rag query \"<question>\" --build-if-needed --json",
        "mcp_briefing": "mdtero mcp briefing --json",
        "serve_mcp": "mdtero mcp serve",
        "agent_detect": "mdtero agent detect --json",
        "agent_install": "mdtero agent install --interactive",
    }
    recovery_commands: dict[str, Any] = {
        "create_server_project": "mdtero project create-server --json",
        "bind_server_project": "mdtero project link --server-project-id <id>",
    }
    if state is None:
        commands["project_init_named"] = "mdtero project init --name <name>"
        commands["project_init_here"] = f"mdtero project init --name {_shell_safe_project_name(project_name)}"
        workflow = [commands["doctor"], commands["project_init_named"], commands["discover"], commands["project_add"], commands["parse_doi_or_url"]]
    elif state.server_project_id:
        commands["ingest_for_rag"] = "mdtero project ingest --json"
        recovery_commands["reingest_for_rag"] = "mdtero project ingest --json"
        workflow = [
            commands["doctor"],
            commands["parse_pending"],
            commands["refresh"],
            commands["ingest_for_rag"],
            commands["rag_status"],
            commands["rag_query"],
        ]
    else:
        commands["bootstrap_rag"] = "mdtero rag build --json"
        workflow = [
            commands["doctor"],
            commands["parse_pending"],
            commands["refresh"],
            commands["rag_build"],
            commands["rag_status"],
            commands["rag_query"],
        ]
    return {
        "project": project_name,
        "server_project_id": server_project_id,
        "commands": commands,
        "recovery_commands": recovery_commands,
        "workflow": workflow,
    }


def build_rag_context(project_root: Path | None = None) -> dict[str, Any]:
    root = project_root or Path.cwd()
    state = _load_project_or_none(root)
    if state is None:
        commands = build_agent_commands(root)["commands"]
        return {
            "project": root.resolve().name,
            "server_project_id": None,
            "ready": False,
            "ready_for_ingest_count": 0,
            "reason_code": "project_not_initialized",
            "action_hint": "Initialize a local Mdtero project before RAG.",
            "commands": commands,
            "next_commands": [commands["project_init_named"], commands["project_add"], commands["parse_doi_or_url"]],
        }
    succeeded = [paper for paper in state.papers if paper.status == "succeeded" and paper.task_id]
    pending = [paper for paper in state.papers if paper.status in {"pending", "created"} and not paper.task_id]
    running = [paper for paper in state.papers if paper.task_id and paper.status not in {"succeeded", "failed"}]
    failed = [paper for paper in state.papers if paper.status == "failed"]
    commands = build_agent_commands(root)["commands"]

    if state.server_project_id and succeeded:
        status = "ready"
        reason_code = "ready"
        action_hint = "Local project has succeeded parse tasks and a linked server project. Ingest or refresh server-side Voyage RAG, then query through CLI or MCP."
        next_commands = [
            commands.get("ingest_for_rag", "mdtero project ingest --json"),
            commands["rag_status"],
            commands["rag_build"],
            commands["rag_query"],
            commands["mcp_briefing"],
        ]
    elif not state.server_project_id and succeeded:
        status = "not_ready"
        reason_code = "server_project_not_linked"
        action_hint = "Run `mdtero rag build --json` to create and bind a server project, import succeeded parse tasks, and start backend Voyage RAG."
        next_commands = [commands["rag_build"], commands["rag_status"], commands["rag_query"]]
    elif running:
        status = "not_ready"
        reason_code = "project_has_running_tasks"
        action_hint = "Wait for running parse tasks to finish before building or querying server-side Voyage RAG."
        next_commands = [commands["refresh"], commands["rag_status"]]
    elif pending:
        status = "not_ready"
        reason_code = "project_has_pending_items"
        action_hint = "Submit pending papers and refresh task status before building server-side Voyage RAG."
        next_commands = [commands["parse_pending"], commands["refresh"], commands["rag_build"]]
    else:
        status = "not_ready"
        reason_code = "no_succeeded_tasks"
        action_hint = "Parse at least one paper successfully before building or querying server-side Voyage RAG. Use the arXiv smoke DOI, direct file upload, or browser-extension handoff, then refresh the local project."
        next_commands = _rag_recovery_commands(commands)

    return redact_sensitive_payload({
        "project": state.name,
        "server_project_id": state.server_project_id,
        "status": status,
        "ready": bool(state.server_project_id and succeeded),
        "ready_for_ingest_count": len(succeeded),
        "local_paper_count": len(state.papers),
        "pending_count": len(pending),
        "running_count": len(running),
        "failed_count": len(failed),
        "reason_code": reason_code,
        "action_hint": action_hint,
        "commands": commands,
        "next_commands": _dedupe_commands(next_commands),
    })


def build_server_rag_status(project_root: Path | None = None, *, fetcher: Any | None = None) -> dict[str, Any]:
    root = project_root or Path.cwd()
    state = _load_project_or_none(root)
    commands = build_agent_commands(root)["commands"]
    if state is None:
        return {
            "status": "not_ready",
            "reason_code": "project_not_initialized",
            "project": root.resolve().name,
            "server_project_id": None,
            "local_ready_for_ingest_count": 0,
            "local_paper_count": 0,
            "action_hint": "Run `mdtero project init --name <name>` before server-side Voyage RAG.",
            "next_commands": [commands["project_init_named"], commands["project_add"], commands["parse_doi_or_url"]],
        }
    local_ready = sum(1 for paper in state.papers if paper.status == "succeeded" and paper.task_id)
    if not state.server_project_id:
        return {
            "status": "not_ready",
            "reason_code": "server_project_not_linked",
            "project": state.name,
            "server_project_id": None,
            "local_ready_for_ingest_count": local_ready,
            "local_paper_count": len(state.papers),
            "action_hint": "Run `mdtero rag build --json` to create and bind a server project, import succeeded parse tasks, and start server-side Voyage RAG.",
            "next_commands": [commands["rag_build"], commands["parse_pending"], commands["refresh"]],
        }

    try:
        status = (fetcher or MdteroClient().rag_status)(state.server_project_id)
    except Exception as exc:
        return redact_sensitive_payload({
            "status": "unavailable",
            "reason_code": "server_rag_status_unavailable",
            "project": state.name,
            "server_project_id": state.server_project_id,
            "local_ready_for_ingest_count": local_ready,
            "local_paper_count": len(state.papers),
            "error_type": exc.__class__.__name__,
            "next_commands": [commands["ingest_for_rag"], "mdtero rag status --json", commands["rag_build"]],
        })

    summary = status.get("summary") if isinstance(status.get("summary"), dict) else {}
    server_status = str(status.get("status") or "unknown")
    reason_code = str(status.get("reason_code") or "unknown")
    status.setdefault("project", state.name)
    status.setdefault("server_project_id", state.server_project_id)
    status.setdefault("local_ready_for_ingest_count", local_ready)
    status.setdefault("local_paper_count", len(state.papers))
    ensure_rag_contract(status)

    readiness = status.get("readiness") if isinstance(status.get("readiness"), dict) else {}
    next_step = str(readiness.get("next_step") or "inspect_status")
    if readiness.get("ready_for_query") or server_status == "ready" or reason_code == "indexed":
        next_commands = ["mdtero rag status --json", commands["rag_query"], commands["mcp_briefing"], commands["serve_mcp"]]
    elif readiness.get("provider_blocked"):
        next_commands = ["mdtero rag status --json"]
    elif next_step == "build":
        next_commands = [commands["rag_build"], "mdtero rag status --json", commands["rag_query"]]
    elif next_step == "ingest" and local_ready > 0:
        next_commands = [commands["ingest_for_rag"], commands["rag_build"], "mdtero rag status --json"]
    elif local_ready > 0:
        next_commands = ["mdtero rag status --json", commands["ingest_for_rag"], commands["rag_build"], commands["rag_query"]]
    else:
        next_commands = ["mdtero rag status --json", commands["parse_pending"], commands["refresh"], commands["ingest_for_rag"]]

    status["next_commands"] = _dedupe_commands(next_commands)
    status["action_hint"] = _server_rag_action_hint(status, commands)
    status["agent_summary"] = _server_rag_agent_summary(status)
    ensure_rag_contract(status)
    return redact_sensitive_payload(status)


def query_server_rag(
    question: str,
    project_root: Path | None = None,
    *,
    query_fn: Any | None = None,
    client: Any | None = None,
    build_if_needed: bool = False,
) -> dict[str, Any]:
    root = project_root or Path.cwd()
    state = _load_project_or_none(root)
    cleaned_question = str(question or "").strip()
    commands = build_agent_commands(root)["commands"]
    if state is None:
        return {
            "status": "not_ready",
            "reason_code": "project_not_initialized",
            "project": root.resolve().name,
            "server_project_id": None,
            "question": cleaned_question,
            "answer": None,
            "action_hint": "Initialize a local Mdtero project before querying server-side Voyage RAG.",
            "next_commands": [commands["project_init_named"], commands["project_add"], commands["parse_doi_or_url"]],
        }
    if not cleaned_question:
        return {
            "status": "failed",
            "reason_code": "rag_question_required",
            "project": state.name,
            "server_project_id": state.server_project_id,
            "answer": None,
            "action_hint": "Provide a concrete question for the project RAG index.",
            "next_commands": [commands["rag_query"]],
        }
    bootstrap: dict[str, Any] | None = None
    if build_if_needed:
        bootstrap_client = client or MdteroClient()
        project_id, bootstrap = _bootstrap_server_rag_for_query(bootstrap_client, root, state, commands)
        if not project_id:
            bootstrap.setdefault("question", cleaned_question)
            return bootstrap
        state = load_project(root)
    if not state.server_project_id:
        return {
            "status": "not_ready",
            "reason_code": "server_project_not_linked",
            "project": state.name,
            "server_project_id": None,
            "question": cleaned_question,
            "answer": None,
            "action_hint": "Run `mdtero rag query \"<question>\" --build-if-needed --json` to create, bind, import, build, and query server-side Voyage RAG from one agent-safe command.",
            "next_commands": [commands["rag_build"], "mdtero rag status --json", commands["rag_query"]],
        }
    try:
        result = (query_fn or (client or MdteroClient()).rag_query)(state.server_project_id, cleaned_question)
    except Exception as exc:
        detail = _rag_query_exception_detail(exc)
        payload = {
            "status": "failed",
            "reason_code": str(detail.get("reason_code") or "server_rag_query_failed"),
            "project": state.name,
            "server_project_id": state.server_project_id,
            "question": cleaned_question,
            "answer": None,
            "error_type": exc.__class__.__name__,
            "action_hint": _public_rag_action_hint(
                str(detail.get("reason_code") or "server_rag_query_failed"),
                detail.get("action_hint"),
            ),
            "next_commands": _rag_query_failure_next_commands(detail, commands),
        }
        if bootstrap is not None:
            payload["bootstrap"] = bootstrap
        return redact_sensitive_payload(payload)
    if not isinstance(result, dict):
        result = {"answer": result}
    result = _normalize_rag_query_result_for_agents(
        result,
        project_name=state.name,
        server_project_id=str(state.server_project_id or ""),
        question=cleaned_question,
        commands=commands,
    )
    if bootstrap is not None:
        result.setdefault("bootstrap", bootstrap)
    return redact_sensitive_payload(result)


def submit_parse_for_agent(
    input_value: str,
    project_root: Path | None = None,
    *,
    client: Any | None = None,
    wait: bool = True,
    timeout: float = 300.0,
    interval: float = 2.0,
) -> dict[str, Any]:
    root = project_root or Path.cwd()
    cleaned_input = str(input_value or "").strip()
    commands = build_agent_commands(root)["commands"]
    if not cleaned_input:
        return {
            "status": "failed",
            "reason_code": "parse_input_required",
            "input": cleaned_input,
            "action_hint": "Provide a DOI, URL, or local file path before asking Mdtero MCP to parse.",
            "next_commands": [commands["parse_doi_or_url"], commands["parse_file"]],
        }
    active_client = client or MdteroClient()
    try:
        result = active_client.parse_with_route(cleaned_input)[1]
    except Exception as exc:
        return _agent_tool_exception_payload(
            exc,
            reason_code="parse_submission_failed",
            action_hint="Parse submission failed. Retry from the CLI with trace output, or use the browser extension/file upload handoff for publisher pages.",
            next_commands=[commands["parse_doi_or_url"], commands["parse_file"], commands["extension_handoff_url"]],
            extra={"input": cleaned_input},
        )
    _enrich_agent_parse_submission(result)
    if result.get("task_id"):
        try:
            add_paper(root, paper_from_submission(cleaned_input, result, source="mcp"))
        except Exception:
            pass
    if wait and result.get("task_id"):
        final_task = _wait_for_agent_task(active_client, str(result["task_id"]), timeout=timeout, interval=interval)
        _enrich_agent_task_status(final_task)
        if final_task.get("status") != "timeout":
            try:
                update_task(root, final_task)
            except Exception:
                pass
        result["final_task"] = final_task
        for key in ("status", "reason_code", "action_hint", "preferred_artifact", "next_commands"):
            if final_task.get(key) not in (None, "", [], {}):
                result[key] = final_task[key]
    return redact_sensitive_payload(result)


def task_status_for_agent(
    task_id: str,
    project_root: Path | None = None,
    *,
    client: Any | None = None,
    wait: bool = False,
    timeout: float = 300.0,
    interval: float = 2.0,
) -> dict[str, Any]:
    root = project_root or Path.cwd()
    cleaned_task_id = str(task_id or "").strip()
    if not cleaned_task_id:
        return {
            "status": "failed",
            "reason_code": "task_id_required",
            "action_hint": "Provide a Mdtero task id before requesting task status.",
            "next_commands": ["mdtero project status --json", "mdtero project refresh --wait --timeout 300 --json"],
        }
    active_client = client or MdteroClient()
    try:
        task = _wait_for_agent_task(active_client, cleaned_task_id, timeout=timeout, interval=interval) if wait else active_client.task(cleaned_task_id)
    except Exception as exc:
        return _agent_tool_exception_payload(
            exc,
            reason_code="task_status_failed",
            action_hint="Task status could not be fetched. Check authentication/connectivity with `mdtero doctor --json`, then retry.",
            next_commands=[f"mdtero status {cleaned_task_id} --json", "mdtero doctor --json"],
            extra={"task_id": cleaned_task_id},
        )
    _enrich_agent_task_status(task)
    if task.get("status") != "timeout":
        try:
            update_task(root, task)
        except Exception:
            pass
    return redact_sensitive_payload(task)


def request_translation_for_agent(
    task_id_or_markdown_path: str,
    project_root: Path | None = None,
    *,
    target_language: str = "zh-CN",
    client: Any | None = None,
    wait: bool = True,
    timeout: float = 600.0,
    interval: float = 2.0,
) -> dict[str, Any]:
    root = project_root or Path.cwd()
    source = str(task_id_or_markdown_path or "").strip()
    commands = build_agent_commands(root)["commands"]
    if not source:
        return {
            "status": "failed",
            "reason_code": "translation_source_required",
            "action_hint": "Provide a parse task id or local Markdown path before requesting translation.",
            "next_commands": [commands["translate"]],
        }
    active_client = client or MdteroClient()
    try:
        local_path = Path(source).expanduser()
        if local_path.exists() and local_path.is_file():
            result = active_client.translate_text(local_path.read_text(encoding="utf-8"), filename=local_path.name, target_language=target_language)
        else:
            result = active_client.translate_task(source, target_language=target_language)
    except ValueError as exc:
        if str(exc) == "translation_source_artifact_missing":
            return {
                "status": "failed",
                "reason_code": "translation_source_artifact_missing",
                "task_id": source,
                "action_hint": "The parse task does not expose a server-side paper_md path for translation. Download paper_md and retry with the local Markdown path.",
                "next_commands": [f"mdtero status {source} --json", f"mdtero download {source} paper_md --output-dir ./mdtero-output --json", commands["translate"]],
            }
        raise
    except Exception as exc:
        return _agent_tool_exception_payload(
            exc,
            reason_code="translation_submission_failed",
            action_hint="Translation submission failed. Check authentication and backend translation provider health, then retry with waitable translation.",
            next_commands=[commands["translate"], "mdtero doctor --json"],
            extra={"source": source, "target_language": target_language},
        )
    _enrich_agent_translate_submission(result)
    if wait and result.get("task_id"):
        final_task = _wait_for_agent_task(active_client, str(result["task_id"]), timeout=timeout, interval=interval)
        _enrich_agent_task_status(final_task)
        result["final_task"] = final_task
        if final_task.get("status") not in {None, "timeout"}:
            try:
                update_task(root, final_task)
            except Exception:
                pass
    return redact_sensitive_payload(result)


def download_artifact_for_agent(
    task_id: str,
    project_root: Path | None = None,
    *,
    artifact: str | None = None,
    output_dir: str | Path = "./mdtero-output",
    client: Any | None = None,
) -> dict[str, Any]:
    root = project_root or Path.cwd()
    cleaned_task_id = str(task_id or "").strip()
    commands = build_agent_commands(root)["commands"]
    if not cleaned_task_id:
        return {
            "status": "failed",
            "reason_code": "task_id_required",
            "action_hint": "Provide a Mdtero task id before requesting an artifact download.",
            "next_commands": ["mdtero project status --json", "mdtero project refresh --wait --timeout 300 --json"],
        }

    active_client = client or MdteroClient()
    selected_artifact = str(artifact or "").strip()
    task: dict[str, Any] | None = None
    if not selected_artifact:
        try:
            task = active_client.task(cleaned_task_id)
            _enrich_agent_task_status(task)
            selected_artifact = _preferred_agent_artifact(
                task,
                default="translated_md" if _looks_like_translation_task(task) else "paper_md",
            )
        except Exception as exc:
            return _agent_tool_exception_payload(
                exc,
                reason_code="artifact_selection_failed",
                action_hint="Mdtero could not inspect the task to select a download artifact. Pass an explicit artifact name or check task status first.",
                next_commands=[f"mdtero status {cleaned_task_id} --json", f"mdtero download {cleaned_task_id} paper_md --output-dir ./mdtero-output --json"],
                extra={"task_id": cleaned_task_id},
            )

    resolved_output_dir = _resolve_agent_output_dir(output_dir, root)
    try:
        path = active_client.download(cleaned_task_id, selected_artifact, resolved_output_dir)
    except FileNotFoundError as exc:
        return {
            "status": "failed",
            "reason_code": "artifact_not_available",
            "task_id": cleaned_task_id,
            "artifact": selected_artifact,
            "output_dir": str(resolved_output_dir),
            "message": redact_sensitive_text(str(exc)),
            "action_hint": "The selected artifact is not available for this task. Check task status for download_artifacts and preferred_artifact, then retry with that artifact name.",
            "next_commands": [f"mdtero status {cleaned_task_id} --json", f"mdtero download {cleaned_task_id} <artifact> --output-dir ./mdtero-output --json"],
        }
    except Exception as exc:
        return _agent_tool_exception_payload(
            exc,
            reason_code="artifact_download_failed",
            action_hint="Artifact download failed. Check authentication, task ownership, and task status before retrying.",
            next_commands=[f"mdtero status {cleaned_task_id} --json", f"mdtero download {cleaned_task_id} {selected_artifact} --output-dir ./mdtero-output --json", "mdtero doctor --json"],
            extra={"task_id": cleaned_task_id, "artifact": selected_artifact, "output_dir": str(resolved_output_dir)},
        )

    payload: dict[str, Any] = {
        "status": "downloaded",
        "reason_code": "artifact_downloaded",
        "task_id": cleaned_task_id,
        "artifact": selected_artifact,
        "path": str(path),
        "output_dir": str(resolved_output_dir),
        "action_hint": "Artifact downloaded. Use the local file for review, translation, Zotero notes, RAG ingest, or downstream agent work.",
        "next_commands": _download_artifact_next_commands(cleaned_task_id, selected_artifact, commands),
    }
    if task is not None:
        payload["task"] = task
    return redact_sensitive_payload(payload)


def _normalize_rag_query_result_for_agents(
    payload: dict[str, Any],
    *,
    project_name: str,
    server_project_id: str,
    question: str,
    commands: dict[str, Any],
) -> dict[str, Any]:
    matches = payload.get("matches") if isinstance(payload.get("matches"), list) else []
    source_nodes = payload.get("source_nodes") if isinstance(payload.get("source_nodes"), list) else _rag_source_nodes_from_matches(matches)
    citations = payload.get("citations") if isinstance(payload.get("citations"), list) else _rag_citations_from_matches(matches)
    payload.setdefault("status", "succeeded")
    payload.setdefault("reason_code", "rag_query_succeeded" if matches or payload.get("answer") else "no_matches")
    payload.setdefault("project", project_name)
    payload.setdefault("server_project_id", server_project_id)
    payload.setdefault("project_id", server_project_id)
    payload.setdefault("question", question)
    payload.setdefault("answer_kind", "extractive_evidence_pack")
    payload.setdefault("answer", _extract_rag_answer(matches))
    payload.setdefault("citations", citations)
    payload.setdefault("source_nodes", source_nodes)
    payload.setdefault("evidence_pack", _rag_evidence_pack(question=question, source_nodes=source_nodes, citations=citations))
    payload.setdefault("action_hint", "RAG query completed. Review evidence_pack.context_markdown, source_nodes, citations, and matches before writing a final synthesis.")
    payload.setdefault("next_commands", ["mdtero rag status --json", commands["rag_query"], commands["mcp_briefing"], commands["serve_mcp"]])
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


def _bootstrap_server_rag_for_query(client: Any, root: Path, state: Any, commands: dict[str, Any]) -> tuple[str | None, dict[str, Any]]:
    succeeded = [paper for paper in state.papers if paper.status == "succeeded" and paper.task_id]
    project_id = str(state.server_project_id or "").strip()
    if not succeeded:
        return None, {
            "status": "not_ready",
            "reason_code": "no_succeeded_tasks",
            "project": state.name,
            "server_project_id": project_id or state.server_project_id,
            "local_ready_for_ingest_count": 0,
            "local_paper_count": len(state.papers),
            "answer": None,
            "action_hint": "Parse at least one paper successfully before querying server-side Voyage RAG. Use the arXiv smoke DOI, direct file upload, or browser-extension handoff, then refresh the local project.",
            "next_commands": _rag_recovery_commands(commands),
        }

    bootstrap: dict[str, Any] = {
        "created_server_project": False,
        "bound_local_project": bool(project_id),
        "ingest": {"imported_count": 0, "failed_count": 0, "items": [], "failures": []},
    }
    if not project_id:
        try:
            created = client.create_project(state.name, description=f"Mdtero local project: {state.name}")
        except Exception as exc:
            return None, _bootstrap_failure_payload(state, commands, exc, reason_code="server_project_create_failed")
        project_id = str(created.get("id") or "").strip() if isinstance(created, dict) else ""
        if not project_id:
            return None, _bootstrap_failure_payload(state, commands, RuntimeError("server_project_id_missing"), reason_code="server_project_id_missing")
        bind_server_project(root, project_id)
        bootstrap.update({"created_server_project": True, "bound_local_project": True, "project": created})

    items: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for paper in succeeded:
        try:
            result = client.import_task_to_project(project_id, paper.task_id)
        except Exception as exc:
            failures.append({
                "input": paper.input,
                "task_id": paper.task_id,
                "status": "failed",
                "error_type": exc.__class__.__name__,
                "reason_code": "server_project_import_failed",
            })
            continue
        items.append({"input": paper.input, "task_id": paper.task_id, "result": result})
    bootstrap["ingest"] = {
        "server_project_id": project_id,
        "imported_count": len(items),
        "failed_count": len(failures),
        "items": items,
        "failures": failures,
    }
    if failures:
        return None, {
            "status": "failed",
            "reason_code": "server_project_import_failed",
            "project": state.name,
            "server_project_id": project_id,
            "answer": None,
            "bootstrap": bootstrap,
            "action_hint": "Some succeeded parse tasks could not be imported into the server project. Fix import failures, then rerun RAG query.",
            "next_commands": ["mdtero project ingest --json", "mdtero rag status --json", commands["rag_query"]],
        }
    try:
        bootstrap["build"] = client.rag_build(project_id)
    except Exception as exc:
        detail = _rag_query_exception_detail(exc)
        return None, {
            "status": "failed",
            "reason_code": str(detail.get("reason_code") or "server_rag_build_failed"),
            "project": state.name,
            "server_project_id": project_id,
            "answer": None,
            "error_type": exc.__class__.__name__,
            "bootstrap": bootstrap,
            "action_hint": _public_rag_action_hint(
                str(detail.get("reason_code") or "server_rag_build_failed"),
                detail.get("action_hint"),
            ),
            "next_commands": _rag_query_failure_next_commands(detail, commands),
        }
    return project_id, bootstrap


def _bootstrap_failure_payload(state: Any, commands: dict[str, Any], exc: Exception, *, reason_code: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "reason_code": reason_code,
        "project": state.name,
        "server_project_id": state.server_project_id,
        "answer": None,
        "error_type": exc.__class__.__name__,
        "action_hint": "Run `mdtero rag build --json` or retry with `mdtero rag query \"<question>\" --build-if-needed --json` so the CLI can create or bind the server project before querying server-side Voyage RAG.",
        "next_commands": [commands["rag_build"], "mdtero rag status --json", commands["rag_query"]],
    }


def _rag_recovery_commands(commands: dict[str, Any]) -> list[str]:
    return [
        "mdtero parse 10.48550/arXiv.1706.03762 --wait --timeout 300 --json",
        commands["parse_file"],
        commands["extension_handoff_url"],
        commands["refresh"],
        commands["rag_query"],
    ]


def _rag_query_exception_detail(exc: Exception) -> dict[str, Any]:
    response = getattr(exc, "response", None)
    try:
        detail = response.json().get("detail") if response is not None else None
    except Exception:
        detail = None
    return redact_sensitive_payload(detail) if isinstance(detail, dict) else {}


def _public_rag_action_hint(reason_code: str, server_hint: object | None = None) -> str:
    if reason_code == "voyage_not_configured":
        return (
            "Server-side Voyage RAG is not available for this Mdtero deployment yet. "
            "This is a Mdtero backend operations issue, not a user-side API key setup step; "
            "rerun `mdtero rag status --json` after the backend RAG service is configured."
        )
    hint = redact_sensitive_text(server_hint).strip()
    if hint:
        return hint
    return "Server RAG query failed. Check `mdtero rag status --json`; build or rebuild the server-side Voyage index if it is not ready."


def _rag_query_failure_next_commands(detail: dict[str, Any], commands: dict[str, Any]) -> list[str]:
    server_commands = [str(command).strip() for command in detail.get("next_commands") or [] if str(command).strip()]
    if server_commands:
        return server_commands
    return ["mdtero rag status --json", commands["rag_build"], commands["rag_query"]]


def _wait_for_agent_task(client: Any, task_id: str, *, timeout: float, interval: float) -> dict[str, Any]:
    try:
        return client.wait(task_id, interval=max(0.25, float(interval or 2.0)), timeout=max(0.25, float(timeout or 300.0)))
    except TimeoutError:
        return {
            "task_id": task_id,
            "status": "timeout",
            "stage": "waiting",
            "reason_code": "task_wait_timeout",
            "action_hint": "The task is still running or queued after the local MCP wait timeout. Poll again later or use a larger timeout.",
            "next_commands": [f"mdtero status {task_id} --wait --timeout {int(timeout)} --json", f"mdtero status {task_id} --json"],
        }


def _enrich_agent_parse_submission(result: dict[str, Any]) -> dict[str, Any]:
    task_id = str(result.get("task_id") or result.get("id") or "").strip()
    if not task_id:
        return result
    result.setdefault("task_id", task_id)
    result.setdefault("task_api", "/api/v1/tasks/{task_id}")
    result.setdefault("download_api", "/api/v1/tasks/{task_id}/download/{artifact}")
    preferred_artifact = _preferred_agent_artifact(result, default="paper_md")
    result.setdefault("preferred_artifact", preferred_artifact)
    result["next_commands"] = _dedupe_commands([
        *[str(command) for command in result.get("next_commands") or []],
        f"mdtero status {task_id} --wait --timeout 300 --json",
        f"mdtero download {task_id} {preferred_artifact} --output-dir ./mdtero-output --json",
        "mdtero project refresh --wait --timeout 300 --json",
    ])
    return result


def _enrich_agent_translate_submission(result: dict[str, Any]) -> dict[str, Any]:
    task_id = str(result.get("task_id") or result.get("id") or "").strip()
    if not task_id:
        return result
    result.setdefault("task_id", task_id)
    result.setdefault("task_api", "/api/v1/tasks/{task_id}")
    result.setdefault("download_api", "/api/v1/tasks/{task_id}/download/{artifact}")
    result.setdefault("preferred_artifact", "translated_md")
    result["next_commands"] = _dedupe_commands([
        *[str(command) for command in result.get("next_commands") or []],
        f"mdtero status {task_id} --wait --timeout 600 --json",
        f"mdtero download {task_id} translated_md --output-dir ./mdtero-output --json",
    ])
    return result


def _enrich_agent_task_status(task: dict[str, Any]) -> dict[str, Any]:
    task_id = str(task.get("task_id") or task.get("id") or "").strip()
    if not task_id:
        return task
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    for key in ("reason_code", "action_hint", "translation_attempts", "download_artifacts"):
        value = result.get(key)
        if value not in (None, "", [], {}) and task.get(key) in (None, "", [], {}):
            task[key] = value
    task.setdefault("task_id", task_id)
    task.setdefault("task_api", "/api/v1/tasks/{task_id}")
    task.setdefault("download_api", "/api/v1/tasks/{task_id}/download/{artifact}")
    preferred_artifact = _preferred_agent_artifact(task, default="translated_md" if _looks_like_translation_task(task) else "paper_md")
    if str(task.get("status") or "").lower() == "succeeded":
        task.setdefault("preferred_artifact", preferred_artifact)
    existing_commands = [str(command) for command in task.get("next_commands") or []]
    status = str(task.get("status") or "").lower()
    if status == "succeeded":
        defaults = [f"mdtero download {task_id} {preferred_artifact} --output-dir ./mdtero-output --json"]
    elif status in {"failed", "cancelled"}:
        defaults = [f"mdtero status {task_id} --json"]
        if _looks_like_translation_task(task):
            defaults.extend(["mdtero translate <task-id-or-markdown-file> --to zh-CN --wait --timeout 600 --json", "mdtero smoke --skip-translate --json"])
        else:
            defaults.append("mdtero project parse --include-failed --wait --timeout 300 --json")
    elif status == "timeout":
        defaults = [f"mdtero status {task_id} --wait --timeout 300 --json", f"mdtero status {task_id} --json"]
    else:
        defaults = [f"mdtero status {task_id} --wait --timeout 300 --json"]
    task["next_commands"] = _dedupe_commands([*existing_commands, *defaults])
    return task


def _preferred_agent_artifact(payload: dict[str, Any], *, default: str) -> str:
    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    candidates = [payload.get("preferred_artifact"), result.get("preferred_artifact"), payload.get("artifact"), result.get("artifact")]
    artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), dict) else {}
    candidates.extend([
        "translated_md" if "translated_md" in artifacts else None,
        "paper_md" if "paper_md" in artifacts else None,
        "paper_bundle" if "paper_bundle" in artifacts else None,
    ])
    for candidate in candidates:
        cleaned = str(candidate or "").strip()
        if cleaned:
            return cleaned
    return default


def _looks_like_translation_task(task: dict[str, Any]) -> bool:
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), dict) else {}
    return str(task.get("task_kind") or "").strip() == "translate" or bool(task.get("translation_attempts") or result.get("translation_attempts")) or "translated_md" in artifacts


def _agent_tool_exception_payload(exc: Exception, *, reason_code: str, action_hint: str, next_commands: list[str], extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "failed",
        "reason_code": reason_code,
        "error_type": exc.__class__.__name__,
        "message": redact_sensitive_text(str(exc)),
        "action_hint": action_hint,
        "next_commands": _dedupe_commands(next_commands),
    }
    response = getattr(exc, "response", None)
    if response is not None and getattr(response, "status_code", None) is not None:
        payload["http_status"] = response.status_code
    detail = getattr(exc, "payload", None)
    if isinstance(detail, dict):
        payload.update({key: value for key, value in redact_sensitive_payload(detail).items() if key not in {"status"} and value not in (None, "", [], {})})
    if extra:
        payload.update(extra)
    return redact_sensitive_payload(payload)


def build_agent_briefing(
    project_root: Path | None = None,
    *,
    rag_status_fetcher: Any | None = None,
    config: MdteroConfig | None = None,
    agent_root: Path | None = None,
) -> dict[str, Any]:
    root = project_root or Path.cwd()
    state = _load_project_or_none(root)
    config = config or load_config()
    commands = build_agent_commands(root)["commands"]
    server_rag = build_server_rag_status(root, fetcher=rag_status_fetcher)
    agent_status = detect_target_status(agent_root)
    detected_agents = [agent for agent in agent_status if agent.detected]
    installed_agents = [agent for agent in agent_status if agent.installed]
    pending_agent_installs = [agent for agent in agent_status if agent.detected and not agent.installed]

    papers = state.papers if state is not None else []
    pending = [paper for paper in papers if paper.status in {"pending", "created"} and not paper.task_id]
    running = [paper for paper in papers if paper.task_id and paper.status not in {"succeeded", "failed"}]
    succeeded = [paper for paper in papers if paper.status == "succeeded" and paper.task_id]
    failed = [paper for paper in papers if paper.status == "failed"]

    next_commands: list[str] = []
    if not config.is_authenticated:
        next_commands.extend([commands["login_api_key"], commands["doctor"]])
    if state is None:
        next_commands.extend([commands["project_init_named"], commands["discover"], commands["project_add"], commands["parse_doi_or_url"]])
    elif not state.papers:
        next_commands.extend([
            "mdtero discover \"<topic>\" --interactive",
            "mdtero project add <doi-or-url> --json",
            commands["parse_doi_or_url"],
        ])
    if pending:
        next_commands.append(commands["parse_pending"])
    if running:
        next_commands.append(commands["refresh"])
    if failed:
        next_commands.append("mdtero project parse --include-failed --wait --timeout 300 --json")
    if succeeded:
        next_commands.append(commands["download_markdown"])
    if pending_agent_installs:
        next_commands.append(commands["agent_install"])
    next_commands.extend(str(command) for command in server_rag.get("next_commands", []) if command)
    next_commands.extend([commands["mcp_briefing"], commands["serve_mcp"]])

    return redact_sensitive_payload({
        "project": {
            "name": state.name if state is not None else root.resolve().name,
            "root": str(root.resolve()),
            "initialized": state is not None,
            "project_file": str(project_path(root)),
            "server_project_id": state.server_project_id if state is not None else None,
            "paper_count": len(papers),
        },
        "account": {
            "authenticated": config.is_authenticated,
            "api_key_source": config.api_key_source,
            "api_base_url": config.api_base_url,
            "action_hint": "Run `mdtero doctor --json` before cloud parse, translation, discovery fallback, RAG, or MCP." if config.is_authenticated else "Authenticate before cloud parse, translation, discovery fallback, RAG, or MCP.",
            "next_commands": [commands["doctor"]] if config.is_authenticated else [commands["login_api_key"], commands["doctor"]],
        },
        "health": {
            "pending_count": len(pending),
            "running_count": len(running),
            "succeeded_count": len(succeeded),
            "failed_count": len(failed),
            "ready_for_ingest_count": len(succeeded),
            "rag_status": server_rag.get("status"),
            "rag_reason_code": server_rag.get("reason_code"),
        },
        "ready_artifacts": [_paper_agent_summary(paper, include_download=True) for paper in succeeded[:20]],
        "blocked_items": [_paper_agent_summary(paper, include_download=False) for paper in failed[:20]],
        "active_items": [_paper_agent_summary(paper, include_download=False) for paper in [*pending, *running][:20]],
        "rag": {
            "server_project_id": server_rag.get("server_project_id"),
            "status": server_rag.get("status"),
            "reason_code": server_rag.get("reason_code"),
            "agent_summary": server_rag.get("agent_summary"),
            "action_hint": server_rag.get("action_hint"),
            "next_commands": server_rag.get("next_commands", []),
        },
        "agents": {
            "detected_count": len(detected_agents),
            "installed_count": len(installed_agents),
            "pending_install_count": len(pending_agent_installs),
            "pending_install_targets": [agent.target for agent in pending_agent_installs],
            "interactive_install_command": commands["agent_install"],
            "action_hint": "Run `mdtero agent install --interactive` and select detected workspaces with spaces." if pending_agent_installs else "Agent skills are installed for detected workspaces, or no local agent workspace was detected.",
            "targets": [
                {
                    "target": agent.target,
                    "label": agent.label,
                    "detected": agent.detected,
                    "installed": agent.installed,
                    "skill_path": agent.skill_path,
                    "install_command": agent.install_command,
                    "selection_index": agent.selection_index,
                }
                for agent in agent_status
            ],
        },
        "recommended_next_commands": _dedupe_commands(next_commands),
        "mcp_tools": [
            "agent_briefing",
            "project_status",
            "paper_context",
            "submit_parse",
            "task_status",
            "download_artifact",
            "request_translation",
            "rag_context",
            "server_rag_status",
            "rag_query",
            "agent_commands",
        ],
    })


def _load_project_or_none(root: Path) -> Any | None:
    try:
        return load_project(root)
    except FileNotFoundError:
        return None


def _server_rag_action_hint(status: dict[str, Any], commands: dict[str, Any]) -> str:
    server_hint = redact_sensitive_text(status.get("action_hint")).strip()
    reason_code = str(status.get("reason_code") or "").strip()
    readiness = status.get("readiness") if isinstance(status.get("readiness"), dict) else {}
    if readiness.get("provider_blocked"):
        return _public_rag_action_hint(reason_code or "server_rag_status_failed", server_hint)
    if readiness.get("ready_for_query"):
        return "Server-side Voyage RAG is ready. Query it with `mdtero rag query \"<question>\" --build-if-needed --json` or expose the project through MCP."
    if readiness.get("needs_build") or readiness.get("next_step") == "build":
        return server_hint or "Build or refresh the server-side Voyage index with `mdtero rag build --json`, then query the project."
    if readiness.get("needs_ingest") or readiness.get("next_step") == "ingest":
        return server_hint or "Import succeeded parse tasks with `mdtero project ingest --json`, then run `mdtero rag build --json`."
    return server_hint or f"Check server-side Voyage RAG status, then run `{commands['rag_build']}` if the project is not query-ready."


def _server_rag_agent_summary(status: dict[str, Any]) -> dict[str, Any]:
    existing = status.get("agent_summary") if isinstance(status.get("agent_summary"), dict) else {}
    readiness = status.get("readiness") if isinstance(status.get("readiness"), dict) else {}
    summary = status.get("summary") if isinstance(status.get("summary"), dict) else {}
    provider_blocked = bool(readiness.get("provider_blocked"))
    return {
        **existing,
        "status": str(status.get("status") or existing.get("status") or "unknown"),
        "reason_code": str(status.get("reason_code") or existing.get("reason_code") or "unknown"),
        "selected_provider": status.get("selected_provider", existing.get("selected_provider")),
        "provider_state": status.get("provider_state", existing.get("provider_state")),
        "provider_configured": False if provider_blocked else bool(existing.get("provider_configured", status.get("provider_configured", readiness.get("ready_for_query") or readiness.get("needs_build") or readiness.get("needs_ingest")))),
        "embedding_model": status.get("embedding_model") or summary.get("embedding_model") or existing.get("embedding_model"),
        "ready_for_query": bool(readiness.get("ready_for_query")),
        "readiness_status": readiness.get("readiness_status"),
        "next_step": readiness.get("next_step"),
        "document_count": readiness.get("document_count", existing.get("document_count", 0)),
        "chunk_count": readiness.get("chunk_count", existing.get("chunk_count", 0)),
        "embedded_count": readiness.get("embedded_count", existing.get("embedded_count", 0)),
        "pending_embedding_count": readiness.get("pending_embedding_count", existing.get("pending_embedding_count", 0)),
        "match_count": readiness.get("match_count", existing.get("match_count", 0)),
        "next_commands": status.get("next_commands", existing.get("next_commands", [])),
    }


def _shell_safe_project_name(name: str) -> str:
    cleaned = str(name or "mdtero-project").strip() or "mdtero-project"
    if _is_shell_safe_project_name(cleaned):
        return cleaned
    return "<name>"


def _is_shell_safe_project_name(value: str) -> bool:
    return all(char.isalnum() or char in {"-", "_", "."} for char in value)


def _paper_commands(paper: Any) -> list[str]:
    if paper.status in {"pending", "created"} and not paper.task_id:
        return ["mdtero project parse --wait --timeout 300 --json"]
    if paper.task_id and paper.status not in {"succeeded", "failed"}:
        return [f"mdtero status {paper.task_id} --wait --timeout 300 --json", "mdtero project refresh --wait --timeout 300 --json"]
    if paper.task_id and paper.status == "succeeded":
        return [f"mdtero download {paper.task_id} {paper.artifact or 'paper_md'} --output-dir ./mdtero-output --json", "mdtero project ingest --json"]
    if paper.status == "failed":
        return ["mdtero project parse --include-failed --wait --timeout 300 --json"]
    return []


def _paper_agent_summary(paper: Any, *, include_download: bool) -> dict[str, Any]:
    payload = {
        "input": paper.input,
        "title": paper.title,
        "doi": paper.doi,
        "task_id": paper.task_id,
        "status": paper.status,
        "reason_code": paper.reason_code,
        "action_hint": paper.action_hint,
        "artifact": paper.artifact,
        "provider": paper.provider,
        "parser_strategy": paper.parser_strategy,
        "translation_attempts": paper.translation_attempts,
        "source": paper.source,
        "recommended_commands": _paper_commands(paper),
    }
    if include_download and paper.task_id:
        payload["download_command"] = f"mdtero download {paper.task_id} {paper.artifact or 'paper_md'} --output-dir ./mdtero-output --json"
    return redact_sensitive_payload(payload)


def _resolve_agent_output_dir(output_dir: str | Path, root: Path) -> Path:
    path = Path(str(output_dir or "./mdtero-output")).expanduser()
    if not path.is_absolute():
        path = root / path
    return path


def _download_artifact_next_commands(task_id: str, artifact: str, commands: dict[str, Any]) -> list[str]:
    next_commands = [
        f"mdtero status {task_id} --json",
        commands.get("download_artifact", "mdtero download <task-id> <artifact> --output-dir ./mdtero-output --json"),
        commands.get("download_markdown", "mdtero project download --output-dir ./mdtero-output --json"),
    ]
    if artifact == "translated_md":
        next_commands.append("mdtero project refresh --wait --timeout 300 --json")
    else:
        next_commands.extend([commands.get("translate", "mdtero translate <task-id-or-markdown-file> --to zh-CN --wait --timeout 600 --json"), "mdtero project ingest --json", commands.get("rag_query", "mdtero rag query \"<question>\" --build-if-needed --json")])
    next_commands.extend([commands.get("mcp_briefing", "mdtero mcp briefing --json"), commands.get("serve_mcp", "mdtero mcp serve")])
    return _dedupe_commands(next_commands)


def _dedupe_commands(commands: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for command in commands:
        cleaned = str(command or "").strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        result.append(cleaned)
    return result


def serve_project_context(project_root: Path | None = None) -> None:
    try:
        from fastmcp import FastMCP
    except Exception as exc:  # pragma: no cover - optional runtime import
        raise RuntimeError(
            "FastMCP is required for `mdtero mcp serve`. Run `mdtero doctor --json` first; "
            "during alpha, reinstall the public client with "
            "`uv tool install --force git+https://github.com/JonbinC/doi2md.git`. "
            "After the PyPI handoff, `uv tool install --force mdtero` is the stable command."
        ) from exc

    root = project_root or Path.cwd()
    mcp = FastMCP("mdtero")

    @mcp.tool
    def project_status() -> dict:
        return build_project_status(root)

    @mcp.tool
    def paper_context(input_or_task_id: str) -> dict:
        return build_paper_context(input_or_task_id, root)

    @mcp.tool
    def rag_context() -> dict:
        return build_rag_context(root)

    @mcp.tool
    def submit_parse(input_value: str, wait: bool = True, timeout: float = 300.0, interval: float = 2.0) -> dict:
        return submit_parse_for_agent(input_value, root, wait=wait, timeout=timeout, interval=interval)

    @mcp.tool
    def task_status(task_id: str, wait: bool = False, timeout: float = 300.0, interval: float = 2.0) -> dict:
        return task_status_for_agent(task_id, root, wait=wait, timeout=timeout, interval=interval)

    @mcp.tool
    def download_artifact(task_id: str, artifact: str | None = None, output_dir: str = "./mdtero-output") -> dict:
        return download_artifact_for_agent(task_id, root, artifact=artifact, output_dir=output_dir)

    @mcp.tool
    def request_translation(task_id_or_markdown_path: str, target_language: str = "zh-CN", wait: bool = True, timeout: float = 600.0, interval: float = 2.0) -> dict:
        return request_translation_for_agent(task_id_or_markdown_path, root, target_language=target_language, wait=wait, timeout=timeout, interval=interval)

    @mcp.tool
    def server_rag_status() -> dict:
        return build_server_rag_status(root)

    @mcp.tool
    def rag_query(question: str) -> dict:
        return query_server_rag(question, root, build_if_needed=True)

    @mcp.tool
    def agent_briefing() -> dict:
        return build_agent_briefing(root)

    @mcp.tool
    def agent_commands() -> dict:
        return build_agent_commands(root)

    mcp.run()
