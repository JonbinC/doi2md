from __future__ import annotations

import re
from typing import Any

SENSITIVE_QUERY_KEYS = (
    r"api[_-]?key|access[_-]?token|security-token|x-oss-security-token|"
    r"signature|x-amz-signature|x-amz-credential|ossaccesskeyid|expires|token"
)

_AUTH_RE = re.compile(r"\b(Bearer|ApiKey)\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
_MDTERO_KEY_RE = re.compile(r"\b(?:mdtero|mdt)_(?:secret|live|test|key)_[A-Za-z0-9_-]+", re.IGNORECASE)
_QUERY_PARAM_RE = re.compile(rf"([?&](?:{SENSITIVE_QUERY_KEYS})=)[^&#\s\"'<>]+", re.IGNORECASE)
_KEY_VALUE_RE = re.compile(rf"\b({SENSITIVE_QUERY_KEYS})(\s*[:=]\s*)['\"]?[^\s&'\",;]+", re.IGNORECASE)
_ALIYUN_URL_RE = re.compile(r"https?://[^\s\"'<>]*aliyuncs\.com[^\s\"'<>]*", re.IGNORECASE)
_OSS_URL_RE = re.compile(r"https?://[^\s\"'<>]*oss-cn-[^\s\"'<>]*", re.IGNORECASE)


def redact_sensitive_text(value: object) -> str:
    text = str(value or "")
    if not text:
        return ""
    text = _AUTH_RE.sub(r"\1 [redacted]", text)
    text = _MDTERO_KEY_RE.sub("[redacted-key]", text)
    text = _QUERY_PARAM_RE.sub(r"\1[redacted]", text)
    text = _KEY_VALUE_RE.sub(r"\1\2[redacted]", text)
    text = _ALIYUN_URL_RE.sub("[redacted-url]", text)
    text = _OSS_URL_RE.sub("[redacted-url]", text)
    return text


def redact_sensitive_payload(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: redact_sensitive_payload(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_sensitive_payload(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive_payload(item) for item in value)
    if isinstance(value, str):
        return redact_sensitive_text(value)
    return value
