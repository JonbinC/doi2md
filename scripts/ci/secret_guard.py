from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]

FORBIDDEN_TRACKED_PATHS = {
    ".env",
    ".env.yaml",
    "env.yaml",
    "secrets/.env",
    "secrets/.env.yaml",
}

SKIPPED_PREFIXES = (
    "dist/",
    "extension/dist/",
    "extension/node_modules/",
    "tests_py/",
    "extension/tests/",
)

SKIPPED_SUFFIXES = (
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".webp",
    ".pdf",
    ".zip",
    ".gz",
    ".pyc",
    ".whl",
    ".tar.gz",
    ".map",
)


@dataclass(frozen=True)
class Finding:
    path: str
    rule: str


FORBIDDEN_TEXT_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("aws-signature", re.compile(r"\bX-Amz-Signature=")),
    ("aliyun-oss-access-key", re.compile(r"\bOSSAccessKeyId=")),
    ("aliyun-oss-signature", re.compile(r"[?&]Signature=")),
    ("aliyun-oss-v2-signature", re.compile(r"\bX-OSS-Signature=")),
    ("oss-security-token", re.compile(r"\bsecurity-token=")),
    ("mdtero-live-secret", re.compile(r"\b(?:mdtero_secret|mdt_live)_[A-Za-z0-9_-]{12,}\b")),
)


def _tracked_files(repo_root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_root,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _should_scan_text(path: str) -> bool:
    if path.startswith(SKIPPED_PREFIXES):
        return False
    return not path.lower().endswith(SKIPPED_SUFFIXES)


def scan_tracked_files(repo_root: Path = REPO_ROOT, tracked_files: list[str] | None = None) -> list[Finding]:
    tracked = tracked_files if tracked_files is not None else _tracked_files(repo_root)
    findings: list[Finding] = []
    for rel_path in tracked:
        normalized = rel_path.replace("\\", "/")
        if normalized in FORBIDDEN_TRACKED_PATHS:
            findings.append(Finding(normalized, "tracked-secret-env-file"))
            continue
        if not _should_scan_text(normalized):
            continue
        path = repo_root / normalized
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for rule_name, pattern in FORBIDDEN_TEXT_RULES:
            if pattern.search(text):
                findings.append(Finding(normalized, rule_name))
    return findings


def main() -> int:
    findings = scan_tracked_files()
    if not findings:
        print("Secret guard passed: no tracked env files, private keys, signed URLs, or Mdtero live secrets found.")
        return 0
    print("Secret guard failed. Remove tracked secrets or signed temporary URLs:", file=sys.stderr)
    for finding in findings:
        print(f"- {finding.path}: {finding.rule}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
