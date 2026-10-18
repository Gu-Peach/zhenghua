"""Comparable request hashes without persisting messages, credentials or image URLs."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any


def request_fingerprint(
    *, model: str, messages: Sequence[Mapping[str, Any]], temperature: float,
    max_tokens: int | None, json_mode: bool, thinking: bool | None,
) -> str:
    """Match the local RecordingGateway cache key; run IDs and file paths are not inputs."""
    return hashlib.sha256(json.dumps(
        {
            "model": model, "messages": messages, "temperature": temperature,
            "max_tokens": max_tokens, "json_mode": json_mode, "thinking": thinking,
        }, ensure_ascii=False, sort_keys=True,
    ).encode()).hexdigest()
