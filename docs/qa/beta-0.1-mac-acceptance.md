# Beta 0.1 internal RC install acceptance

**State:** internal test checklist only. The earlier pre-fix PR #30 was closed. This checklist applies only to an integration candidate containing the verified #28 confirmed-write Cancel fix; passing CI does not clear publication or establish human platform acceptance. Any attached installers are short-lived, unsigned, unnotarized debug artifacts, not a release.

## Locate the candidate artifacts

Use the current internal integration Draft PR and its exact head SHA, not the public Connect Preview.3 release. On that PR page, open **Checks**, select the **Connect native debug artifacts** run for that PR head, then open that run's **Artifacts** section. The expected artifact names are:

- `mdtero-connect-debug-macos-arm64-<head-sha>`
- `mdtero-connect-debug-macos-x64-<head-sha>`
- `mdtero-connect-debug-windows-x64-<head-sha>`

The same run is available from the repository's **Actions → Connect native debug artifacts** workflow history; verify its head SHA matches the PR before downloading. The unmerged RC feature branch sets this workflow's per-artifact retention to **7 days** for new uploads, to support next-day testing. This does not change repository-wide retention settings or extend artifacts from earlier runs; those retain their original expiry. Inspect the artifact contents and recorded checksum before installing; this checklist does not assert that any particular artifact is present or valid.

The existing [Connect Preview.3 release](https://github.com/JonbinC/doi2md/releases/tag/connect-v0.1.0-preview.3) was built from an earlier source commit and does not contain this candidate's Beta integration changes. Do not use it as evidence for this candidate.

## No-real-data first-install smoke

Run each available target on a clean Mac or Windows machine and record the OS version, device architecture, workflow run URL, PR head SHA, artifact filename, and checksum.

- [ ] Download the artifact from the candidate PR workflow run and confirm the recorded head SHA matches the PR.
- [ ] Install and launch the app. Record the installer behavior, first launch result, and any OS warning. Do not bypass an OS warning; stop and report it.
- [ ] Confirm the Mdtero brand mark and sign-in gate render. Do not enter a real account or API key; stop at the gate for this no-real-data smoke.
- [ ] Close and relaunch once. Record whether the app exits and starts cleanly.
- [ ] Attach logs or screenshots only after removing account identifiers, local paths, and other private data.
- [ ] Report failures with the platform, OS version, artifact name, workflow run URL, exact head SHA, and a concise reproduction sequence.

## Optional Stage 2: authorized synthetic test account

Run Stage 2 only after Stage 1 passes on that machine, and only when the tester has explicit authorization to use a dedicated synthetic test account. Do not use a real user's account, real library data, production passwords, or API keys. This stage is not authorized on an RC build until the #28 confirmed-write Cancel fix has a verified source SHA in the integration and its focused combined tests have been rerun. If that gate is not met, mark Stage 2 **BLOCKED** and stop.

The confirm step below writes records to the synthetic test account on the server. The dry-run preview itself must report zero writes; confirming is an explicit server-side write and must never be described as zero writes. If the app shows Cancel enabled during a confirmed write, or any message claims zero writes while the result may be in flight or uncertain, stop immediately, do not retry or re-import, refresh the library to inspect the outcome, and report the issue.

- [ ] Sign in through browser OAuth using the authorized synthetic test account only. Verify in the app that the intended test account is active; if the backend/test configuration blocks login or account verification, mark the step **BLOCKED** and record the redacted diagnostic.
- [ ] Generate a tiny local `.bib` or `.ris` file containing one clearly fake, unpublished citation (no real DOI, author, or publication record) and select it for import.
- [ ] Inspect the import preview. Confirm it is labeled as a dry run and reports zero writes before proceeding. Cancel here if the preview is inaccurate or the destination account is uncertain.
- [ ] After reading the explicit write notice and confirming the synthetic account is selected, confirm exactly once. Wait for a definite result; do not click Cancel during an in-flight write and do not retry an uncertain outcome until refreshing the library and following the app's same-request retry guidance.
- [ ] Refresh the library and verify the single synthetic record appears once. Record whether the UI reports a successful write and whether the count matches.
- [ ] Export metadata or Markdown for that synthetic record. Alternatively, parse one open-access DOI only if the tester has checked the current cost and credential notice first; use no paid API or real credential. If cost, credentials, or service availability are unclear, skip the DOI path.
- [ ] Quit and relaunch the app, then verify it exits and starts cleanly and the synthetic record remains visible. Remove the synthetic record/account data through the authorized test procedure after recording results.
- [ ] Record only safe, redacted diagnostics: platform and OS, artifact/run URL and exact SHA, synthetic test case identifier, step/result, timestamps, and sanitized error codes. Remove account email/IDs, tokens, cookies, local paths, file contents, and screenshots containing private data.

Run Mac Apple Silicon and Mac Intel independently when both artifacts exist. Run Windows x64 as a separate check; it is included to cover the Windows CSRF test robustness change, not to imply Windows acceptance.

## Known limits

- The Connect Playwright fixture assigns origin/control ports from `GITHUB_RUN_ID` and `GITHUB_RUN_ATTEMPT` (with process-local fallback outside Actions), passes them to both fixture servers, and keeps `reuseExistingServer: false`. This preserves the #22/#23 isolation fix for the shared-runner port collision reported on #29; do not disable the live UI test, reuse an existing server, or restore fixed `18742` ports in the CI config.
- The candidate artifacts are unsigned and macOS artifacts are unnotarized. This checklist gives no signing-warning bypass procedure.
- Human Mac and Windows acceptance is pending. A CI build or synthetic UI test does not establish installation, account login, credential-store, upgrade, or uninstall behavior.
- Native jobs currently bundle Python 3.11, while the optional local full-text parser requires Python 3.12 or newer. The parser compatibility gate marks the current native Python as unsupported; do not claim local HTML/PDF parsing is supported or tested by this candidate.
- The public Preview.3 release is a separate, older artifact. Candidate PR artifacts remain unverified until the human smoke above is completed.
- Passing this checklist does not clear Beta go/no-go by itself. Keep RC publication blocked until the #28 confirmed-write Cancel P0 fix is included and verified; record that exact source SHA and the rerun focused test results before considering an artifact.
