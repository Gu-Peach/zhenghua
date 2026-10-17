from typing import Annotated, Any

from fastapi import Depends, FastAPI, Request
from fastapi.responses import StreamingResponse

from .explain_contract import ExplainEvent, ExplainTurn
from .explain_service import ExplainService


def install_explain_routes(app: FastAPI, identity: Any) -> None:
    User = Annotated[str, Depends(identity)]

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
