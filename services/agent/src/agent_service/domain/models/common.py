from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
