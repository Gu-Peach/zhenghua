from __future__ import annotations

from ..domain.models.extraction_stages import (
    CrossPageCompletionData,
    CrossPageCompletionRequest,
    PageClassificationData,
    PageClassificationRequest,
    PageScanData,
    PageScanRequest,
)
from ..domain.ports import ExtractionStageAdapter


class ProfileBoundStageDispatcher:
    """Resolve each stage implementation through the locked Profile adapter key."""

    def __init__(self) -> None:
        self._adapters: dict[str, ExtractionStageAdapter] = {}

    def register(self, adapter_key: str, adapter: ExtractionStageAdapter) -> None:
        normalized = adapter_key.strip()
        if not normalized:
            raise ValueError("adapter_key is required.")
        if normalized in self._adapters:
            raise ValueError(f"Stage adapter {normalized!r} is already registered.")
        self._adapters[normalized] = adapter

    async def classify_page(self, request: PageClassificationRequest) -> PageClassificationData:
        return await self._adapter(request.profile.adapter).classify_page(request)

    async def scan_page(self, request: PageScanRequest) -> PageScanData:
        return await self._adapter(request.profile.adapter).scan_page(request)

    async def resolve_cross_page(
        self,
        request: CrossPageCompletionRequest,
    ) -> CrossPageCompletionData:
        return await self._adapter(request.profile.adapter).resolve_cross_page(request)

    def _adapter(self, adapter_key: str) -> ExtractionStageAdapter:
        try:
            return self._adapters[adapter_key]
        except KeyError as exc:
            raise ValueError(f"No extraction stage adapter is registered for {adapter_key!r}.") from exc
