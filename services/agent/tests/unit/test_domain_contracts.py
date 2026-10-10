from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent_service.domain.enums import RunType, ScopeType
from agent_service.domain.models.proposals import ProposalOperation
from agent_service.domain.models.runs import CreateRunRequest, RunScope


def base_request(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "run_type": RunType.FULL_EXTRACTION,
        "project_id": "project-1",
        "source_document_id": "document-1",
        "requested_by": "user-1",
        "scope": RunScope(type=ScopeType.PROJECT, id="project-1"),
    }
    payload.update(overrides)
    return payload


def test_scoped_remediation_requires_feedback_id() -> None:
    with pytest.raises(ValidationError, match="feedback_id"):
        CreateRunRequest.model_validate(
            base_request(
                run_type=RunType.SCOPED_CORRECTION,
                scope=RunScope(type=ScopeType.CONNECTION, id="connection-1"),
            )
        )


def test_profile_scope_is_restricted_to_improvement_runs() -> None:
    with pytest.raises(ValidationError, match="PROFILE scope"):
        CreateRunRequest.model_validate(base_request(scope=RunScope(type=ScopeType.PROFILE, id="zh")))


def test_replace_operation_requires_before_after_and_evidence() -> None:
    with pytest.raises(ValidationError):
        ProposalOperation(
            op="replace",
            target_type="CONNECTION",
            target_id="connection-1",
            before=None,
            after={"end_terminal": "FC103:2"},
            evidence_ids=[],
            reason="visible terminal",
            confidence=0.9,
        )
