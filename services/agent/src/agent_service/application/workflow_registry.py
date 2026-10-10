from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import Field

from ..domain.enums import WorkflowKind
from ..domain.models.common import FrozenModel
from ..domain.models.supervisor import WorkflowCommand


class WorkflowDispatchReceipt(FrozenModel):
    command_id: str
    workflow: WorkflowKind
    status: str = Field(pattern=r"^(QUEUED|RUNNING|WAITING_INPUT|COMPLETED|FAILED)$")
    agent_run_id: str | None = None
    message: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)


@runtime_checkable
class WorkflowHandler(Protocol):
    async def dispatch(self, command: WorkflowCommand) -> WorkflowDispatchReceipt: ...


class WorkflowRegistry:
    def __init__(self) -> None:
        self._handlers: dict[WorkflowKind, WorkflowHandler] = {}

    def register(self, workflow: WorkflowKind, handler: WorkflowHandler) -> None:
        if workflow in self._handlers:
            raise ValueError(f"Workflow {workflow.value!r} is already registered.")
        self._handlers[workflow] = handler

    def list_registered(self) -> list[WorkflowKind]:
        return sorted(self._handlers, key=lambda item: item.value)

    async def dispatch(self, command: WorkflowCommand) -> WorkflowDispatchReceipt:
        handler = self._handlers.get(command.workflow)
        if handler is None:
            raise ValueError(f"Workflow {command.workflow.value!r} is not registered.")
        return await handler.dispatch(command)
