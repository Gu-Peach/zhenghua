from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

# The downstream import format has a closed vocabulary.  A missing value is
# represented by None (for example SPARE and PE cores), never by a raw device
# name such as XD3.
ALLOWED_TERMINAL_STRIPS = (
    "X0",
    "X1",
    "X21/X23",
    "X22/X24",
    "X3",
    "X4",
    "X5",
    "X21",
    "X22",
    "X23",
    "X24",
    "X6",
    "X61",
)
# Actual X-terminal codes allowed in stage-three endpoint data.  This is
# separate from the normalized import-column terminal-strip vocabulary.
ALLOWED_TERMINAL_CODES = (
    "X0",
    "X21",
    "X22",
    "X23",
    "X24",
    "X3",
    "X4",
    "X5",
)

_ALLOWED_TERMINAL_STRIPS = frozenset(ALLOWED_TERMINAL_STRIPS)

DEFAULT_TERMINAL_STRIP_MAPPING = {
    "XD0": "X0",
    "XA": "X1",
    "XD10": "X1",
    "XD11": "X1",
    "XD12": "X1",
    "XD21": "X21",
    "XD23": "X23",
    "XD22": "X22",
    "XD24": "X24",
    "XD3": "X3",
    "XD5": "X3",
    "XD4": "X4",
    "XH": "X5",
}


def normalize_terminal_strip(
    value: Any,
    mapping: Mapping[str, str] | None = None,
) -> str | None:
    """Return one canonical import value, or None for an unknown value."""
    text = _key(value)
    if not text:
        return None
    if text in _ALLOWED_TERMINAL_STRIPS:
        return text

    aliases = {
        "XD0": "X0",
        "XD21/XD23": "X21/X23",
        "XD22/XD24": "X22/X24",
    }
    mapped = aliases.get(text)
    if mapped:
        return mapped

    active_mapping = mapping or DEFAULT_TERMINAL_STRIP_MAPPING
    mapped = active_mapping.get(text)
    if mapped is None:
        return None
    mapped_text = _key(mapped)
    return mapped_text if mapped_text in _ALLOWED_TERMINAL_STRIPS else None


def terminal_strip_for_device(
    device: Any,
    mapping: Mapping[str, str] | None = None,
) -> str | None:
    """Map a drawing terminal device (e.g. ``-XD3``) to import vocabulary."""
    code = _key(device)
    if not code:
        return None
    active_mapping = mapping or DEFAULT_TERMINAL_STRIP_MAPPING
    return normalize_terminal_strip(active_mapping.get(code), active_mapping)


def validate_terminal_strip_mapping(mapping: Mapping[str, str]) -> dict[str, str]:
    """Normalize and validate a user-provided mapping from `.env`."""
    validated: dict[str, str] = {}
    for key, value in mapping.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError("Terminal strip mapping keys and values must be strings")
        normalized_key = _key(key)
        normalized_value = normalize_terminal_strip(value)
        if not normalized_key or normalized_value is None:
            raise ValueError(
                "Terminal strip mapping values must be one of: " + ", ".join(ALLOWED_TERMINAL_STRIPS)
            )
        validated[normalized_key] = normalized_value
    return validated


def _key(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    text = re.sub(r"\s+", "", text).lstrip("-").upper()
    return text or None
