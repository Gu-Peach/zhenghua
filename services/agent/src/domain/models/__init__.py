"""Lazy public model exports avoid cycles with independently imported agents."""

from importlib import import_module
from typing import Any

__all__ = [
    "AgentEvent",
    "AgentRun",
    "AcceptedFeedback",
    "CorrectionContext",
    "CorrectionFacts",
    "CorrectionPlan",
    "ConnectionSearchQuery",
    "ConnectionSearchResult",
    "ConversationTurn",
    "CrossPageCompletionRequest",
    "CrossPageCompletionResult",
    "CreateRunRequest",
    "Diagnosis",
    "DrawingPageInput",
    "ExtractionExecutionResult",
    "EvalMetrics",
    "EvalReport",
    "EvaluationJudgement",
    "FeedbackTarget",
    "LegacyExtractionRequest",
    "ImprovementCase",
    "ProfileManifest",
    "ProfileCandidate",
    "ProfileAssignment",
    "ProfileBinding",
    "ProfileCandidateScore",
    "ProfileDetectionResult",
    "ProfileRef",
    "ProfileRouterModelOutput",
    "ProfileRuleSet",
    "ProfileSnapshot",
    "ProposalOperation",
    "ProposalValidation",
    "PrepareCorrectionRequest",
    "PreparedCorrection",
    "ResultPatchProposal",
    "ResultProposal",
    "ResultCommitResult",
    "RunScope",
    "PageClassificationRequest",
    "PageClassificationResult",
    "PageScanRequest",
    "PageScanResult",
    "SupervisorDecision",
    "SupervisorUserEvent",
    "WorkflowCommand",
]

_EXPORTS = {
    "CorrectionContext": ("src.domain.models.correction", "CorrectionContext"),
    "CorrectionFacts": ("src.domain.models.correction", "CorrectionFacts"),
    "CorrectionPlan": ("src.domain.models.correction", "CorrectionPlan"),
    "FeedbackTarget": ("src.domain.models.correction", "FeedbackTarget"),
    "ExtractionExecutionResult": (
        "src.agent.extraction_agent.domain.models.extraction",
        "ExtractionExecutionResult",
    ),
    "LegacyExtractionRequest": (
        "src.agent.extraction_agent.domain.models.extraction",
        "LegacyExtractionRequest",
    ),
    "CrossPageCompletionRequest": (
        "src.agent.extraction_agent.domain.models.extraction_stages",
        "CrossPageCompletionRequest",
    ),
    "CrossPageCompletionResult": (
        "src.agent.extraction_agent.domain.models.extraction_stages",
        "CrossPageCompletionResult",
    ),
    "DrawingPageInput": ("src.agent.extraction_agent.domain.models.extraction_stages", "DrawingPageInput"),
    "PageClassificationRequest": (
        "src.agent.extraction_agent.domain.models.extraction_stages",
        "PageClassificationRequest",
    ),
    "PageClassificationResult": (
        "src.agent.extraction_agent.domain.models.extraction_stages",
        "PageClassificationResult",
    ),
    "PageScanRequest": ("src.agent.extraction_agent.domain.models.extraction_stages", "PageScanRequest"),
    "PageScanResult": ("src.agent.extraction_agent.domain.models.extraction_stages", "PageScanResult"),
    "AcceptedFeedback": ("src.domain.models.improvement", "AcceptedFeedback"),
    "Diagnosis": ("src.domain.models.improvement", "Diagnosis"),
    "EvalMetrics": ("src.domain.models.improvement", "EvalMetrics"),
    "EvalReport": ("src.domain.models.improvement", "EvalReport"),
    "EvaluationJudgement": ("src.domain.models.improvement", "EvaluationJudgement"),
    "ImprovementCase": ("src.domain.models.improvement", "ImprovementCase"),
    "ProfileCandidate": ("src.domain.models.improvement", "ProfileCandidate"),
    "ProfileAssignment": ("src.domain.models.profile_detection", "ProfileAssignment"),
    "ProfileCandidateScore": ("src.domain.models.profile_detection", "ProfileCandidateScore"),
    "ProfileDetectionResult": ("src.domain.models.profile_detection", "ProfileDetectionResult"),
    "ProfileRouterModelOutput": ("src.domain.models.profile_detection", "ProfileRouterModelOutput"),
    "ProfileBinding": ("src.domain.models.profiles", "ProfileBinding"),
    "ProfileManifest": ("src.domain.models.profiles", "ProfileManifest"),
    "ProfileRuleSet": ("src.domain.models.profiles", "ProfileRuleSet"),
    "ProfileSnapshot": ("src.domain.models.profiles", "ProfileSnapshot"),
    "ProposalOperation": ("src.domain.models.proposals", "ProposalOperation"),
    "ProposalValidation": ("src.domain.models.proposals", "ProposalValidation"),
    "ResultPatchProposal": ("src.domain.models.proposals", "ResultPatchProposal"),
    "ResultProposal": ("src.domain.models.proposals", "ResultProposal"),
    "ConnectionSearchQuery": ("src.domain.models.result_data", "ConnectionSearchQuery"),
    "ConnectionSearchResult": ("src.domain.models.result_data", "ConnectionSearchResult"),
    "PrepareCorrectionRequest": ("src.domain.models.result_data", "PrepareCorrectionRequest"),
    "PreparedCorrection": ("src.domain.models.result_data", "PreparedCorrection"),
    "ResultCommitResult": ("src.domain.models.result_data", "ResultCommitResult"),
    "AgentEvent": ("src.domain.models.runs", "AgentEvent"),
    "AgentRun": ("src.domain.models.runs", "AgentRun"),
    "CreateRunRequest": ("src.domain.models.runs", "CreateRunRequest"),
    "ProfileRef": ("src.domain.models.runs", "ProfileRef"),
    "RunScope": ("src.domain.models.runs", "RunScope"),
    "ConversationTurn": ("src.domain.models.supervisor", "ConversationTurn"),
    "SupervisorDecision": ("src.domain.models.supervisor", "SupervisorDecision"),
    "SupervisorUserEvent": ("src.domain.models.supervisor", "SupervisorUserEvent"),
    "WorkflowCommand": ("src.domain.models.supervisor", "WorkflowCommand"),
}


def __getattr__(name: str) -> Any:
    if name not in _EXPORTS:
        raise AttributeError(name)
    module, symbol = _EXPORTS[name]
    value = getattr(import_module(module), symbol)
    globals()[name] = value
    return value
