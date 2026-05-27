from __future__ import annotations

import re
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".forgejo" / "workflows"

FORBIDDEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("push-trigger", re.compile(r"^\s{2}push\s*:", re.MULTILINE)),
    ("pull-request-trigger", re.compile(r"^\s{2}pull_request\s*:", re.MULTILINE)),
    ("schedule-trigger", re.compile(r"^\s{2}schedule\s*:", re.MULTILINE)),
    ("cron-trigger", re.compile(r"^\s{4,}-\s*cron\s*:", re.MULTILINE)),
    ("embedded-pat", re.compile(r"PERSONAL_ACCESS_TOKEN|PAT\s*=")),
    ("admin-credential", re.compile(r"ADMIN_(?:PASSWORD|TOKEN|SECRET)|ROOT_PASSWORD|admin_(?:password|token|secret)")),
    ("secret-assignment", re.compile(r"(?:INFISICAL_TOKEN|MDTERO_API_KEY|VERCEL_TOKEN)\s*=")),
)

GITHUB_ROLLBACK_FORBIDDEN_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("push-trigger", re.compile(r"^\s{2}push\s*:", re.MULTILINE)),
    ("pull-request-trigger", re.compile(r"^\s{2}pull_request\s*:", re.MULTILINE)),
    ("schedule-trigger", re.compile(r"^\s{2}schedule\s*:", re.MULTILINE)),
    ("cron-trigger", re.compile(r"^\s{4,}-\s*cron\s*:", re.MULTILINE)),
    ("embedded-pat", re.compile(r"PERSONAL_ACCESS_TOKEN|PAT\s*=")),
    ("admin-credential", re.compile(r"ADMIN_(?:PASSWORD|TOKEN|SECRET)|ROOT_PASSWORD|admin_(?:password|token|secret)")),
)


def workflow_dispatch_only(text: str) -> bool:
    in_on_block = False
    events: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if line == "on:" or line.startswith("on:"):
            in_on_block = True
            inline_value = line.removeprefix("on:").strip()
            if inline_value:
                events.append(inline_value.rstrip(":"))
            continue
        if in_on_block and not line.startswith(" "):
            break
        if in_on_block and line.startswith("  ") and not line.startswith("    "):
            events.append(stripped.rstrip(":"))
    return events == ["workflow_dispatch"]


def workflow_files(workflow_dir: Path = WORKFLOW_DIR) -> list[Path]:
    if not workflow_dir.is_dir():
        return []
    return sorted([*workflow_dir.glob("*.yml"), *workflow_dir.glob("*.yaml")])


def check_workflow(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    failures: list[str] = []
    if "workflow_dispatch:" not in text:
        failures.append("missing workflow_dispatch")
    if not workflow_dispatch_only(text):
        failures.append("not workflow_dispatch-only")
    if "runs-on: linux-small" not in text:
        failures.append("missing linux-small runner")
    if "List required secret names" not in text:
        failures.append("missing secret-name listing step")
    if "Forgejo secrets used by this workflow" not in text:
        failures.append("missing Forgejo secret-name summary")
    for rule_name, pattern in FORBIDDEN_PATTERNS:
        if pattern.search(text):
            failures.append(rule_name)
    return failures


def check_github_rollback_workflow(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    failures: list[str] = []
    if "workflow_dispatch:" not in text:
        failures.append("missing workflow_dispatch")
    if not workflow_dispatch_only(text):
        failures.append("not workflow_dispatch-only")
    for rule_name, pattern in GITHUB_ROLLBACK_FORBIDDEN_PATTERNS:
        if pattern.search(text):
            failures.append(rule_name)
    return failures


def check_all(repo_root: Path = REPO_ROOT) -> dict[str, list[str]]:
    failures: dict[str, list[str]] = {}
    for path in workflow_files(repo_root / ".forgejo" / "workflows"):
        issues = check_workflow(path)
        if issues:
            failures[str(path.relative_to(repo_root))] = issues
    for path in workflow_files(repo_root / ".github" / "workflows"):
        issues = check_github_rollback_workflow(path)
        if issues:
            failures[str(path.relative_to(repo_root))] = issues
    return failures


def main() -> int:
    failures = check_all()
    if not failures:
        print("Forgejo workflow policy passed: Forgejo workflows are manual linux-small secret-listing checks, and GitHub workflows remain manual rollback-only.")
        return 0
    print("Forgejo workflow policy failed:", file=sys.stderr)
    for path, issues in failures.items():
        print(f"- {path}: {', '.join(issues)}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
