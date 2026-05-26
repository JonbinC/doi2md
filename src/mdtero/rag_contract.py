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
    provider_configured = _provider_configured(payload, ready_for_query=ready_for_query)
    needs_ingest = reason_code == "project_has_no_chunks" or chunk_count <= 0
    needs_build = reason_code in {"rag_index_not_built", "rag_index_partial"} or (chunk_count > 0 and embedded_count < chunk_count)
    provider_blocked = not provider_configured or reason_code in {
        "voyage_not_configured",
        "voyage_timeout",
        "voyage_rate_limited",
        "voyage_request_failed",
        "voyage_response_invalid",
    }
    if provider_blocked:
        next_step = "check_backend_rag_provider"
    elif ready_for_query:
        next_step = "query"
    elif needs_ingest:
        next_step = "ingest"
    elif needs_build:
        next_step = "build"
    else:
        next_step = "inspect_status"
    return {
        "ready_for_query": ready_for_query,
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
        "provider_configured": _provider_configured(payload, ready_for_query=bool(readiness.get("ready_for_query"))),
        "embedding_model": payload.get("embedding_model") or summary.get("embedding_model"),
        "ready_for_query": bool(readiness.get("ready_for_query")),
        "next_step": readiness.get("next_step"),
        "document_count": readiness.get("document_count", 0),
        "chunk_count": readiness.get("chunk_count", 0),
        "embedded_count": readiness.get("embedded_count", 0),
        "pending_embedding_count": readiness.get("pending_embedding_count", 0),
        "match_count": readiness.get("match_count", 0),
        "next_commands": payload.get("next_commands", []),
    }


def _summary_int(summary: dict[str, Any], *keys: str) -> int:
    for key in keys:
        try:
            return int(summary.get(key) or 0)
        except (TypeError, ValueError):
            continue
    return 0


def _provider_configured(payload: dict[str, Any], *, ready_for_query: bool) -> bool:
    if "provider_configured" in payload:
        return bool(payload.get("provider_configured"))
    if "voyage_configured" in payload:
        return bool(payload.get("voyage_configured"))
    return ready_for_query
