from __future__ import annotations

from typing import Any

from src.domain.models.common import StrictModel

from .models import (
    DocumentTool,
    EmptyTool,
    ExplainScope,
    FindTargets,
    NavigateTool,
    OpenPageTool,
    ProfileDiagnosis,
    RescanScopeTool,
    ScopeTool,
    SearchConnections,
    TaskTool,
)

TOOL_MODELS: dict[str, type[StrictModel]] = {
    "find_targets": FindTargets,
    "navigate_to": NavigateTool,
    "read_scope": ScopeTool,
    "search_connections": SearchConnections,
    "explain_scope": ExplainScope,
    "start_rescan": RescanScopeTool,
    "get_task_status": TaskTool,
    "cancel_task": TaskTool,
    "diagnose_profile": ProfileDiagnosis,
    "propose_connection_edit": ExplainScope,
    "list_rule_packages": EmptyTool,
    "open_agent_page": OpenPageTool,
    "start_document_extraction": DocumentTool,
    "export_project": ScopeTool,
}
DESCRIPTIONS = {
    "find_targets": "检索授权项目及真实工作区/业务页索引，含零记录图纸。多个同名对象返回候选，不猜ID。",
    "navigate_to": "按已定位真实ID打开项目、工作区或图纸。唯一匹配的打开请求可直接调用。",
    "read_scope": "读取授权范围概览、代表记录、实际图纸索引和冻结规则，并注明证据缺口。",
    "search_connections": (
        "精确AND检索；多个编号用principle_numbers。单值未命中可解析有界编号范围。"
        "has_more=false后不要重复同参数，转入修改/诊断。"
    ),
    "explain_scope": "委托Explain只读解释来源和提取方法；不创建重扫，不修改结果。",
    "start_rescan": "明确范围即可创建候选任务。all整范围替换；start/end仅修该侧。参考图需绑定PDF物理页。",
    "get_task_status": "读取本会话已创建重扫任务的最新状态。",
    "cancel_task": "取消本会话所选重扫任务，不撤销已提交结果。",
    "diagnose_profile": "用当次冻结规则、实际图纸和结果委托Profile诊断；propose_changes可生成diff待确认。",
    "propose_connection_edit": "明确修订请求时委托Explain生成线表修改proposal；不提交。",
    "list_rule_packages": "查询数据库规则包及key、version、显示名。",
    "open_agent_page": "打开提取或规则配置页面，可定位授权规则。",
    "start_document_extraction": "用户明确要求提取已上传PDF并指定规则key时，复用现有导入和提取任务。",
    "export_project": "用户要求导出时返回项目全量XLSX的下载动作。",
}


def definitions() -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": DESCRIPTIONS[name],
                "parameters": model.model_json_schema(),
            },
        }
        for name, model in TOOL_MODELS.items()
    ]
