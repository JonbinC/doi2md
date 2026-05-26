# Private platform migration phase 1

The public Mdtero CLI/browser-extension repo (`doi2md`) now has a private Forgejo mirror for internal migration work. GitHub remains the public ecosystem and rollback remote for now.

## Git remotes

- `origin`: GitHub public/rollback remote
- `forgejo`: `http://100.97.234.105:3020/jianbin/doi2md.git`

Keep remote URLs clean. Do not embed PATs, service tokens, or passwords in `git remote -v` output.

For private/internal migration branches:

```bash
git push forgejo <branch>
git push forgejo --tags
```

## Forgejo Actions

Forgejo Actions is manual-first during phase 1.

- Use `workflow_dispatch` only.
- Default `check_scope=smoke` runs only lightweight public contract tests.
- Use `check_scope=full` for the Python package build and browser-extension build/test path.
- Do not add push/PR triggers until a manual Forgejo smoke has passed.
- Keep runner labels narrow, currently `linux-small`.

## Secrets

The public CLI and extension should not require production provider secrets in CI. If future private deploy or smoke jobs need credentials, read them from Infisical at runtime through a service token or machine identity. Do not commit generated env files, print secret values, or bake bootstrap/admin tokens into CI.

Do not remove GitHub or PyPI/public release paths until the private path has successful manual smoke evidence, release evidence, and rollback evidence.
