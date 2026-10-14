from __future__ import annotations

import hashlib
import json
from typing import Any

from src.domain.errors import ErrorEnvelope
from src.domain.models.correction import CorrectionEvidenceBundle, CorrectionPlan, FeedbackTarget
from src.agent.extraction_agent.domain.models.extraction_stages import (
    CrossPageCompletionRequest,
    CrossPageCompletionResult,
    PageClassificationRequest,
    PageClassificationResult,
    PageScanRequest,
    PageScanResult,
)
from src.domain.models.imports import (
    ImportedDocument,
    ProjectResultsResponse,
    ProjectTreeResponse,
    RunStageSummaryResponse,
)
from src.domain.models.improvement import (
    AcceptedFeedback,
    Diagnosis,
    EvalReport,
    EvaluationJudgement,
    ProfileCandidate,
    ReleaseDecision,
)
from src.domain.models.profile_detection import ProfileAssignment, ProfileDetectionResult
from src.domain.models.profiles import ProfileManifest
from src.domain.models.proposals import ResultPatchProposal, ResultProposal
from src.domain.models.result_data import (
    ConnectionSearchQuery,
    ConnectionSearchResult,
    PrepareCorrectionRequest,
    PreparedCorrection,
    ResultCommitResult,
)
from src.domain.models.runs import AgentEvent, AgentRun, CreateRunRequest
from src.domain.models.stage_persistence import (
    RunFinalizationReceipt,
    RunLease,
    StageCommitReceipt,
    StageInput,
    StageItem,
    StageManifest,
)
from src.domain.models.supervisor import ConversationTurn, SupervisorDecision, SupervisorUserEvent

CONTRACT_MODELS = (
    ImportedDocument,
    ProjectTreeResponse,
    ProjectResultsResponse,
    RunStageSummaryResponse,
    RunLease,
    StageInput,
    StageItem,
    StageManifest,
    StageCommitReceipt,
    RunFinalizationReceipt,
    AgentRun,
    CreateRunRequest,
    AgentEvent,
    ProfileManifest,
    ProfileDetectionResult,
    ProfileAssignment,
    ResultProposal,
    ResultPatchProposal,
    ConnectionSearchQuery,
    ConnectionSearchResult,
    PrepareCorrectionRequest,
    PreparedCorrection,
    ResultCommitResult,
    FeedbackTarget,
    Diagnosis,
    CorrectionPlan,
    CorrectionEvidenceBundle,
    AcceptedFeedback,
    ProfileCandidate,
    EvalReport,
    EvaluationJudgement,
    ReleaseDecision,
    PageClassificationRequest,
    PageClassificationResult,
    PageScanRequest,
    PageScanResult,
    CrossPageCompletionRequest,
    CrossPageCompletionResult,
    ConversationTurn,
    SupervisorDecision,
    SupervisorUserEvent,
    ErrorEnvelope,
)


def contract_schema_bundle() -> dict[str, Any]:
    return {
        "contract_version": "6",
        "schemas": {model.__name__: model.model_json_schema() for model in CONTRACT_MODELS},
    }


def contract_schema_checksum() -> str:
    serialized = json.dumps(
        contract_schema_bundle(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"sha256:{hashlib.sha256(serialized.encode('utf-8')).hexdigest()}"
