"""Bounded, verified private ZIP resources, with no Agent runtime dependency."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import mimetypes
import re
import stat
import zipfile
from pathlib import PurePosixPath
from typing import Any
from urllib.parse import quote

import httpx

from .repository import Repository, ServiceError

LIMIT = 30 * 1024 * 1024
REF = re.compile(
    r"^storage://project-assets/(profiles/[0-9a-f-]{36}/[a-z][a-z0-9_-]{0,63}/\d+\.\d+\.\d+/[0-9a-f]{64}\.zip)$"
)


async def object_request(
    db: Repository, method: str, path: str, **kwargs: Any
) -> httpx.Response:
    headers = {
        "apikey": db.settings.service_key,
        "Authorization": "Bearer " + db.settings.service_key,
    }
    headers.update(kwargs.pop("headers", {}))
    try:
        return await db.http.request(
            method, db.settings.supabase_url + path, headers=headers, **kwargs
        )
    except httpx.HTTPError as exc:
        raise ServiceError(
            503, "PROFILE_STORAGE_UNAVAILABLE", "规则存储暂不可用，请稍后重试"
        ) from exc


def digest(content: bytes) -> str:
    return "sha256:" + hashlib.sha256(content).hexdigest()


def unpack(content: bytes, expected: str) -> tuple[dict[str, Any], dict[str, bytes]]:
    try:
        if len(content) > LIMIT or digest(content) != expected:
            raise ValueError("Invalid archive digest/size")
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            entries = archive.infolist()
            names = [f.filename for f in entries]
            if (
                len(names) > 500
                or len(set(names)) != len(names)
                or sum(f.file_size for f in entries) > LIMIT
            ):
                raise ValueError("Archive expansion limit")
            files = {}
            for item in entries:
                path = PurePosixPath(item.filename)
                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or "\\" in item.filename
                    or ":" in item.filename
                    or path.as_posix() != item.filename
                    or stat.S_ISLNK(item.external_attr >> 16)
                ):
                    raise ValueError("Unsafe archive path")
                files[item.filename] = archive.read(item)
        inventory = json.loads(files["manifest.json"])
        listed = inventory["files"]
        if len({f["path"] for f in listed}) != len(listed) or set(files) != {
            "manifest.json",
            *(f["path"] for f in listed),
        }:
            raise ValueError("Inventory mismatch")
        for item in listed:
            if (
                digest(files[item["path"]]) != item["checksum"]
                or len(files[item["path"]]) != item["size"]
            ):
                raise ValueError("Resource digest mismatch")
        if (
            digest(
                json.dumps(
                    sorted(listed, key=lambda f: f["path"]),
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            )
            != inventory["package_checksum"]
        ):
            raise ValueError("Inventory checksum mismatch")
        manifest = json.loads(files["profile.json"])
        if (
            manifest["key"] != inventory["profile_key"]
            or manifest["version"] != inventory["profile_version"]
            or manifest["adapter"]
            not in {"zh_native", "abb_native", "zh_gantry_reel_native"}
        ):
            raise ValueError("Profile identity mismatch")
        for value in manifest["resources"].values():
            if value not in files and not any(p.startswith(value + "/") for p in files):
                raise ValueError("Missing resource")
        return manifest, files
    except (ValueError, KeyError, TypeError, zipfile.BadZipFile, RuntimeError) as exc:
        raise ServiceError(
            422, "PROFILE_PACKAGE_INVALID", "规则包不完整或校验失败"
        ) from exc


async def download(db: Repository, row: dict[str, Any]) -> bytes:
    match = REF.fullmatch(row["resource_ref"])
    if not match:
        raise ServiceError(422, "PROFILE_RESOURCE_INVALID", "规则存储地址无效")
    response = await object_request(
        db, "GET", "/storage/v1/object/project-assets/" + quote(match[1], safe="/")
    )
    if response.is_error:
        raise ServiceError(503, "PROFILE_RESOURCE_UNAVAILABLE", "规则包暂不可用")
    return response.content


def preview(content: bytes, expected: str) -> dict[str, Any]:
    manifest, files = unpack(content, expected)
    texts, images = [], []
    for path, data in files.items():
        suffix = PurePosixPath(path).suffix.lower()
        if suffix in {".md", ".json"}:
            texts.append({"path": path, "content": data.decode("utf-8")})
        elif suffix in {".png", ".jpg", ".jpeg", ".webp"}:
            mime = mimetypes.guess_type(path)[0] or "image/png"
            images.append(
                {
                    "path": path,
                    "url": f"data:{mime};base64,{base64.b64encode(data).decode()}",
                }
            )
    return {"manifest": manifest, "files": texts, "images": images}
