from __future__ import annotations

from ..domain.models.profiles import ProfileBinding


def require_stage_resources(profile: ProfileBinding, stage: str) -> None:
    resource_names = profile.rules.extraction.dynamic_resources.get(stage)
    if not resource_names:
        raise ValueError(f"Profile {profile.profile.key!r} does not define stage {stage!r}.")
    missing = sorted(set(resource_names) - profile.resolved_resources.keys())
    if missing:
        raise ValueError(f"Profile stage {stage!r} is missing resources: {', '.join(missing)}.")
