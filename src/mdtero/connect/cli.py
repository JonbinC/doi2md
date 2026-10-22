"""CLI entry for the local Mdtero Connect bridge."""

from __future__ import annotations

import argparse
import json
from typing import Any

from mdtero.connect.bridge import ConnectBridge, run_bridge
from mdtero.connect.security import assert_loopback_bind


def register_connect_parser(sub: Any) -> argparse.ArgumentParser:
    parser = sub.add_parser(
        "connect",
        help="Start the local Mdtero Connect bridge (loopback UI for library/tags/export).",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Loopback bind address only (127.0.0.1 or ::1).")
    parser.add_argument("--port", type=int, default=8741, help="Local port (default 8741). Use 0 to pick a free port.")
    parser.add_argument("--no-browser", action="store_true", help="Do not open a browser window.")
    parser.add_argument("--full", action="store_true", help="Enable the optional local Pi research runtime (requires its Node dependencies and your model key).")
    parser.add_argument("--json", action="store_true", help="Print a secret-safe machine-readable summary and keep serving.")
    parser.set_defaults(func=cmd_connect)
    return parser


def cmd_connect(args: argparse.Namespace) -> int:
    host = assert_loopback_bind(str(args.host))
    port = int(args.port)
    open_browser = not bool(args.no_browser)
    if args.json:
        bridge = ConnectBridge(host=host, port=port, full_mode=bool(args.full))
        url = bridge.start()
        payload = {
            "status": "running",
            "url": url,
            "host": host,
            "port": bridge.bound_port,
            "product": "mdtero-connect",
            "secrets_in_ui": False,
            "mode": "full" if args.full else "library",
            "action_hint": "Open the URL in a local browser. Stop with Ctrl+C.",
        }
        print(json.dumps(payload, ensure_ascii=False), flush=True)
        try:
            import threading

            threading.Event().wait()
        except KeyboardInterrupt:
            pass
        finally:
            bridge.stop()
        return 0
    run_bridge(host=host, port=port, open_browser=open_browser, forever=True, full_mode=bool(args.full))
    return 0
