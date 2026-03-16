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

---

## 2. API Endpoint Usage

**Production Base URL**: `https://api.mdtero.com`
**Auth Header Required**: `ApiKey: ${MDTERO_API_KEY}`

### Parse an Elsevier Paper
To initiate parsing, send a `POST /tasks/parse`.

```bash
curl -X POST https://api.mdtero.com/tasks/parse \
  -H "ApiKey: $MDTERO_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"input": "https://doi.org/10.1016/j.enconman.2026.121230"}'
```

**Response**:
You will receive a JSON response with a local `"task_id"`. This is an asynchronous process if the paper is new; you must poll to get the complete results.

### Check Task Status
To check the status of a task and retrieve its outputs, send a `GET /tasks/{task_id}`.

```bash
curl https://api.mdtero.com/tasks/<TASK_ID> \
  -H "ApiKey: $MDTERO_API_KEY"
```

**Response Overview**:
Look for `"status": "succeeded"`. The `"result"` object will contain the metadata and URLs to the generated assets (Markdown, ZIP Bundle, XML, Images).

### Downloading Output & Images
If you need to fetch the images locally for the parser agents to read context:
```bash
# Retrieve original image from the task storage link
curl -H "ApiKey: $MDTERO_API_KEY" \
  -o local_image.jpg \
  https://api.mdtero.com/api/v1/downloads/.../image.jpg
```
