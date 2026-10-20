from __future__ import annotations

import hashlib
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from ..models import ConnectionQuery, ExplainActor, ExplainError, ExplainTurn, RescanRequest, RescanRun
from ..repository import ExplanationRepository
from ..rescan_planning import RescanPlanError, require_tool_requirements, validate_requirements


class RescanConnectionsTool:
    name = "rescan_connections"

    @classmethod
    def definition(cls) -> dict[str, Any]:
        schema = RescanRequest.model_json_schema()
        require_tool_requirements(schema, schema)
        target = schema["$defs"]["RescanTargetBinding"]["properties"]
        target["workspace_code"]["description"] = (
            "目标图纸所属工作区，只能来自目标目录；不是scope里的源工作区。"
            "不确定时省略，按drawing_page在本项目完整目录定位，不要继承当前工作区。"
        )
        target["pdf_page_number"]["description"] = "目标图纸的PDF物理页，只填目录检索确认的页号。"
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": "用户要求重新识别、重扫端子/页/工作区时创建提取Agent任务。"
                "读取数据库原页/关联图及任务冻结规则，用户截图作为辅助。"
                "默认沿用历史规则；项目明确启用规则升级时，新任务冻结项目当前选定版本，以返回的profile为准。"
                "fields=end只替换终点，start只替换起点；all且页/工作区范围时确认后删除旧范围并写入全部新结果。"
                "按行ID/原理号重扫只修订选中行，不新增范围外结果。只保存候选，确认前不改线表。"
                "工作区直接传workspace_code，不只传当前页几行。"
                "requirements完整列出所需字段和预期起点。纠正整页起点集合/补漏/多提或原理号时用整页fields=all，connection_set=rebuild，不带旧行ID。"
                "仅明确保留已有行、只补终点时才用fields=end；指定终点页填写target_bindings，按connection_ids绑定原样业务页号；"
                "不能只写instructions，不能把002M03扩写为33/34/35页。"
                "目标工作区不得继承scope的源工作区；先按目标业务页单独检索目录。"
                "工具反馈目标限制冲突时按返回目录更正参数后再调用，不把模型参数错误转嫁给用户；真正歧义再追问。",
                "parameters": schema,
            },
        }

    @staticmethod
    async def execute(
        repository: ExplanationRepository, turn: ExplainTurn, actor: ExplainActor, request: RescanRequest
    ) -> RescanRun:
        if not turn.allow_rescan:
            raise ExplainError("RESCAN_NOT_REQUESTED", "本轮仅解释来源，未授权发起重扫。", 422)
        if request.requirements is None or not {
            "required_fields",
            "expected_start_terminals",
            "connection_set",
            "endpoint_location",
        }.issubset(request.requirements.model_fields_set):
            raise ExplainError(
                "RESCAN_REQUIREMENTS_MISSING",
                "请先明确requirements：所需字段、预期起点集合与同页约束，再创建重扫任务。",
                422,
            )
        try:
            validate_requirements(request)
            if (
                request.requirements.expected_start_terminals
                and request.requirements.connection_set == "preserve"
            ):
                queries = [ConnectionQuery(connection_id=value) for value in request.scope.connection_ids]
                if not queries:
                    queries = [
                        ConnectionQuery(
                            workspace_code=request.scope.workspace_code,
                            drawing_page=request.scope.drawing_page,
                            principle_number=value,
                        )
                        for value in request.scope.principle_numbers
                    ]
                if not queries:
                    raise RescanPlanError(
                        "保留连接集合时请明确完整行ID/原理号；重建整页集合应使用connection_set=rebuild。"
                    )
                rows: list[dict[str, Any]] = []
                for query in queries:
                    result = await repository.search(turn, actor, query)
                    if result.has_more:
                        raise RescanPlanError(
                            "连接范围不唯一，请明确行ID或重建整页候选。", "RESCAN_SCOPE_INCOMPLETE"
                        )
                    rows.extend(item.row.model_dump(mode="json") for item in result.rows)
                validate_requirements(request, rows)
        except RescanPlanError as exc:
            raise ExplainError(exc.code, str(exc), 422) from exc
        request = request.model_copy(update={"result_mode": request.resolved_mode()})
        digest = hashlib.sha256(request.model_dump_json().encode()).hexdigest()
        identifier = str(
            uuid5(NAMESPACE_URL, f"explain-rescan:{actor.user_id}:{turn.project_id}:{turn.turn_id}:{digest}")
        )
        return await repository.start_rescan(turn, actor, identifier, request)
