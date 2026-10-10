from __future__ import annotations

import asyncio
import json
import re
from collections import deque
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, Protocol

import httpx
from pydantic import BaseModel, ValidationError

from ..domain.enums import ErrorCode
from ..domain.errors import AgentServiceError
from ..domain.ports import TraceStore
from .retry import RetryPolicy, is_retryable_status


class ModelGatewayError(AgentServiceError):
    pass


@dataclass(frozen=True, slots=True)
class ModelRequest:
    agent_name: str
    run_id: str
    messages: list[dict[str, Any]]
    model: str | None = None
    output_model: type[BaseModel] | None = None
    temperature: float = 0.0
    max_tokens: int | None = None
    json_mode: bool = False
    enable_thinking: bool | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ModelResponse:
    content: str
    parsed: BaseModel | None
    model: str
    duration_seconds: float
    attempts: int
    usage: dict[str, Any] = field(default_factory=dict)


class ModelGateway(Protocol):
    async def invoke(self, request: ModelRequest) -> ModelResponse: ...


class OpenAICompatibleModelGateway:
    def __init__(
        self,
        *,
        base_url: str,
        default_model: str,
        chat_completions_url: str | None = None,
        api_key: str | None = None,
        timeout_seconds: float = 300.0,
        retry_policy: RetryPolicy | None = None,
        trace_store: TraceStore | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        if not base_url.strip():
            raise ValueError("base_url is required.")
        if not default_model.strip():
            raise ValueError("default_model is required.")
        self._url = self._chat_completions_url(chat_completions_url or base_url)
        self._default_model = default_model
        self._api_key = api_key
        self._timeout_seconds = timeout_seconds
        self._retry_policy = retry_policy or RetryPolicy()
        self._trace_store = trace_store
        self._client = client

    @staticmethod
    def _chat_completions_url(base_url: str) -> str:
        normalized = base_url.rstrip("/")
        if normalized.endswith("/chat/completions"):
            return normalized
        if normalized.endswith("/v1"):
            return f"{normalized}/chat/completions"
        return f"{normalized}/v1/chat/completions"

    @staticmethod
    def _normalize_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert internal structured message content to provider-safe JSON.

        Multimodal content is already represented by the OpenAI-compatible
        list form and is preserved. A mapping is an internal convenience for
        agents such as Supervisor and Improvement; it must become a JSON
        string before it is sent over the wire.
        """
        normalized: list[dict[str, Any]] = []
        for message in messages:
            item = dict(message)
            content = item.get("content")
            if isinstance(content, dict):
                item["content"] = json.dumps(content, ensure_ascii=False, separators=(",", ":"))
            elif content is not None and not isinstance(content, (str, list)):
                item["content"] = str(content)
            normalized.append(item)
        return normalized

    async def invoke(self, request: ModelRequest) -> ModelResponse:
        model = request.model or self._default_model
        payload: dict[str, Any] = {
            "model": model,
            # OpenAI-compatible APIs only accept string or multimodal-array
            # message content. Internal agents may keep structured Python
            # payloads while composing a request; serialize those objects at
            # this boundary so providers do not reject the whole turn with a
            # 400 before the model is reached.
            "messages": self._normalize_messages(request.messages),
            "temperature": request.temperature,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        # ``output_model`` controls local Pydantic validation only.  Do not
        # infer provider-side structured-output mode from it: several
        # OpenAI-compatible servers reject ``response_format`` unless they
        # were started with a dedicated structured-output flag.  Callers opt
        # into that provider feature explicitly through ``json_mode``.
        if request.json_mode:
            payload["response_format"] = {"type": "json_object"}
        if request.enable_thinking is not None:
            payload["chat_template_kwargs"] = {"enable_thinking": request.enable_thinking}

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        start = perf_counter()
        attempts = 0
        last_error: Exception | None = None
        owns_client = self._client is None
        client = self._client or httpx.AsyncClient(timeout=self._timeout_seconds)
        try:
            for attempt in range(self._retry_policy.max_retries + 1):
                attempts = attempt + 1
                try:
                    response = await client.post(self._url, headers=headers, json=payload)
                    if response.is_error:
                        retryable = is_retryable_status(response.status_code)
                        provider_details = _provider_error_details(response)
                        provider_message = provider_details.get("provider_message")
                        summary = f"Model request failed with HTTP {response.status_code}" + (
                            f": {provider_message}" if provider_message else "."
                        )
                        error = ModelGatewayError(
                            ErrorCode.MODEL_TEMPORARILY_UNAVAILABLE
                            if retryable
                            else ErrorCode.INVALID_REQUEST,
                            summary,
                            retryable=retryable,
                            details={"status_code": response.status_code, **provider_details},
                        )
                        if not retryable or attempt >= self._retry_policy.max_retries:
                            raise error
                        last_error = error
                    else:
                        content, usage = self._read_response(response)
                        parsed = self._parse_output(content, request.output_model)
                        result = ModelResponse(
                            content=content,
                            parsed=parsed,
                            model=model,
                            duration_seconds=perf_counter() - start,
                            attempts=attempts,
                            usage=usage,
                        )
                        await self._trace(request, result=result, error=None)
                        return result
                except (httpx.TimeoutException, httpx.NetworkError) as exc:
                    last_error = exc
                    if attempt >= self._retry_policy.max_retries:
                        break
                if attempt < self._retry_policy.max_retries:
                    await asyncio.sleep(self._retry_policy.delay_for(attempt))
        finally:
            if owns_client:
                await client.aclose()

        error = ModelGatewayError(
            ErrorCode.MODEL_TEMPORARILY_UNAVAILABLE,
            "Model request failed after retries.",
            retryable=True,
            details={"attempts": attempts, "error_type": type(last_error).__name__},
        )
        await self._trace(request, result=None, error=error)
        raise error from last_error

    @staticmethod
    def _read_response(response: httpx.Response) -> tuple[str, dict[str, Any]]:
        try:
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise ModelGatewayError(
                ErrorCode.MODEL_SCHEMA_INVALID,
                "Model response does not match OpenAI chat completions format.",
                retryable=False,
            ) from exc
        if isinstance(content, list):
            content = "".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
        if not isinstance(content, str):
            raise ModelGatewayError(
                ErrorCode.MODEL_SCHEMA_INVALID,
                "Model response content is not text.",
                retryable=False,
            )
        usage = payload.get("usage") if isinstance(payload.get("usage"), dict) else {}
        return content, usage

    @classmethod
    def _parse_output(
        cls,
        content: str,
        output_model: type[BaseModel] | None,
    ) -> BaseModel | None:
        if output_model is None:
            return None
        try:
            return output_model.model_validate(cls._load_json(content))
        except (ValueError, ValidationError) as exc:
            raise ModelGatewayError(
                ErrorCode.MODEL_SCHEMA_INVALID,
                "Model output failed structured schema validation.",
                retryable=False,
                details={"schema": output_model.__name__},
            ) from exc

    @staticmethod
    def _load_json(content: str) -> Any:
        fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", content, re.IGNORECASE | re.DOTALL)
        raw = fenced.group(1) if fenced else content
        raw = raw.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            object_start, object_end = raw.find("{"), raw.rfind("}")
            array_start, array_end = raw.find("["), raw.rfind("]")
            if 0 <= object_start < object_end:
                return json.loads(raw[object_start : object_end + 1])
            if 0 <= array_start < array_end:
                return json.loads(raw[array_start : array_end + 1])
            raise

    async def _trace(
        self,
        request: ModelRequest,
        *,
        result: ModelResponse | None,
        error: Exception | None,
    ) -> None:
        if self._trace_store is None:
            return
        await self._trace_store.append(
            request.run_id,
            {
                "kind": "model_call",
                "agent": request.agent_name,
                "model": result.model if result else request.model or self._default_model,
                "attempts": result.attempts if result else None,
                "duration_seconds": result.duration_seconds if result else None,
                "usage": result.usage if result else {},
                "metadata": request.metadata,
                "error_type": type(error).__name__ if error else None,
            },
        )


def _provider_error_details(response: httpx.Response) -> dict[str, str]:
    try:
        payload = response.json()
    except ValueError:
        payload = None

    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict):
        message = error.get("message")
        metadata = {
            f"provider_{key}": str(error[key])
            for key in ("type", "code", "param")
            if error.get(key) is not None
        }
    elif isinstance(error, str):
        message = error
        metadata = {}
    elif isinstance(payload, dict):
        message = payload.get("detail") or payload.get("message")
        metadata = {}
    else:
        message = response.text
        metadata = {}

    details = {key: _sanitize_provider_text(value) for key, value in metadata.items()}
    if message:
        details["provider_message"] = _sanitize_provider_text(str(message))
    return details


def _sanitize_provider_text(value: str) -> str:
    text = " ".join(value.split())
    text = re.sub(r"(?i)\bBearer\s+[^\s,;]+", "Bearer [REDACTED]", text)
    text = re.sub(
        r"(?i)\b(api[-_ ]?key|access[-_ ]?token|authorization|secret)\b(\s*[:=]\s*)[^\s,;]+",
        r"\1\2[REDACTED]",
        text,
    )
    return text[:500]


class FakeModelGateway:
    """Deterministic scripted gateway for default tests; it never performs network I/O."""

    def __init__(self, responses: list[str | Exception], model: str = "fake-vlm") -> None:
        self._responses: deque[str | Exception] = deque(responses)
        self.model = model
        self.calls: list[ModelRequest] = []

    async def invoke(self, request: ModelRequest) -> ModelResponse:
        self.calls.append(request)
        if not self._responses:
            raise AssertionError("FakeModelGateway has no scripted response left.")
        scripted = self._responses.popleft()
        if isinstance(scripted, Exception):
            raise scripted
        parsed = OpenAICompatibleModelGateway._parse_output(scripted, request.output_model)
        return ModelResponse(
            content=scripted,
            parsed=parsed,
            model=request.model or self.model,
            duration_seconds=0.0,
            attempts=1,
            usage={},
        )
