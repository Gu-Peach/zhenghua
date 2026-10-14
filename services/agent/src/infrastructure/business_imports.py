from __future__ import annotations

import hashlib
from typing import Any
from uuid import NAMESPACE_URL, UUID, uuid5

from src.domain.errors import AgentServiceError
from src.domain.models.imports import ImportedDocument, ProjectResultsResponse, ProjectTreeResponse
from src.infrastructure.storage_paths import project_source_pdf_path
from src.infrastructure.supabase_client import SupabaseClient


class SupabaseBusinessImports:
    """Immutable source reservation and owner-scoped read models using existing tables."""

    def __init__(self, client: SupabaseClient, *, bucket: str = "project-assets") -> None:
        self._client, self._bucket = client, bucket

    async def import_pdf(
        self, *, user_id: str, key: str, name: str, filename: str, content: bytes, page_count: int
    ) -> ImportedDocument:
        owner = str(UUID(user_id))
        project_id = str(uuid5(NAMESPACE_URL, f"agent-import:{owner}:{key}"))
        document_id = str(uuid5(NAMESPACE_URL, f"agent-import-source:{project_id}"))
        checksum = "sha256:" + hashlib.sha256(content).hexdigest()
        await self._reserve("projects", {
            "id": project_id, "owner_id": owner, "name": name, "status": "draft",
        }, ("owner_id", "name"))
        path = project_source_pdf_path(project_id)
        # Reserve checksum first: concurrent differing payloads cannot overwrite the source object.
        await self._reserve("document_files", {
            "id": document_id, "project_id": project_id, "kind": "source_pdf",
            "original_filename": filename, "storage_bucket": self._bucket, "storage_path": path,
            "checksum": checksum, "mime_type": "application/pdf", "size_bytes": len(content),
        }, ("project_id", "original_filename", "checksum", "storage_bucket", "storage_path"))
        try:
            await self._client.upload(
                bucket=self._bucket, object_path=path, content=content,
                content_type="application/pdf", upsert=False,
            )
        except AgentServiceError:
            # Retry after a lost response or an existing immutable object: verify, never replace.
            stored = await self._client.download(bucket=self._bucket, object_path=path)
            if "sha256:" + hashlib.sha256(stored).hexdigest() != checksum:
                raise ValueError("Stored source does not match the reserved checksum.") from None
        return ImportedDocument(
            project_id=project_id, source_document_id=document_id, attachment_id=document_id,
            filename=filename, checksum=checksum, size=len(content), page_count=page_count,
        )

    async def _reserve(self, table: str, row: dict[str, Any], fields: tuple[str, ...]) -> None:
        filters = {"id": f"eq.{row['id']}", "limit": "1"}
        existing = await self._client.select(table, params=filters)
        if not existing:
            try:
                await self._client.insert(table, row)
                return
            except AgentServiceError:
                existing = await self._client.select(table, params=filters)
                if not existing:
                    raise
        if any(existing[0].get(field) != row[field] for field in fields):
            raise ValueError("Idempotency-Key was reused with different import input.")

    async def require_owner(self, project_id: str, user_id: str) -> dict[str, Any]:
        rows = await self._client.select("projects", params={
            "id": f"eq.{UUID(project_id)}", "owner_id": f"eq.{UUID(user_id)}", "limit": "1",
        })
        if not rows:
            raise PermissionError("Project is absent or not owned by this user.")
        return rows[0]

    async def existing_extraction(self, project_id: str, document_id: str) -> str | None:
        rows = await self._client.select("agent_runs", params={
            "project_id": f"eq.{project_id}", "source_document_id": f"eq.{document_id}",
            "idempotency_key": f"eq.full-extraction:{document_id}", "run_type": "eq.FULL_EXTRACTION",
            "select": "id", "limit": "1",
        })
        return str(rows[0]["id"]) if rows else None

    async def tree(self, project_id: str, user_id: str) -> ProjectTreeResponse:
        project = await self.require_owner(project_id, user_id)
        sources = await self._client.select("document_files", params={
            "project_id": f"eq.{project_id}", "kind": "eq.source_pdf",
            "select": "id,original_filename,checksum,size_bytes", "order": "created_at.asc",
        })
        snapshot = project.get("published_classification_snapshot_id")
        workspaces: list[dict[str, Any]] = []
        if snapshot:
            workspaces = await self._all_rows("workspaces", params={
                "project_id": f"eq.{project_id}", "classification_snapshot_id": f"eq.{snapshot}",
                "order": "sort_order.asc,id.asc",
            })
            drawings = await self._all_rows("drawings", params={
                "project_id": f"eq.{project_id}", "classification_snapshot_id": f"eq.{snapshot}",
                "order": "pdf_page_number.asc,id.asc",
            })
            for workspace in workspaces:
                workspace["drawings"] = [d for d in drawings if d["workspace_id"] == workspace["id"]]
        return ProjectTreeResponse(
            project_id=project_id, name=project["name"], published_snapshot_id=snapshot,
            sources=sources, workspaces=workspaces,
        )

    async def _all_rows(self, table: str, *, params: dict[str, str]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        while True:
            batch = await self._client.select(
                table, params={**params, "offset": str(len(rows)), "limit": "1000"},
            )
            rows.extend(batch)
            if len(batch) < 1000:
                return rows

    async def results(
        self, project_id: str, user_id: str, *, version: str | None, offset: int, limit: int
    ) -> ProjectResultsResponse:
        await self.require_owner(project_id, user_id)
        params = {"project_id": f"eq.{project_id}", "order": "version.desc", "limit": "1"}
        if version:
            params["id"] = f"eq.{UUID(version)}"
        versions = await self._client.select("result_versions", params=params)
        if not versions:
            if version:
                raise ValueError("Result version does not belong to this project.")
            return ProjectResultsResponse(project_id=project_id, offset=offset, limit=limit,
                                          items=[], has_more=False)
        selected = versions[0]
        items = await self._client.select("wiring_connection_rows", params={
            "project_id": f"eq.{project_id}", "result_version_id": f"eq.{selected['id']}",
            "order": "wire_number.asc,core_order.asc,connection_id.asc",
            "offset": str(offset), "limit": str(limit + 1),
        })
        return ProjectResultsResponse(
            project_id=project_id, result_version_id=selected["id"], result_version=selected["version"],
            result_revision=int(selected.get("revision") or 1),
            offset=offset, limit=limit, items=items[:limit], has_more=len(items) > limit,
        )
