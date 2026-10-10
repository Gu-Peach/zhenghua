from __future__ import annotations

from ...domain.enums import ProfileStatus
from ...domain.models.common import StrictModel
from ...domain.models.profiles import ProfileRuleSet
from ...domain.models.runs import ProfileRef


class ProfileRulesResponse(StrictModel):
    profile: ProfileRef
    status: ProfileStatus
    rules: ProfileRuleSet
