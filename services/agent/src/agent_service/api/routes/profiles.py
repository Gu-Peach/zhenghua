from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ...domain.models.runs import ProfileRef
from ...infrastructure.supabase_profile_packages import SupabaseProfilePackageRepository
from ...profiles import ProfileRegistryError
from ..dependencies import require_internal_service
from ..schemas import ProfileRulesResponse

router = APIRouter(
    prefix="/v1/profiles",
    tags=["profiles"],
    dependencies=[Depends(require_internal_service)],
)


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
