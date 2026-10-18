from __future__ import annotations

import asyncio
import base64
import binascii
import logging
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote

from .agent_bridge import AgentBridge
from .profile_packages import LIMIT, REF, digest, download, object_request, unpack
from .profile_references import ProfileReferences
from .repository import Repository, ServiceError


class ProfileAuthoring:
    def __init__(self, db: Repository) -> None:
        self.db, self.bridge = db, AgentBridge(db)

    async def fork(
        self, identifier: str, draft: str, base_checksum: str, user: str
    ) -> Any:
        """Only the Server resolves published resources and ownership; browsers cannot supply ZIPs."""
        from .profile_contract import ProfileImport

        row = await ProfileReferences(self.db).get(identifier)
        if row["created_by"] != user:
            raise ServiceError(403, "ACCESS_DENIED", "只能编辑自己发布或登记的规则")
        if row["checksum"] != base_checksum:
            raise ServiceError(
                409, "PROFILE_SOURCE_CHANGED", "规则版本已变化，请刷新资源"
            )
        latest = next(
            (
                p
                for p in await ProfileReferences(self.db).list(user)
                if p["profile_key"] == row["profile_key"]
            ),
            None,
        )
        if latest and latest["id"] != identifier:
            raise ServiceError(
                409, "PROFILE_SOURCE_CHANGED", "已有更新版本，请重新查看当前规则"
            )
        content = None
        if row["resource_ref"].startswith("storage://"):
            content = await download(self.db, row)
            await asyncio.to_thread(unpack, content, row["checksum"])
        body = ProfileImport.model_validate(
            {
                "draft_id": draft,
                "profile_id": identifier,
                "profile_key": row["profile_key"],
                "profile_version": row["profile_version"],
                "source_checksum": row["checksum"],
                "display_name": row["display_name"],
                "content_base64": base64.b64encode(content).decode()
                if content is not None
                else None,
            }
        )
        return await self.call("POST", "/imports", user, body.model_dump(mode="json"))

    async def cleanup(self, user: str) -> bool:
        """Retry content-addressed GC after DB retirement; failures do not undo successful publication."""
        try:
            jobs = await self.db.rows(
                "profile_asset_gc",
                {"owner_id": f"eq.{user}", "deleted_at": "is.null", "limit": "20"},
            )
            for job in jobs:
                match = REF.fullmatch(job["resource_ref"])
                if not match or not match[1].startswith(f"profiles/{user}/"):
                    continue
                if await self.db.rows(
                    "extraction_profiles",
                    {"resource_ref": f"eq.{job['resource_ref']}", "limit": "1"},
                ):
                    continue
                response = await object_request(
                    self.db,
                    "DELETE",
                    "/storage/v1/object/project-assets",
                    json={"prefixes": [match[1]]},
                )
                if not response.is_error or response.status_code == 404:
                    await self.db.update(
                        "profile_asset_gc",
                        {
                            "resource_ref": f"eq.{job['resource_ref']}",
                            "owner_id": f"eq.{user}",
                        },
                        {"deleted_at": datetime.now(timezone.utc).isoformat()},
                    )
            return bool(
                await self.db.rows(
                    "profile_asset_gc",
                    {"owner_id": f"eq.{user}", "deleted_at": "is.null", "limit": "1"},
                )
            )
        except (ServiceError, KeyError, ValueError):
            logging.getLogger(__name__).warning(
                "Published Profile storage cleanup deferred"
            )
            return True

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
            source = package.get("source") or {}
            replacing = bool(source.get("profile_id"))
            parameters = {
                "actor": user,
                "profile_key_value": key,
                "version_value": version,
                "name_value": manifest["display_name"],
                "checksum_value": package["checksum"],
                "ref_value": "storage://project-assets/" + path,
            }
            if replacing:
                parameters.update(
                    {
                        "base_profile_id": source["profile_id"],
                        "base_checksum": source["checksum"],
                    }
                )
            row = await self.db.rpc(
                "replace_extraction_profile"
                if replacing
                else "publish_extraction_profile",
                parameters,
            )
        except ServiceError as exc:
            if exc.code == "DATABASE_FUNCTION_MISSING":
                raise ServiceError(
                    503,
                    "PROFILE_PUBLICATION_NOT_READY",
                    "规则发布接口尚未部署，请应用数据库迁移并刷新Schema缓存后重试；草稿无需重做",
                ) from exc
            raise
        if replacing:
            pending = await self.cleanup(user)
            return {
                **row["profile"],
                "can_delete": True,
                "cleanup_pending": pending,
                "previous_version_retained": row["previous_version_retained"],
            }
        return {**row, "can_delete": row["created_by"] == user}
