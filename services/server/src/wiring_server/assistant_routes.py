import secrets
from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, FastAPI, Header, Query, Request, Response
from fastapi.responses import StreamingResponse

from .agent_bridge import AgentBridge
from .assistant_actions import AssistantActions
from .assistant_attachments import AssistantAttachments
from .assistant_contract import (
    AssistantActionDecision,
    AssistantActionRead,
    AssistantAttachmentInput,
    AssistantAttachmentRead,
    AssistantConversationCreate,
    AssistantConversationRead,
    AssistantEvent,
    AssistantToolCall,
    AssistantTurnInput,
)
from .assistant_deletion import AssistantDeletion
from .assistant_service import AssistantService
from .assistant_store import AssistantStore
from .assistant_tools import AssistantTools
from .repository import ServiceError


def install_assistant_routes(app: FastAPI, identity: Any) -> None:
    User = Annotated[str, Depends(identity)]

    @app.get("/api/v1/assistant/capabilities", response_model=dict[str, Any])
    async def capabilities(request: Request, user: User) -> Any:
        try:
            await request.app.state.db.rows(
                "assistant_conversations", {"owner_id": f"eq.{user}", "limit": "1"}
            )
            result = await AgentBridge(request.app.state.db).call(
                "GET", "/v1/assistant/capabilities"
            )
            return {
                "available": bool(result.get("available")),
                "message": "" if result.get("available") else "主助手模型尚未配置",
            }
        except ServiceError:
            return {
                "available": False,
                "message": "主助手服务或数据库尚未就绪，请检查迁移与服务状态",
            }

    @app.post(
        "/api/v1/assistant/conversations", response_model=AssistantConversationRead
    )
    async def create(
        body: AssistantConversationCreate, request: Request, user: User
    ) -> Any:
        return await AssistantStore(request.app.state.db).create(body, user)

    @app.get(
        "/api/v1/assistant/conversations",
        response_model=list[AssistantConversationRead],
    )
    async def conversations(request: Request, user: User) -> Any:
        await AssistantDeletion(request.app.state.db).cleanup(user)
        return await AssistantStore(request.app.state.db).list_conversations(user)

    @app.delete("/api/v1/assistant/conversations/{conversation}", status_code=204)
    async def conversation_delete(
        conversation: UUID, request: Request, user: User
    ) -> Response:
        await AssistantDeletion(request.app.state.db).delete(str(conversation), user)
        return Response(status_code=204)

    @app.get(
        "/api/v1/assistant/conversations/{conversation}",
        response_model=AssistantConversationRead,
    )
    async def conversation_get(
        conversation: UUID,
        request: Request,
        user: User,
        offset: int = Query(0, ge=0, le=100000),
    ) -> Any:
        return await AssistantStore(request.app.state.db).get(
            str(conversation), user, offset
        )

    @app.post(
        "/api/v1/assistant/conversations/{conversation}/attachments",
        response_model=AssistantAttachmentRead,
    )
    async def upload(
        conversation: UUID, body: AssistantAttachmentInput, request: Request, user: User
    ) -> Any:
        return await AssistantAttachments(request.app.state.db).upload(
            str(conversation), user, body
        )

    @app.post(
        "/api/v1/assistant/conversations/{conversation}/turns/stream",
        response_class=StreamingResponse,
        responses={
            200: {
                "model": AssistantEvent,
                "description": "持久化主助手SSE事件",
                "content": {"text/event-stream": {}},
            }
        },
    )
    async def stream(
        conversation: UUID, body: AssistantTurnInput, request: Request, user: User
    ) -> StreamingResponse:
        return await AssistantService(request.app.state.db).stream(
            str(conversation), body, user
        )

    @app.get("/api/v1/assistant/actions/{action}", response_model=AssistantActionRead)
    async def action_get(action: UUID, request: Request, user: User) -> Any:
        return await AssistantActions(request.app.state.db).get(str(action), user)

    @app.post(
        "/api/v1/assistant/actions/{action}/decision",
        response_model=AssistantActionRead,
    )
    async def action_decide(
        action: UUID, body: AssistantActionDecision, request: Request, user: User
    ) -> Any:
        return await AssistantActions(request.app.state.db).decide(
            str(action), user, body
        )

    @app.post(
        "/api/internal/assistant/turns/{turn}/tools", response_model=dict[str, Any]
    )
    async def execute_tool(
        turn: UUID,
        body: AssistantToolCall,
        request: Request,
        token: Annotated[str, Header(alias="X-Assistant-Turn-Token", min_length=32)],
        authorization: Annotated[str | None, Header()] = None,
    ) -> Any:
        expected = request.app.state.db.settings.agent_token
        if expected and not secrets.compare_digest(
            authorization or "", "Bearer " + expected
        ):
            raise ServiceError(403, "ASSISTANT_TOOL_DENIED", "内部服务身份未授权")
        owned = await AssistantStore(request.app.state.db).internal_turn(
            str(turn), token
        )
        return await AssistantTools(request.app.state.db).execute(owned, body)
