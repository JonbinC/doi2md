from pathlib import Path

from mdtero.cloud_sync import pull_project_documents
from mdtero.projects import init_project, load_project


def test_pull_writes_markdown_once_and_skips_matching_checksum(tmp_path: Path):
    init_project(tmp_path, name="local")
    manifest = {
        "project_id": 9,
        "cloud_library": {"enabled": True, "storage": "cloudflare_r2"},
        "items": [{
            "document_id": 3,
            "title": "Saved paper",
            "doi": "10.1000/demo",
            "cloud_archive": {"status": "saved", "checksum": "abc"},
        }],
    }
    calls = {"count": 0}

    def read_text(_document_id: int) -> str:
        calls["count"] += 1
        return "# Saved paper\n\nBody\n"

    first = pull_project_documents(tmp_path, manifest=manifest, read_text=read_text)
    assert first["items"][0]["status"] == "pulled"
    assert Path(first["items"][0]["path"]).read_text(encoding="utf-8").startswith("# Saved paper")
    state = load_project(tmp_path)
    assert state.papers[0].doi == "10.1000/demo"
    assert state.papers[0].source == "cloud_sync"

    second = pull_project_documents(tmp_path, manifest=manifest, read_text=read_text)
    assert second["items"][0]["status"] == "unchanged"
    assert calls["count"] == 1
