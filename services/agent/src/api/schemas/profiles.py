from __future__ import annotations

from src.domain.enums import ProfileStatus
from src.domain.models.common import StrictModel
from src.domain.models.profiles import ProfileRuleSet
from src.domain.models.runs import ProfileRef


class ProfileRulesResponse(StrictModel):
    profile: ProfileRef
    status: ProfileStatus
    rules: ProfileRuleSet
