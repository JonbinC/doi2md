from __future__ import annotations

import asyncio
import base64
import json
import signal
from typing import Any, Callable

import httpx
import websockets
from websockets.exceptions import ConnectionClosed

from .config import MdteroConfig
from .network import CAMPUS_PROXY_CHECK_URL, _is_expected_campus_outlet, _proxy_public_summary
from .relay_domains import relay_url_allowed, relay_url_rejection_reason

MAX_RELAY_BODY_BYTES = 32 * 1024 * 1024
DEFAULT_RECONNECT_SECONDS = 5.0


def relay_ws_url(api_base_url: str) -> str:
    base = str(api_base_url or "").strip().rstrip("/")
    if base.startswith("https://"):
        return f"wss://{base.removeprefix('https://')}/api/v1/relay/ws"
    if base.startswith("http://"):
        return f"ws://{base.removeprefix('http://')}/api/v1/relay/ws"
    return f"{base}/api/v1/relay/ws"


async def check_campus_outlet(*, timeout: float = 20.0) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        response = await client.get(CAMPUS_PROXY_CHECK_URL)
        response.raise_for_status()
        payload = response.json()
    summary = _proxy_public_summary(payload)
    return {
        "summary": summary,
        "campus_ok": _is_expected_campus_outlet(payload),
    }


async def execute_relay_fetch(
    *,
    url: str,
    method: str,
    headers: dict[str, str],
    timeout: float,
) -> dict[str, Any]:
    if not relay_url_allowed(url):
        reason_code = relay_url_rejection_reason(url) or "relay_url_domain_not_allowed"
        return {
            "error": "Relay fetch is limited to approved research publisher domains over HTTP/HTTPS.",
            "reason_code": reason_code,
        }

    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.request(method, url, headers=headers)
            body = response.content
            if len(body) > MAX_RELAY_BODY_BYTES:
                return {
                    "error": "Relay response exceeded the maximum allowed body size.",
                    "reason_code": "relay_fetch_body_too_large",
                }
            return {
                "status_code": response.status_code,
                "headers": {key: value for key, value in response.headers.items()},
                "body_b64": base64.b64encode(body).decode("ascii"),
            }
    except Exception as exc:
        return {
            "error": str(exc),
            "reason_code": "relay_fetch_failed",
        }


async def _handle_message(message: dict[str, Any]) -> dict[str, Any] | None:
    message_type = str(message.get("type") or "").strip()
    if message_type != "fetch":
        return None
    request_id = str(message.get("request_id") or "").strip()
    url = str(message.get("url") or "").strip()
    method = str(message.get("method") or "GET").strip().upper()
    timeout = float(message.get("timeout") or 60.0)
    raw_headers = message.get("headers")
    headers: dict[str, str] = {}
    if isinstance(raw_headers, dict):
        headers = {str(key): str(value) for key, value in raw_headers.items()}

    result = await execute_relay_fetch(url=url, method=method, headers=headers, timeout=timeout)
    payload: dict[str, Any] = {
        "type": "fetch_result",
        "request_id": request_id,
    }
    if result.get("error") or result.get("reason_code"):
        payload["error"] = str(result.get("error") or "Relay fetch failed.")
        payload["reason_code"] = str(result.get("reason_code") or "relay_fetch_failed")
    else:
        payload["status_code"] = result.get("status_code")
        payload["headers"] = result.get("headers") or {}
        payload["body_b64"] = result.get("body_b64") or ""
    return payload


async def run_relay_server(
    config: MdteroConfig,
    *,
    label: str | None = None,
    on_status: Callable[[str, dict[str, Any]], None] | None = None,
) -> None:
    api_key = config.effective_api_key
    if not api_key:
        raise RuntimeError("Mdtero API key is missing. Run `mdtero login` or `mdtero login --api-key` first.")

    stop_event = asyncio.Event()

    def _request_stop(*_args: object) -> None:
        stop_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _request_stop)
        except NotImplementedError:
            signal.signal(sig, _request_stop)  # type: ignore[arg-type]

    outlet_payload = await check_campus_outlet()
    if on_status:
        on_status("outlet_checked", outlet_payload)

    ws_url = relay_ws_url(config.api_base_url)
    headers = {"Authorization": f"ApiKey {api_key}", "X-Client-Channel": "python-relay"}

    while not stop_event.is_set():
        try:
            if on_status:
                on_status("connecting", {"ws_url": ws_url})
            async with websockets.connect(ws_url, additional_headers=headers, ping_interval=20, ping_timeout=20) as websocket:
                hello = json.loads(await websocket.recv())
                if str(hello.get("type") or "") != "hello":
                    raise RuntimeError("Relay handshake failed: expected hello message from server.")

                register_payload = {
                    "type": "register",
                    "label": label,
                    "outlet": outlet_payload.get("summary"),
                }
                await websocket.send(json.dumps(register_payload))
                registered = json.loads(await websocket.recv())
                if str(registered.get("type") or "") != "registered":
                    raise RuntimeError(str(registered.get("action_hint") or registered.get("reason_code") or "Relay registration failed."))

                if on_status:
                    on_status("registered", registered)

                while not stop_event.is_set():
                    raw = await websocket.recv()
                    message = json.loads(raw)
                    if not isinstance(message, dict):
                        continue
                    response = await _handle_message(message)
                    if response is not None:
                        await websocket.send(json.dumps(response))
        except ConnectionClosed:
            if stop_event.is_set():
                break
            if on_status:
                on_status("reconnecting", {"delay_seconds": DEFAULT_RECONNECT_SECONDS})
            await asyncio.sleep(DEFAULT_RECONNECT_SECONDS)
        except Exception as exc:
            if stop_event.is_set():
                break
            if on_status:
                on_status("error", {"message": str(exc), "delay_seconds": DEFAULT_RECONNECT_SECONDS})
            await asyncio.sleep(DEFAULT_RECONNECT_SECONDS)

    if on_status:
        on_status("stopped", {})
