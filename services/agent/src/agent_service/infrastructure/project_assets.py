from __future__ import annotations

import asyncio
import hashlib
import json
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from ..domain.enums import ErrorCode
from ..domain.errors import AgentServiceError
from ..domain.models.runs import AgentRun
from .source_documents import SourceDocumentAccess, SourceDocumentProvider
from .storage_paths import drawing_image_path, project_source_pdf_path, run_artifact_path
from .supabase_client import SupabaseClient


@dataclass(frozen=True, slots=True)
class PublishedProjectAssets:
    project_id: str
    workspace_count: int
    drawing_count: int
    object_paths: list[str]


class SupabaseProjectAssetStore:
    """Persist source PDFs and classified page images in the project tree."""

    def __init__(self, client: SupabaseClient, *, bucket: str = "project-assets") -> None:
        self._client = client
        self._bucket = bucket

    async def upload_source_pdf(
        self,
        *,
        project_id: str,
        document_id: str,
        original_filename: str,
        pdf_path: Path,
    ) -> SourceDocumentAccess:
        project_id = str(UUID(project_id))
        document_id = str(UUID(document_id))
        resolved, content = await asyncio.to_thread(_read_file, pdf_path)
        checksum = f"sha256:{hashlib.sha256(content).hexdigest()}"
        object_path = project_source_pdf_path(project_id)
        await self._client.upload(
            bucket=self._bucket,
            object_path=object_path,
            content=content,
            content_type="application/pdf",
        )
        await self._client.insert(
            "document_files",
            {
                "id": document_id,
                "project_id": project_id,
                "kind": "source_pdf",
                "original_filename": Path(original_filename).name,
                "storage_bucket": self._bucket,
                "storage_path": object_path,
                "checksum": checksum,
                "mime_type": "application/pdf",
                "size_bytes": len(content),
            },
            on_conflict="id",
            upsert=True,
        )
        return SourceDocumentAccess(
            document_id=document_id,
            project_id=project_id,
            local_path=resolved,
            checksum=checksum,
        )

    async def publish_extraction_pages(
        self,
        run: AgentRun,
        output_dir: Path,
    ) -> PublishedProjectAssets:
        project_id = str(UUID(run.project_id))
        index_path = output_dir / "agent" / "drawing_index.json"
        index = await asyncio.to_thread(_read_json_object, index_path)
        pages = index.get("pages")
        if not isinstance(pages, list):
            raise ValueError("Drawing index must contain a pages array.")

        workspace_rows: dict[str, dict[str, Any]] = {}
        drawing_rows: list[dict[str, Any]] = []
        object_paths: list[str] = []
        for sort_order, page in enumerate(pages):
            if not isinstance(page, dict):
                continue
            pdf_page = int(page.get("pdf_page") or 0)
            if pdf_page < 1:
                continue
            workspace_code = str(page.get("function") or "UNKNOWN").lstrip("=").strip() or "UNKNOWN"
            workspace_id = str(uuid5(NAMESPACE_URL, f"zhenghua:{project_id}:workspace:{workspace_code}"))
            drawing_id = str(uuid5(NAMESPACE_URL, f"zhenghua:{project_id}:drawing:{pdf_page}"))
            workspace_rows.setdefault(
                workspace_id,
                {
                    "id": workspace_id,
                    "project_id": project_id,
                    "code": workspace_code,
                    "name": workspace_code,
                    "sort_order": sort_order,
                },
            )
            image_path = await asyncio.to_thread(_find_page_image, output_dir, page)
            if image_path is None:
                raise FileNotFoundError(f"Rendered image for PDF page {pdf_page} was not found.")
            content = await asyncio.to_thread(image_path.read_bytes)
            object_path = drawing_image_path(project_id, workspace_id, drawing_id)
            await self._client.upload(
                bucket=self._bucket,
                object_path=object_path,
                content=content,
                content_type=mimetypes.guess_type(image_path.name)[0] or "image/png",
            )
            object_paths.append(object_path)
            internal_page = page.get("internal_page")
            drawing_rows.append(
                {
                    "id": drawing_id,
                    "project_id": project_id,
                    "workspace_id": workspace_id,
                    "pdf_page_number": pdf_page,
                    "workspace_page": str(internal_page) if internal_page is not None else None,
                    "image_bucket": self._bucket,
                    "image_path": object_path,
                    "status": "classified",
                }
            )

        if workspace_rows:
            await self._client.insert(
                "workspaces",
                list(workspace_rows.values()),
                on_conflict="id",
                upsert=True,
            )
        if drawing_rows:
            await self._client.insert(
                "drawings",
                drawing_rows,
                on_conflict="id",
                upsert=True,
            )
        return PublishedProjectAssets(
            project_id=project_id,
            workspace_count=len(workspace_rows),
            drawing_count=len(drawing_rows),
            object_paths=object_paths,
        )

    async def upload_run_artifact(
        self,
        *,
        project_id: str,
        run_id: str,
        stage: str,
        file_path: Path,
    ) -> dict[str, Any]:
        resolved, content = await asyncio.to_thread(_read_file, file_path)
        object_path = run_artifact_path(project_id, run_id, stage, resolved.name)
        await self._client.upload(
            bucket=self._bucket,
            object_path=object_path,
            content=content,
            content_type=mimetypes.guess_type(resolved.name)[0] or "application/octet-stream",
        )
        return {
            "name": resolved.name,
            "storage_bucket": self._bucket,
            "storage_path": object_path,
            "checksum": f"sha256:{hashlib.sha256(content).hexdigest()}",
            "size_bytes": len(content),
        }


class SupabaseSourceDocumentProvider(SourceDocumentProvider):
    """Resolve a private source PDF to a verified local runtime cache."""

    def __init__(self, client: SupabaseClient, *, cache_root: Path) -> None:
        self._client = client
        self._cache_root = cache_root.resolve()

    async def get(self, document_id: str, project_id: str) -> SourceDocumentAccess:
        document_id = str(UUID(document_id))
        project_id = str(UUID(project_id))
        rows = await self._client.select(
            "document_files",
            params={
                "id": f"eq.{document_id}",
                "project_id": f"eq.{project_id}",
                "kind": "eq.source_pdf",
                "limit": "1",
            },
        )
        if not rows:
            raise AgentServiceError(
                ErrorCode.PROJECT_CONTEXT_NOT_FOUND,
                "The source document is not registered in Supabase.",
                retryable=False,
                details={"document_id": document_id, "project_id": project_id},
            )
        row = rows[0]
        content = await self._client.download(
            bucket=str(row["storage_bucket"]),
            object_path=str(row["storage_path"]),
        )
        checksum = f"sha256:{hashlib.sha256(content).hexdigest()}"
        if checksum != row["checksum"]:
            raise AgentServiceError(
                ErrorCode.SOURCE_ARTIFACT_EXPIRED,
                "The source document checksum does not match its database record.",
                retryable=False,
            )
        destination = self._cache_root / project_id / document_id / "original.pdf"
        await asyncio.to_thread(_atomic_write, destination, content)
        return SourceDocumentAccess(
            document_id=document_id,
            project_id=project_id,
            local_path=destination,
            checksum=checksum,
        )


def _read_file(path: Path) -> tuple[Path, bytes]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise FileNotFoundError(resolved)
    return resolved, resolved.read_bytes()


def _read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Expected a JSON object in {path}.")
    return payload


def _find_page_image(output_dir: Path, page: dict[str, Any]) -> Path | None:
    pdf_page = int(page["pdf_page"])
    function = str(page.get("function") or "UNKNOWN").upper().lstrip("=")
    safe_function = "".join(char if char.isalnum() or char in ".-_" else "_" for char in function)
    internal_page = page.get("internal_page")
    label = str(int(internal_page)) if internal_page is not None else f"pdf_{pdf_page:04d}"
    folder = output_dir / "pages" / (safe_function or "UNKNOWN")
    candidates = (
        folder / f"{label}.png",
        folder / f"{label}__pdf_{pdf_page:04d}.png",
    )
    return next((candidate for candidate in candidates if candidate.is_file()), None)


def _atomic_write(destination: Path, content: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    temporary.write_bytes(content)
    os.replace(temporary, destination)
