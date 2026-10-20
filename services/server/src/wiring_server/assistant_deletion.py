"""Permanently remove assistant history; keep private-file cleanup retryable."""

from __future__ import annotations

import logging

from .profile_packages import object_request
from .repository import Repository, ServiceError


class AssistantDeletion:
    def __init__(self, db: Repository) -> None:
        self.db = db

    async def delete(self, conversation: str, user: str) -> None:
        """Commit history deletion and GC jobs together; never remove domain results."""
        try:
            await self.db.rpc(
                "assistant_delete_conversation",
                {"actor": user, "conversation": conversation},
            )
        except ServiceError as exc:
            if exc.status == 409:
                raise ServiceError(
                    409,
                    "ASSISTANT_CONVERSATION_BUSY",
                    "会话正在回复或保存附件，请完成或停止后再删除",
                ) from exc
            if exc.status == 404:
                raise ServiceError(
                    404, "ASSISTANT_NOT_FOUND", "会话不存在，或无权删除"
                ) from exc
            raise
        await self.cleanup(user)

    async def cleanup(self, user: str) -> None:
        """Retry only the authenticated owner's queued assistant objects, bounded per call."""
        try:
            jobs = await self.db.rows(
                "assistant_asset_gc",
                {
                    "owner_id": f"eq.{user}",
                    "order": "created_at.asc,id.asc",
                    "limit": "20",
                },
            )
            for job in jobs:
                path = job["storage_path"]
                prefix = f"assistant/{user}/{job['conversation_id']}/{job['id']}/"
                if (
                    not path.startswith(prefix)
                    or any(part in {"", ".", ".."} for part in path.split("/"))
                    or "\\" in path
                ):
                    logging.getLogger(__name__).warning(
                        "Invalid assistant cleanup path retained"
                    )
                    continue
                # A client may reuse an old UUID after deletion; never delete a live reference.
                if await self.db.rows(
                    "assistant_attachments",
                    {"storage_path": f"eq.{path}", "limit": "1"},
                ):
                    continue
                response = await object_request(
                    self.db,
                    "DELETE",
                    "/storage/v1/object/project-assets",
                    json={"prefixes": [path]},
                )
                if not response.is_error or response.status_code == 404:
                    await self.db.call(
                        "DELETE",
                        "/rest/v1/assistant_asset_gc",
                        params={"id": f"eq.{job['id']}", "owner_id": f"eq.{user}"},
                    )
        except (ServiceError, KeyError, ValueError):
            logging.getLogger(__name__).warning("Assistant attachment cleanup deferred")
