from __future__ import annotations

import re
from pathlib import Path

from pydantic import Field, field_validator, model_validator

from ..enums import ProfileStatus
from .common import FrozenModel
from .runs import ProfileRef


class ProfileManifest(FrozenModel):
    manifest_version: int = Field(default=1, ge=1)
    key: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    version: str = Field(pattern=r"^\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?$")
    display_name: str = Field(min_length=1)
    description: str = ""
    status: ProfileStatus
    adapter: str = Field(min_length=1)
    resource_mode: str = Field(pattern=r"^(packaged|legacy_reference)$")
    resources: dict[str, str]
    capabilities: list[str] = Field(default_factory=list)

    @field_validator("resources")
    @classmethod
    def validate_resources(cls, value: dict[str, str]) -> dict[str, str]:
        if not value:
            raise ValueError("Profile resources cannot be empty.")
        invalid = [name for name, path in value.items() if not name.strip() or not path.strip()]
        if invalid:
            raise ValueError(f"Profile resources contain empty entries: {invalid}")
        return value

    @property
    def semantic_version(self) -> tuple[int, int, int, str]:
        match = re.match(r"^(\d+)\.(\d+)\.(\d+)(.*)$", self.version)
        if match is None:
            return (0, 0, 0, self.version)
        return (int(match.group(1)), int(match.group(2)), int(match.group(3)), match.group(4))


class ProfileSnapshot(FrozenModel):
    manifest: ProfileManifest
    profile_root: Path
    manifest_path: Path
    resolved_resources: dict[str, Path]
    checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")

    def resource(self, name: str) -> Path:
        try:
            return self.resolved_resources[name]
        except KeyError as exc:
            raise KeyError(f"Profile resource {name!r} is not defined.") from exc


class ProfileDetectionRules(FrozenModel):
    summary: str = Field(min_length=1)
    strong_signals: list[str] = Field(min_length=1)
    supporting_signals: list[str] = Field(default_factory=list)
    exclusion_signals: list[str] = Field(default_factory=list)
    guidance: str = Field(min_length=1)


class ProfileExtractionRules(FrozenModel):
    workflow: list[str] = Field(min_length=1)
    dynamic_resources: dict[str, list[str]]
    business_rules: list[str] = Field(default_factory=list)
    output_contract: str = Field(min_length=1)


class ProfileRuleSet(FrozenModel):
    schema_version: int = Field(default=1, ge=1)
    profile_key: str = Field(pattern=r"^[a-z][a-z0-9_-]*$")
    display_name: str = Field(min_length=1)
    detection: ProfileDetectionRules
    extraction: ProfileExtractionRules

    @model_validator(mode="after")
    def validate_dynamic_resources(self) -> ProfileRuleSet:
        if not self.extraction.dynamic_resources:
            raise ValueError("dynamic_resources cannot be empty.")
        return self


class ProfileBinding(FrozenModel):
    profile: ProfileRef
    status: ProfileStatus
    adapter: str = Field(min_length=1)
    rules: ProfileRuleSet
    resolved_resources: dict[str, Path]

    def resource(self, name: str) -> Path:
        try:
            return self.resolved_resources[name]
        except KeyError as exc:
            raise KeyError(f"Bound profile resource {name!r} is not defined.") from exc
