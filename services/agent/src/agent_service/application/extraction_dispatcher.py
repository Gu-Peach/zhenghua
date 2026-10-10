from __future__ import annotations

from ..domain.models.extraction import ExtractionExecutionResult, LegacyExtractionRequest
from ..domain.ports import ExtractionAdapter


class ProfileBoundExtractionDispatcher:
    """Dispatch extraction by the adapter declared in a locked ProfileBinding."""

    def __init__(self) -> None:
        self._adapters: dict[str, ExtractionAdapter] = {}

    def register(self, adapter_key: str, adapter: ExtractionAdapter) -> None:
        normalized = adapter_key.strip()
        if not normalized:
            raise ValueError("adapter_key is required.")
        if normalized in self._adapters:
            raise ValueError(f"Extraction adapter {normalized!r} is already registered.")
        self._adapters[normalized] = adapter

    async def run_full(self, request: LegacyExtractionRequest) -> ExtractionExecutionResult:
        adapter = self._adapters.get(request.profile.adapter)
        if adapter is None:
            raise ValueError(f"No extraction adapter is registered for {request.profile.adapter!r}.")
        return await adapter.run_full(request)
