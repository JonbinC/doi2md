"""Release event resolution and registry guards; all HTTP responses are synthetic."""
from __future__ import annotations

import importlib.util
from io import BytesIO
import json
from pathlib import Path
from urllib.error import HTTPError, URLError

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/ci/release_policy.py"
spec = importlib.util.spec_from_file_location("release_policy", SCRIPT)
policy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(policy)
COMMIT = "a" * 40
OTHER_COMMIT = "b" * 40


@pytest.fixture
def source(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "0.3.4"\n')
    relay = tmp_path / "relay/cmd/mdtero-relay/main.go"
    relay.parent.mkdir(parents=True)
    relay.write_text('package main\nvar version = "0.1.9"\n')
    return tmp_path


@pytest.mark.parametrize("workflow,event,ref,kind,version,expected", [
    ("assets", "push", "refs/heads/main", "", "", "cli/v0.3.4"),
    ("pypi", "push", "refs/heads/main", "", "", "cli/v0.3.4"),
    ("relay", "push", "refs/heads/main", "", "", "relay/v0.1.9"),
    ("assets", "push", "refs/tags/cli/v0.3.4", "", "", "cli/v0.3.4"),
    ("pypi", "push", "refs/tags/cli/v0.3.4", "", "", "cli/v0.3.4"),
    ("assets", "push", "refs/tags/extension/v0.1.11", "", "", "extension/v0.1.11"),
    ("assets", "workflow_dispatch", "refs/heads/main", "cli", "0.3.4", "cli/v0.3.4"),
    ("assets", "workflow_dispatch", "refs/heads/main", "extension", "0.1.12", "extension/v0.1.12"),
    ("pypi", "workflow_dispatch", "refs/heads/main", "", "", "cli/v0.3.4"),
    ("pypi", "workflow_dispatch", "refs/heads/main", "", "0.3.4", "cli/v0.3.4"),
    # Preserve explicit Relay tag/manual versions; Go ldflags embed these.
    ("relay", "workflow_dispatch", "refs/heads/main", "", "0.2.0", "relay/v0.2.0"),
    ("relay", "push", "refs/tags/relay/v0.2.1", "", "", "relay/v0.2.1"),
])
def test_supported_release_events(source, workflow, event, ref, kind, version, expected):
    result = policy.resolve_release(workflow, event, ref, source, kind, version)
    assert result["tag"] == expected
    assert result["tag"] == result["kind"] + "/v" + result["version"]


@pytest.mark.parametrize("workflow,event,ref,kind,version", [
    ("assets", "push", "refs/heads/feature", "", ""),
    ("assets", "pull_request", "refs/heads/main", "", ""),
    ("pypi", "push", "refs/tags/relay/v0.1.9", "", ""),
    ("relay", "push", "refs/tags/cli/v0.3.4", "", ""),
    ("assets", "workflow_dispatch", "refs/heads/main", "other", "0.3.4"),
    ("assets", "workflow_dispatch", "refs/heads/main", "cli", "0.3.3"),
    ("pypi", "workflow_dispatch", "refs/heads/main", "", "0.3.3"),
    ("pypi", "push", "refs/tags/cli/v0.3.3", "", ""),
    ("relay", "workflow_dispatch", "refs/heads/main", "", "0.1.9\npublish=true"),
    ("assets", "workflow_dispatch", "refs/heads/main", "cli", "../../other"),
])
def test_ambiguous_or_mismatched_events_fail(source, workflow, event, ref, kind, version):
    with pytest.raises(policy.ReleaseError):
        policy.resolve_release(workflow, event, ref, source, kind, version)


def test_main_push_uses_this_checkout_not_dispatch_inputs(source):
    (source / "pyproject.toml").write_text('[project]\nversion = "0.3.5"\n')
    result = policy.resolve_release("pypi", "push", "refs/heads/main", source, "", "0.3.4")
    assert result["version"] == "0.3.5"


def test_existing_cli_prerelease_syntax_remains_supported(source):
    (source / "pyproject.toml").write_text('[project]\nversion = "0.2.0a11"\n')
    assert policy.resolve_release("pypi", "push", "refs/tags/cli/v0.2.0a11", source)["version"] == "0.2.0a11"


@pytest.mark.parametrize("kind,bad_version", [("cli", "0.3"), ("relay", "0.1.9/other")])
def test_invalid_source_versions_fail_before_release(source, kind, bad_version):
    if kind == "cli":
        (source / "pyproject.toml").write_text(f'[project]\nversion = "{bad_version}"\n')
    else:
        (source / "relay/cmd/mdtero-relay/main.go").write_text(f'var version = "{bad_version}"\n')
    with pytest.raises(policy.ReleaseError):
        policy.resolve_release("pypi" if kind == "cli" else "relay", "push", "refs/heads/main", source)


def github_check(fetch, *, event="push", ref="refs/heads/main"):
    return policy.github_publish_needed("cli", "0.3.4", repository="JonbinC/doi2md", event=event,
                                        ref=ref, commit_sha=COMMIT, token="synthetic-test-token", fetch=fetch)


@pytest.mark.parametrize("event", ["push", "workflow_dispatch"])
def test_existing_tag_is_logged_noop_for_branch_and_manual(event, capsys):
    calls = []
    def fetch(url, **kwargs):
        calls.append(url)
        return {"object": {"type": "commit", "sha": OTHER_COMMIT}}
    assert github_check(fetch, event=event) is False
    assert len(calls) == 1 and "/git/ref/tags/cli/v0.3.4" in calls[0]
    assert "skipping" in capsys.readouterr().out


def test_new_main_tag_can_publish_but_final_recheck_detects_a_winner():
    assert github_check(lambda *args, **kwargs: None) is True
    assert github_check(lambda *args, **kwargs: {"object": {"type": "commit", "sha": COMMIT}}) is False


@pytest.mark.parametrize("release_exists,expected", [(False, True), (True, False)])
def test_tag_event_publishes_only_first_release_for_its_own_commit(release_exists, expected):
    calls = []
    def fetch(url, **kwargs):
        calls.append(url)
        if "/git/ref/" in url:
            return {"object": {"type": "commit", "sha": COMMIT}}
        return {"id": 123} if release_exists else None
    assert github_check(fetch, ref="refs/tags/cli/v0.3.4") is expected
    assert len(calls) == 2 and "/releases/tags/cli/v0.3.4" in calls[1]


def test_annotated_tag_resolves_to_the_checked_out_commit():
    def fetch(url, **kwargs):
        if "/git/ref/" in url:
            return {"object": {"type": "tag", "sha": OTHER_COMMIT}}
        if "/git/tags/" in url:
            return {"object": {"type": "commit", "sha": COMMIT}}
        return None
    assert github_check(fetch, ref="refs/tags/cli/v0.3.4") is True


@pytest.mark.parametrize("tag_payload", [None, {"object": {"type": "commit", "sha": OTHER_COMMIT}}])
def test_deleted_or_moved_event_tag_is_not_recreated_or_published(tag_payload):
    with pytest.raises(policy.ReleaseError):
        github_check(lambda *args, **kwargs: tag_payload, ref="refs/tags/cli/v0.3.4")


@pytest.mark.parametrize("payload,expected", [(None, True), ({"info": {"version": "0.3.4"}}, False)])
def test_pypi_decision_uses_only_official_version_endpoint(payload, expected):
    calls = []
    def fetch(url, **kwargs):
        calls.append((url, kwargs))
        return payload
    assert policy.pypi_publish_needed("0.3.4", fetch=fetch) is expected
    assert calls == [("https://pypi.org/pypi/mdtero/0.3.4/json", {})]


def test_pypi_still_publishes_after_other_workflow_creates_github_tag():
    assert github_check(lambda *args, **kwargs: {"object": {"type": "commit", "sha": COMMIT}}) is False
    assert policy.pypi_publish_needed("0.3.4", fetch=lambda *args, **kwargs: None) is True


def test_pypi_wrong_version_metadata_fails_closed():
    with pytest.raises(policy.ReleaseError):
        policy.pypi_publish_needed("0.3.4", fetch=lambda *args, **kwargs: {"info": {"version": "0.3.3"}})


@pytest.mark.parametrize("status", [401, 403, 429, 500, 503])
def test_registry_errors_are_failures_not_missing_versions(monkeypatch, status):
    def failing(*args, **kwargs):
        raise HTTPError("https://pypi.org/pypi/mdtero/0.3.4/json", status, "synthetic", {}, None)
    monkeypatch.setattr(policy, "urlopen", failing)
    with pytest.raises(policy.ReleaseError, match=str(status)):
        policy.get_json("https://pypi.org/pypi/mdtero/0.3.4/json")


def test_only_http404_is_a_missing_registry_version(monkeypatch):
    def missing(*args, **kwargs):
        raise HTTPError("https://pypi.org/pypi/mdtero/0.3.4/json", 404, "missing", {}, None)
    monkeypatch.setattr(policy, "urlopen", missing)
    assert policy.get_json("https://pypi.org/pypi/mdtero/0.3.4/json") is None


@pytest.mark.parametrize("body", [b"not JSON", b"[]"])
def test_invalid_http200_body_fails_closed(monkeypatch, body):
    response = BytesIO(body)
    response.status = 200
    monkeypatch.setattr(policy, "urlopen", lambda *args, **kwargs: response)
    with pytest.raises(policy.ReleaseError):
        policy.get_json("https://pypi.org/pypi/mdtero/0.3.4/json")


def test_network_failure_cannot_create_a_release(monkeypatch):
    def failed(*args, **kwargs):
        raise URLError("synthetic unavailable")
    monkeypatch.setattr(policy, "urlopen", failed)
    with pytest.raises(policy.ReleaseError):
        policy.get_json("https://api.github.com/repos/JonbinC/doi2md/git/ref/tags/cli/v0.3.4")


def test_github_credential_is_never_sent_to_pypi():
    with pytest.raises(policy.ReleaseError, match="only be sent"):
        policy.get_json("https://pypi.org/pypi/mdtero/0.3.4/json", token="synthetic-test-token")


def test_http200_json_is_read_with_a_bounded_timeout(monkeypatch):
    response = BytesIO(json.dumps({"info": {"version": "0.3.4"}}).encode())
    response.status = 200
    def opened(request, timeout):
        assert request.full_url == "https://pypi.org/pypi/mdtero/0.3.4/json"
        assert request.get_header("Authorization") is None and timeout == 20
        return response
    monkeypatch.setattr(policy, "urlopen", opened)
    assert policy.get_json("https://pypi.org/pypi/mdtero/0.3.4/json")["info"]["version"] == "0.3.4"
