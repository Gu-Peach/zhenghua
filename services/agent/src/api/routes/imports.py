from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from src.application.supervisor_conversation import SupervisorConversationService
from src.domain.errors import AgentServiceError
from src.domain.models.imports import ImportedDocument, ProjectResultsResponse, ProjectTreeResponse
from src.api.dependencies import refresh_current_profiles

router = APIRouter(prefix="/v1", tags=["business-imports"],
                   dependencies=[Depends(refresh_current_profiles)])


def _error(exc: Exception) -> HTTPException:
    if isinstance(exc, PermissionError):
        return HTTPException(403, detail={"code": "ACCESS_DENIED", "message": "Project access denied."})
    if isinstance(exc, AgentServiceError):
        return HTTPException(503 if exc.retryable else 409,
                             detail={"code": exc.code.value, "message": exc.message})
    return HTTPException(400, detail={"code": "INVALID_REQUEST", "message": str(exc)})


@router.post("/imports", response_model=ImportedDocument, status_code=201)
async def import_pdf(
    request: Request, user_id: UUID, conversation_id: str = Query(min_length=1, max_length=200),
    project_name: str = Query(min_length=1, max_length=200),
    filename: str = Query(min_length=1, max_length=200),
    idempotency_key: str = Header(alias="Idempotency-Key", min_length=1, max_length=200),
) -> ImportedDocument:
    service = getattr(request.app.state, "supervisor_conversations", None)
    if not isinstance(service, SupervisorConversationService) or request.app.state.business_imports is None:
        raise HTTPException(503, detail="Business imports require Supabase and a configured Supervisor.")
    content = bytearray()
    async for chunk in request.stream():
        if len(content) + len(chunk) > request.app.state.settings.profile_max_pdf_bytes:
            raise HTTPException(413, detail="PDF exceeds the configured size limit.")
        content.extend(chunk)
    if not project_name.strip():
        raise HTTPException(400, detail="Project name must not be blank.")
    try:
        return await service.import_pdf(
            conversation_id=conversation_id, user_id=str(user_id), key=idempotency_key,
            project_name=project_name.strip(), filename=filename, content=bytes(content),
        )
    except (ValueError, PermissionError, AgentServiceError) as exc:
        raise _error(exc) from exc


@router.get("/projects/{project_id}/tree", response_model=ProjectTreeResponse)
async def get_tree(project_id: UUID, user_id: UUID, request: Request) -> ProjectTreeResponse:
    backend = request.app.state.business_imports
    if backend is None:
        raise HTTPException(503, detail="Supabase business read models are unavailable.")
    try:
        return await backend.tree(str(project_id), str(user_id))  # type: ignore[no-any-return]
    except (ValueError, PermissionError, AgentServiceError) as exc:
        raise _error(exc) from exc


@router.get("/projects/{project_id}/results", response_model=ProjectResultsResponse)
async def get_results(
    project_id: UUID, user_id: UUID, request: Request, result_version_id: UUID | None = None,
    offset: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=500),
) -> ProjectResultsResponse:
    backend = request.app.state.business_imports
    if backend is None:
        raise HTTPException(503, detail="Supabase business read models are unavailable.")
    try:
        return await backend.results(  # type: ignore[no-any-return]
            str(project_id), str(user_id), version=str(result_version_id) if result_version_id else None,
            offset=offset, limit=limit,
        )
    except (ValueError, PermissionError, AgentServiceError) as exc:
        raise _error(exc) from exc
