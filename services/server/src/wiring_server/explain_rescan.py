"""Private screenshot assets and immutable rescan candidates; no model calls in Server."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import struct
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import pymupdf

from .explain_contract import (
    RescanAsset,
    RescanDecision,
    RescanEvidenceImage,
    RescanRun,
    RescanUpload,
)
from .repository import Repository, ServiceError


def image_dimensions(raw: bytes) -> tuple[int, int]:
    """Read bounded raster headers before asking the decoder to allocate pixels."""
    if raw.startswith(b"\x89PNG\r\n\x1a\n"):
        return struct.unpack(">II", raw[16:24])
    if raw.startswith(b"\xff\xd8"):
        offset = 2
        while offset + 4 <= len(raw):
            if raw[offset] != 255:
                raise ValueError("JPEG marker")
            while raw[offset] == 255:
                offset += 1
            marker = raw[offset]
            offset += 1
            if marker in {0x01, *range(0xD0, 0xD9)}:
                continue
            length = int.from_bytes(raw[offset : offset + 2], "big")
            if marker in {
                0xC0,
                0xC1,
                0xC2,
                0xC3,
                0xC5,
                0xC6,
                0xC7,
                0xC9,
                0xCA,
                0xCB,
                0xCD,
                0xCE,
                0xCF,
            }:
                height, width = struct.unpack(">HH", raw[offset + 3 : offset + 7])
                return width, height
            if length < 2:
                break
            offset += length
    if raw.startswith(b"RIFF") and raw[8:12] == b"WEBP":
        if raw[12:16] == b"VP8X":
            return 1 + int.from_bytes(raw[24:27], "little"), 1 + int.from_bytes(
                raw[27:30], "little"
            )
        if raw[12:16] == b"VP8L" and raw[20] == 0x2F:
            bits = int.from_bytes(raw[21:25], "little")
            return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
        if raw[12:16] == b"VP8 ":
            width, height = struct.unpack("<HH", raw[26:30])
            return width & 0x3FFF, height & 0x3FFF
    raise ValueError("Unsupported raster header")


def normalize_detail(value: str) -> tuple[bytes, int, int]:
    try:
        raw = base64.b64decode(value, validate=True)
        if len(raw) > 8_000_000:
            raise ValueError("size")
        if not (
            raw.startswith((b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff"))
            or raw.startswith(b"RIFF")
            and raw[8:12] == b"WEBP"
        ):
            raise ValueError("format")
        width, height = image_dimensions(raw)
        if width < 1 or height < 1 or width * height > 20_000_000:
            raise ValueError("pixels")
        image = pymupdf.Pixmap(raw)
        if image.width * image.height > 20_000_000:
            raise ValueError("decoded pixels")
        if image.colorspace and image.colorspace.n != 3:
            image = pymupdf.Pixmap(pymupdf.csRGB, image)
        content = image.tobytes("png")
        if len(content) > 12_000_000:
            raise ValueError("normalized size")
        return content, image.width, image.height
    except Exception as exc:
        raise ServiceError(
            422,
            "INVALID_DETAIL_IMAGE",
            "请上传8MB以内的PNG、JPEG或WebP图片（不超过2000万像素）",
        ) from exc


class ExplainRescan:
    def __init__(self, db: Repository) -> None:
        self.db = db

    async def upload(self, project: str, user: str, body: RescanUpload) -> RescanAsset:
        current = await self.db.require_project(project, user, write=True)
        pages = current.get("drawing_index", {}).get("pages", [])
        if (
            sum(page.get("pdf_page_number") == body.pdf_page_number for page in pages)
            != 1
        ):
            raise ServiceError(
                422, "DETAIL_PAGE_UNKNOWN", "请先为截图选择本项目中的原页或关联页"
            )
        content, width, height = await asyncio.to_thread(
            normalize_detail, body.content_base64
        )
        digest = "sha256:" + hashlib.sha256(content).hexdigest()
        identifier = str(
            uuid5(
                NAMESPACE_URL,
                f"rescan-asset:{project}:{user}:{body.conversation_id}:{body.pdf_page_number}:{body.role}:{digest}",
            )
        )
        existing = await self.db.rows(
            "connection_rescan_assets",
            {
                "id": f"eq.{identifier}",
                "created_by": f"eq.{user}",
                "project_id": f"eq.{project}",
                "limit": "1",
            },
        )
        if existing and existing[0].get("uploaded"):
            return RescanAsset.model_validate(
                {key: existing[0][key] for key in RescanAsset.model_fields}
            )
        path = (
            f"projects/{project}/explain/{body.conversation_id}/assets/{identifier}.png"
        )
        row = (
            existing[0]
            if existing
            else await self.db.insert(
                "connection_rescan_assets",
                {
                    "id": identifier,
                    "created_by": user,
                    "project_id": project,
                    "conversation_id": str(body.conversation_id),
                    "pdf_page_number": body.pdf_page_number,
                    "role": body.role,
                    "storage_path": path,
                    "checksum": digest,
                    "width": width,
                    "height": height,
                    "uploaded": False,
                },
            )
        )
        await self.db.call(
            "POST",
            f"/storage/v1/object/project-assets/{path}",
            content=content,
            headers={"Content-Type": "image/png", "x-upsert": "true"},
        )
        stored = await self.db.update(
            "connection_rescan_assets",
            {
                "id": f"eq.{identifier}",
                "project_id": f"eq.{project}",
                "created_by": f"eq.{user}",
            },
            {"uploaded": True},
        )
        try:
            if not stored:
                raise ServiceError(
                    409, "DETAIL_PROJECT_CHANGED", "项目已删除或截图状态已变化"
                )
            await self.db.require_project(project, user, write=True)
        except ServiceError as exc:
            if exc.status in {403, 404, 409}:
                await self.db.call(
                    "DELETE",
                    "/storage/v1/object/project-assets",
                    json={"prefixes": [path]},
                )
            raise
        return RescanAsset.model_validate(
            {key: row[key] for key in RescanAsset.model_fields}
        )

    async def asset_url(
        self, project: str, identifier: str, user: str
    ) -> dict[str, str]:
        await self.db.require_project(project, user)
        rows = await self.db.rows(
            "connection_rescan_assets",
            {
                "id": f"eq.{identifier}",
                "project_id": f"eq.{project}",
                "created_by": f"eq.{user}",
                "limit": "1",
            },
        )
        if not rows or not rows[0].get("uploaded"):
            raise ServiceError(404, "DETAIL_NOT_FOUND", "截图不存在或无权访问")
        return {
            "url": await self.db.signed_url("project-assets", rows[0]["storage_path"])
        }

    async def get(self, project: str, identifier: str, user: str) -> RescanRun:
        await self.db.require_project(project, user)
        rows = await self.db.rows(
            "connection_rescan_runs",
            {
                "id": f"eq.{identifier}",
                "project_id": f"eq.{project}",
                "created_by": f"eq.{user}",
                "limit": "1",
                "select": ",".join(RescanRun.model_fields),
            },
        )
        if not rows:
            raise ServiceError(
                404, "RESCAN_NOT_FOUND", "重扫任务不存在、关联记录已删除或无权访问"
            )
        return RescanRun.model_validate(rows[0])

    async def list_runs(self, project: str, user: str) -> list[RescanRun]:
        await self.db.require_project(project, user)
        rows = await self.db.rows(
            "connection_rescan_runs",
            {
                "project_id": f"eq.{project}",
                "created_by": f"eq.{user}",
                "status": "in.(queued,running,ready,failed)",
                "order": "created_at.desc",
                "limit": "20",
                "select": ",".join(RescanRun.model_fields),
            },
        )
        return [RescanRun.model_validate(row) for row in rows]

    async def decide(
        self, project: str, identifier: str, user: str, body: RescanDecision | None
    ) -> RescanRun:
        await self.db.require_project(project, user, write=True)
        if body and body.accepted:
            current = await self.get(project, identifier, user)
            if current.request.result_mode == "replace_scope":
                if not current.candidate or not current.candidate.replacement:
                    raise ServiceError(
                        409,
                        "RESCAN_REPLACEMENT_REQUIRED",
                        "全量替换候选不完整，请重新发起重扫",
                    )
                try:
                    contract = await self.db.rpc("rescan_replacement_contract", {})
                except ServiceError as exc:
                    raise ServiceError(
                        503,
                        "RESCAN_REPLACEMENT_UNAVAILABLE",
                        "范围替换事务尚未部署，旧线表未改动；请先应用新迁移",
                    ) from exc
                if type(contract) is not int or contract != 1:
                    raise ServiceError(
                        503,
                        "RESCAN_REPLACEMENT_UNAVAILABLE",
                        "数据库尚不支持范围替换，旧线表未改动",
                    )
            elif (
                current.status == "ready"
                and current.request.resolved_mode() == "replace_scope"
            ):
                raise ServiceError(
                    409,
                    "RESCAN_REPLACEMENT_REQUIRED",
                    "旧版全量候选不能按范围替换提交，请重新重扫",
                )
        value: dict[str, Any] = {"project_id": project, "id": identifier, "actor": user}
        value.update(body.model_dump(mode="json") if body else {"action": "cancel"})
        result = await self.db.rpc("decide_connection_rescan", {"value": value})
        return RescanRun.model_validate(result)

    async def evidence(
        self, project: str, identifier: str, user: str
    ) -> list[RescanEvidenceImage]:
        await self.get(project, identifier, user)
        rows = await self.db.rows(
            "connection_rescan_runs",
            {
                "id": f"eq.{identifier}",
                "project_id": f"eq.{project}",
                "created_by": f"eq.{user}",
                "select": "project_snapshot,attachment_ids,checkpoint",
                "limit": "1",
            },
        )
        if not rows:
            raise ServiceError(404, "RESCAN_NOT_FOUND", "重扫任务已删除或不可访问")
        run = rows[0]
        used = {
            int(key.split(":", 1)[1])
            for key in run["checkpoint"]
            if key.startswith("image:") and key.split(":", 1)[1].isdigit()
        }
        result: list[RescanEvidenceImage] = []
        for page in run["project_snapshot"]["pages"]:
            number = page["pdf_page_number"]
            if number not in used or len(result) >= 8:
                continue
            path = page.get("image_path", "")
            url = None
            if (
                path.startswith(f"projects/{project}/")
                and ".." not in path.split("/")
                and page.get("image_bucket", "project-assets") == "project-assets"
            ):
                try:
                    url = await self.db.signed_url("project-assets", path)
                except ServiceError:
                    pass
            result.append(
                RescanEvidenceImage(
                    id=f"page:{number}",
                    title=f"原图 · {page.get('drawing_page') or '未识别页'} · PDF {number}",
                    pdf_page_number=number,
                    image_url=url,
                )
            )
        for asset in run["attachment_ids"]:
            try:
                data = await self.asset_url(project, asset, user)
            except ServiceError:
                data = {}
            result.append(
                RescanEvidenceImage(
                    id=asset, title="用户上传的辅助细节图", image_url=data.get("url")
                )
            )
        return result
