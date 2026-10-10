from __future__ import annotations

import hashlib
import json
from typing import Any

from .errors import ErrorEnvelope
from .models.correction import CorrectionEvidenceBundle, CorrectionPlan, FeedbackTarget
from .models.extraction_stages import (
    CrossPageCompletionRequest,
    CrossPageCompletionResult,
    PageClassificationRequest,
    PageClassificationResult,
    PageScanRequest,
    PageScanResult,
)
from .models.improvement import (
    AcceptedFeedback,
    Diagnosis,
    EvalReport,
    EvaluationJudgement,
    ProfileCandidate,
    ReleaseDecision,
)
from .models.profile_detection import ProfileAssignment, ProfileDetectionResult
from .models.profiles import ProfileManifest
from .models.proposals import ResultPatchProposal, ResultProposal
from .models.result_data import (
    ConnectionSearchQuery,
    ConnectionSearchResult,
    PrepareCorrectionRequest,
    PreparedCorrection,
    ResultCommitResult,
)
from .models.runs import AgentEvent, AgentRun, CreateRunRequest
from .models.supervisor import ConversationTurn, SupervisorDecision, SupervisorUserEvent

CONTRACT_MODELS = (
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
        "contract_version": "2",
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
