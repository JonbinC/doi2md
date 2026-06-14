from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .core import ArtifactRef, PaperDocument, ProviderResult


PROJECT_DIR_NAME = ".mdtero"
PROJECT_FILE_NAME = "project.json"
BIB_DOI_FIELD_PATTERN = re.compile(r'\bdoi\s*=\s*[{"]?\s*(10\.\d{4,9}/[^\s}",]+)', re.I)
BIB_URL_FIELD_PATTERN = re.compile(r'\burl\s*=\s*[{"]?\s*(https?://[^\s}",]+)', re.I)


@dataclass
class PaperRecord:
    input: str
    task_id: str | None = None
    status: str = "pending"
    reason_code: str | None = None
    action_hint: str | None = None
    title: str | None = None
    doi: str | None = None
    source: str | None = None
    artifact: str | None = None
    provider: str | None = None
    parser_strategy: str | None = None
    translation_attempts: list[dict[str, Any]] = field(default_factory=list)
    zotero_key: str | None = None
    zotero_synced_task_id: str | None = None


@dataclass
class ProjectState:
    name: str
    server_project_id: str | None = None
    papers: list[PaperRecord] = field(default_factory=list)


def project_path(root: Path) -> Path:
    return root / PROJECT_DIR_NAME / PROJECT_FILE_NAME


def init_project(root: Path, *, name: str | None = None) -> Path:
    target = project_path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        state = ProjectState(name=name or root.resolve().name)
        target.write_text(json.dumps(asdict(state), indent=2) + "\n", encoding="utf-8")
    return target


def save_project(root: Path, state: ProjectState) -> Path:
    target = project_path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(asdict(state), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def load_project(root: Path) -> ProjectState:
    payload = json.loads(project_path(root).read_text(encoding="utf-8"))
    return ProjectState(
        name=str(payload.get("name") or root.resolve().name),
        server_project_id=str(payload.get("server_project_id") or "").strip() or None,
        papers=[_paper_record_from_payload(paper) for paper in payload.get("papers") or [] if isinstance(paper, dict)],
    )


def bind_server_project(root: Path, server_project_id: str) -> ProjectState:
    state = ensure_project(root)
    cleaned = str(server_project_id or "").strip()
    if not cleaned:
        raise ValueError("server_project_id is required")
    state.server_project_id = cleaned
    save_project(root, state)
    return state


def ensure_project(root: Path) -> ProjectState:
    init_project(root)
    return load_project(root)


def add_paper(root: Path, paper: PaperRecord) -> ProjectState:
    state = ensure_project(root)
    state.papers = [existing for existing in state.papers if existing.input != paper.input]
    state.papers.append(paper)
    save_project(root, state)
    return state


def remove_paper(root: Path, input_or_task_id: str) -> ProjectState:
    state = ensure_project(root)
    needle = input_or_task_id.strip()
    state.papers = [paper for paper in state.papers if paper.input != needle and paper.task_id != needle]
    save_project(root, state)
    return state


def update_paper_submission(root: Path, input_value: str, result: dict) -> ProjectState:
    state = ensure_project(root)
    for paper in state.papers:
        if paper.input == input_value:
            paper.task_id = str(result.get("task_id") or paper.task_id or "")
            paper.status = str(result.get("status") or paper.status or "queued")
            paper.reason_code = _reason_code(result) or paper.reason_code
            paper.action_hint = _action_hint(result) or paper.action_hint
            paper.artifact = _preferred_artifact(result) or paper.artifact
            paper.provider = _selected_provider(result) or paper.provider
            paper.parser_strategy = _parser_strategy(result) or paper.parser_strategy
            paper.translation_attempts = _translation_attempts(result) or paper.translation_attempts
            break
    save_project(root, state)
    return state


def paper_from_submission(input_value: str, result: dict, *, source: str | None = None, title: str | None = None, doi: str | None = None) -> PaperRecord:
    return PaperRecord(
        input=input_value,
        task_id=str(result.get("task_id") or "") or None,
        status=str(result.get("status") or "queued"),
        reason_code=_reason_code(result),
        action_hint=_action_hint(result),
        title=title,
        doi=doi,
        source=source,
        artifact=_preferred_artifact(result),
        provider=_selected_provider(result),
        parser_strategy=_parser_strategy(result),
        translation_attempts=_translation_attempts(result),
    )


def project_pending_papers(state: ProjectState, *, include_failed: bool = False) -> list[PaperRecord]:
    selected = [paper for paper in state.papers if not paper.task_id and paper.status in {"pending", "created"}]
    if include_failed:
        selected.extend(paper for paper in state.papers if paper.status == "failed")
    return selected


def project_task_ids(state: ProjectState) -> list[str]:
    return [paper.task_id for paper in state.papers if paper.task_id]


def project_rag_local_coverage(state: ProjectState) -> dict[str, Any]:
    ready: list[dict[str, Any]] = []
    blocked: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []

    for paper in state.papers:
        item = _paper_rag_coverage_item(paper)
        if item["ready_for_ingest"]:
            ready.append(item)
        elif paper.status == "failed":
            failed.append(item)
            blocked.append(item)
        elif paper.status in {"pending", "created", "queued", "running"} or not paper.task_id:
            pending.append(item)
            blocked.append(item)
        else:
            blocked.append(item)

    return {
        "paper_count": len(state.papers),
        "ready_for_ingest_count": len(ready),
        "blocked_count": len(blocked),
        "pending_count": len(pending),
        "failed_count": len(failed),
        "ready": ready,
        "blocked": blocked,
    }


def import_bib(root: Path, paths: list[Path]) -> dict:
    imported = 0
    skipped = 0
    seen: set[str] = set()
    state = ensure_project(root)
    existing = {paper.input for paper in state.papers}
    for path in paths:
        text = path.read_text(encoding="utf-8")
        for target in extract_bib_targets(text):
            value = target["value"]
            if value in seen or value in existing:
                skipped += 1
                continue
            seen.add(value)
            state.papers.append(
                PaperRecord(
                    input=value,
                    doi=value if target["kind"] == "doi" else None,
                    source=f"bib:{path.name}",
                )
            )
            imported += 1
    save_project(root, state)
    return {"imported_count": imported, "skipped_count": skipped, "paper_count": len(state.papers)}


def extract_bib_targets(text: str) -> list[dict[str, str]]:
    targets: list[dict[str, str]] = []
    for match in BIB_DOI_FIELD_PATTERN.finditer(text):
        targets.append({"kind": "doi", "value": _clean_bib_value(match.group(1))})
    for match in BIB_URL_FIELD_PATTERN.finditer(text):
        url = _clean_bib_value(match.group(1))
        if "doi.org/10." in url.lower():
            doi = url.split("doi.org/", 1)[1]
            targets.append({"kind": "doi", "value": _clean_bib_value(doi)})
        else:
            targets.append({"kind": "url", "value": url})
    unique: list[dict[str, str]] = []
    seen: set[str] = set()
    for target in targets:
        value = target["value"]
        if value and value not in seen:
            unique.append(target)
            seen.add(value)
    return unique


def update_task(root: Path, task: dict) -> ProjectState:
    state = ensure_project(root)
    task_id = str(task.get("task_id") or "")
    for paper in state.papers:
        if paper.task_id == task_id:
            paper.status = str(task.get("status") or paper.status)
            paper.reason_code = _reason_code(task) or paper.reason_code
            paper.action_hint = _action_hint(task) or paper.action_hint
            paper.artifact = _preferred_artifact(task) or paper.artifact
            paper.provider = _selected_provider(task) or paper.provider
            paper.parser_strategy = _parser_strategy(task) or paper.parser_strategy
            paper.translation_attempts = _translation_attempts(task) or paper.translation_attempts
    save_project(root, state)
    return state


def project_documents(root: Path) -> list[PaperDocument]:
    state = ensure_project(root)
    return [paper_to_document(paper) for paper in state.papers]


def paper_to_document(paper: PaperRecord) -> PaperDocument:
    artifacts = []
    if paper.artifact:
        artifacts.append(ArtifactRef(key=paper.artifact, kind="unknown"))
    return PaperDocument(
        input=paper.input,
        title=paper.title,
        doi=paper.doi,
        task_id=paper.task_id,
        status=paper.status,
        provider=ProviderResult(
            provider=paper.provider,
            strategy=paper.parser_strategy,
            reason_code=paper.reason_code,
            action_hint=paper.action_hint,
            diagnostics={"translation_attempts": paper.translation_attempts} if paper.translation_attempts else {},
        ),
        artifacts=artifacts,
    )


def _paper_rag_coverage_item(paper: PaperRecord) -> dict[str, Any]:
    ready = paper.status == "succeeded" and bool(paper.task_id) and bool(paper.artifact)
    if ready:
        reason_code = "ready_for_ingest"
        action_hint = None
    elif paper.status == "succeeded" and paper.task_id and not paper.artifact:
        reason_code = "missing_downloadable_artifact"
        action_hint = "Refresh the task, then download or ingest a Markdown artifact before RAG."
    elif paper.status == "failed":
        reason_code = paper.reason_code or "parse_failed"
        action_hint = paper.action_hint or "Fix the parse failure, then rerun project refresh before RAG."
    elif not paper.task_id:
        reason_code = "not_submitted"
        action_hint = "Submit this project paper with `mdtero project parse --wait --timeout 300 --json`."
    else:
        reason_code = f"task_{paper.status or 'not_ready'}"
        action_hint = paper.action_hint or "Wait for the task to finish or refresh project status before RAG."
    return {
        "input": paper.input,
        "task_id": paper.task_id,
        "status": paper.status,
        "title": paper.title,
        "doi": paper.doi,
        "artifact": paper.artifact,
        "provider": paper.provider,
        "parser_strategy": paper.parser_strategy,
        "source": paper.source,
        "zotero_key": paper.zotero_key,
        "ready_for_ingest": ready,
        "reason_code": reason_code,
        "action_hint": action_hint,
    }


def _paper_record_from_payload(payload: dict[str, Any]) -> PaperRecord:
    allowed = PaperRecord.__dataclass_fields__.keys()
    data = {key: value for key, value in payload.items() if key in allowed}
    attempts = data.get("translation_attempts")
    data["translation_attempts"] = attempts if isinstance(attempts, list) else []
    return PaperRecord(**data)


def _reason_code(task: dict) -> str | None:
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    quality = result.get("quality") if isinstance(result.get("quality"), dict) else {}
    return task.get("reason_code") or result.get("reason_code") or quality.get("reason_code") or task.get("error_code")


def _action_hint(task: dict) -> str | None:
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    quality = result.get("quality") if isinstance(result.get("quality"), dict) else {}
    value = task.get("action_hint") or result.get("action_hint") or quality.get("action_hint")
    return str(value).strip() if value else None


def _translation_attempts(task: dict) -> list[dict[str, Any]]:
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    attempts = task.get("translation_attempts") or result.get("translation_attempts")
    if not isinstance(attempts, list):
        return []
    return [dict(item) for item in attempts if isinstance(item, dict)]


def _preferred_artifact(task: dict) -> str | None:
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    preferred = result.get("preferred_artifact")
    if preferred:
        return str(preferred)
    artifacts = result.get("artifacts") if isinstance(result.get("artifacts"), dict) else {}
    if "paper_md" in artifacts:
        return "paper_md"
    if artifacts:
        return str(next(iter(artifacts)))
    return None


def _selected_provider(task: dict) -> str | None:
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    quality = result.get("quality") if isinstance(result.get("quality"), dict) else {}
    value = result.get("selected_provider") or quality.get("selected_pdf_provider") or quality.get("provider")
    return str(value) if value else None


def _parser_strategy(task: dict) -> str | None:
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    quality = result.get("quality") if isinstance(result.get("quality"), dict) else {}
    value = result.get("parser_strategy") or quality.get("parser_strategy")
    return str(value) if value else None


def _clean_bib_value(value: str) -> str:
    return str(value or "").strip().rstrip("}.,;")
