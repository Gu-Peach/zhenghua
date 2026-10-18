from __future__ import annotations

import hashlib
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from ..models import ExplainActor, ExplainError, ExplainTurn, RescanRequest, RescanRun
from ..repository import ExplanationRepository


class RescanConnectionsTool:
    name = "rescan_connections"

    @classmethod
    def definition(cls) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": "用户要求重新识别、重扫端子/页/工作区时创建提取Agent任务。"
                "始终读取数据库原页/关联图及原Profile，用户截图作为辅助。"
                "fields=end只补终点，start只修起点，all重新扫描。只保存候选，确认前不改线表。"
                "工作区直接传workspace_code，不只传当前页几行。",
                "parameters": RescanRequest.model_json_schema(),
            },
        }

    @staticmethod
    async def execute(
        repository: ExplanationRepository, turn: ExplainTurn, actor: ExplainActor, request: RescanRequest
    ) -> RescanRun:
        if not turn.allow_rescan:
            raise ExplainError("RESCAN_NOT_REQUESTED", "本轮仅解释来源，未授权发起重扫。", 422)
        digest = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
        identifier = str(
            uuid5(NAMESPACE_URL, f"explain-rescan:{actor.user_id}:{turn.project_id}:{turn.turn_id}:{digest}")
        )
        return await repository.start_rescan(turn, actor, identifier, request)
