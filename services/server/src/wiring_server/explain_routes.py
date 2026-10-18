from typing import Annotated, Any
from uuid import UUID

from fastapi import Depends, FastAPI, Request
from fastapi.responses import StreamingResponse

from .explain_contract import (
    ConnectionEditDecision,
    ConnectionEditProposal,
    ConnectionEditReceipt,
    ExplainEvent,
    ExplainTurn,
)
from .explain_edits import ExplainEdits
from .explain_service import ExplainService


def install_explain_routes(app: FastAPI, identity: Any) -> None:
    User = Annotated[str, Depends(identity)]

    @app.get(
        "/api/v1/projects/{project}/connection-edits",
        response_model=list[ConnectionEditProposal],
    )
    async def edits(project: UUID, request: Request, user: User) -> Any:
        return await ExplainEdits(request.app.state.db).list(str(project), user)

    @app.get(
        "/api/v1/projects/{project}/connection-edits/{proposal}",
        response_model=ConnectionEditProposal,
    )
    async def edit(project: UUID, proposal: UUID, request: Request, user: User) -> Any:
        return await ExplainEdits(request.app.state.db).get(
            str(project), str(proposal), user
        )

    @app.post(
        "/api/v1/projects/{project}/connection-edits/{proposal}/decision",
        response_model=ConnectionEditReceipt,
    )
    async def decide_edit(
        project: UUID,
        proposal: UUID,
        body: ConnectionEditDecision,
        request: Request,
        user: User,
    ) -> Any:
        return await ExplainEdits(request.app.state.db).decide(
            str(project), str(proposal), user, body
        )

    @app.post(
        "/api/v1/explain/turns/stream",
        response_class=StreamingResponse,
        responses={
            200: {
                "model": ExplainEvent,
                "description": "SSE公开事件，data为ExplainEvent。",
                "content": {"text/event-stream": {}},
            }
        },
    )
    async def explain(
        body: ExplainTurn, request: Request, user: User
    ) -> StreamingResponse:
        return await ExplainService(request.app.state.db).stream(body, user)
