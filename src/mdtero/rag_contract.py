from __future__ import annotations

from typing import Any


def ensure_rag_contract(payload: dict[str, Any]) -> dict[str, Any]:
    """Backfill the shared server/CLI/MCP RAG readiness contract."""

    payload.setdefault("readiness", build_rag_readiness(payload))
    payload.setdefault("agent_summary", build_rag_agent_summary(payload))
    return payload


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
