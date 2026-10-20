"""Narrow fallback for providers rejecting required tool choice; decisions remain typed."""

from __future__ import annotations

import json
from dataclasses import replace
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import Field

from src.domain.models.common import StrictModel
from src.harness.model_gateway import (
    ModelGateway,
    ModelGatewayError,
    ModelRequest,
    ModelResponse,
    ModelToolCall,
)

from .models import ConnectionQuery, DrawingQuery, ExplainError, RescanRequest
from .rescan_receipts import claims_rescan_execution


class RescanDecision(StrictModel):
    action: Literal["rescan_connections"]
    request: RescanRequest


class SearchDecision(StrictModel):
    action: Literal["search_connections"]
    query: ConnectionQuery


class ViewDecision(StrictModel):
    action: Literal["view_drawings"]
    query: DrawingQuery


class ClarifyDecision(StrictModel):
    action: Literal["clarify"]
    question: str = Field(min_length=1, max_length=1000)


class ToolDecision(StrictModel):
    decision: Annotated[
        RescanDecision | SearchDecision | ViewDecision | ClarifyDecision, Field(discriminator="action")
    ]


def unsupported_tool_choice(error: ModelGatewayError) -> bool:
    """Only an explicit provider capability rejection permits the extra decision call."""
    return (
        error.details.get("status_code") == 400
        and error.details.get("provider_code") == "tool_choice_not_supported"
    )


async def structured_tool_decision(gateway: ModelGateway, request: ModelRequest) -> ModelResponse:
    """Validate a JSON decision and route it through the existing tool execution boundary."""
    schema = ToolDecision.model_json_schema()
    schema["$defs"]["RescanRequest"]["properties"].pop("result_mode", None)
    response = await gateway.invoke(
        replace(
            request,
            messages=[
                *request.messages,
                {
                    "role": "system",
                    "content": (
                        "当前模型服务不支持强制工具选择。只输出符合以下JSON Schema的对象，"
                        "不输出工具调用、Markdown或执行成功说明。"
                        "必须使用decision对象：action=rescan_connections时用request；search_connections/view_drawings用query；"
                        "范围不明确用clarify/question追问，不猜行ID或目标页。不要复制完整聊天作为指令。"
                        "你只产生决策，程序还会校验权限、范围和真实执行回执；没有保存权限。\n"
                        + json.dumps(schema, ensure_ascii=False)
                    ),
                },
            ],
            tools=[],
            tool_choice=None,
            json_mode=False,
            output_model=ToolDecision,
            metadata={**request.metadata, "operation": "rescan_structured_decision"},
        )
    )
    if (
        response.tool_calls
        or response.finish_reason == "length"
        or not isinstance(response.parsed, ToolDecision)
    ):
        raise ExplainError("RESCAN_NOT_CREATED", "模型未返回有效重扫决策，任务未创建，正式线表未改动。", 502)
    decision = response.parsed.decision
    if isinstance(decision, ClarifyDecision):
        if claims_rescan_execution(decision.question) or any(
            term in decision.question for term in ("修改预览", "修改方案")
        ):
            raise ExplainError(
                "RESCAN_NOT_CREATED", "模型未返回有效重扫决策，任务未创建，正式线表未改动。", 502
            )
        raise ExplainError("RESCAN_SCOPE_UNCLEAR", decision.question, 422)
    arguments = decision.request if isinstance(decision, RescanDecision) else decision.query
    if isinstance(decision, RescanDecision) and "result_mode" in decision.request.model_fields_set:
        raise ExplainError("RESCAN_NOT_CREATED", "重扫模式由程序决定，请明确范围后重试。", 502)
    return replace(
        response,
        content="",
        parsed=None,
        tool_calls=(
            ModelToolCall(
                f"decision-{uuid4()}",
                decision.action,
                arguments.model_dump_json(
                    exclude={"result_mode"} if isinstance(decision, RescanDecision) else set()
                ),
            ),
        ),
    )
