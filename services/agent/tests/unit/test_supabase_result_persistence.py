from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import httpx
import pytest

from agent_service.domain.enums import ScopeType
from agent_service.domain.errors import AgentServiceError
from agent_service.domain.models.proposals import (
    ProposalOperation,
    ProposalValidation,
    ResultProposal,
)
from agent_service.domain.models.runs import ModelRef, ProfileRef, RunScope
from agent_service.infrastructure.result_mapping import proposal_to_normalized_units
from agent_service.infrastructure.supabase_client import SupabaseClient
from agent_service.infrastructure.supabase_repositories import SupabaseProposalRepository


def _proposal(*records: dict[str, object]) -> ResultProposal:
    run_id = str(uuid4())
    project_id = str(uuid4())
    return ResultProposal(
        proposal_id=f"{run_id}:result-proposal",
        agent_run_id=run_id,
        project_id=project_id,
        base_result_version=0,
        profile=ProfileRef(key="zh", version="1.0.0"),
        model=ModelRef(name="fake-vlm"),
        scope=RunScope(type=ScopeType.PROJECT, id=project_id),
        operations=[
            ProposalOperation(
                op="add",
                target_type="CONNECTION",
                target_id=f"source-{index}",
                after=record,
                evidence_ids=["page-1"],
                reason="test",
                confidence=0.9,
            )
            for index, record in enumerate(records, start=1)
        ],
        validation=ProposalValidation(schema_valid=True, business_rules_valid=True),
    )


def test_proposal_mapping_groups_terminal_strip_and_preserves_queryable_fields() -> None:
    workspace_id = str(uuid4())
    drawing_id = str(uuid4())
    proposal = _proposal(
        {
            "unit_id": "unit-1",
            "pdf_page_number": 1,
            "source_pages": [1],
            "terminal_strip": "X21",
            "attribute": "690V",
            "line_number": "002C0101",
            "start_device": "-XD21",
            "start_name": "start",
            "start_terminal": "7",
            "end_device": "-M1",
            "end_name": "motor",
            "end_terminal": "U1",
            "current": "400A",
            "color": "BK",
            "is_cross_page": "same_page",
        },
        {
            "unit_id": "unit-1",
            "pdf_page_number": 1,
            "source_pages": [1],
            "terminal_strip": "X21",
            "line_number": "002C0102",
            "start_device": "-XD21",
            "start_terminal": "8",
            "end_device": "-M2",
            "end_terminal": "V1",
            "is_cross_page": "cross_page",
            "status": "needs_review",
        },
    )

    units = proposal_to_normalized_units(
        proposal,
        drawings=[
            {
                "id": drawing_id,
                "workspace_id": workspace_id,
                "pdf_page_number": 1,
            }
        ],
        workspaces=[{"id": workspace_id, "code": "002.C"}],
    )

    assert len(units) == 1
    assert units[0]["terminal_strip"] == "X21"
    assert units[0]["voltage_level"] == "690V"
    assert units[0]["needs_review"] is True
    assert [item["core_order"] for item in units[0]["connections"]] == [1, 2]
    first = units[0]["connections"][0]
    assert first["principle_number"] == "002C0101"
    assert first["start_code"] == "-XD21"
    assert first["end_description"] == "motor"
    assert first["current_value"] == "400A"
    assert first["color_mark"] == "BK"
    assert first["evidence"] == [
        {"drawing_id": drawing_id, "kind": "source", "raw_text": None}
    ]


def test_proposal_mapping_rejects_unmapped_drawing() -> None:
    proposal = _proposal({"pdf_page_number": 99, "line_number": "missing"})
    with pytest.raises(AgentServiceError, match="persisted drawing"):
        proposal_to_normalized_units(proposal, drawings=[], workspaces=[])


def test_supabase_proposal_repository_accepts_run_scoped_text_id() -> None:
    async def run() -> None:
        requests: list[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            if request.method == "GET":
                return httpx.Response(200, json=[])
            return httpx.Response(201, json=[json.loads(request.content)])

        client = SupabaseClient(
            base_url="http://supabase.local",
            service_role_key="secret",
            transport=httpx.MockTransport(handler),
        )
        repository = SupabaseProposalRepository(client)
        proposal = _proposal({"pdf_page_number": 1})
        assert await repository.submit(proposal) == proposal.proposal_id
        posted = json.loads(requests[-1].content)
        assert posted["id"] == proposal.proposal_id
        assert posted["id"].endswith(":result-proposal")

    asyncio.run(run())
