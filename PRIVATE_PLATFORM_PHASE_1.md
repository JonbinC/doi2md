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
- Use `platform_preflight=check` when an operator wants a non-deploying private-platform check for clean Forgejo remotes, secret scanning, and the checked-in extension dist smoke.
- Do not add push/PR triggers until a manual Forgejo smoke has passed.
- Keep runner labels narrow, currently `linux-small`.

The local equivalent is:

```bash
scripts/ci/private_platform_preflight.sh
```

It does not read provider secrets, deploy, publish, or print credentials. It only verifies the private Forgejo remote, runs `scripts/ci/secret_guard.py`, and validates the checked-in MV3 extension bundle with `scripts/ci/extension_dist_smoke.py`.

## Manual smoke evidence

Before treating Forgejo as the healthy private CI path, run this workflow from Forgejo Web:

- Repo: `jianbin/doi2md`
- Workflow: `Public CLI and Extension CI`
- Branch: `main`
- Inputs: `check_scope=smoke`, `platform_preflight=check`

A passing smoke run must show these non-secret steps in the job log:

- `Optional private platform preflight`
- `Run secret guard`
- `Run lightweight public contract tests`
- `public_private_platform_preflight: status=ok`

For release-candidate validation, run the same workflow with `check_scope=full` after the smoke run passes. The full run is expected to build the Python package, smoke-install the wheel, run all Python tests, run the browser-extension test suite, build the MV3 bundle, and execute `scripts/ci/extension_dist_smoke.py`. Keep this full run manual until the lightweight runner has repeated green evidence.

## Secrets

The public CLI and extension should not require production provider secrets in CI. If future private deploy or smoke jobs need credentials, read them from Infisical at runtime through a service token or machine identity. Do not commit generated env files, print secret values, or bake bootstrap/admin tokens into CI.

Do not remove GitHub or PyPI/public release paths until the private path has successful manual smoke evidence, release evidence, and rollback evidence.
