"""Agent-facing compact payloads and paper summary helpers."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_COMPACT_TOP_KEYS = (
    "task_id",
    "status",
    "stage",
    "task_kind",
    "quality_label",
    "quality_summary",
    "quality_warning",
    "reason_code",
    "action_hint",
    "next_commands",
    "preferred_artifact",
    "download_artifacts",
    "parse_outcome",
    "client_acquisition",
    "quality_route_summary",
    "route_quality_comparison",
    "selected_provider",
    "parser_strategy",
    "error_code",
    "error_message",
    "input",
    "paper_input",
    "authenticated",
    "ready",
    "status_code",
    "results",
    "count",
    "total",
    "query",
    "providers",
    "project_add",
    "path",
    "artifact",
    "title",
    "sections",
    "line_count",
    "range",
    "excerpt",
    "front_matter",
    "source",
)

_COMPACT_NESTED_KEEP = {
    "quality_summary": (
        "quality_label",
        "content_level",
        "coverage_score",
        "structure_score",
        "fidelity_score",
        "section_count",
        "paragraph_count",
        "body_token_count",
        "quality_issue_codes",
        "next_action",
        "abstract_only",
    ),
    "parse_outcome": ("billable", "outcome_code", "reason_codes", "next_action"),
    "client_acquisition": ("status", "reason_code", "artifact_kind", "source_url", "action_hint"),
    "quality_warning": ("code", "message"),
}


def wants_json_compact(args: Any) -> bool:
    return bool(getattr(args, "json_compact", False))


def wants_json_output(args: Any) -> bool:
    return bool(getattr(args, "json", False) or getattr(args, "json_compact", False) or getattr(args, "trace", False))


def compact_agent_payload(payload: Any) -> Any:
    """Shrink task/discovery/doctor payloads for agent context windows."""
    if isinstance(payload, list):
        return [compact_agent_payload(item) for item in payload[:50]]
    if not isinstance(payload, dict):
        return payload

    # Prefer an already-agent-shaped object; otherwise project nested task.
    source = payload
    if "task_id" not in payload and isinstance(payload.get("final_task"), dict):
        merged = dict(payload.get("final_task") or {})
        for key in ("client_acquisition", "reason_code", "action_hint", "quality_label"):
            if key in payload and key not in merged:
                merged[key] = payload[key]
        source = merged
    elif "task_id" not in payload and isinstance(payload.get("task"), dict):
        source = dict(payload.get("task") or {})

    out: dict[str, Any] = {"schema": "mdtero.agent.v1", "compact": True}
    for key in _COMPACT_TOP_KEYS:
        if key not in source:
            continue
        value = source.get(key)
        if value in (None, "", [], {}):
            continue
        if key in _COMPACT_NESTED_KEEP and isinstance(value, dict):
            keep = _COMPACT_NESTED_KEEP[key]
            trimmed = {item: value.get(item) for item in keep if value.get(item) not in (None, "", [], {})}
            if trimmed:
                out[key] = trimmed
            continue
        if key == "route_quality_comparison" and isinstance(value, list):
            out[key] = [
                {
                    "connector": item.get("connector"),
                    "source_format": item.get("source_format"),
                    "status": item.get("status"),
                    "reason_code": ((item.get("failure") or {}) if isinstance(item.get("failure"), dict) else {}).get("reason_code")
                    or item.get("reason_code"),
                    "quality_label": item.get("quality_label"),
                }
                for item in value[:12]
                if isinstance(item, dict)
            ]
            continue
        if key == "results" and isinstance(value, list):
            out[key] = [_compact_discovery_hit(item) for item in value[:20] if isinstance(item, dict)]
            continue
        if key == "next_commands" and isinstance(value, list):
            out[key] = [str(item) for item in value[:8]]
            continue
        if key == "download_artifacts" and isinstance(value, (list, dict)):
            if isinstance(value, dict):
                out[key] = sorted(str(item) for item in value.keys())[:12]
            else:
                out[key] = [str(item) for item in value[:12]]
            continue
        out[key] = value

    # Pull scores from nested result.quality when top-level summary missing.
    if "quality_summary" not in out:
        result = source.get("result") if isinstance(source.get("result"), dict) else {}
        quality = result.get("quality") if isinstance(result.get("quality"), dict) else {}
        if quality:
            summary = {
                key: quality.get(key)
                for key in _COMPACT_NESTED_KEEP["quality_summary"]
                if quality.get(key) not in (None, "", [], {})
            }
            if summary:
                out["quality_summary"] = summary
    return out


def _compact_discovery_hit(item: dict[str, Any]) -> dict[str, Any]:
    return {
        key: item.get(key)
        for key in ("doi", "title", "year", "venue", "url", "oa_url", "source", "cited_by_count")
        if item.get(key) not in (None, "", [], {})
    }


_FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)
_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+?)\s*$", re.MULTILINE)


def summarize_markdown_paper(
    markdown: str,
    *,
    source: str | None = None,
    range_spec: str | None = None,
) -> dict[str, Any]:
    text = str(markdown or "")
    front_matter: dict[str, str] = {}
    body = text
    match = _FRONT_MATTER_RE.match(text)
    if match:
        for line in match.group(1).splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip().strip("\"'")
            if key:
                front_matter[key] = value
        body = text[match.end() :]

    sections: list[dict[str, Any]] = []
    for heading in _HEADING_RE.finditer(body):
        level = len(heading.group(1))
        title = heading.group(2).strip()
        # Approximate line number in full document.
        line_no = text.count("\n", 0, heading.start() + (match.end() if match else 0)) + 1
        sections.append({"level": level, "title": title, "line": line_no})

    lines = text.splitlines()
    start, end = _parse_range(range_spec, len(lines))
    excerpt_lines = lines[start - 1 : end] if lines else []
    title = front_matter.get("title") or next((s["title"] for s in sections if s["level"] == 1), None)

    return {
        "schema": "mdtero.paper_summary.v1",
        "source": source,
        "title": title,
        "front_matter": front_matter or None,
        "line_count": len(lines),
        "sections": sections[:80],
        "range": {"start": start, "end": end} if range_spec else None,
        "excerpt": "\n".join(excerpt_lines) if range_spec else None,
    }


def summarize_markdown_file(path: Path, *, range_spec: str | None = None) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    text = resolved.read_text(encoding="utf-8", errors="replace")
    return summarize_markdown_paper(text, source=str(resolved), range_spec=range_spec)


def _parse_range(range_spec: str | None, line_count: int) -> tuple[int, int]:
    if not range_spec:
        return (1, min(line_count, 1) if line_count else 1)
    cleaned = str(range_spec).strip()
    if ":" in cleaned:
        left, right = cleaned.split(":", 1)
    elif "-" in cleaned:
        left, right = cleaned.split("-", 1)
    else:
        left, right = cleaned, cleaned
    start = max(1, int(left or 1))
    end = max(start, int(right or start))
    if line_count > 0:
        end = min(end, line_count)
        start = min(start, end)
    return start, end
