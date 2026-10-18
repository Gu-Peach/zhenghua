from __future__ import annotations

from typing import Any
from uuid import NAMESPACE_URL, uuid5

from ..models import ConnectionEditProposal, ConnectionEditRequest, ExplainActor, ExplainTurn
from ..repository import ExplanationRepository


class ProposeConnectionEditTool:
    name = "propose_connection_edit"

    @classmethod
    def definition(cls) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": (
                    "用户明确要求修改线表时，在当前项目/批次按工作区、原理号列表或行ID生成全范围逐行对照；"
                    "不写业务行。支持端子前缀删除、整组端点调换（默认，含元件/描述/坐标对象，记录所属页/工作区不变）、"
                    "仅端子交换、字段赋值。用户需在界面确认后由Server提交；不要把首批检索当成整个工作区。"
                ),
                "parameters": ConnectionEditRequest.model_json_schema(),
            },
        }

    @staticmethod
    async def execute(
        repository: ExplanationRepository,
        turn: ExplainTurn,
        actor: ExplainActor,
        request: ConnectionEditRequest,
        index: int,
    ) -> ConnectionEditProposal:
        identifier = uuid5(
            NAMESPACE_URL, f"explain-edit:{actor.user_id}:{turn.project_id}:{turn.turn_id}:{index}"
        )
        return await repository.propose_edit(turn, actor, str(identifier), request)
