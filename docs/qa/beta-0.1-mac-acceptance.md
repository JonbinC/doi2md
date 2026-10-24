# Beta 0.1 internal RC install acceptance

**State:** internal test checklist for the candidate integration PR. Any attached installers are short-lived, unsigned, unnotarized debug artifacts. They are not a release and have not passed human platform acceptance.

## Find the candidate artifacts

Use the internal integration Draft PR and its exact head SHA, not the public Connect Preview.3 release. On the PR page, open **Checks**, select the **Connect native debug artifacts** run for the PR head, then open that run's **Artifacts** section. The expected artifact names are:

- `mdtero-connect-debug-macos-arm64-<head-sha>`
- `mdtero-connect-debug-macos-x64-<head-sha>`
- `mdtero-connect-debug-windows-x64-<head-sha>`

The same run is available from the repository's **Actions → Connect native debug artifacts** workflow history; verify its head SHA matches the PR before downloading. These workflow artifacts expire after one day. Inspect the artifact contents and recorded checksum before installing; this checklist does not assert that any particular artifact is present or valid.

The existing [Connect Preview.3 release](https://github.com/JonbinC/doi2md/releases/tag/connect-v0.1.0-preview.3) was built from an earlier source commit and does not contain this candidate's Beta integration changes. Do not use it as evidence for this candidate.

## No-real-data first-install smoke

Run each available target on a clean Mac or Windows machine and record the OS version, device architecture, workflow run URL, PR head SHA, artifact filename, and checksum.

- [ ] Download the artifact from the candidate PR workflow run and confirm the recorded head SHA matches the PR.
- [ ] Install and launch the app. Record the installer behavior, first launch result, and any OS warning. Do not bypass an OS warning; stop and report it.
- [ ] Confirm the Mdtero brand mark and sign-in gate render. Do not enter a real account or API key; stop at the gate for this no-real-data smoke.
- [ ] Close and relaunch once. Record whether the app exits and starts cleanly.
- [ ] Attach logs or screenshots only after removing account identifiers, local paths, and other private data.
- [ ] Report failures with the platform, OS version, artifact name, workflow run URL, exact head SHA, and a concise reproduction sequence.

Run Mac Apple Silicon and Mac Intel independently when both artifacts exist. Run Windows x64 as a separate check; it is included to cover the Windows CSRF test robustness change, not to imply Windows acceptance.

## Known limits

- The candidate artifacts are unsigned and macOS artifacts are unnotarized. This checklist gives no signing-warning bypass procedure.
- Human Mac and Windows acceptance is pending. A CI build or synthetic UI test does not establish installation, account login, credential-store, upgrade, or uninstall behavior.
- Native jobs currently bundle Python 3.11, while the optional local full-text parser requires Python 3.12 or newer. The parser compatibility gate marks the current native Python as unsupported; do not claim local HTML/PDF parsing is supported or tested by this candidate.
- The public Preview.3 release is a separate, older artifact. Candidate PR artifacts remain unverified until the human smoke above is completed.
