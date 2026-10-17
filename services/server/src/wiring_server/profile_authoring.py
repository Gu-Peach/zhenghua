from __future__ import annotations

import asyncio
import base64
import binascii
from typing import Any
from urllib.parse import quote

from .agent_bridge import AgentBridge
from .profile_packages import LIMIT, digest, object_request, unpack
from .repository import Repository, ServiceError


class ProfileAuthoring:
    def __init__(self, db: Repository) -> None:
        self.db, self.bridge = db, AgentBridge(db)

    async def call(
        self, method: str, path: str, user: str, body: dict[str, Any] | None = None
    ) -> Any:
        return await self.bridge.call(
            method,
            "/v1/profile" + path,
            headers={"X-Profile-User-Id": user},
            **({"json": body} if body is not None else {}),
        )

    async def publish(self, draft: str, revision: int, user: str) -> dict[str, Any]:
        package = await self.call(
            "POST", f"/drafts/{draft}/publication", user, {"revision": revision}
        )
        try:
            content = base64.b64decode(package["content_base64"], validate=True)
        except (KeyError, binascii.Error) as exc:
            raise ServiceError(
                502, "PROFILE_PACKAGE_INVALID", "规则助手没有返回有效资源包"
            ) from exc
        if len(content) > LIMIT:
            raise ServiceError(413, "PROFILE_PACKAGE_TOO_LARGE", "规则包超过30MiB")
        manifest, _ = await asyncio.to_thread(unpack, content, package["checksum"])
        key, version = manifest["key"], manifest["version"]
        import re

        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", key) or not re.fullmatch(
            r"\d+\.\d+\.\d+", version
        ):
            raise ServiceError(
                422, "PROFILE_IDENTITY_INVALID", "规则标识或版本格式错误"
            )
        # Content addressed upload can be retried after DB failure; an existing blob is verified.
        path = f"profiles/{user}/{key}/{version}/{digest(content)[7:]}.zip"
        url = "/storage/v1/object/project-assets/" + quote(path, safe="/")
        response = await object_request(
            self.db,
            "POST",
            url,
            content=content,
            headers={
                "Content-Type": "application/zip",
                "x-upsert": "false",
            },
        )
        if response.is_error:
            if response.status_code not in {400, 409}:
                raise ServiceError(
                    503, "PROFILE_STORAGE_FAILED", "规则包存储失败，可重试"
                )
            existing = await object_request(self.db, "GET", url)
            if existing.is_error or digest(existing.content) != package["checksum"]:
                raise ServiceError(409, "PROFILE_STORAGE_CONFLICT", "规则包存储冲突")
        try:
            row = await self.db.rpc(
                "publish_extraction_profile",
                {
                    "actor": user,
                    "profile_key_value": key,
                    "version_value": version,
                    "name_value": manifest["display_name"],
                    "checksum_value": package["checksum"],
                    "ref_value": "storage://project-assets/" + path,
                },
            )
        except ServiceError as exc:
            if exc.code == "DATABASE_FUNCTION_MISSING":
                raise ServiceError(
                    503,
                    "PROFILE_PUBLICATION_NOT_READY",
                    "规则发布接口尚未部署，请应用数据库迁移并刷新Schema缓存后重试；草稿无需重做",
                ) from exc
            raise
        return {**row, "can_delete": row["created_by"] == user}
