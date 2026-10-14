from __future__ import annotations

from typing import Any, Protocol

from src.agent.extraction_agent.domain.models.image_payload import ImagePayload


class DocumentStageClient(Protocol):
    async def classify_page(self, image: ImagePayload, *, context_text: str = "") -> Any: ...

    async def scan_page(self, image: ImagePayload, *, page_context: str = "") -> Any: ...

    async def resolve_cross_page(
        self,
        target_image: ImagePayload,
        *,
        source_image: ImagePayload | None = None,
        task_context: str = "",
    ) -> Any: ...
