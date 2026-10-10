from __future__ import annotations

from datetime import datetime

from pydantic import Field, model_validator

from ..enums import ProfileDetectionStatus
from .common import FrozenModel, StrictModel, utc_now
from .profiles import ProfileBinding
from .runs import ProfileRef


class ProfileCandidateScore(StrictModel):
    profile_key: str = Field(min_length=1)
    score: float = Field(ge=0.0, le=1.0)
    matched_signals: list[str] = Field(default_factory=list)


class ProfileRouterModelOutput(StrictModel):
    recognized: bool
    selected_profile_key: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    candidates: list[ProfileCandidateScore] = Field(default_factory=list)
    observed_signals: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_selection(self) -> ProfileRouterModelOutput:
        if self.recognized and not self.selected_profile_key:
            raise ValueError("recognized output requires selected_profile_key.")
        return self


class FirstPageEvidence(FrozenModel):
    pdf_page_number: int = 1
    image_checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    mime_type: str = "image/png"


class ProfileDetectionResult(StrictModel):
    run_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    status: ProfileDetectionStatus
    detected_profile: ProfileRef | None = None
    assigned_profile: ProfileRef | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    candidates: list[ProfileCandidateScore] = Field(default_factory=list)
    observed_signals: list[str] = Field(default_factory=list)
    reason: str = Field(min_length=1)
    evidence: FirstPageEvidence
    needs_user_confirmation: bool
    user_question: str | None = None

    @model_validator(mode="after")
    def validate_status(self) -> ProfileDetectionResult:
        if self.status == ProfileDetectionStatus.PROFILE_SELECTED:
            if self.assigned_profile is None or self.needs_user_confirmation:
                raise ValueError("PROFILE_SELECTED requires an assigned profile without confirmation.")
        if self.status == ProfileDetectionStatus.WAITING_INPUT:
            if not self.needs_user_confirmation or not self.user_question:
                raise ValueError("WAITING_INPUT requires a user question.")
        return self


class ProfileAssignment(FrozenModel):
    run_id: str
    project_id: str
    binding: ProfileBinding
    source: str = Field(pattern=r"^(automatic|user_confirmation)$")
    detected_profile: ProfileRef | None = None
    confirmed_by: str | None = None
    assigned_at: datetime = Field(default_factory=utc_now)
