from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request

from src.application.candidate_release import CandidateReleaseService
from src.application.improvement_workflow import ImprovementWorkflow
from src.api.dependencies import require_internal_service
from src.api.schemas import (
    BuildCandidateRequest,
    CanaryAssessmentRequest,
    CandidateEvaluationRequest,
    PrepareCandidateRequest,
    PrepareCandidateResponse,
    ReviewerRequest,
)
from src.api.schemas.improvement import (
    ConfirmCandidateReleaseRequest,
    ConfirmRuleUpdateRequest,
    StartEvaluationRequest,
)

router = APIRouter(
    prefix="/v1",
    tags=["improvement"],
    dependencies=[Depends(require_internal_service)],
)


def _release(request: Request) -> CandidateReleaseService:
    service = getattr(request.app.state, "candidate_release", None)
    if not isinstance(service, CandidateReleaseService):
        raise HTTPException(503, detail="Candidate evaluation/release is not configured.")
    return service


@router.post("/profile-candidates/{candidate_id}/evaluations", status_code=202)
async def start_evaluation(
    candidate_id: str, payload: StartEvaluationRequest, request: Request
) -> dict[str, Any]:
    raise HTTPException(410, detail="规则修改不再需要模型评测；请确认建议后调用 /confirm。")


@router.post("/profile-candidates/{candidate_id}/confirm")
async def confirm_rule_update(
    candidate_id: str, payload: ConfirmRuleUpdateRequest, request: Request
) -> dict[str, Any]:
    try:
        return _model_json(
            await _release(request).confirm(candidate_id, payload.reviewer_id, payload.confirmed)
        )
    except PermissionError as exc:
        raise HTTPException(403, detail=str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(409, detail=str(exc)) from exc


@router.post("/profile-candidates/{candidate_id}/publish")
async def publish_candidate(
    candidate_id: str, payload: ConfirmCandidateReleaseRequest, request: Request
) -> dict[str, Any]:
    try:
        return _model_json(
            await _release(request).publish(
                candidate_id, payload.evaluation_run_id, payload.reviewer_id, payload.confirmed
            )
        )
    except PermissionError as exc:
        raise HTTPException(403, detail=str(exc)) from exc
    except (KeyError, ValueError) as exc:
        raise HTTPException(409, detail=str(exc)) from exc


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
    raise HTTPException(
        409, detail="Client-supplied reports are not release evidence; start /evaluations instead."
    )


@router.post("/profile-candidates/{candidate_id}/approve")
async def approve_candidate(
    candidate_id: str,
    payload: ConfirmCandidateReleaseRequest,
    request: Request,
) -> dict[str, Any]:
    try:
        candidate = await _release(request).approve(
            candidate_id, payload.evaluation_run_id, payload.reviewer_id, payload.confirmed
        )
    except PermissionError as exc:
        raise HTTPException(403, detail=str(exc)) from exc
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
    raise HTTPException(
        409,
        detail=(
            "Client-reported canary counts cannot authorize publication; "
            "use /publish with a verified evaluation receipt."
        ),
    )


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
