from __future__ import annotations

from typing import Any

from pydantic import Field

from src.domain.models.common import StrictModel
from src.domain.models.runs import AgentEvent, AgentRun


class HumanInputRequest(StrictModel):
    payload: dict[str, Any] = Field(default_factory=dict)


class RunEventsResponse(StrictModel):
    items: list[AgentEvent]


class RunArtifactsResponse(StrictModel):
    items: list[dict[str, Any]]


class RunResponse(StrictModel):
    run: AgentRun
