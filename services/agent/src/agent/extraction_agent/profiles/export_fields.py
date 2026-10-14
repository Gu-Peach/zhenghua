from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


class ExportFields(Protocol):
    def terminal_strip(self, device: Any, value: Any, mapping: Mapping[str, str] | None) -> str | None: ...
    def terminal(self, device: Any, value: Any) -> str | None: ...


class PreparedExportFields:
    """Default writers consume values already normalized by a Profile."""

    def terminal_strip(self, device: Any, value: Any, mapping: Mapping[str, str] | None) -> str | None:
        return str(value).strip() or None if value is not None else None

    def terminal(self, device: Any, value: Any) -> str | None:
        return str(value).strip() or None if value is not None else None


PREPARED_EXPORT_FIELDS = PreparedExportFields()
