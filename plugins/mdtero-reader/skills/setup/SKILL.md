---
name: mdtero-setup
description: Set up Mdtero Reader after the plugin is installed. Use when the user just installed Mdtero or asks how to connect ChatGPT, Claude, Cursor, Codex, the campus relay, or an Elsevier key.
---

# Mdtero Reader setup

The plugin talks to `https://api.mdtero.com/mcp`. Parsing stays on Mdtero's servers. This package does not contain the parser.

1. Ask the user to sign in with the Mdtero account when the host shows the login. The login is an email code on `https://api.mdtero.com`.
2. Never ask for an Elsevier API key, InstToken, campus password, or proxy credential in the chat. The key is saved only at `https://api.mdtero.com/mcp/settings`.
3. Call `get_setup_guide` and follow `next_step`. Search works before the key and before the campus helper are ready.
4. A campus subscription still needs the Relay helper on a computer that is allowed to reach the publisher. Helper online status is not the path a paper took. After a parse, read `access_path`.
5. Submit a parse or translation once, with one stable `request_id`. Check progress with `get_task`. Do not save or index a paper unless the user asks.
