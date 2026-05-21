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
