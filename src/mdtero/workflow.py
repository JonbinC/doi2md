from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from .core import WorkflowStep


WorkflowKind = Literal["parse", "upload", "translate", "rag"]


@dataclass
class WorkflowTrace:
    kind: WorkflowKind
    input: str
    steps: list[WorkflowStep] = field(default_factory=list)

    def add(self, name: str, status: str, **metadata: Any) -> WorkflowStep:
        step = WorkflowStep(
            name=name,
            status=status,  # type: ignore[arg-type]
            reason_code=metadata.pop("reason_code", None),
            action_hint=metadata.pop("action_hint", None),
            metadata=metadata,
        )
        self.steps.append(step)
        return step

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "input": self.input,
            "steps": [step.to_dict() for step in self.steps],
        }


def parse_trace_from_route(input_value: str, route: dict[str, Any], task: dict[str, Any] | None = None) -> WorkflowTrace:
    trace = WorkflowTrace(kind="parse", input=input_value)
    client_acquisition = task.get("client_acquisition") if isinstance(task, dict) and isinstance(task.get("client_acquisition"), dict) else None
    local_actions = {"fetch_remote_html", "fetch_epub_asset", "fetch_structured_xml", "fallback_pdf_parse"}
    action_sequence = {str(action) for action in route.get("action_sequence") or []}
    local_acquisition_planned = bool(route.get("requires_raw_upload") or action_sequence.intersection(local_actions))
    trace.add(
        "route",
        "succeeded",
        route_kind=route.get("route_kind"),
        acquisition_mode=route.get("acquisition_mode"),
        requires_raw_upload=route.get("requires_raw_upload"),
        action_hint=route.get("action_hint"),
    )
    if client_acquisition:
        trace.add(
            "client_acquire_raw",
            "succeeded",
            source=client_acquisition.get("source"),
            artifact_kind=client_acquisition.get("artifact_kind"),
            url=client_acquisition.get("url"),
            status_code=client_acquisition.get("status_code"),
            content_type=client_acquisition.get("content_type"),
        )
        trace.add("upload_raw", "succeeded" if task and task.get("task_id") else "pending", task_id=(task or {}).get("task_id"))
    elif local_acquisition_planned:
        trace.add("client_acquire_raw", "pending", action_hint=route.get("action_hint"))
    else:
        trace.add("server_parse", "succeeded" if task and task.get("task_id") else "pending", task_id=(task or {}).get("task_id"))
    return trace


def upload_trace(file_path: Path, task: dict[str, Any] | None = None) -> WorkflowTrace:
    trace = WorkflowTrace(kind="upload", input=str(file_path))
    trace.add("select_file", "succeeded", filename=file_path.name, suffix=file_path.suffix.lower())
    trace.add("upload_raw", "succeeded" if task and task.get("task_id") else "pending", task_id=(task or {}).get("task_id"))
    trace.add("server_parse", "pending", action_hint="Poll task status until Mdtero returns download_artifacts.")
    return trace


def status_trace(task: dict[str, Any]) -> WorkflowTrace:
    trace = WorkflowTrace(kind="parse", input=str(task.get("input_summary") or task.get("paper_input") or task.get("task_id") or "task"))
    status = str(task.get("status") or "pending")
    trace.add(
        "task_status",
        "succeeded" if status == "succeeded" else "failed" if status == "failed" else "running",
        task_id=task.get("task_id"),
        task_status=status,
        reason_code=task.get("error_code"),
        action_hint="Download artifacts when task status is succeeded.",
    )
    result = task.get("result") if isinstance(task.get("result"), dict) else {}
    artifacts = result.get("download_artifacts") if isinstance(result, dict) else None
    if artifacts:
        trace.add("download_artifacts", "pending", artifacts=artifacts)
    return trace
