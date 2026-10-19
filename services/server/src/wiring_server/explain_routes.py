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
    RescanAsset,
    RescanDecision,
    RescanEvidenceImage,
    RescanRun,
    RescanUpload,
)
from .explain_edits import ExplainEdits
from .explain_rescan import ExplainRescan
from .explain_service import ExplainService


def install_explain_routes(app: FastAPI, identity: Any) -> None:
    User = Annotated[str, Depends(identity)]

    @app.post("/api/v1/projects/{project}/rescan-assets", response_model=RescanAsset)
    async def rescan_image(
        project: UUID, body: RescanUpload, request: Request, user: User
    ) -> Any:
        return await ExplainRescan(request.app.state.db).upload(
            str(project), user, body
        )

    @app.get(
        "/api/v1/projects/{project}/rescan-assets/{asset}",
        response_model=dict[str, str],
    )
    async def rescan_image_url(
        project: UUID, asset: UUID, request: Request, user: User
    ) -> Any:
        return await ExplainRescan(request.app.state.db).asset_url(
            str(project), str(asset), user
        )

    @app.get(
        "/api/v1/projects/{project}/rescans/{run}/evidence",
        response_model=list[RescanEvidenceImage],
    )
    async def rescan_evidence(
        project: UUID, run: UUID, request: Request, user: User
    ) -> Any:
        return await ExplainRescan(request.app.state.db).evidence(
            str(project), str(run), user
        )

    @app.get(
        "/api/v1/projects/{project}/rescans",
        response_model=list[RescanRun],
        response_model_exclude_unset=True,
    )
    async def rescan_list(project: UUID, request: Request, user: User) -> Any:
        return await ExplainRescan(request.app.state.db).list_runs(str(project), user)

    @app.get(
        "/api/v1/projects/{project}/rescans/{run}",
        response_model=RescanRun,
        response_model_exclude_unset=True,
    )
    async def rescan_get(project: UUID, run: UUID, request: Request, user: User) -> Any:
        return await ExplainRescan(request.app.state.db).get(
            str(project), str(run), user
        )

    @app.post(
        "/api/v1/projects/{project}/rescans/{run}/decision",
        response_model=RescanRun,
        response_model_exclude_unset=True,
    )
    async def rescan_decide(
        project: UUID, run: UUID, body: RescanDecision, request: Request, user: User
    ) -> Any:
        return await ExplainRescan(request.app.state.db).decide(
            str(project), str(run), user, body
        )

    @app.post(
        "/api/v1/projects/{project}/rescans/{run}/cancel",
        response_model=RescanRun,
        response_model_exclude_unset=True,
    )
    async def rescan_cancel(
        project: UUID, run: UUID, request: Request, user: User
    ) -> Any:
        return await ExplainRescan(request.app.state.db).decide(
            str(project), str(run), user, None
        )

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
