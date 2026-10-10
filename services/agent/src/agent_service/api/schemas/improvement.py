from __future__ import annotations

from pydantic import Field

from ...domain.models.common import StrictModel
from ...domain.models.improvement import (
    AcceptedFeedback,
    Diagnosis,
    EvalReport,
    ImprovementCase,
    ProfileCandidate,
)


class ReviewerRequest(StrictModel):
    reviewer_id: str = Field(min_length=1)


class CanaryAssessmentRequest(ReviewerRequest):
    severe_regressions: int = Field(ge=0)


class PrepareCandidateRequest(StrictModel):
    accepted_feedback: list[AcceptedFeedback] = Field(min_length=1)


class PrepareCandidateResponse(StrictModel):
    regression_cases: list[ImprovementCase]
    diagnoses: list[Diagnosis]
    candidate: ProfileCandidate | None = None
    reason: str
    candidate_recommended: bool = False
    authorization_required: bool = False


class BuildCandidateRequest(StrictModel):
    accepted_feedback: list[AcceptedFeedback] = Field(min_length=1)
    diagnoses: list[Diagnosis] = Field(min_length=1)
    authorized_by: str = Field(min_length=1)


class CandidateEvaluationRequest(StrictModel):
    report: EvalReport
