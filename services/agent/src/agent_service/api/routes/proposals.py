from __future__ import annotations

from typing import cast

from fastapi import APIRouter, Depends, HTTPException, Request

from ...domain.models.proposals import ResultProposal
from ..dependencies import require_internal_service

router = APIRouter(
    prefix="/v1/proposals",
    tags=["proposals"],
    dependencies=[Depends(require_internal_service)],
)


@router.get("/{proposal_id}", response_model=ResultProposal)
async def get_proposal(proposal_id: str, request: Request) -> ResultProposal:
    proposal = await request.app.state.proposal_repository.get(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="Result proposal not found.")
    return cast(ResultProposal, proposal)
