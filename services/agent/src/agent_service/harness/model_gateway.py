from __future__ import annotations

import asyncio
import json
import re
from collections import deque
from collections.abc import Awaitable, Callable
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
                        try:
                            parsed = self._parse_output(content, request.output_model)
                        except ModelGatewayError as exc:
                            await self._trace(
                                request,
                                result=ModelResponse(
                                    content=content,
                                    parsed=None,
                                    model=model,
                                    duration_seconds=perf_counter() - start,
                                    attempts=attempts,
                                    usage=usage,
                                ),
                                error=exc,
                            )
                            raise
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

    async def stream_text(
        self, request: ModelRequest, on_text: Callable[[str], Awaitable[None]]
    ) -> ModelResponse:
        """Stream public text only; never retry after any text has reached the client."""
        if request.output_model is not None:
            raise ValueError("Text streaming is not a structured-output operation.")
        model = request.model or self._default_model
        payload: dict[str, Any] = {
            "model": model,
            "messages": self._normalize_messages(request.messages),
            "temperature": request.temperature,
            "stream": True,
        }
        if request.max_tokens is not None:
            payload["max_tokens"] = request.max_tokens
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        client = self._client or httpx.AsyncClient(timeout=self._timeout_seconds)
        started = perf_counter()
        parts: list[str] = []
        usage: dict[str, Any] = {}
        attempts = 0
        try:
            for attempt in range(self._retry_policy.max_retries + 1):
                attempts = attempt + 1
                try:
                    async with client.stream("POST", self._url, headers=headers, json=payload) as response:
                        if response.is_error:
                            await response.aread()
                            details = _provider_error_details(response)
                            retryable = is_retryable_status(response.status_code)
                            raise ModelGatewayError(
                                ErrorCode.MODEL_TEMPORARILY_UNAVAILABLE
                                if retryable
                                else ErrorCode.INVALID_REQUEST,
                                f"Model request failed with HTTP {response.status_code}: "
                                + details.get("provider_message", "Provider rejected the request."),
                                retryable=retryable,
                                details={"status_code": response.status_code, **details},
                            )
                        if "application/json" in response.headers.get("content-type", ""):
                            await response.aread()
                            content, usage = self._read_response(response)
                            if content:
                                parts.append(content)
                                await on_text(content)
                        else:
                            finished = False
                            async for line in response.aiter_lines():
                                if not line.startswith("data:"):
                                    continue
                                data = line[5:].strip()
                                if data == "[DONE]":
                                    finished = True
                                    break
                                if not data:
                                    continue
                                try:
                                    frame = json.loads(data)
                                    if not isinstance(frame, dict) or frame.get("error"):
                                        raise ValueError("Invalid stream frame")
                                    if isinstance(frame.get("usage"), dict):
                                        usage = frame["usage"]
                                    choices = frame.get("choices") or []
                                    if not choices:
                                        continue
                                    choice = choices[0]
                                    delta = choice.get("delta") or {}
                                    delta_text = delta.get("content")
                                    finished = finished or choice.get("finish_reason") is not None
                                except (ValueError, TypeError, KeyError, AttributeError) as exc:
                                    raise ModelGatewayError(
                                        ErrorCode.MODEL_SCHEMA_INVALID,
                                        "Invalid model text stream.",
                                        retryable=False,
                                    ) from exc
                                # reasoning_content/tool_calls are deliberately never forwarded.
                                if isinstance(delta_text, str) and delta_text:
                                    parts.append(delta_text)
                                    await on_text(delta_text)
                            if not finished:
                                raise ModelGatewayError(
                                    ErrorCode.MODEL_TEMPORARILY_UNAVAILABLE,
                                    "Model text stream ended before completion.",
                                    retryable=True,
                                )
                        if not parts or not "".join(parts).strip():
                            raise ModelGatewayError(
                                ErrorCode.MODEL_SCHEMA_INVALID,
                                "Model returned an empty answer.",
                                retryable=False,
                            )
                        result = ModelResponse(
                            content="".join(parts),
                            parsed=None,
                            model=model,
                            duration_seconds=perf_counter() - started,
                            attempts=attempts,
                            usage=usage,
                        )
                        await self._trace(request, result=result, error=None)
                        return result
                except (httpx.TransportError, ModelGatewayError) as exc:
                    retryable = not isinstance(exc, ModelGatewayError) or exc.retryable
                    if parts or not retryable or attempt >= self._retry_policy.max_retries:
                        error = (
                            exc
                            if isinstance(exc, ModelGatewayError)
                            else ModelGatewayError(
                                ErrorCode.MODEL_TEMPORARILY_UNAVAILABLE,
                                "Model text stream interrupted.",
                                retryable=True,
                            )
                        )
                        await self._trace(request, result=None, error=error)
                        raise error from exc
                    await asyncio.sleep(self._retry_policy.delay_for(attempt))
            raise AssertionError("Unreachable text-stream retry state.")
        finally:
            if self._client is None:
                await client.aclose()

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
            fields = (
                [
                    {"location": list(item["loc"]), "type": item["type"]}
                    for item in exc.errors(include_input=False, include_context=False, include_url=False)
                ]
                if isinstance(exc, ValidationError)
                else [{"location": [], "type": "invalid_json"}]
            )
            raise ModelGatewayError(
                ErrorCode.MODEL_SCHEMA_INVALID,
                "Model output failed structured schema validation.",
                retryable=False,
                details={"schema": output_model.__name__, "validation_errors": fields},
            ) from exc

    @staticmethod
    def _load_json(content: str) -> Any:
        # A complete JSON response may contain Markdown fences inside a file string.
        # Never treat those embedded prompt examples as the provider response wrapper.
        raw = content.strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            pass
        fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", raw, re.IGNORECASE | re.DOTALL)
        if fenced:
            raw = fenced.group(1).strip()
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
                "response_content": result.content if result else None,
                "error_type": type(error).__name__ if error else None,
                "schema_error": error.details
                if isinstance(error, ModelGatewayError) and error.code == ErrorCode.MODEL_SCHEMA_INVALID
                else None,
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

    async def stream_text(
        self, request: ModelRequest, on_text: Callable[[str], Awaitable[None]]
    ) -> ModelResponse:
        result = await self.invoke(request)
        for index in range(0, len(result.content), 8):
            await on_text(result.content[index : index + 8])
        return result
