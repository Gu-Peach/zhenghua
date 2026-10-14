from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path
from typing import Protocol
from uuid import uuid4

from src.domain.enums import ErrorCode
from src.domain.errors import AgentServiceError
from src.domain.models.correction import CorrectionEvidenceBundle
from src.agent.extraction_agent.domain.models.extraction_stages import DrawingPageInput
from src.infrastructure.supabase_client import SupabaseClient


class CorrectionDataProvider(Protocol):
    async def get_bundle(self, feedback_id: str) -> CorrectionEvidenceBundle: ...


class CorrectionDataRepository(CorrectionDataProvider, Protocol):
    async def materialize_page(self, page: DrawingPageInput) -> DrawingPageInput: ...

    async def register(
        self,
        bundle: CorrectionEvidenceBundle,
        requested_by: str | None = None,
    ) -> None: ...


class InMemoryCorrectionDataProvider:
    def __init__(self) -> None:
        self._bundles: dict[str, CorrectionEvidenceBundle] = {}
        self._lock = asyncio.Lock()

    async def register(
        self,
        bundle: CorrectionEvidenceBundle,
        requested_by: str | None = None,
    ) -> None:
        _ = requested_by
        async with self._lock:
            self._bundles[bundle.facts.feedback_id] = bundle.model_copy(deep=True)

    async def get_bundle(self, feedback_id: str) -> CorrectionEvidenceBundle:
        async with self._lock:
            bundle = self._bundles.get(feedback_id)
        if bundle is None:
            raise AgentServiceError(
                ErrorCode.PROJECT_CONTEXT_NOT_FOUND,
                f"Feedback {feedback_id!r} was not found.",
                retryable=False,
            )
        return bundle.model_copy(deep=True)

    async def materialize_page(self, page: DrawingPageInput) -> DrawingPageInput:
        return page


class SupabaseCorrectionDataRepository:
    """Durable correction context consumed by scoped correction workers."""

    def __init__(self, client: SupabaseClient, *, cache_root: Path) -> None:
        self._client = client
        self._cache_root = cache_root.resolve()

    async def register(
        self,
        bundle: CorrectionEvidenceBundle,
        requested_by: str | None = None,
    ) -> None:
        target = bundle.facts.target
        existing = await self._client.select(
            "feedback_items", params={"id": f"eq.{bundle.facts.feedback_id}"}
        )
        if existing:
            previous = CorrectionEvidenceBundle.model_validate(existing[0]["correction_bundle"])
            if (
                previous.facts != bundle.facts
                or previous.context.field != bundle.context.field
                or previous.context.suggested_value != bundle.context.suggested_value
                or previous.base_result_version != bundle.base_result_version
            ):
                raise ValueError("Feedback id already exists with different correction input.")
            return  # Never reset accepted feedback to prepared on a network retry.
        await self._client.insert(
            "feedback_items",
            {
                "id": bundle.facts.feedback_id,
                "project_id": target.project_id,
                "target_type": target.type.value,
                "target_id": target.id,
                "target_field": target.field,
                "issue_kind": bundle.facts.issue_kind.value,
                "status": "prepared",
                "requested_by": requested_by,
                "base_result_version": bundle.base_result_version,
                "base_result_version_id": target.result_version_id,
                "correction_bundle": bundle.model_dump(mode="json"),
            },
        )

    async def get_bundle(self, feedback_id: str) -> CorrectionEvidenceBundle:
        rows = await self._client.select(
            "feedback_items",
            params={"id": f"eq.{feedback_id}", "limit": "1"},
        )
        if not rows:
            raise AgentServiceError(
                ErrorCode.PROJECT_CONTEXT_NOT_FOUND,
                f"Feedback {feedback_id!r} was not found.",
                retryable=False,
            )
        bundle = CorrectionEvidenceBundle.model_validate(rows[0]["correction_bundle"])
        bundle.page_classification_requests = [
            request.model_copy(update={"page": await self._materialize(bundle, request.page)})
            for request in bundle.page_classification_requests
        ]
        bundle.page_scan_requests = [
            request.model_copy(update={"page": await self._materialize(bundle, request.page)})
            for request in bundle.page_scan_requests
        ]
        bundle.cross_page_requests = [
            request.model_copy(update={"target_page": await self._materialize(bundle, request.target_page)})
            for request in bundle.cross_page_requests
        ]
        return bundle

    async def _materialize(
        self,
        bundle: CorrectionEvidenceBundle,
        page: DrawingPageInput,
    ) -> DrawingPageInput:
        if not page.storage_bucket or not page.storage_path:
            if await asyncio.to_thread(page.image_path.is_file):
                return page
            raise AgentServiceError(
                ErrorCode.SOURCE_ARTIFACT_EXPIRED,
                "Correction drawing does not have a durable Storage reference.",
                retryable=False,
            )
        name = f"{page.drawing_id or page.pdf_page_number}.png"
        destination = self._cache_root / bundle.facts.target.project_id / name
        if not await asyncio.to_thread(destination.is_file):
            content = await self._client.download(
                bucket=page.storage_bucket,
                object_path=page.storage_path,
            )
            await asyncio.to_thread(_atomic_write, destination, content)
        return page.model_copy(update={"image_path": destination})

    async def materialize_page(self, page: DrawingPageInput) -> DrawingPageInput:
        if not page.storage_bucket or not page.storage_path:
            if page.image_path.is_file():
                return page
            raise ValueError("No durable drawing reference.")
        digest = hashlib.sha256(f"{page.storage_bucket}/{page.storage_path}".encode()).hexdigest()
        path = self._cache_root / "targets" / f"{digest}.png"
        if not path.is_file():
            content = await self._client.download(bucket=page.storage_bucket, object_path=page.storage_path)
            await asyncio.to_thread(_atomic_write, path, content)
        return page.model_copy(update={"image_path": path})


def _atomic_write(destination: Path, content: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    temporary.write_bytes(content)
    os.replace(temporary, destination)
