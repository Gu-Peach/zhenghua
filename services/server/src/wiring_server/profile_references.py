from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
from pathlib import Path
from typing import Any

from .repository import Repository, ServiceError

ROOT = Path(__file__).resolve().parents[4]
PROFILE_ROOT = ROOT / "services/agent/src/agent/extraction_agent/profiles"


class ProfileReferences:
    """Serve stored packages; retain local assets only for explicit publishing and legacy reads."""

    def __init__(self, db: Repository) -> None:
        self.db = db
        self.root = db.settings.profile_root or PROFILE_ROOT

    def catalog(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for path in sorted(self.root.glob("*/profile.json")):
            try:
                manifest = json.loads(path.read_text(encoding="utf-8"))
                if manifest.get("status") == "retired":
                    continue
                resources = {
                    name: self.safe(path.parent / value)
                    for name, value in manifest["resources"].items()
                }
                files = {self.safe(path)}
                for resource in resources.values():
                    files.update(
                        self.safe(child)
                        for child in resource.rglob("*")
                        if child.is_file()
                    ) if resource.is_dir() else files.add(resource)
                digest = hashlib.sha256()
                for file in sorted(files, key=lambda item: str(item).lower()):
                    digest.update(file.relative_to(ROOT).as_posix().encode())
                    digest.update(b"\0")
                    digest.update(file.read_bytes())
                result[manifest["key"]] = {
                    "profile_key": manifest["key"],
                    "profile_version": manifest["version"],
                    "display_name": manifest["display_name"],
                    "checksum": "sha256:" + digest.hexdigest(),
                    "resource_ref": f"local://{path.parent.name}/profile.json",
                    "manifest": manifest,
                    "resources": resources,
                }
            except (OSError, ValueError, KeyError, ServiceError):
                # An incomplete unrelated local draft must not block data management.
                continue
        return result

    @staticmethod
    def safe(path: Path) -> Path:
        resolved = path.resolve()
        if (
            path.is_symlink()
            or not resolved.is_relative_to(ROOT)
            or not resolved.exists()
        ):
            raise ServiceError(409, "PROFILE_RESOURCE_INVALID", "本地规则资源路径无效")
        return resolved

    async def register(self, key: str, user: str) -> dict[str, Any]:
        """Compatibility lookup: new imports must bind an already uploaded package."""
        option = (await self.available(user)).get(key)
        if option is None:
            raise ServiceError(
                422, "PROFILE_NOT_AVAILABLE", "规则尚未上传或不可用，请先发布规则包"
            )
        return await self.get(option["id"])

    async def available(self, user: str) -> dict[str, dict[str, Any]]:
        return {row["profile_key"]: row for row in await self.list(user)}

    @staticmethod
    def is_uploaded(row: dict[str, Any]) -> bool:
        from .profile_packages import REF

        match = REF.fullmatch(str(row.get("resource_ref") or ""))
        if not match:
            return False
        parts = match[1].split("/")
        return (
            parts[2] == row.get("profile_key")
            and parts[3] == row.get("profile_version")
            and "sha256:" + parts[4].removesuffix(".zip") == row.get("checksum")
        )

    async def package(self, row: dict[str, Any]) -> dict[str, Any]:
        import asyncio

        from .profile_packages import download, preview

        if row["resource_ref"].startswith("storage://"):
            content = await download(self.db, row)
            return await asyncio.to_thread(preview, content, row["checksum"])
        return await asyncio.to_thread(self.resource_package, row)

    async def list(self, user: str) -> list[dict[str, Any]]:
        rows = await self.db.all_rows(
            "extraction_profiles", {"order": "profile_key.asc,created_at.desc"}
        )
        latest: dict[str, dict[str, Any]] = {}
        for row in rows:
            if not self.is_uploaded(row):
                continue
            current = latest.get(row["profile_key"])

            def version(value: str) -> tuple[int, ...]:
                try:
                    return tuple(int(p) for p in value.split("."))
                except ValueError:
                    return (0,)

            if current is None or version(row["profile_version"]) > version(
                current["profile_version"]
            ):
                latest[row["profile_key"]] = row
        return [
            {**row, "can_delete": row["created_by"] == user, "can_rename": row["created_by"] == user}
            for row in latest.values()
        ]

    async def get(self, identifier: str) -> dict[str, Any]:
        rows = await self.db.rows(
            "extraction_profiles", {"id": f"eq.{identifier}", "limit": "1"}
        )
        if not rows:
            raise ServiceError(404, "PROFILE_NOT_FOUND", "规则引用不存在")
        return rows[0]

    async def remove(self, identifier: str, user: str) -> None:
        row = await self.get(identifier)
        if row["created_by"] != user:
            raise ServiceError(403, "ACCESS_DENIED", "只能删除自己登记的规则引用")
        if await self.db.rows(
            "extraction_projects", {"profile_id": f"eq.{identifier}", "limit": "1"}
        ):
            raise ServiceError(409, "PROFILE_IN_USE", "规则正被项目引用，不能删除")
        await self.db.call(
            "DELETE",
            "/rest/v1/extraction_profiles",
            params={"id": f"eq.{identifier}", "created_by": f"eq.{user}"},
        )

    async def rename(self, identifier: str, user: str, name: str, expected_name: str) -> dict[str, Any]:
        """Rename catalog metadata without changing immutable package bytes or project bindings."""
        row = await self.get(identifier)
        if row["created_by"] != user:
            raise ServiceError(403, "ACCESS_DENIED", "只能修改自己发布的规则名称")
        if not self.is_uploaded(row):
            raise ServiceError(422, "PROFILE_NOT_AVAILABLE", "仅已上传的规则包支持修改名称")
        if row["display_name"] == name:
            return {**row, "can_delete": True, "can_rename": True}
        if row["display_name"] != expected_name:
            raise ServiceError(409, "PROFILE_NAME_CONFLICT", "规则名称已变化，请刷新后重试")
        updated = await self.db.update(
            "extraction_profiles",
            {"id": f"eq.{identifier}", "created_by": f"eq.{user}", "display_name": f"eq.{expected_name}"},
            {"display_name": name},
        )
        if not updated:
            raise ServiceError(409, "PROFILE_NAME_CONFLICT", "规则名称已变化，请刷新后重试")
        return {**updated[0], "can_delete": True, "can_rename": True}

    def resource_package(self, row: dict[str, Any]) -> dict[str, Any]:
        option = self.catalog().get(row["profile_key"])
        if (
            not option
            or option["resource_ref"] != row["resource_ref"]
            or option["checksum"] != row["checksum"]
        ):
            raise ServiceError(
                409,
                "PROFILE_REFERENCE_STALE",
                "本地规则已变化或不可用，请重新登记当前版本",
            )
        manifest = dict(option["manifest"])
        virtual: dict[str, str] = {}
        files: list[dict[str, str]] = []
        images: list[dict[str, str]] = []
        size = 0
        for name, resource in option["resources"].items():
            virtual[name] = (
                f"resources/{name}"
                if resource.is_dir()
                else f"resources/{name}{resource.suffix}"
            )
            paths = sorted(resource.rglob("*")) if resource.is_dir() else [resource]
            for path in paths:
                if not path.is_file():
                    continue
                path = self.safe(path)
                suffix = path.suffix.lower()
                if suffix not in {".md", ".json", ".png", ".jpg", ".jpeg", ".webp"}:
                    continue
                content = path.read_bytes()
                size += len(content)
                if size > 30 * 1024 * 1024:
                    raise ServiceError(
                        413, "PROFILE_RESOURCE_TOO_LARGE", "规则预览资源过大"
                    )
                output_path = virtual[name] + (
                    "/" + path.relative_to(resource).as_posix()
                    if resource.is_dir()
                    else ""
                )
                if suffix in {".json", ".md"}:
                    files.append(
                        {"path": output_path, "content": content.decode("utf-8")}
                    )
                else:
                    media = mimetypes.guess_type(path.name)[0] or "image/png"
                    images.append(
                        {
                            "path": output_path,
                            "url": f"data:{media};base64,{base64.b64encode(content).decode()}",
                        }
                    )
        manifest["resources"] = virtual
        files.append(
            {
                "path": "profile.json",
                "content": json.dumps(manifest, ensure_ascii=False),
            }
        )
        return {"manifest": manifest, "files": files, "images": images}
