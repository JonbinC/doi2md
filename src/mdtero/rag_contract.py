from __future__ import annotations

from typing import Any


def ensure_rag_contract(payload: dict[str, Any]) -> dict[str, Any]:
    """Backfill the shared server/CLI/MCP RAG readiness contract."""

    payload.setdefault("citation_contract", build_rag_citation_contract(payload))
    payload.setdefault("readiness", build_rag_readiness(payload))
    payload["next_best_action"] = build_rag_next_best_action(payload)
    payload.setdefault("agent_summary", build_rag_agent_summary(payload))
    payload.setdefault("agent_tool_plan", build_rag_agent_tool_plan(payload))
    payload.setdefault("mcp_server", build_mcp_server_contract(payload))
    return payload


def build_mcp_server_contract(payload: dict[str, Any]) -> dict[str, Any]:
    root = str(payload.get("project_root") or payload.get("local_project_root") or "<local-mdtero-project-root>")
    return {
        "name": "mdtero",
        "runtime": "FastMCP",
        "transport": "stdio",
        "serve_command": "mdtero mcp serve",
        "briefing_command": "mdtero mcp briefing --json",
        "startup_order": ["mdtero doctor --json", "mdtero mcp briefing --json", "mdtero mcp serve"],
        "primary_tool": "agent_briefing",
        "tools": [
            "agent_briefing",
            "project_init",
            "project_status",
            "project_add",
            "paper_context",
            "submit_parse",
            "task_status",
            "download_artifact",
            "request_translation",
            "rag_context",
            "server_rag_status",
            "server_rag_build",
            "rag_query",
            "agent_commands",
        ],
        "agent_config_hint": {
            "mcpServers": {
                "mdtero": {
                    "command": "mdtero",
                    "args": ["mcp", "serve"],
                    "cwd": root,
                }
            }
        },
        "action_hint": "Start this FastMCP stdio server from the local project root after running `mdtero mcp briefing --json`; agents should call `agent_briefing` before other tools.",
    }


def build_rag_readiness(payload: dict[str, Any]) -> dict[str, Any]:
    status = str(payload.get("status") or "").strip().lower()
    reason_code = str(payload.get("reason_code") or "").strip().lower()
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    chunk_count = _summary_int(summary, "chunk_count", "indexed_chunk_count")
    embedded_count = _summary_int(summary, "embedded_count", "indexed_chunk_count")
    pending_embedding_count = _summary_int(summary, "pending_embedding_count")
    match_count = _summary_int(summary, "match_count")
    ready_for_query = status in {"ready", "succeeded"} or reason_code in {"indexed", "rag_query_succeeded", "ok", "no_matches"}
    explicit_needs_build = reason_code in {"rag_index_not_built", "rag_index_partial"}
    needs_ingest = reason_code == "project_has_no_chunks" or (chunk_count <= 0 and not explicit_needs_build)
    needs_build = explicit_needs_build or (chunk_count > 0 and embedded_count < chunk_count)
    provider_configured = _provider_configured(
        payload,
        ready_for_query=ready_for_query,
        reason_code=reason_code,
        needs_ingest=needs_ingest,
        needs_build=needs_build,
    )
    provider_blocked = _provider_blocked(payload, provider_configured=provider_configured, reason_code=reason_code)
    if reason_code in {
        "voyage_not_configured",
        "voyage_timeout",
        "voyage_rate_limited",
        "voyage_request_failed",
        "voyage_response_invalid",
    }:
        provider_blocked = True
    if ready_for_query:
        needs_ingest = False
        needs_build = False
        provider_blocked = False
    if provider_blocked:
        readiness_status = "blocked"
    elif ready_for_query:
        readiness_status = "ready"
    elif needs_ingest or needs_build:
        readiness_status = "waiting"
    else:
        readiness_status = "not_ready"
    if provider_blocked:
        next_step = "check_backend_rag_provider"
    elif ready_for_query:
        next_step = "query"
    elif needs_build:
        next_step = "build"
    elif needs_ingest:
        next_step = "ingest"
    else:
        next_step = "inspect_status"
    return {
        "ready_for_query": ready_for_query,
        "readiness_status": readiness_status,
        "can_build": provider_configured and chunk_count > 0,
        "needs_ingest": needs_ingest,
        "needs_build": needs_build,
        "provider_blocked": provider_blocked,
        "next_step": next_step,
        "blocker_reason_code": None if ready_for_query else (reason_code or None),
        "document_count": _summary_int(summary, "document_count"),
        "chunk_count": chunk_count,
        "embedded_count": embedded_count,
        "pending_embedding_count": pending_embedding_count,
        "match_count": match_count,
    }


def build_rag_agent_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    readiness = payload.get("readiness") if isinstance(payload.get("readiness"), dict) else build_rag_readiness(payload)
    return {
        "status": str(payload.get("status") or "unknown"),
        "reason_code": str(payload.get("reason_code") or "unknown"),
        "selected_provider": payload.get("selected_provider"),
        "provider_state": payload.get("provider_state"),
        "provider_configured": _provider_configured(
            payload,
            ready_for_query=bool(readiness.get("ready_for_query")),
            reason_code=str(payload.get("reason_code") or "").strip().lower(),
            needs_ingest=bool(readiness.get("needs_ingest")),
            needs_build=bool(readiness.get("needs_build")),
        ),
        "embedding_model": payload.get("embedding_model") or summary.get("embedding_model"),
        "ready_for_query": bool(readiness.get("ready_for_query")),
        "readiness_status": readiness.get("readiness_status"),
        "next_step": readiness.get("next_step"),
        "document_count": readiness.get("document_count", 0),
        "chunk_count": readiness.get("chunk_count", 0),
        "embedded_count": readiness.get("embedded_count", 0),
        "pending_embedding_count": readiness.get("pending_embedding_count", 0),
        "match_count": readiness.get("match_count", 0),
        "next_commands": _next_commands(payload),
    }


def build_rag_next_best_action(payload: dict[str, Any]) -> dict[str, Any]:
    readiness = payload.get("readiness") if isinstance(payload.get("readiness"), dict) else build_rag_readiness(payload)
    reason_code = str(payload.get("reason_code") or "unknown").strip() or "unknown"
    next_commands = _next_commands(payload)
    primary_command = next_commands[0] if next_commands else "mdtero rag status --json"
    if readiness.get("provider_blocked"):
        action = "check_backend_provider"
        scope = "backend_operations"
        hint = "Backend Voyage RAG is blocked; users should wait for backend provider configuration rather than setting a local Voyage key."
    elif readiness.get("ready_for_query"):
        action = "query"
        scope = "user_or_agent"
        hint = "RAG is ready; ask a grounded project question and preserve answer, citations, source_nodes, and evidence_pack."
    elif readiness.get("needs_build"):
        action = "build"
        scope = "user_or_agent"
        hint = "Imported chunks exist but embeddings are incomplete; prefer the one-command RAG bootstrap query so the CLI can build backend Voyage RAG and query without a separate server project id step."
    elif readiness.get("needs_ingest"):
        action = "ingest"
        scope = "user_or_agent"
        hint = "Import succeeded parse Markdown artifacts into the bound server project before building RAG."
    else:
        action = "inspect_status"
        scope = "user_or_agent"
        hint = "Inspect project and server RAG status before choosing parse, ingest, build, or query."
    primary_command = _primary_command_for_action(action, next_commands, fallback=primary_command)
    return {
        "action": action,
        "scope": scope,
        "reason_code": reason_code,
        "readiness_status": readiness.get("readiness_status"),
        "next_step": readiness.get("next_step"),
        "primary_command": primary_command,
        "action_hint": hint,
        "preserve_fields": ["reason_code", "action_hint", "next_commands", "readiness", "agent_summary", "download_artifacts"],
        "citation_contract": payload.get("citation_contract") or build_rag_citation_contract(payload),
    }


def build_rag_citation_contract(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    answer_kind = str((payload or {}).get("answer_kind") or "extractive_evidence_pack")
    return {
        "answer_kind": answer_kind,
        "evidence_fields": ["answer", "citations", "source_nodes", "matches", "evidence_pack.context_markdown"],
        "required_for_final_answer": ["citations", "source_nodes"],
        "agent_instruction": (
            "Use source_nodes and citations as grounded evidence. Treat answer as an extractive summary, "
            "not a generated final synthesis, unless a downstream LLM rewrites it with citations preserved."
        ),
        "preserve_fields": ["reason_code", "action_hint", "next_commands", "readiness", "agent_summary", "citation_contract"],
    }


def _primary_command_for_action(action: str, commands: list[str], *, fallback: str) -> str:
    prefixes = {
        "check_backend_provider": ("mdtero rag status",),
        "query": ("mdtero rag query",),
        "build": ("mdtero rag query", "mdtero rag build"),
        "ingest": ("mdtero project ingest",),
        "inspect_status": ("mdtero rag status", "mdtero project status"),
    }.get(action, ())
    for prefix in prefixes:
        for command in commands:
            if command.startswith(prefix):
                return command
    return fallback


def build_rag_agent_tool_plan(payload: dict[str, Any]) -> list[dict[str, Any]]:
    readiness = payload.get("readiness") if isinstance(payload.get("readiness"), dict) else build_rag_readiness(payload)
    reason_code = str(payload.get("reason_code") or "unknown").strip()
    normalized_reason = reason_code.lower()
    status = str(payload.get("status") or "unknown").strip()
    project_id = str(payload.get("server_project_id") or payload.get("project_id") or "<project-id>")
    next_commands = _next_commands(payload)
    ready_for_query = bool(readiness.get("ready_for_query"))
    provider_blocked = bool(readiness.get("provider_blocked"))
    needs_ingest = bool(readiness.get("needs_ingest"))
    needs_build = bool(readiness.get("needs_build"))

    plan: list[dict[str, Any]] = [
        {
            "step": "inspect_rag_status",
            "tool": "server_rag_status",
            "purpose": "Read backend Voyage RAG readiness before build/query decisions.",
            "when": "Always call first for a server project or after a failed build/query.",
            "arguments": {"project_id": project_id},
            "success_signal": "readiness.next_step, agent_summary, reason_code, and next_commands are present.",
            "failure_fields": ["reason_code", "action_hint", "next_commands", "readiness"],
            "next_commands": ["mdtero rag status --json"],
        }
    ]

    if normalized_reason == "server_project_not_linked":
        plan.append({
            "step": "create_or_link_server_project",
            "tool": "project_bridge",
            "purpose": "Create or bind the local Mdtero project to a server project before server-side Voyage RAG can ingest, build, or query.",
            "when": "reason_code is server_project_not_linked or server_project_id is missing.",
            "arguments": {"project_id": project_id},
            "success_signal": "server_project_id is present in the local project and `mdtero rag status --json` can inspect it.",
            "failure_fields": ["reason_code", "action_hint", "next_commands", "server_project_id"],
            "next_commands": next_commands,
        })
    elif provider_blocked:
        plan.append({
            "step": "check_backend_provider",
            "tool": "backend_operations",
            "purpose": "Confirm the server-side Voyage provider is configured and reachable; users should not provide a local Voyage key.",
            "when": "readiness.provider_blocked is true or reason_code starts with voyage_.",
            "arguments": {"selected_provider": payload.get("selected_provider") or "voyage"},
            "success_signal": "provider_state becomes configured and provider_configured is true.",
            "failure_fields": ["reason_code", "action_hint", "next_commands", "provider_state"],
            "next_commands": next_commands,
        })
    elif needs_ingest:
        plan.append({
            "step": "ingest_project_documents",
            "tool": "project_ingest",
            "purpose": "Import succeeded parse Markdown artifacts into the server project before building Voyage embeddings.",
            "when": "readiness.needs_ingest is true or reason_code is project_has_no_chunks.",
            "arguments": {"project_id": project_id},
            "success_signal": "summary.chunk_count is greater than zero.",
            "failure_fields": ["reason_code", "action_hint", "next_commands"],
            "next_commands": next_commands,
        })
    elif needs_build:
        plan.append({
            "step": "build_rag_index",
            "tool": "server_rag_build",
            "purpose": "Build backend Voyage embeddings through the local FastMCP wrapper and wait until the server project is query-ready.",
            "when": "readiness.needs_build is true or reason_code is rag_index_not_built/rag_index_partial.",
            "arguments": {"project_id": project_id, "wait": True, "timeout": 300, "interval": 2},
            "success_signal": "status_after_build.ready_for_query is true, or readiness.ready_for_query becomes true after build polling.",
            "failure_fields": ["reason_code", "action_hint", "next_commands", "readiness"],
            "next_commands": next_commands,
        })
        plan.append({
            "step": "query_after_build",
            "tool": "rag_query",
            "purpose": "Ask the first grounded project question after server_rag_build reports readiness.",
            "when": "server_rag_build.status_after_build.ready_for_query is true.",
            "arguments": {"project_id": project_id, "question": "<project question>", "limit": 5},
            "success_signal": "reason_code is rag_query_succeeded/no_matches and evidence_pack plus citations are present.",
            "failure_fields": ["reason_code", "action_hint", "next_commands", "readiness"],
            "next_commands": ["mdtero rag query \"<question>\" --build-if-needed --json"],
        })

    if ready_for_query or status == "succeeded" or reason_code in {"indexed", "rag_query_succeeded", "ok", "no_matches"}:
        plan.append({
            "step": "query_rag",
            "tool": "rag_query",
            "purpose": "Ask grounded project questions against server-side Voyage RAG and use evidence_pack/source_nodes/citations as the evidence surface.",
            "when": "readiness.ready_for_query is true, or after rag_build succeeds.",
            "arguments": {"project_id": project_id, "question": "<project question>", "limit": 5},
            "success_signal": "reason_code is rag_query_succeeded/no_matches and evidence_pack plus citations are present.",
            "failure_fields": ["reason_code", "action_hint", "next_commands", "readiness"],
            "next_commands": next_commands,
        })

    plan.append({
        "step": "handoff_to_local_agent",
        "tool": "mcp_briefing",
        "purpose": "Expose the server RAG state to local FastMCP agents through the CLI project bridge.",
        "when": "After status/build/query, or whenever a local agent needs project context.",
        "arguments": {},
        "success_signal": "mdtero mcp briefing --json includes project_bridge, rag, recommended_next_commands, and mcp_tool_plan.",
        "failure_fields": ["reason_code", "action_hint", "next_commands"],
        "next_commands": ["mdtero mcp briefing --json", "mdtero mcp serve"],
    })
    return plan


def _next_commands(payload: dict[str, Any]) -> list[str]:
    commands = payload.get("next_commands")
    if isinstance(commands, list) and commands:
        return [str(command) for command in commands]
    return [
        "mdtero rag status --json",
        "mdtero rag query \"<question>\" --build-if-needed --json",
        "mdtero mcp briefing --json",
        "mdtero mcp serve",
    ]


def _summary_int(summary: dict[str, Any], *keys: str) -> int:
    for key in keys:
        try:
            return int(summary.get(key) or 0)
        except (TypeError, ValueError):
            continue
    return 0


def _provider_configured(payload: dict[str, Any], *, ready_for_query: bool, reason_code: str = "", needs_ingest: bool = False, needs_build: bool = False) -> bool:
    if "provider_configured" in payload:
        return bool(payload.get("provider_configured"))
    if "voyage_configured" in payload:
        return bool(payload.get("voyage_configured"))
    reason_code = reason_code or str(payload.get("reason_code") or "").strip().lower()
    if reason_code in {"voyage_not_configured", "provider_not_configured"}:
        return False
    if needs_ingest or needs_build:
        return True
    provider_state = str(payload.get("provider_state") or "").strip().lower()
    if provider_state in {"configured", "ready", "available", "enabled", "done", "indexed"}:
        return True
    if provider_state in {"missing", "not_configured", "unconfigured", "disabled", "failed", "error"}:
        return False
    selected_provider = str(payload.get("selected_provider") or "").strip().lower()
    if selected_provider in {"voyage", "voyageai", "voyage_ai", "voyage-3", "voyage-4"}:
        return True
    return ready_for_query


def _provider_blocked(payload: dict[str, Any], *, provider_configured: bool, reason_code: str) -> bool:
    if reason_code in {"rag_index_not_built", "rag_index_partial", "project_has_no_chunks"}:
        return False
    if provider_configured:
        return False
    provider_state = str(payload.get("provider_state") or "").strip().lower()
    if provider_state in {"missing", "not_configured", "unconfigured", "disabled", "failed", "error"}:
        return True
    return reason_code.startswith("voyage_") or reason_code.startswith("provider_")
