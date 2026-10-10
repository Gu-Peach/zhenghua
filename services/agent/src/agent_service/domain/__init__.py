"""Provider-neutral domain contracts for agent runs and proposals."""

from .enums import (
    AgentStage,
    CorrectionAction,
    CorrectionIssueKind,
    ErrorCode,
    ProfileDetectionStatus,
    ProfileStatus,
    RunStatus,
    RunType,
    ScopeType,
    SupervisorIntent,
    SupervisorTurnStatus,
    WorkflowKind,
)

__all__ = [
    "AgentStage",
    "CorrectionAction",
    "CorrectionIssueKind",
    "ErrorCode",
    "ProfileDetectionStatus",
    "ProfileStatus",
    "RunStatus",
    "RunType",
    "ScopeType",
    "SupervisorIntent",
    "SupervisorTurnStatus",
    "WorkflowKind",
]
