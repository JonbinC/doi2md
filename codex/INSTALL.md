---
name: mdtero
description: Powerful Elsevier-first paper parser that converts raw DOIs to Markdown bundles
---

# Mdtero Integration Guide

This guide allows an AI coding agent or a standalone script to interact with the Mdtero API, passing DOI links and receiving a parsed Markdown bundle, or checking the status of existing parsing tasks.

## 1. Authentication

You must provide an API key. This key belongs to your Mdtero account and deducts your parse quota.

```bash
export MDTERO_API_KEY="mdt_live_..."
```

For Elsevier papers, including ScienceDirect article pages, also provide your own Elsevier key:

```bash
export ELSEVIER_API_KEY="your-elsevier-key"
```

---

## 2. Recommended Local Helper

Install the local helper from Mdtero so Elsevier retrieval happens on the user's own machine and network:

```bash
curl -fsSL https://api.mdtero.com/helpers/install_mdtero_helper.sh | sh
```

The installer auto-detects `python3`, `python`, or `node` and writes a runnable `mdtero-local` wrapper into `~/.local/bin`.

For agent UX, treat this as the default Elsevier path rather than an optional detail. If the user asks to parse an Elsevier paper and this helper is not installed yet, stop and tell them to install it first.

Then parse papers with:

```bash
mdtero-local parse "10.1016/j.enconman.2026.121230"
```

Check task status with:

```bash
mdtero-local status <TASK_ID>
```

Download markdown with:

```bash
mdtero-local download <TASK_ID> paper_md ./paper.md
```

## 3. Direct API Fallback

**Production Base URL**: `https://api.mdtero.com`
**Auth Header Required**: `Authorization: ApiKey ${MDTERO_API_KEY}`

### Parse a Paper
To initiate parsing, send a `POST /tasks/parse`.

```bash
curl -X POST https://api.mdtero.com/tasks/parse \
  -H "Authorization: ApiKey $MDTERO_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input": "10.1016/j.enconman.2026.121230"}'
```

If you have your own Elsevier key, include it:

```bash
curl -X POST https://api.mdtero.com/tasks/parse \
  -H "Authorization: ApiKey $MDTERO_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"input\": \"10.1016/j.enconman.2026.121230\", \"elsevier_api_key\": \"$ELSEVIER_API_KEY\"}"
```

**Response**:
You will receive a JSON response with a local `"task_id"`. This is an asynchronous process if the paper is new; you must poll to get the complete results.

If the API returns a direct Elsevier setup hint instead of a task, stop and tell the user they still need the local helper or `ELSEVIER_API_KEY`.
Use this wording:

```text
This Elsevier paper needs local acquisition first. Please install the Mdtero local helper and set your ELSEVIER_API_KEY, then retry.
```

### Translate Parsed Markdown
Use `POST /tasks/translate` with the `paper_md` path from a succeeded parse task.

```bash
curl -X POST https://api.mdtero.com/tasks/translate \
  -H "Authorization: ApiKey $MDTERO_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "source_markdown_path": "/absolute/path/from/paper_md",
    "target_language": "zh",
    "mode": "standard"
  }'
```

### Check Task Status
To check the status of a task and retrieve its outputs, send a `GET /tasks/{task_id}`.

```bash
curl https://api.mdtero.com/tasks/<TASK_ID> \
  -H "Authorization: ApiKey $MDTERO_API_KEY"
```

**Response Overview**:
Look for `"status": "succeeded"`. The `"result"` object contains artifact metadata, not inline Markdown text. If `"warning_code": "elsevier_abstract_only"` appears, ask the user whether they are on a campus or institutional IP.
Use this wording:

```text
Mdtero only received the abstract from Elsevier. Are you currently on a campus or institutional network IP?
```

### Downloading Output

```bash
curl -L https://api.mdtero.com/tasks/<TASK_ID>/download/paper_md \
  -H "Authorization: ApiKey $MDTERO_API_KEY" \
  -o paper.md
```

To retrieve the ZIP bundle instead, replace `paper_md` with `paper_bundle`.

To retrieve translated Markdown instead, download `translated_md`.

### Elsevier Troubleshooting

- If Mdtero accepts the task but it later fails with Elsevier `401 Unauthorized`, your `ELSEVIER_API_KEY` is missing or invalid.
- If Mdtero only returns an abstract, ask whether the user is on a campus or institutional IP.
- The local helper is preferred because Elsevier retrieval then uses the user's local network/IP instead of cloud egress.
- The helper is dependency-light: a single downloaded file plus whichever runtime the user already has (`python3`, `python`, or `node`).
- For Elsevier inputs, use raw DOI form instead of `https://doi.org/...`.

### Downloading Images
Artifacts are downloaded through the task download route rather than a guessed static path. For example:

```bash
curl -L https://api.mdtero.com/tasks/<TASK_ID>/download/paper_bundle \
  -H "Authorization: ApiKey $MDTERO_API_KEY" \
  -o paper_bundle.zip
```
