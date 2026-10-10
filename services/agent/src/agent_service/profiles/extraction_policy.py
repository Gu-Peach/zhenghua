from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any, Protocol

from ..domain.models.drawing_index import DrawingIndex
from ..domain.models.wiring import WireConnection, WireRecord
from .export_fields import ExportFields


class ExtractionPolicy(Protocol):
    """Template-owned deterministic behavior used by the document Graph."""

    @property
    def export_fields(self) -> ExportFields: ...
    def project_identity(self, text: str) -> tuple[str | None, str | None]: ...

    def build_drawing_index(self, path: Path) -> DrawingIndex: ...
    def parse_references(self, page: Any) -> list[Any]: ...
    def prepare_reference(
        self, raw: Mapping[str, Any], *, source_page: Mapping[str, Any], drawing_index: Mapping[str, Any]
    ) -> dict[str, Any]: ...
    def normalize_record(self, record: WireRecord, mapping: Mapping[str, str]) -> WireRecord: ...
    def orient_connection(self, connection: WireConnection) -> tuple[WireConnection | None, bool]: ...
    def validated_current(self, value: Any, basis: str | None, source_text: str | None) -> str | None: ...
    def validate_record(self, record: WireRecord, mapping: Mapping[str, str]) -> list[str]: ...


class ExtractionPolicyRegistry:
    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], ExtractionPolicy]] = {}

    def register(self, adapter: str, factory: Callable[[], ExtractionPolicy]) -> None:
        self._factories[adapter] = factory

    def resolve(self, adapter: str) -> ExtractionPolicy:
        factory = self._factories.get(adapter)
        if factory is None:
            raise ValueError(f"No deterministic extraction policy is registered for {adapter!r}.")
        return factory()


def default_extraction_policies() -> ExtractionPolicyRegistry:
    from .zh.policy import ZhExtractionPolicy

    registry = ExtractionPolicyRegistry()
    registry.register("zh_native", ZhExtractionPolicy)
    return registry
