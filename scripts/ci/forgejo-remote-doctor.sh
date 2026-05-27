#!/usr/bin/env bash
set -euo pipefail

remote_name="${1:-forgejo}"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  printf 'forgejo_remote_doctor: not inside a git worktree.\n' >&2
  exit 64
fi

remote_url="$(git remote get-url "$remote_name" 2>/dev/null || true)"
if [[ -z "$remote_url" ]]; then
  printf 'forgejo_remote_doctor: remote %s is not configured.\n' "$remote_name" >&2
  exit 65
fi

case "$remote_url" in
  http://100.97.234.105:3020/*) ;;
  *)
    printf 'forgejo_remote_doctor: remote %s does not point at the private Forgejo Tailnet host.\n' "$remote_name" >&2
    exit 66
    ;;
esac

if [[ "$remote_url" =~ ^https?://[^/@]+:[^/@]+@ ]]; then
  printf 'forgejo_remote_doctor: remote %s embeds credentials; remove them before continuing.\n' "$remote_name" >&2
  exit 67
fi

if [[ "$remote_url" =~ ^(https?://[^/]+)/ ]]; then
  forgejo_base="${BASH_REMATCH[1]}"
else
  printf 'forgejo_remote_doctor: remote %s is not an HTTP(S) Forgejo URL.\n' "$remote_name" >&2
  exit 66
fi

if ! curl --fail --silent --show-error --max-time 5 --head "$forgejo_base" >/dev/null; then
  printf 'forgejo_remote_doctor: Forgejo web endpoint is not reachable at %s.\n' "$forgejo_base" >&2
  exit 68
fi

tmp_stdout="$(mktemp)"
tmp_stderr="$(mktemp)"
cleanup() {
  rm -f "$tmp_stdout" "$tmp_stderr"
}
trap cleanup EXIT

set +e
GIT_TERMINAL_PROMPT=0 git ls-remote --heads "$remote_name" HEAD >"$tmp_stdout" 2>"$tmp_stderr"
status=$?
set -e

if [[ $status -eq 0 ]]; then
  printf 'forgejo_remote_doctor: remote=%s status=ok url=clean endpoint=reachable auth=ok\n' "$remote_name"
  exit 0
fi

stderr_text="$(tr '\n' ' ' <"$tmp_stderr")"
case "$stderr_text" in
  *'Authentication failed'*|*'Update your password'*|*'could not read Username'*)
    printf 'forgejo_remote_doctor: remote=%s status=auth_failed url=clean endpoint=reachable action=refresh_git_credential\n' "$remote_name" >&2
    exit 69
    ;;
  *)
    printf 'forgejo_remote_doctor: remote=%s status=git_failed url=clean endpoint=reachable exit=%s\n' "$remote_name" "$status" >&2
    exit "$status"
    ;;
esac
