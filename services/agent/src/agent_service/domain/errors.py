from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .enums import ErrorCode


class AgentServiceError(RuntimeError):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details or {}


class ErrorDetail(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: ErrorCode
    message: str = Field(min_length=1)
    retryable: bool = False
    agent_run_id: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ErrorEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error: ErrorDetail
