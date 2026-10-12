from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from ...application.profile_package_lifecycle import (
    CreateProfilePackage,
    PackageLifecycleError,
    ProfilePackageLifecycle,
)
from ...domain.errors import AgentServiceError
from ...domain.models.runs import ProfileRef
from ...infrastructure.supabase_profile_packages import SupabaseProfilePackageRepository
from ...profiles import ProfileRegistryError
from ..dependencies import refresh_current_profiles
from ..schemas import ProfileRulesResponse

router = APIRouter(
    prefix="/v1/profiles",
    tags=["profiles"],
    dependencies=[Depends(refresh_current_profiles)],
)


def _lifecycle(request: Request) -> ProfilePackageLifecycle:
    service = request.app.state.profile_package_lifecycle
    if service is None:
        raise HTTPException(503, detail="请启用 Supabase 规则资源包模式")
    return service  # type: ignore[no-any-return]


def _package_error(exc: Exception) -> HTTPException:
    if isinstance(exc, PackageLifecycleError):
        return HTTPException(exc.status, detail={"code": exc.code, "message": exc.message})
    if isinstance(exc, AgentServiceError):
        return HTTPException(
            503, detail={"code": "PACKAGE_STORAGE_FAILED", "message": "规则包存储失败，可重试"}
        )
    return HTTPException(422, detail={"code": "PACKAGE_INVALID", "message": "规则包资源校验失败"})


@router.post("/packages", status_code=201)
async def create_package(value: CreateProfilePackage, user_id: UUID, request: Request) -> dict[str, object]:
    try:
        return await _lifecycle(request).create(value, str(user_id))
    except (PackageLifecycleError, AgentServiceError, ValueError, OSError) as exc:
        raise _package_error(exc) from exc


@router.delete("/packages/{package_id}")
async def delete_package(
    package_id: UUID,
    user_id: UUID,
    request: Request,
    confirmed: bool = Query(default=False),
) -> dict[str, object]:
    if not confirmed:
        raise HTTPException(422, detail={"code": "CONFIRMATION_REQUIRED", "message": "请确认删除规则包"})
    try:
        return await _lifecycle(request).retire(str(package_id), str(user_id))
    except (PackageLifecycleError, AgentServiceError, ValueError, OSError) as exc:
        raise _package_error(exc) from exc


@router.get("")
async def list_profiles(request: Request) -> dict[str, Any]:
    registry = request.app.state.profile_registry
    return {
        "items": [
            {
                "key": snapshot.manifest.key,
                "version": snapshot.manifest.version,
                "status": snapshot.manifest.status,
                "adapter": snapshot.manifest.adapter,
                "checksum": snapshot.checksum,
                "capabilities": snapshot.manifest.capabilities,
            }
            for snapshot in registry.list_profiles()
        ],
        "errors": list(registry.errors),
    }


@router.get(
    "/{profile_key}/versions/{version}/rules",
    response_model=ProfileRulesResponse,
)
async def get_profile_rules(
    profile_key: str,
    version: str,
    request: Request,
) -> ProfileRulesResponse:
    registry = request.app.state.profile_registry
    try:
        binding = registry.bind(profile_key, version, allow_experimental=True)
    except ProfileRegistryError as exc:
        raise HTTPException(status_code=404, detail=exc.message) from exc
    return ProfileRulesResponse(
        profile=binding.profile,
        status=binding.status,
        rules=binding.rules,
    )


@router.get("/{profile_key}/versions/{version}/package")
async def get_profile_package(
    profile_key: str, version: str, checksum: str, request: Request
) -> dict[str, object]:
    packages: SupabaseProfilePackageRepository | None = request.app.state.profile_packages
    if packages is None:
        raise HTTPException(status_code=503, detail="Profile package mode is not enabled.")
    return await packages.display(ProfileRef(key=profile_key, version=version, checksum=checksum))
