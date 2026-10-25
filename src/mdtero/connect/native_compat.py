"""Native Python/parser capability checks shared by preparation and collection.

The private ``mdtero-parser`` runtime currently declares Python >=3.12. Keep
that requirement visible in native artifact metadata; a successful PyInstaller
build alone does not prove local HTML/PDF parsing is available.
"""

from __future__ import annotations

from collections.abc import Sequence


PARSER_MINIMUM_PYTHON = (3, 12)


def parser_runtime_status(version: Sequence[int], module_available: bool) -> str:
    """Return a stable status for the actual frozen interpreter and parser."""
    try:
        actual = tuple(int(part) for part in version[:3])
    except (TypeError, ValueError):
        return "invalid_python_version"
    if len(actual) < 2:
        return "invalid_python_version"
    if actual[:2] < PARSER_MINIMUM_PYTHON:
        return "unsupported_python"
    if not module_available:
        return "parser_not_installed"
    return "python_supported_module_detected"


def validate_parser_runtime(manifest: object) -> None:
    """Reject missing or contradictory parser/runtime declarations."""
    if not isinstance(manifest, dict):
        raise ValueError("native manifest must be an object")
    version = manifest.get("python_version")
    available = manifest.get("local_fulltext_parser_module_detected")
    status = manifest.get("local_fulltext_parser_status")
    minimum = manifest.get("local_fulltext_parser_minimum_python")
    if not isinstance(version, str) or not isinstance(available, bool) or not isinstance(status, str) or minimum != "3.12":
        raise ValueError("native manifest must record Python and local parser capability")
    try:
        parts = tuple(int(part) for part in version.split("."))
    except ValueError as error:
        raise ValueError("native manifest has an invalid Python version") from error
    expected = parser_runtime_status(parts, available)
    if status != expected:
        raise ValueError("native manifest parser capability does not match its bundled Python runtime")
