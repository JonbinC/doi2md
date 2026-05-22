from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass
from importlib import resources
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class AgentTarget:
    name: str
    label: str
    skill_directory: str


@dataclass(frozen=True)
class AgentInstallResult:
    target: str
    label: str
    path: str
    action: str
    detected: bool


@dataclass(frozen=True)
class AgentDetectionResult:
    target: str
    label: str
    workspace_path: str
    skill_path: str
    detected: bool
    installed: bool
    install_command: str
    selection_index: int


TARGETS: dict[str, AgentTarget] = {
    "codex": AgentTarget("codex", "Codex", ".codex/skills/mdtero"),
    "claude_code": AgentTarget("claude_code", "Claude Code", ".claude/skills/mdtero"),
    "gemini_cli": AgentTarget("gemini_cli", "Gemini CLI", ".gemini/skills/mdtero"),
    "hermes": AgentTarget("hermes", "Hermes Agent", ".hermes/skills/mdtero"),
    "opencode": AgentTarget("opencode", "OpenCode", ".opencode/skills/mdtero"),
}


def target_names() -> list[str]:
    return list(TARGETS)


def detect_targets(root: Path | None = None) -> list[AgentTarget]:
    base = _root(root)
    detected = []
    for target in TARGETS.values():
        marker = base / target.skill_directory.split("/", 1)[0]
        if marker.exists():
            detected.append(target)
    return detected


def detect_target_status(root: Path | None = None) -> list[AgentDetectionResult]:
    base = _root(root)
    results = []
    for index, target in enumerate(TARGETS.values(), start=1):
        workspace_path = base / target.skill_directory.split("/", 1)[0]
        skill_path = _safe_skill_path(target, root)
        results.append(
            AgentDetectionResult(
                target=target.name,
                label=target.label,
                workspace_path=str(workspace_path),
                skill_path=str(skill_path),
                detected=workspace_path.exists(),
                installed=(skill_path / "SKILL.md").exists(),
                install_command=f"mdtero agent install --target {target.name}",
                selection_index=index,
            )
        )
    return results


def default_interactive_targets(detections: list[AgentDetectionResult]) -> list[str]:
    pending = [item.target for item in detections if item.detected and not item.installed]
    if pending:
        return pending
    detected = [item.target for item in detections if item.detected]
    if detected:
        return detected
    return []


def parse_agent_selection(selection: str, detections: list[AgentDetectionResult]) -> list[str]:
    cleaned = str(selection or "").strip().lower()
    if not cleaned:
        return default_interactive_targets(detections)
    if cleaned in {"all", "a", "*"}:
        return [item.target for item in detections]
    by_index = {str(item.selection_index): item.target for item in detections}
    by_target = {item.target: item.target for item in detections}
    by_label = {item.label.lower().replace(" ", "_"): item.target for item in detections}
    selected: list[str] = []
    for token in cleaned.replace(",", " ").split():
        target = by_index.get(token) or by_target.get(token) or by_label.get(token)
        if not target:
            raise ValueError(f"Unknown agent selection `{token}`. Use numbers, target names, all, or Enter for detected pending installs.")
        if target not in selected:
            selected.append(target)
    return selected


def install_targets(
    names: Iterable[str] | None = None,
    *,
    root: Path | None = None,
    install_all: bool = False,
    dry_run: bool = False,
) -> list[AgentInstallResult]:
    selected = _select_targets(names, root=root, install_all=install_all)
    return [_install_one(target, root=root, dry_run=dry_run) for target in selected]


def uninstall_targets(
    names: Iterable[str],
    *,
    root: Path | None = None,
    dry_run: bool = False,
) -> list[AgentInstallResult]:
    results = []
    for target in _targets_from_names(names):
        path = _safe_skill_path(target, root)
        detected = path.exists()
        if detected and not dry_run:
            shutil.rmtree(path)
        results.append(
            AgentInstallResult(
                target=target.name,
                label=target.label,
                path=str(path),
                action="removed" if detected else "missing",
                detected=detected,
            )
        )
    return results


def results_to_json(results: list[AgentInstallResult]) -> str:
    return json.dumps([asdict(result) for result in results], indent=2, ensure_ascii=False)


def detections_to_json(results: list[AgentDetectionResult]) -> str:
    return json.dumps([asdict(result) for result in results], indent=2, ensure_ascii=False)


def _select_targets(names: Iterable[str] | None, *, root: Path | None, install_all: bool) -> list[AgentTarget]:
    explicit_names = [name for name in (names or []) if name]
    if install_all:
        return list(TARGETS.values())
    if explicit_names:
        return _targets_from_names(explicit_names)
    detected = detect_targets(root)
    if detected:
        return detected
    raise ValueError("No agent workspace detected. Pass --target codex, --target claude_code, --target gemini_cli, --target hermes, or --target opencode.")


def _targets_from_names(names: Iterable[str]) -> list[AgentTarget]:
    targets = []
    for name in names:
        if name not in TARGETS:
            supported = ", ".join(TARGETS)
            raise ValueError(f"Unsupported agent target '{name}'. Supported targets: {supported}.")
        targets.append(TARGETS[name])
    return targets


def _install_one(target: AgentTarget, *, root: Path | None, dry_run: bool) -> AgentInstallResult:
    path = _safe_skill_path(target, root)
    detected = path.parent.parent.exists()
    if not dry_run:
        path.mkdir(parents=True, exist_ok=True)
        (path / "SKILL.md").write_text(_skill_template(), encoding="utf-8")
    return AgentInstallResult(
        target=target.name,
        label=target.label,
        path=str(path),
        action="would_install" if dry_run else "installed",
        detected=detected,
    )


def _skill_template() -> str:
    return resources.files("mdtero.skills.mdtero").joinpath("SKILL.md").read_text(encoding="utf-8")


def _safe_skill_path(target: AgentTarget, root: Path | None) -> Path:
    base = _root(root)
    relative = Path(target.skill_directory)
    if relative.is_absolute():
        raise ValueError(f"Refusing absolute skill directory for {target.name}.")
    path = (base / relative).resolve()
    if path == base or base not in path.parents:
        raise ValueError(f"Refusing unsafe skill directory outside install root for {target.name}.")
    return path


def _root(root: Path | None) -> Path:
    return (root or Path.home()).expanduser().resolve()
