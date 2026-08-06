# Relay allowlist mirror

This directory mirrors `backend/contracts/relay/allowed_host_suffixes.json`.

Do not edit by hand. From the workspace backend root:

```bash
python3 scripts/contracts/sync_relay_allowlist.py
```

The generated Go and Python consumers under `relay/` and `src/mdtero/` must stay
byte-identical to this contract.
