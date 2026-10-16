from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from .repository import Repository, ServiceError

ROOT = Path(__file__).resolve().parents[4]
PROFILE_ROOT = ROOT / "services/agent/src/agent/extraction_agent/profiles"


class ProfileReferences:
    """Read trusted local manifests; client input never selects an arbitrary file path."""

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
        import asyncio

        option = (await asyncio.to_thread(self.catalog)).get(key)
        if option is None:
            raise ServiceError(
                422, "PROFILE_NOT_AVAILABLE", "本地规则不存在或资源不完整"
            )
        identifier = str(
            uuid5(
                NAMESPACE_URL,
                f"profile-ref:{key}:{option['profile_version']}:{option['checksum']}",
            )
        )
        filters = {
            "profile_key": f"eq.{key}",
            "profile_version": f"eq.{option['profile_version']}",
            "checksum": f"eq.{option['checksum']}",
            "limit": "1",
        }
        rows = await self.db.rows("extraction_profiles", filters)
        if rows:
            return rows[0]
        value = {
            name: option[name]
            for name in (
                "profile_key",
                "profile_version",
                "display_name",
                "checksum",
                "resource_ref",
            )
        }
        try:
            return await self.db.insert(
                "extraction_profiles", {**value, "id": identifier, "created_by": user}
            )
        except ServiceError:
            rows = await self.db.rows("extraction_profiles", filters)
            if rows:
                return rows[0]
            raise

    async def list(self, user: str) -> list[dict[str, Any]]:
        rows = await self.db.all_rows(
            "extraction_profiles", {"order": "profile_key.asc,created_at.desc"}
        )
        return [{**row, "can_delete": row["created_by"] == user} for row in rows]

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
