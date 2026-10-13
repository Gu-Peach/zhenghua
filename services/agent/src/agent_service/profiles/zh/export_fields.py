from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class ZhExportFields:
    def terminal_strip(self, device: Any, value: Any, mapping: Mapping[str, str] | None) -> str | None:
        # Keep observed/inferred page-workflow output before any legacy device fallback.
        return str(value).strip() if value not in (None, "") else None

    def terminal(self, device: Any, value: Any) -> str | None:
        if value is None:
            return None
        terminal = str(value).strip()
        if not terminal or terminal in {"*", "PE"} or ":" in terminal:
            return terminal or None
        code = str(device or "").strip().lstrip("-")
        if code.upper() in {"XA", "XH"} or code.upper().startswith("XD"):
            return f"{code}:{terminal}"
        return terminal
