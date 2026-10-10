from __future__ import annotations

from datetime import datetime

from pydantic import Field

from ..domain.models.common import FrozenModel, utc_now
from ..domain.models.runs import ProfileRef


class ContextResource(FrozenModel):
    resource_id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    object_ref: str = Field(min_length=1)
    checksum: str | None = None
    size_bytes: int = Field(default=0, ge=0)


class ContextManifest(FrozenModel):
    run_id: str = Field(min_length=1)
    agent_name: str = Field(min_length=1)
    profile: ProfileRef
    resources: list[ContextResource]
    constraints: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    total_bytes: int = Field(ge=0)
    image_count: int = Field(ge=0)


class ContextBuilder:
    def __init__(self, *, max_images: int = 8, max_total_bytes: int = 40 * 1024 * 1024) -> None:
        if max_images < 1 or max_total_bytes < 1:
            raise ValueError("Context budgets must be positive.")
        self.max_images = max_images
        self.max_total_bytes = max_total_bytes

    def build(
        self,
        *,
        run_id: str,
        agent_name: str,
        profile: ProfileRef,
        resources: list[ContextResource],
        constraints: dict[str, str | int | float | bool | None] | None = None,
    ) -> ContextManifest:
        image_count = sum(1 for item in resources if item.kind in {"image", "drawing_image"})
        total_bytes = sum(item.size_bytes for item in resources)
        if image_count > self.max_images:
            raise ValueError(f"Context contains {image_count} images; limit is {self.max_images}.")
        if total_bytes > self.max_total_bytes:
            raise ValueError(f"Context contains {total_bytes} bytes; limit is {self.max_total_bytes}.")
        return ContextManifest(
            run_id=run_id,
            agent_name=agent_name,
            profile=profile,
            resources=list(resources),
            constraints=constraints or {},
            total_bytes=total_bytes,
            image_count=image_count,
        )
