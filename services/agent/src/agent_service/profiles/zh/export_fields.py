from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .terminal_strips import normalize_terminal_strip, terminal_strip_for_device


class ZhExportFields:
    def terminal_strip(self, device: Any, value: Any, mapping: Mapping[str, str] | None) -> str | None:
        return terminal_strip_for_device(device, mapping) or normalize_terminal_strip(value, mapping)

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
