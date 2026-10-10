from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from ..domain.enums import ErrorCode
from ..domain.errors import AgentServiceError
from ..domain.models.common import FrozenModel


class ToolCallContext(FrozenModel):
    run_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    agent_name: str = Field(min_length=1)
    scope_id: str = Field(min_length=1)


ToolHandler = Callable[[ToolCallContext, BaseModel], BaseModel | Awaitable[BaseModel]]


@dataclass(frozen=True, slots=True)
class ToolDefinition:
    name: str
    description: str
    allowed_agents: frozenset[str]
    input_model: type[BaseModel]
    output_model: type[BaseModel]
    handler: ToolHandler


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, definition: ToolDefinition) -> None:
        if not definition.name.strip():
            raise ValueError("Tool name cannot be empty.")
        if definition.name in self._tools:
            raise ValueError(f"Tool {definition.name!r} is already registered.")
        if not definition.allowed_agents:
            raise ValueError("A tool must allow at least one agent.")
        self._tools[definition.name] = definition

    def list_for(self, agent_name: str) -> list[str]:
        return sorted(
            name for name, definition in self._tools.items() if agent_name in definition.allowed_agents
        )

    async def invoke(
        self,
        tool_name: str,
        context: ToolCallContext,
        payload: dict[str, Any] | BaseModel,
    ) -> BaseModel:
        definition = self._tools.get(tool_name)
        if definition is None:
            raise AgentServiceError(
                ErrorCode.INVALID_REQUEST,
                f"Unknown tool {tool_name!r}.",
                retryable=False,
            )
        if context.agent_name not in definition.allowed_agents:
            raise AgentServiceError(
                ErrorCode.TOOL_NOT_ALLOWED,
                f"Agent {context.agent_name!r} cannot use tool {tool_name!r}.",
                retryable=False,
            )
        validated_input = (
            payload
            if isinstance(payload, definition.input_model)
            else definition.input_model.model_validate(payload)
        )
        result = definition.handler(context, validated_input)
        if inspect.isawaitable(result):
            result = await result
        return definition.output_model.model_validate(result)
