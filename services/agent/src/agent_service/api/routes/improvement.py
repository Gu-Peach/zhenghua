from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request

from ...application.improvement_workflow import ImprovementWorkflow
from ..dependencies import require_internal_service
from ..schemas import (
    BuildCandidateRequest,
    CanaryAssessmentRequest,
    CandidateEvaluationRequest,
    PrepareCandidateRequest,
    PrepareCandidateResponse,
    ReviewerRequest,
)

router = APIRouter(
    prefix="/v1",
    tags=["improvement"],
    dependencies=[Depends(require_internal_service)],
)


def _workflow(request: Request) -> ImprovementWorkflow:
    workflow = getattr(request.app.state, "improvement_workflow", None)
    if workflow is None:
        raise HTTPException(status_code=503, detail="Improvement workflow is not configured.")
    return cast(ImprovementWorkflow, workflow)


def _model_json(model: Any) -> dict[str, Any]:
    return cast(dict[str, Any], model.model_dump(mode="json"))


@router.get("/profile-candidates/{candidate_id}")
async def get_candidate(candidate_id: str, request: Request) -> dict[str, Any]:
    try:
        candidate = await request.app.state.candidate_repository.get(candidate_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Profile candidate not found.") from exc
    return _model_json(candidate)


@router.post("/profile-candidates/prepare", response_model=PrepareCandidateResponse)
async def prepare_candidate(
    payload: PrepareCandidateRequest,
    request: Request,
) -> PrepareCandidateResponse:
    try:
        result = await _workflow(request).prepare(payload.accepted_feedback)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PrepareCandidateResponse(
        regression_cases=result.regression_cases,
        diagnoses=result.diagnoses,
        candidate=result.candidate,
        reason=result.reason,
        candidate_recommended=result.candidate_recommended,
        authorization_required=result.authorization_required,
    )


@router.post("/profile-candidates/build", response_model=PrepareCandidateResponse)
async def build_candidate(
    payload: BuildCandidateRequest,
    request: Request,
) -> PrepareCandidateResponse:
    try:
        result = await _workflow(request).build_candidate(
            feedback=payload.accepted_feedback,
            diagnoses=payload.diagnoses,
            authorized_by=payload.authorized_by,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return PrepareCandidateResponse(
        regression_cases=result.regression_cases,
        diagnoses=result.diagnoses,
        candidate=result.candidate,
        reason=result.reason,
        candidate_recommended=result.candidate_recommended,
        authorization_required=result.authorization_required,
    )


@router.post("/profile-candidates/{candidate_id}/evaluate")
async def evaluate_candidate(
    candidate_id: str,
    payload: CandidateEvaluationRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        result = await _workflow(request).evaluate(candidate_id, payload.report)
        await request.app.state.eval_repository.put(result.report)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "report": result.report.model_dump(mode="json"),
        "judgement": result.judgement.model_dump(mode="json"),
        "gate": result.gate.model_dump(mode="json"),
        "candidate": result.candidate.model_dump(mode="json"),
    }


@router.post("/profile-candidates/{candidate_id}/approve")
async def approve_candidate(
    candidate_id: str,
    payload: ReviewerRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        candidate = await _workflow(request).approve(candidate_id, payload.reviewer_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _model_json(candidate)


@router.post("/profile-candidates/{candidate_id}/reject")
async def reject_candidate(candidate_id: str, request: Request) -> dict[str, Any]:
    try:
        candidate = await _workflow(request).reject(candidate_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _model_json(candidate)


@router.post("/profile-candidates/{candidate_id}/rollback")
async def rollback_candidate(
    candidate_id: str,
    payload: ReviewerRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        candidate = await _workflow(request).rollback(candidate_id, payload.reviewer_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _model_json(candidate)


@router.post("/profile-candidates/{candidate_id}/canary-assessment")
async def assess_canary(
    candidate_id: str,
    payload: CanaryAssessmentRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        candidate = await _workflow(request).assess_canary(
            candidate_id,
            severe_regressions=payload.severe_regressions,
            reviewer_id=payload.reviewer_id,
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _model_json(candidate)


@router.get("/profile-candidates/{candidate_id}/audit")
async def candidate_audit(candidate_id: str, request: Request) -> dict[str, Any]:
    return {"items": await request.app.state.candidate_repository.audit_log(candidate_id)}


@router.get("/evals/{eval_run_id}")
async def get_eval(eval_run_id: str, request: Request) -> dict[str, Any]:
    try:
        report = await request.app.state.eval_repository.get(eval_run_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Evaluation report not found.") from exc
    return _model_json(report)


@router.get("/evals/{eval_run_id}/report")
async def get_eval_report(eval_run_id: str, request: Request) -> dict[str, Any]:
    return await get_eval(eval_run_id, request)
