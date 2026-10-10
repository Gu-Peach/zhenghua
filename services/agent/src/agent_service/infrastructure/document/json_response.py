from __future__ import annotations

import json
import re
from typing import Any


def _loads_json(content: str) -> Any:
    raw = content.strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", raw, re.IGNORECASE | re.DOTALL)
    raw = fenced.group(1) if fenced else raw
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if 0 <= start < end:
            return json.loads(raw[start : end + 1])
        start, end = raw.find("["), raw.rfind("]")
        if 0 <= start < end:
            return json.loads(raw[start : end + 1])
        raise


def _extract_json_candidate(raw: str) -> str:
    try:
        _loads_json(raw)
        return raw
    except json.JSONDecodeError:
        start, end = raw.find("{"), raw.rfind("}")
        if 0 <= start < end:
            return raw[start : end + 1]
        start, end = raw.find("["), raw.rfind("]")
        return raw[start : end + 1] if 0 <= start < end else raw
