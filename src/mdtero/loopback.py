"""Literal loopback HTTP listeners that never require reverse DNS."""

from __future__ import annotations

from http.server import ThreadingHTTPServer
from socketserver import TCPServer


class LoopbackThreadingHTTPServer(ThreadingHTTPServer):
    """Bind only reviewed loopback literals, including IPv6 subclasses.

    HTTPServer.server_bind calls socket.getfqdn, which can block startup on
    hosts with slow reverse DNS. Local callbacks need the bound address and
    port, so skip that unrelated lookup while preserving TCPServer binding.
    """

    def server_bind(self) -> None:
        if self.server_address[0] not in {"127.0.0.1", "::1"}:
            raise ValueError("Local HTTP services must bind to 127.0.0.1 or ::1 only.")
        TCPServer.server_bind(self)
        host, port = self.server_address[:2]
        if host not in {"127.0.0.1", "::1"}:
            raise ValueError("Local HTTP services must bind to 127.0.0.1 or ::1 only.")
        self.server_name = host
        self.server_port = port
