from __future__ import annotations

from collections.abc import Awaitable, Callable
from pathlib import Path

from ..domain.models.profile_detection import ProfileDetectionResult
from ..graphs.profile_detection import ProfileDetectionRuntime, run_profile_detection


class ProfileDetectionTool:
    """Supervisor-facing capability that exposes only constrained first-page detection."""

    def __init__(
        self,
        runtime: ProfileDetectionRuntime,
        *,
        refresh_profiles: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self._runtime = runtime
        self._refresh_profiles = refresh_profiles

    async def detect(
        self,
        *,
        run_id: str,
        project_id: str,
        pdf_path: Path,
    ) -> ProfileDetectionResult:
        if self._refresh_profiles is not None:
            await self._refresh_profiles()
        return await run_profile_detection(
            runtime=self._runtime,
            run_id=run_id,
            project_id=project_id,
            pdf_path=pdf_path,
        )
