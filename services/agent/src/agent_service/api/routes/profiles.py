from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

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
