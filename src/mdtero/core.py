from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


ArtifactKind = Literal["markdown", "zip", "pdf", "epub", "html", "xml", "json", "unknown"]
WorkflowStatus = Literal["pending", "running", "succeeded", "failed", "skipped"]


@dataclass
class ArtifactRef:
    key: str
    filename: str | None = None
    media_type: str | None = None
    path: str | None = None
    download_url: str | None = None
    kind: ArtifactKind = "unknown"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ProviderResult:
    provider: str | None = None
    strategy: str | None = None
    reason_code: str | None = None
    action_hint: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PaperChunk:
    chunk_id: str
    text: str
    paper_id: str | None = None
    section: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class PaperDocument:
    input: str
    title: str | None = None
    doi: str | None = None
    year: int | None = None
    authors: list[str] = field(default_factory=list)
    task_id: str | None = None
    status: str = "pending"
    provider: ProviderResult = field(default_factory=ProviderResult)
    artifacts: list[ArtifactRef] = field(default_factory=list)
    chunks: list[PaperChunk] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class WorkflowStep:
    name: str
    status: WorkflowStatus = "pending"
    reason_code: str | None = None
    action_hint: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def artifacts_from_task_result(task_id: str, result: dict[str, Any] | None) -> list[ArtifactRef]:
    if not isinstance(result, dict):
        return []
    raw_artifacts = result.get("artifacts")
    if not isinstance(raw_artifacts, dict):
        return []
    artifacts: list[ArtifactRef] = []
    for key, descriptor in raw_artifacts.items():
        if not isinstance(descriptor, dict):
            continue
        filename = _optional_str(descriptor.get("filename"))
        artifacts.append(
            ArtifactRef(
                key=str(key),
                filename=filename,
                media_type=_optional_str(descriptor.get("media_type")),
                path=_optional_str(descriptor.get("path")),
                download_url=f"/api/v1/tasks/{task_id}/download/{key}",
                kind=infer_artifact_kind(key=str(key), filename=filename, media_type=_optional_str(descriptor.get("media_type"))),
            )
        )
    return artifacts


def provider_from_task_result(result: dict[str, Any] | None) -> ProviderResult:
    if not isinstance(result, dict):
        return ProviderResult()
    quality = result.get("quality") if isinstance(result.get("quality"), dict) else {}
    return ProviderResult(
        provider=_optional_str(result.get("selected_provider") or quality.get("selected_pdf_provider") or quality.get("provider")),
        strategy=_optional_str(result.get("parser_strategy") or quality.get("parser_strategy")),
        reason_code=_optional_str(result.get("reason_code") or quality.get("reason_code") or quality.get("provider_failure_reason")),
        action_hint=_optional_str(result.get("action_hint")),
        diagnostics={key: value for key, value in quality.items() if key in {"trace_id", "batch_id", "provider_state", "external_upload_used"}},
    )


def paper_from_task(input_value: str, task: dict[str, Any]) -> PaperDocument:
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    return PaperDocument(
        input=input_value,
        task_id=_optional_str(task.get("task_id")),
        status=str(task.get("status") or "pending"),
        provider=provider_from_task_result(result),
        artifacts=artifacts_from_task_result(str(task.get("task_id") or ""), result),
    )


def infer_artifact_kind(*, key: str, filename: str | None = None, media_type: str | None = None) -> ArtifactKind:
    value = " ".join(part for part in [key, filename or "", media_type or ""] if part).lower()
    if "markdown" in value or value.endswith(".md") or "_md" in key:
        return "markdown"
    if "zip" in value or value.endswith(".zip") or "bundle" in key:
        return "zip"
    if "pdf" in value or value.endswith(".pdf"):
        return "pdf"
    if "epub" in value or value.endswith(".epub"):
        return "epub"
    if "html" in value or value.endswith(".html"):
        return "html"
    if "xml" in value or value.endswith(".xml"):
        return "xml"
    if "json" in value or value.endswith(".json"):
        return "json"
    return "unknown"


def _optional_str(value: object) -> str | None:
    cleaned = str(value or "").strip()
    return cleaned or None

