# Connect full edition: local Pi runtime

The full edition embeds the Pi TypeScript SDK behind the Python loopback bridge. The basic edition remains a library client and never loads the SDK. This is a source/runtime integration, not a signed desktop installer.

From a repository checkout, with Node.js **22.19.0 or newer**:

```sh
npm --prefix connect/agent ci --ignore-scripts
uv run mdtero connect --full
```

For an installed Python wheel, the runtime sources are packaged beside `mdtero.connect`; install the pinned dependencies into that `agent` directory using `npm ci --ignore-scripts`. The bridge's Agent status reports missing Node or dependencies. It never installs packages when a page is opened. Native bundles and an automatic dependency installer are not implemented.

Configure a local AI key in Connect (OpenAI, Anthropic, Google, or OpenRouter), select 1–10 documents, and preview a research question. The preview shows the exact metadata, provider, catalog model, data size, one model request, and output token limit. Approving it consumes a short-lived, single-use ID. Later page edits cannot modify the approved request. Runs can be cancelled and are stopped after 90 seconds.

Only selected **metadata** is sent: ID, title, authors, year, venue, and DOI. No full text, abstracts, images, tags, other library entries, or institution credentials are available to Pi. Answers are instructed to cite `[document_id]` and acknowledge missing evidence. This does not validate research findings or provide full-text analysis.

## Loopback UI contract

The real UI calls the existing same-origin bridge. `GET /connect/v1/agent/status` reports the edition, dependencies, configured AI providers, catalog models, and any active run ID. In basic mode it does not load Node or read AI credentials. Explicit provider settings are managed separately.

1. `POST /connect/v1/agent/prepare` accepts `{document_ids, prompt, provider, model, max_output_tokens}`. The bridge reads the current account library and freezes only the selected metadata.
2. `POST /connect/v1/agent/runs` accepts only `{approval_id}` and starts that frozen request. The page cannot replace approved documents or task text at execution time.
3. `GET /connect/v1/agent/runs/{run_id}` polls a running, completed, failed, or cancelled result. The status endpoint's `active_run` allows a reopened page to recover control of a running request.
4. `POST /connect/v1/agent/runs/{run_id}/cancel` stops the supervised process. All POSTs retain the existing Host/Origin and CSRF protections.

The preview's `input_bytes` counts the serialized selected request data. It excludes credentials, system instructions, and the provider's HTTP framing; it is not a billed-token estimate. Results remain plain text and numeric usage, without HTML rendering or executable tool output.

## Runtime boundary

- `@earendil-works/pi-coding-agent` is pinned to `1.3.0` in `package-lock.json`; no remote code installation occurs during runs.
- The Python process supervises one Node child per approved request. Keys travel through stdin, never argv, browser responses, or inherited provider environment variables. The child has a disposable working directory.
- Pi has `tools: []`, no custom tools, a host-owned empty resource loader, in-memory settings and conversation storage, and a nonpersistent credential store. It cannot discover project `AGENTS.md`, skills, extensions, prompt templates, auth files, or MCP configurations.
- Only the pinned SDK's built-in model catalog is accepted. The page cannot supply endpoints, credentials, tool names, file paths, or model definitions.
- Cache warming, automatic compaction, automatic retries, telemetry, and analytics are disabled. A wrapper limits model execution to one request and caps `maxTokens` at the approved amount (128–4,096). This is a request/token limit, not a dollar-denominated account budget.
- Errors are generic and do not forward upstream error bodies. Results are plain text plus numeric token usage. Credentials are redacted defensively. Pending approvals, runs, and results live only in Python process memory.

This is **not an OS sandbox**: the installed Pi SDK and its dependencies remain trusted local code. The restrictions remove model-callable shell/filesystem capabilities and ambient resource discovery; they do not contain a compromised Node package. Signed native packaging, dependency delivery, OS sandboxing, persistent run history, dollar budgets, full-text tools, and library mutation tools remain future work.

OpenAlex discovery, MinerU parsing, and Voyage embeddings are distinct BYOK services. They are not language-model providers and are not passed to Pi as AI credentials.

## Verification

```sh
npm --prefix connect/agent test
uv run pytest tests_py/test_connect_agent.py -q
```

Node tests use the real pinned Pi SDK with a synthetic local HTTP model server, and verify the request cap, output token cap, absent tools, ignored `AGENTS.md`, no session/auth files, no retries, timeout cancellation, and sanitized errors. Python tests verify account-owned selection, frozen/single-use approval, concurrency, key isolation, subprocess cancellation, timeout, and basic/full edition behavior. These tests do not spend API credits or validate real model service availability.

Official sources, checked against the installed `1.3.0` package:

- [Pi SDK and lifecycle](https://github.com/earendil-works/pi/blob/v1.3.0/packages/coding-agent/docs/sdk.md)
- [Full-control resource loader](https://github.com/earendil-works/pi/blob/v1.3.0/packages/coding-agent/examples/sdk/12-full-control.ts)
- [ModelRuntime credential and catalog boundaries](https://github.com/earendil-works/pi/blob/v1.3.0/packages/coding-agent/src/core/model-runtime.ts)
- [SDK tool selection](https://github.com/earendil-works/pi/blob/v1.3.0/packages/coding-agent/src/core/sdk.ts)

The project moved from `badlogic/pi-mono` / `@mariozechner/pi-coding-agent` to `earendil-works/pi` / `@earendil-works/pi-coding-agent`; old examples use different APIs. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for the Pi license.
