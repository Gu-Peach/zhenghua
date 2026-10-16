"""Visual uncertainty is model input; review decisions are program output."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ReviewModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


ReviewPhase = Literal["scan", "final"]
ProcessingStatus = Literal["scanned", "pending_completion", "completed", "failed"]


class VisualUncertainty(ReviewModel):
    field: Literal["direction", "start", "end", "page", "connection"]
    detail: str = Field(min_length=1)


class ReviewReason(ReviewModel):
    code: str = Field(min_length=1)
    field: str | None = None
    message: str = Field(min_length=1)


class ReviewDecision(ReviewModel):
    needs_review: bool
    review_reasons: list[ReviewReason] = Field(default_factory=list)
    processing_status: ProcessingStatus
