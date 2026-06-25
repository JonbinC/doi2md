from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

RELAY_ALLOWED_HOST_SUFFIXES = (
    "academic.oup.com",
    "acm.org",
    "api.crossref.org",
    "api.elsevier.com",
    "api.openalex.org",
    "arxiv.org",
    "cambridge.org",
    "cell.com",
    "crossref.org",
    "dl.acm.org",
    "doi.org",
    "elsevier.com",
    "frontiersin.org",
    "ieeexplore.ieee.org",
    "ieee.org",
    "journals.aps.org",
    "link.springer.com",
    "mdpi.com",
    "nature.com",
    "ncbi.nlm.nih.gov",
    "onlinelibrary.wiley.com",
    "openalex.org",
    "oup.com",
    "plos.org",
    "pnas.org",
    "pubmed.ncbi.nlm.nih.gov",
    "sagepub.com",
    "science.org",
    "sciencedirect.com",
    "springer.com",
    "tandfonline.com",
    "wiley.com",
)

_LOCAL_HOSTS = {"localhost", "localhost.localdomain", "127.0.0.1", "::1"}


def relay_url_allowed(url: str) -> bool:
    parsed = urlparse(str(url or "").strip())
    scheme = str(parsed.scheme or "").strip().lower()
    if scheme not in {"http", "https"}:
        return False
    host = str(parsed.hostname or "").strip().lower().rstrip(".")
    if not host or host in _LOCAL_HOSTS or host.endswith(".localhost"):
        return False
    if _host_resolves_to_private(host):
        return False
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in RELAY_ALLOWED_HOST_SUFFIXES)


def relay_url_rejection_reason(url: str) -> str | None:
    if relay_url_allowed(url):
        return None
    parsed = urlparse(str(url or "").strip())
    scheme = str(parsed.scheme or "").strip().lower()
    host = str(parsed.hostname or "").strip().lower()
    if scheme not in {"http", "https"}:
        return "relay_url_scheme_unsupported"
    if not host:
        return "relay_url_host_missing"
    if host in _LOCAL_HOSTS or host.endswith(".localhost") or _host_resolves_to_private(host):
        return "relay_url_private_host_blocked"
    return "relay_url_domain_not_allowed"


def _host_resolves_to_private(host: str) -> bool:
    if host in _LOCAL_HOSTS:
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except OSError:
            return False
        if not infos:
            return False
        for info in infos:
            try:
                ip = ipaddress.ip_address(info[4][0])
            except ValueError:
                continue
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return True
        return False
    return ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
