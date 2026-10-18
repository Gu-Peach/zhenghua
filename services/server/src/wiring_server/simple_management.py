from __future__ import annotations

import asyncio
import hashlib
from typing import Any
from urllib.parse import quote
from uuid import NAMESPACE_URL, uuid5

import httpx
import pymupdf as fitz

from .profile_references import ProfileReferences
from .repository import Repository, ServiceError
from .simple_index import (
    connection_read,
    drawing_id,
    index_drawings,
    project_read,
)
from .simple_models import (
    SimpleConnectionCreate,
    SimpleConnectionDelete,
    SimpleConnectionEdit,
)


class ManagementService:
    """Application service for the three-table data-management contract."""

    def __init__(self, db: Repository) -> None:
        self.db = db
        self.profiles = ProfileReferences(db)

    async def projects(self, user: str, token: str) -> list[dict[str, Any]]:
        projects = await self.db.all_rows(
            "extraction_projects",
            {"owner_id": f"eq.{user}", "order": "created_at.asc,id.asc"},
            token=token,
        )
        if not projects:
            return []
        profiles = {
            row["id"]: row["profile_key"] for row in await self.profiles.list(user)
        }
        return [project_read(row, profiles.get(row["profile_id"])) for row in projects]

    async def detail(self, project: str, user: str) -> dict[str, Any]:
        row = await self.db.require_project(project, user)
        profile = await self.profiles.get(row["profile_id"])
        result = project_read(row, profile["profile_key"])
        result["batch_id"] = await self.batch(row)
        return result

    async def create(
        self, name: str, profile_id: str | None, user: str
    ) -> dict[str, Any]:
        if not profile_id:
            raise ServiceError(422, "PROFILE_REQUIRED", "请选择规则引用")
        profile = await self.profiles.get(profile_id)
        row = await self.db.insert(
            "extraction_projects",
            {"name": name.strip(), "profile_id": profile_id, "owner_id": user},
        )
        return project_read(row, profile["profile_key"])

    async def rename(self, project: str, name: str, user: str) -> dict[str, Any]:
        await self.db.require_project(project, user, write=True)
        await self.db.update(
            "extraction_projects",
            {"id": f"eq.{project}", "owner_id": f"eq.{user}"},
            {"name": name.strip()},
        )
        return await self.detail(project, user)

    async def batch(
        self, project: dict[str, Any], requested: str | None = None
    ) -> str | None:
        chosen = requested or (project.get("drawing_index") or {}).get(
            "active_batch_id"
        )
        rows = await self.db.rows(
            "extraction_connection_rows",
            {
                "project_id": f"eq.{project['id']}",
                "select": "batch_id",
                "order": "created_at.desc,id.desc",
                "limit": "1",
                **({"batch_id": f"eq.{chosen}"} if chosen else {}),
            },
        )
        if requested and not rows:
            raise ServiceError(404, "BATCH_NOT_FOUND", "结果批次不存在")
        return (
            str(rows[0]["batch_id"])
            if rows
            else str(chosen)
            if chosen and not requested
            else None
        )

    async def results(
        self,
        project: str,
        user: str,
        *,
        offset: int,
        limit: int,
        batch: str | None = None,
        workspace: str | None = None,
        drawing: str | None = None,
        search: str = "",
    ) -> dict[str, Any]:
        row = await self.db.require_project(project, user)
        selected = await self.batch(row, batch)
        empty: dict[str, Any] = {
            "items": [],
            "batch_id": selected,
            "offset": offset,
            "limit": limit,
            "has_more": False,
        }
        if selected is None:
            return empty
        params = {
            "project_id": f"eq.{project}",
            "batch_id": f"eq.{selected}",
            "offset": str(offset),
            "limit": str(limit + 1),
            "order": "source_pdf_page_number.asc,row_order.asc,id.asc",
        }
        catalog = index_drawings(row)
        if workspace:
            match = next(
                (page for page in catalog if page["workspace_id"] == workspace), None
            )
            if match is None:
                raise ServiceError(404, "WORKSPACE_NOT_FOUND", "工作区不属于当前项目")
            params["workspace_code"] = f"eq.{match['workspace_code']}"
        if drawing:
            match = self.find_drawing(row, drawing)
            params["source_pdf_page_number"] = f"eq.{match['pdf_page_number']}"
        safe = "".join(char for char in search if char.isalnum() or char in " :_-+")[
            :100
        ]
        if safe:
            params["or"] = (
                "("
                + ",".join(
                    f"{key}.ilike.*{safe}*"
                    for key in [
                        "start_terminal",
                        "end_terminal",
                        "principle_number",
                        "start_description",
                        "end_description",
                    ]
                )
                + ")"
            )
        records = await self.db.rows("extraction_connection_rows", params)
        return {
            **empty,
            "items": [connection_read(record) for record in records[:limit]],
            "has_more": len(records) > limit,
        }

    @staticmethod
    def find_drawing(project: dict[str, Any], identifier: str) -> dict[str, Any]:
        match = next(
            (page for page in index_drawings(project) if page["id"] == identifier), None
        )
        if match is None:
            raise ServiceError(404, "DRAWING_NOT_FOUND", "图纸不在当前项目索引中")
        return match

    @staticmethod
    def asset_path(project: str, path: str) -> str:
        if (
            not path.startswith(f"projects/{project}/")
            or any(part in {"..", ".", ""} for part in path.split("/"))
            or "\\" in path
        ):
            raise ServiceError(409, "UNSAFE_PATH", "文件路径不属于当前项目")
        return path

    async def drawing(self, identifier: str, user: str) -> dict[str, Any]:
        projects = await self.db.all_rows(
            "extraction_projects", {"owner_id": f"eq.{user}", "order": "id.asc"}
        )
        for project in projects:
            for page in index_drawings(project):
                if page["id"] == identifier:
                    return await self.drawing_url(page)
        raise ServiceError(404, "DRAWING_NOT_FOUND", "图纸不存在或无权访问")

    async def drawing_url(self, page: dict[str, Any]) -> dict[str, Any]:
        path = page.get("image_path")
        return {
            **page,
            "image_url": await self.db.signed_url(
                page["image_bucket"], self.asset_path(page["project_id"], path)
            )
            if path
            else None,
        }

    async def connection(
        self, identifier: str, user: str, *, write: bool = False
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        rows = await self.db.rows(
            "extraction_connection_rows", {"id": f"eq.{identifier}", "limit": "1"}
        )
        if not rows:
            raise ServiceError(404, "CONNECTION_NOT_FOUND", "连接不存在")
        project = await self.db.require_project(
            rows[0]["project_id"], user, write=write
        )
        return rows[0], project

    async def target(self, identifier: str, user: str) -> dict[str, Any]:
        row, project = await self.connection(identifier, user)
        if not row["is_cross_page"] or not row.get("target_pdf_page_number"):
            raise ServiceError(404, "TARGET_UNCONFIRMED", "尚未确认跨页目标图纸")
        page = self.find_drawing(
            project, drawing_id(project["id"], row["target_pdf_page_number"])
        )
        return await self.drawing_url(page)

    async def source(self, project: str, user: str) -> dict[str, str]:
        row = await self.db.require_project(project, user)
        if row.get("drawing_index", {}).get("upload_state") != "saved":
            raise ServiceError(409, "SOURCE_NOT_READY", "PDF尚未保存成功，请完成上传")
        path = row.get("source_pdf_path")
        if not path or not row.get("source_pdf_bucket"):
            raise ServiceError(404, "SOURCE_NOT_FOUND", "项目尚未上传PDF")
        return {
            "url": await self.db.signed_url(
                row["source_pdf_bucket"], self.asset_path(project, path)
            )
        }

    async def mutate(
        self,
        project: str,
        user: str,
        action: str,
        key: str,
        *,
        identifier: str | None = None,
        body: SimpleConnectionCreate | SimpleConnectionDelete | SimpleConnectionEdit,
    ) -> dict[str, Any]:
        row = await self.db.require_project(project, user, write=True)
        if row["status"] == "processing":
            raise ServiceError(
                409, "EXTRACTION_IN_PROGRESS", "提取期间结果只读，请等待处理完成"
            )
        payload = body.model_dump(mode="json", exclude_unset=True)
        if isinstance(body, SimpleConnectionCreate):
            source = self.find_drawing(row, str(body.source_drawing_id))
            target = (
                self.find_drawing(row, str(body.target_drawing_id))
                if body.target_drawing_id
                else None
            )
            if not (body.fields.start_terminal or "").strip():
                raise ServiceError(422, "START_REQUIRED", "请填写起点端子")
            payload["source"] = source
            payload["target"] = target
        return await self.db.rpc(
            "manage_extraction_connection",
            {
                "value": {
                    "project_id": project,
                    "actor": user,
                    "action": action,
                    "key": key,
                    "connection_id": identifier,
                    "body": payload,
                }
            },
        )

    async def edit(
        self, identifier: str, user: str, body: SimpleConnectionEdit, key: str
    ) -> dict[str, Any]:
        row, _ = await self.connection(identifier, user, write=True)
        return await self.mutate(
            row["project_id"], user, "edit", key, identifier=identifier, body=body
        )

    async def import_pdf(
        self,
        *,
        content: bytes,
        filename: str,
        name: str,
        key: str,
        user: str,
        profile_key: str,
    ) -> dict[str, Any]:
        def inspect() -> int:
            try:
                with fitz.open(stream=content, filetype="pdf") as document:
                    if document.is_encrypted or document.page_count < 1:
                        raise ValueError("PDF is encrypted or empty")
                    return int(document.page_count)
            except Exception as exc:
                raise ServiceError(422, "INVALID_PDF", "PDF无效、为空或已加密") from exc

        pages = await asyncio.to_thread(inspect)
        profile = await self.profiles.register(profile_key, user)
        identifier = str(uuid5(NAMESPACE_URL, f"simple-import:{user}:{key}"))
        checksum = "sha256:" + hashlib.sha256(content).hexdigest()
        source = {
            "filename": filename,
            "checksum": checksum,
            "size": len(content),
            "page_count": pages,
        }
        existing = await self.db.rows("extraction_projects", {"id": f"eq.{identifier}"})
        if not existing:
            try:
                existing = [
                    await self.db.insert(
                        "extraction_projects",
                        {
                            "id": identifier,
                            "name": name.strip(),
                            "owner_id": user,
                            "profile_id": profile["id"],
                            "source_pdf_bucket": "project-assets",
                            "source_pdf_path": f"projects/{identifier}/source/original.pdf",
                            "drawing_index": {
                                "source": source,
                                "pages": [],
                                "upload_state": "pending",
                            },
                        },
                    )
                ]
            except ServiceError:
                existing = await self.db.rows(
                    "extraction_projects", {"id": f"eq.{identifier}"}
                )
                if not existing:
                    raise
        project = existing[0]
        if (
            project["owner_id"] != user
            or project["profile_id"] != profile["id"]
            or project["name"] != name.strip()
            or project["drawing_index"].get("source") != source
        ):
            raise ServiceError(
                409, "IMPORT_CONFLICT", "相同上传标识对应的内容或规则已变化"
            )
        if project["status"] == "archived":
            raise ServiceError(409, "PROJECT_ARCHIVED", "项目已归档，不能重新上传")
        path = self.asset_path(identifier, project["source_pdf_path"])
        try:
            await self.save_pdf(path, content, checksum)
        except (ServiceError, httpx.HTTPError) as exc:
            await self.db.update(
                "extraction_projects",
                {
                    "id": f"eq.{identifier}",
                    "owner_id": f"eq.{user}",
                    "updated_at": f"eq.{project['updated_at']}",
                },
                {"status": "failed"},
            )
            raise ServiceError(
                503, "UPLOAD_FAILED", "PDF保存失败，可使用相同上传标识重试"
            ) from exc
        if project["drawing_index"].get("upload_state") != "saved":
            updated = await self.db.update(
                "extraction_projects",
                {
                    "id": f"eq.{identifier}",
                    "owner_id": f"eq.{user}",
                    "updated_at": f"eq.{project['updated_at']}",
                },
                {
                    "status": "draft",
                    "drawing_index": {
                        **project["drawing_index"],
                        "upload_state": "saved",
                    },
                },
            )
            if not updated:
                raise ServiceError(409, "IMPORT_CONFLICT", "项目已变化，请刷新后重试")
        run = await self.start_extraction(identifier, user)
        return {
            "project_id": identifier,
            "source_document_id": identifier,
            "attachment_id": identifier,
            "filename": filename,
            "checksum": checksum,
            "size": len(content),
            "page_count": pages,
            "extraction_started": True,
            "run_id": run["run_id"],
        }

    async def start_extraction(
        self, project: str, user: str, *, retry: bool = False
    ) -> dict[str, Any]:
        await self.db.require_project(project, user, write=True)
        return await self.db.rpc(
            "start_simple_extraction",
            {
                "project": project,
                "actor": user,
                "requested_run": str(
                    uuid5(NAMESPACE_URL, f"simple-extraction:{project}")
                ),
                "retry": retry,
            },
        )

    async def extraction_progress(
        self, project: str, user: str
    ) -> dict[str, Any] | None:
        row = await self.db.require_project(project, user)
        return row.get("drawing_index", {}).get("processing")

    async def extraction_events(
        self, project: str, user: str, cursor: int
    ) -> list[dict[str, Any]]:
        row = await self.db.require_project(project, user)
        run = row.get("drawing_index", {}).get("processing", {}).get("run_id")
        if not run:
            return []
        return await self.db.rows(
            "agent_events",
            {
                "agent_run_id": f"eq.{run}",
                "seq": f"gt.{cursor}",
                "order": "seq.asc",
                "limit": "100",
            },
        )

    async def save_pdf(self, path: str, content: bytes, checksum: str) -> None:
        """Immutable upload with checksum verification after duplicate/lost responses."""
        url = (
            self.db.settings.supabase_url
            + f"/storage/v1/object/project-assets/{quote(path, safe='/')}"
        )
        headers = {
            "apikey": self.db.settings.service_key,
            "Authorization": "Bearer " + self.db.settings.service_key,
        }
        try:
            response = await self.db.http.post(
                url,
                content=content,
                headers={
                    **headers,
                    "Content-Type": "application/pdf",
                    "x-upsert": "false",
                },
            )
            if not response.is_error:
                return
        except httpx.HTTPError:
            pass
        stored = await self.db.http.get(url, headers=headers)
        if (
            stored.is_error
            or "sha256:" + hashlib.sha256(stored.content).hexdigest() != checksum
        ):
            raise ServiceError(503, "UPLOAD_FAILED", "PDF保存失败")

    async def delete_project(self, project: str, user: str, updated_at: str) -> None:
        row = await self.db.require_project(project, user, owner=True)
        if row["updated_at"] != updated_at:
            raise ServiceError(409, "VERSION_CONFLICT", "项目已改变，请刷新再删除")
        if await self.db.rows(
            "agent_runs",
            {
                "project_id": f"eq.{project}",
                "status": "in.(QUEUED,RUNNING,WAITING_INPUT)",
                "limit": "1",
            },
        ):
            raise ServiceError(409, "ACTIVE_RUN", "请先结束项目处理任务")
        if await self.db.rows(
            "connection_rescan_runs",
            {
                "project_id": f"eq.{project}",
                "status": "in.(queued,running)",
                "limit": "1",
            },
        ):
            raise ServiceError(409, "ACTIVE_RESCAN", "请先取消或结束项目重扫任务")
        assets: dict[str, list[str]] = {}
        details = await self.db.all_rows(
            "connection_rescan_assets",
            {"project_id": f"eq.{project}", "order": "id.asc"},
        )
        assets["project-assets"] = [
            self.asset_path(project, item["storage_path"]) for item in details
        ]
        if row.get("source_pdf_path"):
            assets.setdefault(row["source_pdf_bucket"], []).append(
                self.asset_path(project, row["source_pdf_path"])
            )
        for page in index_drawings(row):
            if page.get("image_path"):
                assets.setdefault(page["image_bucket"], []).append(
                    self.asset_path(project, page["image_path"])
                )
        progress = row.get("drawing_index", {}).get("processing") or {}
        if progress.get("run_id"):
            # Include assets uploaded before a lost metadata response, plus the frozen Profile.
            run = str(progress["run_id"])
            prefix = self.asset_path(project, f"projects/{project}/runs/{run}")
            paths = assets.setdefault("project-assets", [])
            paths.append(f"{prefix}/profile.zip")
            total = int(
                row.get("drawing_index", {}).get("source", {}).get("page_count", 0)
            )
            paths.extend(
                f"{prefix}/pages/{number}.png" for number in range(1, total + 1)
            )
        archived = await self.db.update(
            "extraction_projects",
            {
                "id": f"eq.{project}",
                "owner_id": f"eq.{user}",
                "updated_at": f"eq.{updated_at}",
            },
            {"status": "archived"},
        )
        if not archived:
            raise ServiceError(409, "VERSION_CONFLICT", "项目已变化")
        for bucket, paths in assets.items():
            for start in range(0, len(paths), 100):
                await self.db.call(
                    "DELETE",
                    f"/storage/v1/object/{quote(bucket, safe='')}",
                    json={"prefixes": sorted(set(paths[start : start + 100]))},
                )
        await self.db.call(
            "DELETE",
            "/rest/v1/extraction_projects",
            params={
                "id": f"eq.{project}",
                "owner_id": f"eq.{user}",
                "status": "eq.archived",
                "updated_at": f"eq.{archived[0]['updated_at']}",
            },
        )
