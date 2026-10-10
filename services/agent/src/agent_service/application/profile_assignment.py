from __future__ import annotations

from ..domain.enums import ProfileDetectionStatus
from ..domain.models.profile_detection import ProfileAssignment, ProfileDetectionResult
from ..profiles import ProfileRegistry


class ProfileAssignmentService:
    def __init__(self, registry: ProfileRegistry) -> None:
        self._registry = registry

    def from_automatic_detection(self, result: ProfileDetectionResult) -> ProfileAssignment:
        if result.status != ProfileDetectionStatus.PROFILE_SELECTED or result.assigned_profile is None:
            raise ValueError("Detection result is not eligible for automatic assignment.")
        binding = self._registry.bind(
            result.assigned_profile.key,
            result.assigned_profile.version,
        )
        return ProfileAssignment(
            run_id=result.run_id,
            project_id=result.project_id,
            binding=binding,
            source="automatic",
            detected_profile=result.detected_profile,
        )

    def confirm(
        self,
        result: ProfileDetectionResult,
        *,
        profile_key: str,
        confirmed_by: str,
    ) -> ProfileAssignment:
        if result.status != ProfileDetectionStatus.WAITING_INPUT:
            raise ValueError("Only WAITING_INPUT results can be confirmed manually.")
        if not confirmed_by.strip():
            raise ValueError("confirmed_by is required.")
        detected = result.detected_profile
        version = detected.version if detected and detected.key == profile_key else None
        binding = self._registry.bind(profile_key, version, allow_experimental=True)
        return ProfileAssignment(
            run_id=result.run_id,
            project_id=result.project_id,
            binding=binding,
            source="user_confirmation",
            detected_profile=result.detected_profile,
            confirmed_by=confirmed_by,
        )
