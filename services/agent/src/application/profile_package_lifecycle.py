"""Human-created Profile packages, distinct from the AI candidate release workflow."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Literal
from uuid import NAMESPACE_URL, UUID, uuid5

from pydantic import Field, field_validator

from src.domain.enums import ProfileStatus
from src.domain.models.common import StrictModel
from src.domain.models.profiles import ProfileManifest, ProfileRuleSet
from src.infrastructure.supabase_profile_packages import SupabaseProfilePackageRepository
from src.profiles.package import safe_path, seal_package
from src.profiles.registry import ProfileRegistry

PromptName = Literal["classification_prompt", "page_scan_prompt", "cross_page_prompt"]


class CreateProfilePackage(StrictModel):
    base_package_id: UUID
    profile_key: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,63}$")
    display_name: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=4000)
    detection_summary: str = Field(min_length=1, max_length=4000)
    strong_signals: list[str] = Field(min_length=1, max_length=30)
    prompts: dict[PromptName, str] = Field(default_factory=dict)
    confirmed: Literal[True]

    @field_validator("display_name", "detection_summary")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("名称和识别说明不能为空")
        return value.strip()

    @field_validator("strong_signals")
    @classmethod
    def signals(cls, value: list[str]) -> list[str]:
        if any(not v.strip() or len(v) > 2000 for v in value):
            raise ValueError("识别特征不能为空或超过 2000 字符")
        return [v.strip() for v in value]

    @field_validator("prompts")
    @classmethod
    def valid_prompts(cls, value: dict[PromptName, str]) -> dict[PromptName, str]:
        if any(not prompt.strip() or len(prompt) > 100000 for prompt in value.values()):
            raise ValueError("Prompt 不能为空或超过 100000 字符")
        return value


class PackageLifecycleError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


class ProfilePackageLifecycle:
    def __init__(self, packages: SupabaseProfilePackageRepository, registry: ProfileRegistry) -> None:
        self.packages, self.registry = packages, registry
        self._lock = asyncio.Lock()

    async def create(self, value: CreateProfilePackage, user: str) -> dict[str, object]:
        """Validate inherited assets, publish a new key, and complete registration on retries."""
        user = str(UUID(user))
        async with self._lock:
            base_rows = await self.packages.client.select(
                "profile_resource_packages", params={"id": f"eq.{value.base_package_id}"}
            )
            if not base_rows or base_rows[0]["status"] == "retired":
                raise PackageLifecycleError(404, "TEMPLATE_UNAVAILABLE", "请选择一个未停用的规则模板")
            base = base_rows[0]
            root, manifest = await self.packages._resolve_row(base)
            package_id = str(uuid5(NAMESPACE_URL, f"human-profile-key:{value.profile_key}"))
            existing = await self.packages.client.select(
                "profile_resource_packages", params={"profile_key": f"eq.{value.profile_key}"}
            )
            if any(row["id"] != package_id or row["created_by"] != user for row in existing):
                raise PackageLifecycleError(409, "PROFILE_KEY_EXISTS", "规则标识已占用，请使用新的标识")
            if any(row["status"] == "retired" for row in existing):
                raise PackageLifecycleError(409, "PROFILE_KEY_RETIRED", "该规则标识已停用，请使用新的标识")
            with TemporaryDirectory(prefix="profile-create-") as temporary:
                target = Path(temporary) / "package"
                sealed = await asyncio.to_thread(
                    clone_package, root, target, value, manifest.package_checksum
                )
                if any(row["package_checksum"] != sealed for row in existing):
                    raise PackageLifecycleError(409, "PROFILE_KEY_EXISTS", "规则标识已占用且内容不同")
                row = await self.packages.upload(
                    target,
                    created_by=user,
                    status="active",
                    base_package_id=str(value.base_package_id),
                    package_id=package_id,
                )
            if row["created_by"] != user or row["package_checksum"] != sealed:
                raise PackageLifecycleError(409, "PROFILE_KEY_EXISTS", "规则标识已占用")
            if row["status"] != "active":
                await self.packages.client.update(
                    "profile_resource_packages",
                    {"status": "active"},
                    filters={"id": f"eq.{package_id}", "created_by": f"eq.{user}"},
                )
            await self.packages.load_registry(self.registry)
            return {
                "id": package_id,
                "profile_key": value.profile_key,
                "status": "active",
                "registered": True,
            }

    async def retire(self, package_id: str, user: str) -> dict[str, object]:
        async with self._lock:
            rows = await self.packages.client.select(
                "profile_resource_packages", params={"id": f"eq.{UUID(package_id)}"}
            )
            if not rows:
                raise PackageLifecycleError(404, "PACKAGE_NOT_FOUND", "规则包不存在")
            if rows[0]["created_by"] != str(UUID(user)):
                raise PackageLifecycleError(403, "PACKAGE_DELETE_DENIED", "只能删除自己创建的规则包")
            await self.packages.client.update(
                "profile_resource_packages",
                {"status": "retired"},
                filters={"id": f"eq.{package_id}", "created_by": f"eq.{user}"},
            )
            await self.packages.load_registry(self.registry)
            return {"id": package_id, "status": "retired", "historical_resources_retained": True}


def clone_package(root: Path, target: Path, value: CreateProfilePackage, base_checksum: str) -> str:
    """Copy a verified template without changing its cache, samples, or algorithm."""
    shutil.copytree(root, target)
    profile_path = target / "profile.json"
    profile = ProfileManifest.model_validate_json(profile_path.read_text(encoding="utf-8"))
    if profile.adapter not in {"zh_native", "abb_native"}:
        raise PackageLifecycleError(422, "UNSUPPORTED_ADAPTER", "当前模板的提取适配器尚未实现")
    profile = profile.model_copy(
        update={
            "key": value.profile_key,
            "version": "1.0.0",
            "display_name": value.display_name,
            "description": value.description,
            "status": ProfileStatus.ACTIVE,
        }
    )
    profile_path.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
    rules_path = target / safe_path(profile.resources["routing_rules"])
    rules = ProfileRuleSet.model_validate_json(rules_path.read_text(encoding="utf-8"))
    payload = rules.model_dump(mode="json")
    payload.update(profile_key=value.profile_key, display_name=value.display_name)
    payload["detection"].update(
        summary=value.detection_summary,
        strong_signals=value.strong_signals,
        supporting_signals=[],
        exclusion_signals=[],
        guidance=value.detection_summary,
    )
    rules_path.write_text(ProfileRuleSet.model_validate(payload).model_dump_json(indent=2), encoding="utf-8")
    for name, content in value.prompts.items():
        (target / safe_path(profile.resources[name])).write_text(content, encoding="utf-8")
    (target / "CHANGELOG.md").write_text(
        f"# {value.display_name}\n\n1.0.0：用户创建独立规则包。模板摘要：{base_checksum}。\n"
        "继承模板的三阶段 Schema、Few-shot 与确定性适配器；识别规则由创建者填写。\n",
        encoding="utf-8",
    )
    # Inventory excludes its own manifest, so using the business inventory digest is stable.
    manifest = seal_package(target, source_checksum="sha256:" + "0" * 64)
    seal_package(target, source_checksum=manifest.package_checksum)
    return manifest.package_checksum
