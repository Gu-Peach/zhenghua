"""Read-only projection of structured model outputs; no hidden reasoning or prompts."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

_PRIVATE = {
    "reasoning",
    "reasoning_content",
    "chain_of_thought",
    "thinking",
    "thoughts",
    "thought",
    "scratchpad",
    "internal_reasoning",
    "analysis",
    "authorization",
    "api_key",
    "service_role_key",
    "signed_url",
    "signedurl",
    "image_url",
}


def safe_output(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: safe_output(item) for key, item in value.items() if str(key).lower() not in _PRIVATE}
    if isinstance(value, list):
        return [safe_output(item) for item in value]
    if isinstance(value, str):
        value = re.sub(r"<(think|analysis|thinking)\b[^>]*>.*?</\1>", "", value, flags=re.I | re.S)
        value = re.split(r"<(?:think|analysis|thinking)\b", value, maxsplit=1, flags=re.I)[0]
    return value


def model_output_view(key: str, index: int, trace: Mapping[str, Any]) -> dict[str, Any]:
    raw = trace.get("response_content")
    output = None
    if isinstance(raw, str):
        raw = str(safe_output(raw)).strip()
        fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.I | re.S)
        try:
            output = safe_output(json.loads(fenced.group(1) if fenced else raw))
        except ValueError:
            pass  # Malformed/free-form text is not a public reasoning channel.
    metadata = trace.get("metadata") or {}
    return {
        "trace_id": f"{key}:{index}",
        "agent": trace.get("agent"),
        "model": trace.get("model"),
        "profile": safe_output(metadata.get("profile")),
        "profile_version": metadata.get("profile_version"),
        "prompt_checksum": metadata.get("prompt_checksum"),
        "stage": metadata.get("stage"),
        "item_id": metadata.get("item_id"),
        "duration_seconds": trace.get("duration_seconds"),
        "attempts": trace.get("attempts"),
        "usage": safe_output(trace.get("usage") or {}),
        "output": output,
        "output_available": output is not None,
        "error_type": trace.get("error_type"),
        "schema_error": safe_output(trace.get("schema_error")),
    }
