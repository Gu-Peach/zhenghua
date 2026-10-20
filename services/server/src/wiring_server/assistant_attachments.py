from __future__ import annotations

import asyncio
import base64
from pathlib import PurePath
from typing import Any
from urllib.parse import quote

import pymupdf

from .assistant_contract import AssistantAttachmentInput, AssistantAttachmentRead
from .assistant_store import AssistantStore, public_fields
from .explain_rescan import normalize_detail
from .profile_packages import digest, object_request
from .repository import Repository, ServiceError


class AssistantAttachments:
    def __init__(self, db: Repository) -> None:
        self.db, self.store = db, AssistantStore(db)

    async def upload(
        self, conversation: str, user: str, body: AssistantAttachmentInput
    ) -> AssistantAttachmentRead:
        await self.store.owned("assistant_conversations", conversation, user)
        if body.project_id:
            await self.db.require_project(str(body.project_id), user)
        if body.role == "pdf":

            def inspect() -> bytes:
                try:
                    content = base64.b64decode(body.content_base64, validate=True)
                    if len(content) > 50 * 1024 * 1024:
                        raise ValueError("size")
                    with pymupdf.open(stream=content, filetype="pdf") as document:
                        if document.is_encrypted or document.page_count < 1:
                            raise ValueError("empty/encrypted")
                    return content
                except Exception as exc:
                    raise ServiceError(
                        422, "INVALID_PDF", "请上传50MiB以内的有效PDF"
                    ) from exc

            content, mime = await asyncio.to_thread(inspect), "application/pdf"
        else:
            content, _, _ = await asyncio.to_thread(
                normalize_detail, body.content_base64
            )
            mime = "image/png"
        checksum = digest(content)
        existing = await self.db.rows(
            "assistant_attachments", {"id": f"eq.{body.id}", "limit": "1"}
        )
        if existing:
            row = await self.store.owned("assistant_attachments", str(body.id), user)
            if row["conversation_id"] != conversation or row["checksum"] != checksum:
                raise ServiceError(409, "ATTACHMENT_CONFLICT", "附件标识已用于其他内容")
        else:
            row = await self.db.insert(
                "assistant_attachments",
                {
                    "id": str(body.id),
                    "conversation_id": conversation,
                    "owner_id": user,
                    "project_id": str(body.project_id) if body.project_id else None,
                    "filename": PurePath(body.filename.replace("\\", "/")).name,
                    "mime_type": mime,
                    "role": body.role,
                    "pdf_page_number": body.pdf_page_number,
                    "checksum": checksum,
                    "uploaded": False,
                    "storage_path": f"assistant/{user}/{conversation}/{body.id}/{checksum[7:]}",
                },
            )
        if not row["uploaded"]:
            response = await object_request(
                self.db,
                "POST",
                "/storage/v1/object/project-assets/" + row["storage_path"],
                content=content,
                headers={"Content-Type": mime, "x-upsert": "true"},
            )
            if response.is_error:
                raise ServiceError(
                    503, "ATTACHMENT_UPLOAD_FAILED", "附件保存失败，可以重试"
                )
            await self.db.update(
                "assistant_attachments", {"id": f"eq.{body.id}"}, {"uploaded": True}
            )
        return AssistantAttachmentRead.model_validate(
            public_fields(AssistantAttachmentRead, row)
        )

    async def rows(
        self, conversation: str, identifiers: list[str], user: str
    ) -> list[dict[str, Any]]:
        result = []
        for identifier in identifiers:
            row = await self.store.owned("assistant_attachments", identifier, user)
            if row["conversation_id"] != conversation or not row["uploaded"]:
                raise ServiceError(
                    403, "ATTACHMENT_DENIED", "附件不属于当前会话或尚未保存"
                )
            result.append(row)
        return result

    async def content(self, row: dict[str, Any]) -> bytes:
        prefix = f"assistant/{row['owner_id']}/{row['conversation_id']}/{row['id']}/"
        if not row["storage_path"].startswith(prefix) or ".." in row[
            "storage_path"
        ].split("/"):
            raise ServiceError(403, "ATTACHMENT_DENIED", "附件路径无效")
        response = await object_request(
            self.db,
            "GET",
            "/storage/v1/object/project-assets/" + quote(row["storage_path"], safe="/"),
        )
        if response.is_error or digest(response.content) != row["checksum"]:
            raise ServiceError(409, "ATTACHMENT_CHANGED", "附件不可用或校验失败")
        return response.content
