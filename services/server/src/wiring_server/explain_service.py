from __future__ import annotations

from fastapi.responses import StreamingResponse

from .agent_bridge import AgentBridge
from .explain_contract import ExplainTurn
from .repository import Repository


class ExplainService:
    """Validate the current project, then forward a read-only turn using trusted identity."""

    def __init__(self, db: Repository) -> None:
        self.db = db
        self.agent = AgentBridge(db)

    async def stream(self, turn: ExplainTurn, user: str) -> StreamingResponse:
        await self.db.require_project(str(turn.project_id), user)
        return await self.agent.stream(
            "POST",
            "/v1/explain/turns/stream",
            headers={"X-Explain-User-Id": user},
            json=turn.model_dump(mode="json"),
        )
