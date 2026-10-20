"""Explain-only numeric request diagnostics; never persist prompts, responses or provider text."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Awaitable, Callable
from dataclasses import replace
from time import perf_counter
from typing import Any
from uuid import UUID, uuid4

from src.agent.extraction_agent.infrastructure.document.model_traces import LocalModelTraceStore
from src.domain.errors import AgentServiceError
from src.harness.model_gateway import ModelGateway, ModelRequest, ModelResponse

logger = logging.getLogger(__name__)


def request_summary(request: ModelRequest) -> dict[str, Any]:
    text_chars, image_count, image_chars = 0, 0, 0
    for message in request.messages:
        content = message.get("content")
        if isinstance(content, str):
            text_chars += len(content)
        elif isinstance(content, list):
            for part in content:
                if not isinstance(part, dict):
                    continue
                if part.get("type") == "text":
                    text_chars += len(str(part.get("text", "")))
                elif part.get("type") == "image_url":
                    image_count += 1
                    image_chars += len(str((part.get("image_url") or {}).get("url", "")))
    names = [tool.get("function", {}).get("name") for tool in request.tools]
    allowed = {name for name in names if isinstance(name, str)}
    prior_tools = [
        call.get("function", {}).get("name")
        for message in request.messages
        for call in message.get("tool_calls", [])
        if call.get("function", {}).get("name") in allowed
    ]
    summary = {
        "message_count": len(request.messages),
        "text_characters": text_chars,
        "image_count": image_count,
        "image_encoded_characters": image_chars,
        "tool_count": len(request.tools),
        "tool_result_messages": sum(message.get("role") == "tool" for message in request.messages),
        "prior_tool_names": prior_tools[:8],
        "tool_schema_characters": len(json.dumps(request.tools, ensure_ascii=False)),
        "tool_names": [
            name
            for name in names
            if isinstance(name, str) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,63}", name)
        ],
        "max_output_tokens": request.max_tokens,
        "tool_choice": request.tool_choice,
        "structured_output": request.output_model is not None,
    }
    for key in ("tool_round", "history_messages", "history_characters"):
        if type(request.metadata.get(key)) is int:
            summary[key] = request.metadata[key]
    return summary


def error_summary(error: Exception) -> dict[str, Any]:
    """Inspect technical error text in memory, persisting only a canonical classification."""
    if not isinstance(error, AgentServiceError):
        return {"error_type": type(error).__name__, "cause": "unknown"}
    text = str(error.details.get("provider_message", "")).casefold()
    if error.details.get("provider_code") == "tool_choice_not_supported":
        cause = "tool_choice_compatibility"
    elif "mtp" in text and ("materializ" in text or "checkpoint" in text):
        cause = "model_checkpoint"
    elif any(
        term in text for term in ("out of memory", "cuda oom", "kv cache exhausted", "kv cache is full")
    ):
        cause = "memory_capacity"
    elif any(
        term in text
        for term in (
            "maximum context",
            "context length",
            "context_length",
            "max_model_len",
            "too many tokens",
        )
    ):
        cause = "context_limit"
    elif "tool" in text and any(term in text for term in ("not support", "unsupported", "not enabled")):
        cause = "tool_compatibility"
    elif error.details.get("status_code") == 429 or "rate limit" in text:
        cause = "rate_limit"
    else:
        cause = "unknown"
    result: dict[str, Any] = {"error_type": type(error).__name__, "code": str(error.code), "cause": cause}
    for key in ("provider_code", "provider_type", "failure_kind"):
        value = error.details.get(key)
        if (
            isinstance(value, str)
            and re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", value)
            and not value.casefold().startswith(("sk-", "bearer"))
        ):
            result[key] = value
    if type(error.details.get("status_code")) is int:
        result["status_code"] = error.details["status_code"]
    return result


class ExplainDiagnosticGateway:
    def __init__(self, delegate: ModelGateway, store: LocalModelTraceStore, default_model: str) -> None:
        self.delegate, self.store, self.default_model = delegate, store, default_model

    async def invoke(self, request: ModelRequest) -> ModelResponse:
        return await self._call(request, None)

    async def stream_text(
        self, request: ModelRequest, on_text: Callable[[str], Awaitable[None]]
    ) -> ModelResponse:
        return await self._call(request, on_text)

    async def _call(
        self, request: ModelRequest, sink: Callable[[str], Awaitable[None]] | None
    ) -> ModelResponse:
        identifier, started = str(uuid4()), perf_counter()
        summary = request_summary(request)
        query = replace(request, metadata={**request.metadata, "diagnostic_id": identifier})
        record: dict[str, Any] = {
            "kind": "explain_model_call",
            "agent": request.agent_name,
            "model": request.model or self.default_model,
            "metadata": {"diagnostic_id": identifier, "request_summary": summary, "stream": sink is not None},
        }
        try:
            record["metadata"]["conversation_id"] = str(UUID(str(request.metadata.get("conversation_id"))))
        except (ValueError, TypeError):
            pass
        logger.info(
            "Explain model start run=%s diagnostic_id=%s summary=%s", request.run_id, identifier, summary
        )
        try:
            stream = getattr(self.delegate, "stream_text", None)
            result: ModelResponse
            if sink is not None and callable(stream):
                result = await stream(query, sink)
            else:
                result = await self.delegate.invoke(query)
                if sink is not None and result.content:
                    await sink(result.content)
            record.update(
                usage={
                    key: value
                    for key, value in result.usage.items()
                    if key in {"prompt_tokens", "completion_tokens", "total_tokens"} and type(value) is int
                },
                finish_reason=result.finish_reason,
                attempts=result.attempts,
            )
            record["metadata"]["returned_tool_calls"] = len(result.tool_calls)
            return result
        except Exception as error:
            details = error_summary(error)
            if isinstance(error, AgentServiceError):
                error.details.update(
                    diagnostic_id=identifier, diagnostic_cause=details["cause"], request_summary=summary
                )
            record.update(error_type=type(error).__name__, schema_error=details)
            logger.error(
                "Explain model failed run=%s diagnostic_id=%s cause=%s summary=%s",
                request.run_id,
                identifier,
                details["cause"],
                summary,
            )
            raise
        finally:
            record["duration_seconds"] = round(perf_counter() - started, 4)
            try:
                await self.store.append(request.run_id, record)
            except (OSError, ValueError, TypeError):
                logger.warning("Explain diagnostic write failed diagnostic_id=%s", identifier)
