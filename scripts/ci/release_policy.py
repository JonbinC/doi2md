"""Resolve reviewed release events and fail closed on ambiguous registry state."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
import tomllib
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class ReleaseError(RuntimeError):
    pass


def validate_version(kind: str, version: str) -> None:
    if kind == "cli":
        pattern = r"\d+\.\d+\.\d+(?:(?:a|b|rc)\d+)?(?:\.post\d+)?(?:\.dev\d+)?"
    elif kind in {"relay", "extension"}:
        pattern = r"\d+\.\d+\.\d+(?:-[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?(?:\+[0-9A-Za-z]+(?:[.-][0-9A-Za-z]+)*)?"
    else:
        raise ReleaseError("Unsupported release kind")
    if not isinstance(version, str) or not re.fullmatch(pattern, version):
        raise ReleaseError(f"Invalid {kind} release version")


def source_version(root: Path, kind: str) -> str:
    if kind == "cli":
        return tomllib.loads((root / "pyproject.toml").read_text())["project"]["version"]
    if kind == "relay":
        source = (root / "relay/cmd/mdtero-relay/main.go").read_text()
        versions = re.findall(r'^var version = "([^"]+)"\s*$', source, re.MULTILINE)
        if len(versions) == 1:
            return versions[0]
    raise ReleaseError("Could not resolve one source release version")


def resolve_release(workflow: str, event: str, ref: str, root: Path,
                    input_kind: str = "", input_version: str = "") -> dict[str, str]:
    allowed = {"assets": {"cli", "extension"}, "pypi": {"cli"}, "relay": {"relay"}}
    if workflow not in allowed:
        raise ReleaseError("Unsupported release workflow")
    if event == "push" and ref == "refs/heads/main":
        kind = "relay" if workflow == "relay" else "cli"
        version = source_version(root, kind)
    elif event == "push" and ref.startswith("refs/tags/"):
        tag = ref.removeprefix("refs/tags/")
        kind, separator, version = tag.partition("/v")
        if not separator:
            raise ReleaseError("Invalid release tag")
    elif event == "workflow_dispatch":
        kind = input_kind if workflow == "assets" else ("relay" if workflow == "relay" else "cli")
        version = input_version
        if workflow == "pypi" and not version:
            version = source_version(root, "cli")
    else:
        raise ReleaseError("Release requires a main push, a release tag, or manual dispatch")
    if kind not in allowed[workflow]:
        raise ReleaseError("Release kind does not match this workflow")
    validate_version(kind, version)
    # Python builds embed the source version. Relay's existing tag/manual
    # flows intentionally use the requested version through Go ldflags.
    if kind == "cli" and version != source_version(root, "cli"):
        raise ReleaseError("CLI release version does not match pyproject.toml")
    return {"kind": kind, "version": version, "tag": f"{kind}/v{version}"}


def get_json(url: str, token: str = "") -> dict | None:
    headers = {"Accept": "application/json", "User-Agent": "doi2md-release-policy"}
    if token:
        if not url.startswith("https://api.github.com/"):
            raise ReleaseError("GitHub token must only be sent to the GitHub API")
        headers["Authorization"] = f"Bearer {token}"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    try:
        with urlopen(Request(url, headers=headers), timeout=20) as response:
            if response.status != 200:
                raise ReleaseError(f"Registry returned HTTP {response.status}")
            payload = json.load(response)
    except HTTPError as exc:
        if exc.code == 404:
            return None
        raise ReleaseError(f"Registry lookup failed with HTTP {exc.code}") from exc
    except (URLError, TimeoutError, ValueError) as exc:
        raise ReleaseError("Registry lookup failed; refusing to guess release state") from exc
    if not isinstance(payload, dict):
        raise ReleaseError("Registry returned an invalid response")
    return payload


def github_publish_needed(kind: str, version: str, *, repository: str, event: str,
                          ref: str, commit_sha: str, token: str, fetch=get_json) -> bool:
    validate_version(kind, version)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ReleaseError("Invalid GitHub repository")
    tag = f"{kind}/v{version}"
    api = f"https://api.github.com/repos/{repository}"
    existing = fetch(f"{api}/git/ref/tags/{quote(tag, safe='/')}", token=token)
    tag_event = event == "push" and ref == "refs/tags/" + tag
    if existing is None:
        if tag_event:
            raise ReleaseError("The triggering release tag no longer exists")
        print(f"GitHub tag {tag} is new; publication may proceed")
        return True
    if not tag_event:
        print(f"GitHub tag {tag} already exists; skipping without modifying it")
        return False
    # A new tag event must be allowed to create its first release. Resolve
    # annotated tags too, but never attach artifacts built from another commit.
    target = existing.get("object") or {}
    for _ in range(8):
        if target.get("type") == "commit":
            break
        if target.get("type") != "tag" or not re.fullmatch(r"[0-9a-f]{40}", str(target.get("sha", ""))):
            raise ReleaseError("Release tag does not resolve to a commit")
        annotated = fetch(f"{api}/git/tags/{target['sha']}", token=token)
        if annotated is None:
            raise ReleaseError("Annotated release tag could not be resolved")
        target = annotated.get("object") or {}
    if target.get("type") != "commit" or target.get("sha") != commit_sha:
        raise ReleaseError("Release tag does not match the checked-out event commit")
    release = fetch(f"{api}/releases/tags/{quote(tag, safe='/')}", token=token)
    if release is not None:
        print(f"GitHub release {tag} already exists; skipping without overwriting assets")
        return False
    print(f"GitHub tag {tag} matches this commit and has no release yet")
    return True


def pypi_publish_needed(version: str, *, fetch=get_json) -> bool:
    validate_version("cli", version)
    # Independent of GitHub tags: the GitHub-assets workflow may create its
    # tag before this workflow gets here, while PyPI still needs publication.
    payload = fetch(f"https://pypi.org/pypi/mdtero/{quote(version, safe='')}/json")
    if payload is None:
        print(f"PyPI mdtero {version} is new; publication may proceed")
        return True
    if (payload.get("info") or {}).get("version") != version:
        raise ReleaseError("PyPI returned metadata for an unexpected version")
    print(f"PyPI mdtero {version} already exists; skipping publication")
    return False


def main() -> None:
    command = sys.argv[1]
    if command == "resolve":
        values = resolve_release(sys.argv[2], os.environ["GITHUB_EVENT_NAME"], os.environ["GITHUB_REF"],
                                 Path.cwd(), os.environ.get("INPUT_KIND", ""), os.environ.get("INPUT_VERSION", ""))
        print(f"Resolved {values['tag']} from {os.environ['GITHUB_REF']}")
    elif command == "check-github":
        publish = github_publish_needed(
            os.environ["RELEASE_KIND"], os.environ["RELEASE_VERSION"],
            repository=os.environ["GITHUB_REPOSITORY"], event=os.environ["GITHUB_EVENT_NAME"],
            ref=os.environ["GITHUB_REF"], commit_sha=os.environ["GITHUB_SHA"], token=os.environ["GITHUB_TOKEN"],
        )
        values = {"publish": str(publish).lower()}
    elif command == "check-pypi":
        values = {"publish": str(pypi_publish_needed(os.environ["RELEASE_VERSION"])).lower()}
    else:
        raise ReleaseError("Unsupported release command")
    with Path(os.environ["GITHUB_OUTPUT"]).open("a") as output:
        for key, value in values.items():
            output.write(f"{key}={value}\n")


if __name__ == "__main__":
    try:
        main()
    except ReleaseError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        raise SystemExit(1)
