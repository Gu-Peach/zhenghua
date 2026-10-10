from __future__ import annotations

import asyncio
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ..domain.enums import ErrorCode
from ..domain.errors import AgentServiceError


@dataclass(frozen=True, slots=True)
class SourceDocumentAccess:
    document_id: str
    project_id: str
    local_path: Path
    checksum: str


class SourceDocumentProvider(Protocol):
    async def get(self, document_id: str, project_id: str) -> SourceDocumentAccess: ...


class InMemorySourceDocumentProvider:
    """Controlled development adapter; callers register paths outside HTTP payloads."""

    def __init__(self) -> None:
        self._documents: dict[tuple[str, str], SourceDocumentAccess] = {}
        self._lock = asyncio.Lock()

    async def register(self, document_id: str, project_id: str, local_path: Path) -> None:
        path, checksum = await asyncio.to_thread(_resolve_document, local_path)
        async with self._lock:
            self._documents[(project_id, document_id)] = SourceDocumentAccess(
                document_id=document_id,
                project_id=project_id,
                local_path=path,
                checksum=checksum,
            )

    async def get(self, document_id: str, project_id: str) -> SourceDocumentAccess:
        async with self._lock:
            value = self._documents.get((project_id, document_id))
        if value is None:
            raise AgentServiceError(
                ErrorCode.PROJECT_CONTEXT_NOT_FOUND,
                "The source document is not registered with the Agent runtime.",
                retryable=False,
                details={"document_id": document_id, "project_id": project_id},
            )
        return value


def _resolve_document(local_path: Path) -> tuple[Path, str]:
    path = local_path.resolve()
    if not path.is_file():
        raise FileNotFoundError(path)
    return path, f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"
