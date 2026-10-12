from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any
from uuid import UUID

import httpx
from fastapi.responses import StreamingResponse

from .models import SupervisorTurn
from .repository import Repository, ServiceError


class AgentBridge:
    """Authenticated bridge to :8100; client identity never comes from request bodies."""

    def __init__(self, db: Repository) -> None:
        self.db = db

    async def call(self, method: str, path: str, **kwargs: Any) -> Any:
        response = await self.open(method, path, **kwargs)
        try:
            await response.aread()
            return response.json()
        finally:
            await response.aclose()

    async def open(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        headers = kwargs.pop("headers", {})
        if self.db.settings.agent_token:
            headers["Authorization"] = "Bearer " + self.db.settings.agent_token
        request = self.db.http.build_request(
            method, self.db.settings.agent_url + path, headers=headers, **kwargs
        )
        try:
            response = await self.db.http.send(request, stream=True)
        except httpx.HTTPError as exc:
            raise ServiceError(
                503, "AGENT_UNAVAILABLE", "Agent 服务未启动或不可用"
            ) from exc
        if response.is_error:
            await response.aread()
            status = response.status_code
            rule_error = None
            if path.startswith("/v1/profiles/packages"):
                try:
                    detail = response.json().get("detail")
                    if isinstance(detail, dict):
                        messages = {
                            "TEMPLATE_UNAVAILABLE": "请选择一个已发布的规则模板",
                            "PROFILE_KEY_EXISTS": "规则标识已占用，请使用新的标识",
                            "PROFILE_KEY_RETIRED": "该规则标识已停用，请使用新的标识",
                            "PACKAGE_DELETE_DENIED": "只能删除自己创建的规则包",
                            "PACKAGE_NOT_FOUND": "规则包不存在",
                            "PACKAGE_NOT_PUBLISHED": "未发布候选请通过候选审核流程处理",
                            "PACKAGE_INVALID": "规则包资源校验失败",
                            "UNSUPPORTED_ADAPTER": "当前模板的提取适配器尚未实现",
                            "PACKAGE_STORAGE_FAILED": "规则包存储失败，可重试",
                        }
                        code = detail.get("code")
                        if isinstance(code, str) and code in messages:
                            rule_error = ServiceError(status, code, messages[code])
                except (ValueError, AttributeError):
                    pass
            await response.aclose()
            if rule_error is not None:
                raise rule_error
            if status == 401:
                # This is the Server->Agent credential, not the browser's JWT.
                raise ServiceError(
                    502,
                    "AGENT_SERVICE_AUTH_FAILED",
                    "Server 与 Agent 内部鉴权配置不匹配，请检查服务配置",
                )
            raise ServiceError(
                status, "AGENT_REQUEST_FAILED", "Agent 请求失败，请检查任务状态"
            )
        return response

    async def stream(self, method: str, path: str, **kwargs: Any) -> StreamingResponse:
        response = await self.open(method, path, **kwargs)

        async def chunks() -> AsyncIterator[bytes]:
            try:
                async for chunk in response.aiter_bytes():
                    yield chunk
            finally:
                await response.aclose()

        return StreamingResponse(
            chunks(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    async def require_run(
        self, run_id: str, user: str, *, write: bool = False
    ) -> dict[str, Any]:
        rows = await self.db.rows(
            "agent_runs", {"id": f"eq.{UUID(run_id)}", "limit": "1"}
        )
        if not rows:
            raise ServiceError(404, "RUN_NOT_FOUND", "任务不存在")
        await self.db.require_project(rows[0]["project_id"], user, write=write)
        return rows[0]

    async def turn(self, turn: SupervisorTurn, user: str) -> StreamingResponse:
        if turn.project_id:
            await self.db.require_project(str(turn.project_id), user, write=True)
        hints = turn.target_hint
        if hints.get("agent_run_id"):
            run = await self.require_run(hints["agent_run_id"], user, write=True)
            if turn.project_id and run["project_id"] != str(turn.project_id):
                raise ServiceError(403, "SCOPE_MISMATCH", "任务不属于当前项目")
        if hints.get("proposal_id"):
            rows = await self.db.rows(
                "result_proposals", {"id": f"eq.{hints['proposal_id']}"}
            )
            if not rows:
                raise ServiceError(404, "PROPOSAL_NOT_FOUND", "修订建议不存在")
            await self.db.require_project(rows[0]["project_id"], user, write=True)
            if turn.project_id and rows[0]["project_id"] != str(turn.project_id):
                raise ServiceError(403, "SCOPE_MISMATCH", "修订建议不属于当前项目")
        # UUID-only attachments are checked against the authenticated user's source documents.
        for attachment in turn.attachment_ids:
            rows = await self.db.rows("document_files", {"id": f"eq.{attachment}"})
            if not rows:
                raise ServiceError(403, "ATTACHMENT_DENIED", "文件不存在或无访问权限")
            await self.db.require_project(rows[0]["project_id"], user, write=True)
            if turn.project_id and rows[0]["project_id"] != str(turn.project_id):
                raise ServiceError(403, "SCOPE_MISMATCH", "附件不属于当前项目")
        return await self.stream(
            "POST",
            "/v1/supervisor/turns/stream",
            json={**turn.model_dump(mode="json"), "user_id": user},
        )
