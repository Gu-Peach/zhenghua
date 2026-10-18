"""The business Server is the only caller that can confirm an Explain modification."""

from __future__ import annotations

from typing import Any

from .explain_contract import (
    ConnectionEditDecision,
    ConnectionEditProposal,
    ConnectionEditReceipt,
)
from .repository import Repository, ServiceError


class ExplainEdits:
    def __init__(self, db: Repository) -> None:
        self.db = db

    async def list(self, project: str, user: str) -> list[ConnectionEditProposal]:
        await self.db.require_project(project, user)
        rows = await self.db.rows(
            "connection_edit_proposals",
            {
                "project_id": f"eq.{project}",
                "created_by": f"eq.{user}",
                "status": "eq.pending",
                "order": "created_at.desc",
                "limit": "20",
                "select": ",".join(ConnectionEditProposal.model_fields),
            },
        )
        return [
            ConnectionEditProposal.model_validate(
                {key: row[key] for key in ConnectionEditProposal.model_fields}
            )
            for row in rows
        ]

    async def get(
        self, project: str, identifier: str, user: str
    ) -> ConnectionEditProposal:
        await self.db.require_project(project, user)
        rows = await self.db.rows(
            "connection_edit_proposals",
            {
                "proposal_id": f"eq.{identifier}",
                "project_id": f"eq.{project}",
                "created_by": f"eq.{user}",
                "select": ",".join(ConnectionEditProposal.model_fields),
                "limit": "1",
            },
        )
        if not rows:
            raise ServiceError(
                404, "EDIT_PROPOSAL_NOT_FOUND", "修改方案不存在或无权访问"
            )
        return ConnectionEditProposal.model_validate(
            {key: rows[0][key] for key in ConnectionEditProposal.model_fields}
        )

    async def decide(
        self, project: str, identifier: str, user: str, body: ConnectionEditDecision
    ) -> ConnectionEditReceipt:
        """Confirm the stored immutable preview, never a client-supplied field patch."""
        await self.db.require_project(project, user, write=True)
        value: dict[str, Any] = await self.db.rpc(
            "decide_explain_connection_edit",
            {
                "value": {
                    "project_id": project,
                    "proposal_id": identifier,
                    "actor": user,
                    **body.model_dump(mode="json"),
                }
            },
        )
        return ConnectionEditReceipt.model_validate(value)
