"""Private response diagnostics and public, categorized errors for Profile model calls."""

from __future__ import annotations

import logging
import re
from dataclasses import replace
from typing import Any
from uuid import uuid4

from src.agent.extraction_agent.infrastructure.document.model_traces import LocalModelTraceStore
from src.domain.enums import ErrorCode
from src.domain.errors import AgentServiceError
from src.harness.model_gateway import ModelGateway, ModelRequest, ModelResponse

logger = logging.getLogger(__name__)


def safe_error_details(error: AgentServiceError) -> dict[str, Any]:
    """Whitelist protocol diagnostics; never copy provider messages, headers or request bodies."""
    return {
        key: error.details[key]
        for key in ("status_code", "error_type", "attempts", "schema", "validation_errors", "finish_reason")
        if key in error.details
    }


class ProfileModelGateway:
    def __init__(
        self,
        delegate: ModelGateway,
        traces: LocalModelTraceStore,
        *,
        enable_thinking: bool | None = None,
        json_mode: bool = False,
        default_model: str | None = None,
    ) -> None:
        self.delegate, self.traces = delegate, traces
        self.enable_thinking, self.json_mode = enable_thinking, json_mode
        self.default_model = default_model

    async def invoke(self, request: ModelRequest) -> ModelResponse:
        diagnostic_id = str(uuid4())
        query = replace(
            request,
            model=request.model or self.default_model,
            metadata={**request.metadata, "diagnostic_id": diagnostic_id},
            enable_thinking=request.enable_thinking
            if request.enable_thinking is not None
            else self.enable_thinking,
            json_mode=request.json_mode or (
                self.json_mode and request.output_model is not None and not request.tools
            ),
        )
        try:
            return await self.delegate.invoke(query)
        except AgentServiceError as error:
            error.details["diagnostic_id"] = diagnostic_id
            if error.code == ErrorCode.MODEL_SCHEMA_INVALID:
                try:
                    rows = await self.traces.list(query.run_id)
                    recent = next(
                        (
                            row
                            for row in reversed(rows)
                            if row.get("metadata", {}).get("diagnostic_id") == diagnostic_id
                        ),
                        None,
                    )
                    if recent and recent.get("finish_reason"):
                        error.details["finish_reason"] = recent["finish_reason"]
                except OSError:
                    pass
            details = safe_error_details(error)
            logger.error(
                "Profile model failed run=%s stage=%s code=%s diagnostic_id=%s details=%s",
                query.run_id,
                query.metadata.get("stage"),
                error.code,
                diagnostic_id,
                details,
            )
            await self.traces.append(
                query.run_id,
                {
                    "kind": "model_failure",
                    "agent": "profile_agent",
                    "model": query.model,
                    "metadata": query.metadata,
                    "error_type": type(error).__name__,
                    "schema_error": {"code": str(error.code), **details},
                },
            )
            raise


def public_model_error(error: AgentServiceError) -> dict[str, str]:
    details = error.details
    code = str(error.code)
    status = details.get("status_code")
    if details.get("finish_reason") == "length":
        code, message = (
            "MODEL_TRUNCATED",
            "模型输出达到长度上限，JSON未完整生成；请缩小样图范围或调整输出上限后重试。",
        )
    elif code == "MODEL_SCHEMA_INVALID":
        fields = []
        for item in details.get("validation_errors", [])[:6]:
            location = [str(part) for part in item.get("location", [])]
            if location and all(re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*|[0-9]+", part) for part in location):
                fields.append(".".join(location)[:100])
        schema = details.get("schema")
        label = (
            schema if isinstance(schema, str) and re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", schema) else "响应"
        )
        message = (
            f"模型返回的JSON不符合{label}格式"
            + (f"，请核对字段：{'、'.join(fields)}" if fields else "或JSON不完整")
            + "。"
        )
    elif isinstance(status, int):
        reason = {
            401: "模型鉴权失败",
            403: "当前令牌无权访问模型",
            413: "模型请求或图片超出服务限制",
            429: "模型服务限流",
        }.get(status, "模型服务拒绝请求" if status < 500 else "模型服务暂时不可用")
        message = f"{reason}（HTTP {status}），请检查配置或稍后重试。"
    elif "Timeout" in str(details.get("error_type", "")):
        message = "模型请求超时，重试后仍未完成；请缩小样图范围或检查模型服务。"
    else:
        message = "规则助手模型请求失败，请检查模型服务或重试。"
    result = {"code": code, "message": message}
    diagnostic_id = details.get("diagnostic_id")
    if isinstance(diagnostic_id, str) and re.fullmatch(r"[0-9a-f-]{36}", diagnostic_id):
        result["diagnostic_id"] = diagnostic_id
    return result
