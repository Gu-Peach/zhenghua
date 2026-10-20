from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote
from uuid import UUID

from .assistant_contract import AssistantScope, FindTargets
from .profile_packages import digest, download, object_request, unpack
from .profile_references import ProfileReferences
from .repository import Repository, ServiceError
from .simple_index import index_drawings
from .simple_management import ManagementService


def normalized(value: str) -> str:
    return re.sub(r"[\W_]+", "", value.casefold())


@dataclass
class BoundProfile:
    row: dict[str, Any]
    manifest: dict[str, Any]
    files: dict[str, bytes]
    content: bytes
    checksum: str
    origin: str

    def facts(self) -> dict[str, Any]:
        rules = {}
        for key in (
            "classification_prompt",
            "page_scan_prompt",
            "cross_page_prompt",
            "routing_rules",
        ):
            path = self.manifest.get("resources", {}).get(key)
            if path in self.files:
                rules[key] = self.files[path].decode("utf-8")[:14000]
        return {
            "key": self.manifest["key"],
            "version": self.manifest["version"],
            "checksum": self.checksum,
            "source": self.origin,
            "rules": rules,
        }


class AssistantEvidence:
    def __init__(self, db: Repository) -> None:
        self.db, self.management = db, ManagementService(db)

    async def resolve(
        self, scope: AssistantScope, user: str
    ) -> tuple[AssistantScope, dict[str, Any]]:
        if not scope.project_id:
            raise ServiceError(422, "ASSISTANT_SCOPE_REQUIRED", "请先定位项目和工作区")
        project = await self.db.require_project(str(scope.project_id), user)
        pages = index_drawings(project)
        result = scope.model_copy(deep=True)
        result.project_name = project["name"]
        matches = pages
        if scope.workspace_code:
            matches = [
                page
                for page in matches
                if normalized(page["workspace_code"])
                == normalized(scope.workspace_code)
            ]
        if scope.workspace_id:
            matches = [
                page
                for page in matches
                if page["workspace_id"] == str(scope.workspace_id)
            ]
        if scope.drawing_id:
            matches = [page for page in matches if page["id"] == str(scope.drawing_id)]
        if scope.pdf_page_number:
            matches = [
                page
                for page in matches
                if page["pdf_page_number"] == scope.pdf_page_number
            ]
        if scope.drawing_page:
            matches = [
                page
                for page in matches
                if normalized(page["workspace_page"] or "")
                == normalized(scope.drawing_page)
            ]
        filtered = any(
            (
                scope.workspace_code,
                scope.workspace_id,
                scope.drawing_id,
                scope.pdf_page_number,
                scope.drawing_page,
            )
        )
        if filtered and not matches:
            raise ServiceError(
                404, "ASSISTANT_SCOPE_NOT_FOUND", "工作区或图纸不属于该项目"
            )
        if matches and filtered:
            codes = {p["workspace_code"] for p in matches}
            if len(codes) == 1:
                result.workspace_code = matches[0]["workspace_code"]
                result.workspace_id = UUID(matches[0]["workspace_id"])
            if any((scope.drawing_id, scope.pdf_page_number, scope.drawing_page)):
                if len(matches) != 1:
                    raise ServiceError(
                        409,
                        "ASSISTANT_SCOPE_AMBIGUOUS",
                        "业务页重名，请指定工作区或PDF物理页",
                    )
                result.drawing_id = UUID(matches[0]["id"])
                result.drawing_page = matches[0]["workspace_page"]
                result.pdf_page_number = matches[0]["pdf_page_number"]
        active_batch = (project.get("drawing_index") or {}).get("active_batch_id")
        # A completed batch can legitimately contain zero connection rows.
        result.batch_id = (
            str(active_batch)
            if scope.batch_id and scope.batch_id == active_batch
            else (await self.management.batch(project, scope.batch_id))
        )
        if scope.connection_ids:
            records = await self.db.rows(
                "extraction_connection_rows",
                {
                    "project_id": f"eq.{scope.project_id}",
                    "id": "in.(" + ",".join(str(i) for i in scope.connection_ids) + ")",
                    **(
                        {"batch_id": f"eq.{result.batch_id}"} if result.batch_id else {}
                    ),
                    "limit": "201",
                },
            )
            if len(records) != len(set(scope.connection_ids)):
                raise ServiceError(
                    409, "ASSISTANT_SCOPE_CHANGED", "所选记录已变化或不属于当前项目批次"
                )
            if result.workspace_code and any(
                r["workspace_code"] != result.workspace_code for r in records
            ):
                raise ServiceError(
                    409, "ASSISTANT_SCOPE_CHANGED", "所选记录不属于该工作区"
                )
            if result.pdf_page_number and any(
                r["source_pdf_page_number"] != result.pdf_page_number for r in records
            ):
                raise ServiceError(
                    409, "ASSISTANT_SCOPE_CHANGED", "所选记录不属于该图纸"
                )
        return result, project

    async def find(
        self, query: FindTargets, user: str, current: AssistantScope
    ) -> dict[str, Any]:
        projects = await self.db.all_rows(
            "extraction_projects",
            {
                "owner_id": f"eq.{user}",
                "status": "neq.archived",
                "order": "created_at.asc,id.asc",
            },
        )
        if query.project_name:
            term = normalized(query.project_name)
            exact = [p for p in projects if normalized(p["name"]) == term]
            projects = exact or [p for p in projects if term in normalized(p["name"])]
        elif current.project_id and (query.workspace_code or query.drawing_page):
            projects = [p for p in projects if p["id"] == str(current.project_id)]
        targets = []
        for project in projects:
            pages = index_drawings(project)
            if not query.workspace_code and not query.drawing_page:
                targets.append(
                    {
                        "scope": {
                            "project_id": project["id"],
                            "project_name": project["name"],
                        },
                        "label": project["name"],
                        "created_at": project["created_at"],
                        "page_count": len(pages),
                    }
                )
                continue
            pages = [
                p
                for p in pages
                if (
                    not query.workspace_code
                    or normalized(p["workspace_code"])
                    == normalized(query.workspace_code)
                )
                and (
                    not query.drawing_page
                    or normalized(p["workspace_page"] or "")
                    == normalized(query.drawing_page)
                )
            ]
            groups: dict[str, list[dict[str, Any]]] = {}
            for page in pages:
                groups.setdefault(
                    page["id"] if query.drawing_page else page["workspace_code"], []
                ).append(page)
            for group in groups.values():
                first = group[0]
                scope = {
                    "project_id": project["id"],
                    "project_name": project["name"],
                    "workspace_code": first["workspace_code"],
                    "workspace_id": first["workspace_id"],
                }
                if query.drawing_page:
                    scope.update(
                        drawing_id=first["id"],
                        drawing_page=first["workspace_page"],
                        pdf_page_number=first["pdf_page_number"],
                    )
                targets.append(
                    {
                        "scope": scope,
                        "label": f"{project['name']} / {first['workspace_code']}"
                        + (
                            f" / {first['workspace_page']}"
                            if query.drawing_page
                            else ""
                        ),
                        "created_at": project["created_at"],
                        "page_count": len(group),
                    }
                )
        return {
            "targets": targets[:50],
            "has_more": len(targets) > 50,
            "event": "selection_required" if len(targets) > 1 else None,
        }

    async def bound_profile(self, scope: AssistantScope, user: str) -> BoundProfile:
        scope, project = await self.resolve(scope, user)
        row = await ProfileReferences(self.db).get(project["profile_id"])
        content: bytes | None = None
        origin = "project_reference"
        if scope.batch_id:
            try:
                UUID(scope.batch_id)
            except ValueError:
                pass
            else:
                rows = await self.db.rows(
                    "agent_artifacts",
                    {
                        "agent_run_id": f"eq.{scope.batch_id}",
                        "artifact_id": f"eq.simple:{scope.batch_id}:profile-package",
                        "select": "payload",
                        "limit": "1",
                    },
                )
                if rows:
                    saved = rows[0]["payload"]["snapshot"]
                    path = saved["path"]
                    if not path.startswith(
                        f"projects/{scope.project_id}/runs/{scope.batch_id}/"
                    ) or ".." in path.split("/"):
                        raise ServiceError(
                            409, "PROFILE_SCOPE_MISMATCH", "历史规则路径不属于项目任务"
                        )
                    response = await object_request(
                        self.db,
                        "GET",
                        "/storage/v1/object/project-assets/" + quote(path, safe="/"),
                    )
                    if (
                        response.is_error
                        or digest(response.content) != saved["checksum"]
                    ):
                        raise ServiceError(
                            409,
                            "FROZEN_PROFILE_UNAVAILABLE",
                            "当次冻结规则包不可用，不能用最新包替代",
                        )
                    content, origin = response.content, "frozen_run_artifact"
        if content is None:
            if not row["resource_ref"].startswith("storage://"):
                raise ServiceError(
                    409,
                    "FROZEN_PROFILE_UNAVAILABLE",
                    "该历史项目未保留可读取的冻结规则包",
                )
            content = await download(self.db, row)
            if digest(content) != row["checksum"]:
                raise ServiceError(
                    409, "FROZEN_PROFILE_UNAVAILABLE", "项目绑定规则的内容摘要不一致"
                )
        checksum = digest(content)
        manifest, files = await asyncio.to_thread(unpack, content, checksum)
        if origin == "project_reference" and (manifest["key"], manifest["version"]) != (
            row["profile_key"],
            row["profile_version"],
        ):
            raise ServiceError(
                409, "PROFILE_SCOPE_MISMATCH", "项目绑定规则与包内版本不一致"
            )
        return BoundProfile(row, manifest, files, content, checksum, origin)

    async def overview(self, scope: AssistantScope, user: str) -> dict[str, Any]:
        scope, project = await self.resolve(scope, user)
        pages = [
            p
            for p in index_drawings(project)
            if not scope.workspace_code or p["workspace_code"] == scope.workspace_code
        ]
        if scope.drawing_id:
            pages = [p for p in pages if p["id"] == str(scope.drawing_id)]
        params = {
            "project_id": f"eq.{scope.project_id}",
            "order": "source_pdf_page_number.asc,row_order.asc",
            "limit": "21",
        }
        if scope.batch_id:
            params["batch_id"] = f"eq.{scope.batch_id}"
        if scope.workspace_code:
            params["workspace_code"] = f"eq.{scope.workspace_code}"
        if scope.pdf_page_number:
            params["source_pdf_page_number"] = f"eq.{scope.pdf_page_number}"
        if scope.connection_ids:
            params["id"] = "in.(" + ",".join(str(i) for i in scope.connection_ids) + ")"
        records = await self.db.rows("extraction_connection_rows", params)
        gaps = []
        profile: dict[str, Any] | None = None
        try:
            profile = (await self.bound_profile(scope, user)).facts()
            if profile["source"] != "frozen_run_artifact":
                gaps.append("只有项目绑定规则，不能证明当次模型的全部执行过程")
        except ServiceError as exc:
            gaps.append(exc.message)
        return {
            "scope": scope.model_dump(mode="json"),
            "pages": [
                {
                    k: p[k]
                    for k in (
                        "id",
                        "workspace_code",
                        "workspace_page",
                        "pdf_page_number",
                        "status",
                    )
                }
                for p in pages[:100]
            ],
            "page_count": len(pages),
            "records": [
                {
                    k: v
                    for k, v in r.items()
                    if k not in {"evidence", "extraction_evidence"}
                }
                for r in records[:20]
            ],
            "has_more_records": len(records) > 20,
            "profile": profile,
            "gaps": gaps,
        }

    async def drawing_bytes(
        self, project: dict[str, Any], numbers: list[int]
    ) -> list[tuple[int, bytes]]:
        images = []
        for page in index_drawings(project):
            if page["pdf_page_number"] not in numbers or not page.get("image_path"):
                continue
            path = page["image_path"]
            if not path.startswith(f"projects/{project['id']}/") or ".." in path.split(
                "/"
            ):
                raise ServiceError(403, "DRAWING_SCOPE_MISMATCH", "原图不属于当前项目")
            response = await object_request(
                self.db,
                "GET",
                "/storage/v1/object/project-assets/" + quote(path, safe="/"),
            )
            if response.is_error:
                raise ServiceError(503, "DRAWING_UNAVAILABLE", "原图读取失败")
            images.append((page["pdf_page_number"], response.content))
        return images
