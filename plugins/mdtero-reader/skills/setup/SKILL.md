---
name: mdtero-setup
description: Set up Mdtero Reader after the plugin is installed. Use when the user just installed Mdtero or asks how to connect ChatGPT, Claude, Cursor, Codex, the campus relay, or an Elsevier key.
---

# Mdtero Reader setup

The plugin talks to `https://api.mdtero.com/mcp`. Parsing stays on Mdtero's servers. This package does not contain the parser.

1. Use the host's OAuth sign-in with the user's Mdtero account at `https://api.mdtero.com`. Follow the [Cloud MCP setup guide](https://mdtero.com/docs/install#cloud-mcp-chatgpt-claude-cursor) if the connection is missing.
2. Never ask for an Elsevier API key, InstToken, campus password, or proxy credential in the chat. The key is saved only at `https://api.mdtero.com/mcp/settings`.
3. Call `get_setup_guide` and follow `next_step`. Search works before the key and before the campus helper are ready.
4. For institutional access, connect the Relay helper on an authorized campus device under the same Mdtero account. When the user asks to check that access, call `check_relay_entitlement` and read `verdict`, `action_hint`, and the full-text confirmation. Helper online status alone does not establish article entitlement. After a parse, read `access_path` and its content quality; metadata-only output is not a full-text result.
5. Submit a parse or translation once, with one stable `request_id`. Check progress with `get_task`. Do not save or index a paper unless the user asks.
