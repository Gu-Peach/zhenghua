from __future__ import annotations

from typing import Any

from .agent_bridge import AgentBridge
from .models import RuleCreate
from .repository import Repository, ServiceError


class RuleLibraryService:
    """JWT-scoped lifecycle bridge; Profile assets and registration belong to Agent."""

    def __init__(self, db: Repository, agent: AgentBridge) -> None:
        self.db, self.agent = db, agent

    async def create(self, value: RuleCreate, user: str, token: str) -> dict[str, Any]:
        rows = await self.db.rows(
            "profile_resource_packages",
            {"id": f"eq.{value.base_package_id}"},
            token=token,
        )
        if not rows or rows[0]["status"] != "active":
            raise ServiceError(
                404, "TEMPLATE_UNAVAILABLE", "请选择一个已发布的规则模板"
            )
        result: dict[str, Any] = await self.agent.call(
            "POST",
            "/v1/profiles/packages",
            params={"user_id": user},
            json=value.model_dump(mode="json"),
        )
        return result

    async def remove(
        self, package_id: str, user: str, token: str, confirmed: bool
    ) -> dict[str, Any]:
        if not confirmed:
            raise ServiceError(422, "CONFIRMATION_REQUIRED", "请确认删除规则包")
        rows = await self.db.rows(
            "profile_resource_packages", {"id": f"eq.{package_id}"}, token=token
        )
        if not rows:
            raise ServiceError(404, "PACKAGE_NOT_FOUND", "规则包不存在")
        if rows[0]["created_by"] != user:
            raise ServiceError(403, "PACKAGE_DELETE_DENIED", "只能删除自己创建的规则包")
        result: dict[str, Any] = await self.agent.call(
            "DELETE",
            f"/v1/profiles/packages/{package_id}",
            params={"user_id": user, "confirmed": "true"},
        )
        return result
