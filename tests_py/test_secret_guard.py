from __future__ import annotations

import tempfile
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.ci.secret_guard import Finding, scan_tracked_files


def test_rejects_tracked_env_files() -> None:
    findings = scan_tracked_files(Path.cwd(), tracked_files=[".env.yaml"])

    assert Finding(".env.yaml", "tracked-secret-env-file") in findings


def test_rejects_signed_url_tokens_outside_tests() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        path = root / "src" / "mdtero" / "bad.py"
        path.parent.mkdir(parents=True)
        path.write_text(
            'url = "https://mineru.oss-cn-shanghai.aliyuncs.com/a.pdf?OSSAccessKeyId=abc&Signature=def&security-token=tok"\n',
            encoding="utf-8",
        )

        findings = scan_tracked_files(root, tracked_files=["src/mdtero/bad.py"])

    assert Finding("src/mdtero/bad.py", "aliyun-oss-access-key") in findings
    assert Finding("src/mdtero/bad.py", "aliyun-oss-signature") in findings
    assert Finding("src/mdtero/bad.py", "oss-security-token") in findings


def test_rejects_live_mdtero_secret_outside_tests() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        path = root / "README.md"
        path.write_text("mdtero_secret_live_realistic_value_123\n", encoding="utf-8")

        findings = scan_tracked_files(root, tracked_files=["README.md"])

    assert Finding("README.md", "mdtero-live-secret") in findings


def test_skips_redaction_fixtures_in_tests() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        path = root / "tests_py" / "test_redaction.py"
        path.parent.mkdir(parents=True)
        path.write_text(
            'raw = "mdtero_secret_live_fixture https://x?OSSAccessKeyId=abc&Signature=def"\n',
            encoding="utf-8",
        )

        findings = scan_tracked_files(root, tracked_files=["tests_py/test_redaction.py"])

    assert findings == []
