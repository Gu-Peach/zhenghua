from __future__ import annotations

from typing import Any, Literal
from uuid import uuid4

from pydantic import Field, model_validator

from .common import StrictModel
from .runs import ModelRef, ProfileRef, RunScope


class ProposalOperation(StrictModel):
    op: Literal["add", "replace", "remove"]
    target_type: str = Field(min_length=1)
    target_id: str = Field(min_length=1)
    expected_version: int | None = Field(default=None, ge=0)
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    evidence_ids: list[str] = Field(min_length=1)
    reason: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_operation_payload(self) -> ProposalOperation:
        if self.op == "add" and self.after is None:
            raise ValueError("add operations require after data.")
        if self.op == "replace" and (self.before is None or self.after is None):
            raise ValueError("replace operations require before and after data.")
        if self.op == "remove" and self.before is None:
            raise ValueError("remove operations require before data.")
        return self


class UnchangedAssertion(StrictModel):
    scope: str = Field(min_length=1)
    connection_ids: list[str] = Field(default_factory=list)
    hash: str = Field(min_length=1)


class ProposalValidation(StrictModel):
    schema_valid: bool
    business_rules_valid: bool
    regressions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ResultProposal(StrictModel):
    proposal_id: str = Field(default_factory=lambda: str(uuid4()))
    agent_run_id: str = Field(min_length=1)
    project_id: str = Field(min_length=1)
    base_result_version: int = Field(ge=0)
    profile: ProfileRef
    model: ModelRef
    scope: RunScope
    operations: list[ProposalOperation] = Field(default_factory=list)
    unchanged_assertions: list[UnchangedAssertion] = Field(default_factory=list)
    validation: ProposalValidation
    status: Literal["READY_FOR_REVIEW", "NEEDS_REVIEW", "REJECTED"] = "READY_FOR_REVIEW"


class ResultPatchProposal(ResultProposal):
    feedback_id: str = Field(min_length=1)
