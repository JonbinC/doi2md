from __future__ import annotations

from pathlib import Path
from typing import Any

from .agent import detect_target_status
from .client import MdteroClient
from .config import MdteroConfig, load_config
from .projects import bind_server_project, load_project, paper_to_document, project_documents, project_path
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
        "download_markdown": "mdtero project download --output-dir ./mdtero-output --json",
        "translate": "mdtero translate <task-id-or-markdown-file> --to zh-CN --json",
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
    return {
        "project": state.name,
        "server_project_id": state.server_project_id,
        "ready": bool(state.server_project_id and succeeded),
        "ready_for_ingest_count": len(succeeded),
        "reason_code": "ready" if state.server_project_id and succeeded else "server_project_not_linked" if not state.server_project_id else "no_succeeded_tasks",
        "commands": build_agent_commands(root)["commands"],
    }


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
    next_commands = ["mdtero rag status --json"]
    if server_status == "ready" or reason_code == "indexed":
        next_commands.extend([commands["rag_query"], commands["mcp_briefing"], commands["serve_mcp"]])
    elif local_ready > 0:
        next_commands.extend([commands["ingest_for_rag"], commands["rag_build"], commands["rag_query"]])
    else:
        next_commands.extend([commands["parse_pending"], commands["refresh"], commands["ingest_for_rag"]])

    status.setdefault("project", state.name)
    status.setdefault("server_project_id", state.server_project_id)
    status.setdefault("local_ready_for_ingest_count", local_ready)
    status.setdefault("local_paper_count", len(state.papers))
    status["next_commands"] = next_commands
    status["agent_summary"] = {
        "status": server_status,
        "reason_code": reason_code,
        "embedded_count": summary.get("embedded_count", 0),
        "chunk_count": summary.get("chunk_count", 0),
        "pending_embedding_count": summary.get("pending_embedding_count", 0),
    }
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
        "action_hint": "Create or link a server project before querying server-side Voyage RAG.",
        "next_commands": ["mdtero project create-server --json", "mdtero project ingest --json", "mdtero rag status --json", commands["rag_query"]],
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
