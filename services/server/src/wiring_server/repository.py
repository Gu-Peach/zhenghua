from __future__ import annotations

from typing import Any, cast
from urllib.parse import quote

import httpx

from .config import Settings


class ServiceError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        self.status, self.code, self.message = status, code, message
        super().__init__(message)


class Repository:
    """Central PostgREST/Storage adapter. No URLs or SQL in routes."""

    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self.settings, self.http = settings, http

    async def call(
        self, method: str, path: str, *, token: str | None = None, **kwargs: Any
    ) -> Any:
        headers = {
            "apikey": self.settings.service_key,
            "Authorization": f"Bearer {token or self.settings.service_key}",
        }
        headers.update(kwargs.pop("headers", {}))
        try:
            response = await self.http.request(
                method, self.settings.supabase_url + path, headers=headers, **kwargs
            )
        except httpx.HTTPError as exc:
            raise ServiceError(503, "DATABASE_UNAVAILABLE", "数据服务暂不可用") from exc
        if response.is_error:
            code = ""
            try:
                code = response.json().get("code", "")
            except ValueError:
                pass
            status = (
                409
                if code in {"PT409", "23505", "23503"}
                else 403
                if code == "PT403"
                else 503
                if response.status_code >= 500
                else 404 if code == "PT404" else 422 if code == "PT422" else 400
            )
            raise ServiceError(
                status,
                "VERSION_CONFLICT" if status == 409 else "DATABASE_REQUEST_FAILED",
                "数据已变更，请刷新后重试" if status == 409 else "数据操作失败",
            )
        return response.json() if response.content.strip() else None

    async def rows(
        self,
        table: str,
        params: dict[str, str] | None = None,
        *,
        token: str | None = None,
    ) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            await self.call("GET", f"/rest/v1/{table}", params=params, token=token),
        )

    async def all_rows(
        self, table: str, params: dict[str, str], *, token: str | None = None
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        while True:
            batch = await self.rows(
                table,
                {**params, "offset": str(len(rows)), "limit": "1000"},
                token=token,
            )
            rows.extend(batch)
            if len(batch) < 1000:
                return rows

    async def insert(self, table: str, value: dict[str, Any]) -> dict[str, Any]:
        rows = await self.call(
            "POST",
            f"/rest/v1/{table}",
            json=value,
            headers={"Prefer": "return=representation"},
        )
        return cast(dict[str, Any], rows[0])

    async def update(
        self, table: str, params: dict[str, str], value: dict[str, Any]
    ) -> list[dict[str, Any]]:
        return cast(
            list[dict[str, Any]],
            await self.call(
                "PATCH",
                f"/rest/v1/{table}",
                params=params,
                json=value,
                headers={"Prefer": "return=representation"},
            ),
        )

    async def rpc(self, name: str, value: dict[str, Any]) -> Any:
        return await self.call("POST", f"/rest/v1/rpc/{name}", json=value)

    async def signed_url(self, bucket: str, path: str) -> str:
        data = await self.call(
            "POST",
            f"/storage/v1/object/sign/{quote(bucket, safe='')}/{quote(path, safe='/')}",
            json={"expiresIn": 600},
        )
        return self.settings.supabase_url + "/storage/v1" + str(data["signedURL"])

    async def text_object(self, bucket: str, path: str) -> str:
        response = await self.http.get(
            self.settings.supabase_url
            + f"/storage/v1/object/{quote(bucket, safe='')}/{quote(path, safe='/')}",
            headers={
                "apikey": self.settings.service_key,
                "Authorization": f"Bearer {self.settings.service_key}",
            },
        )
        if response.is_error:
            raise ServiceError(503, "RESOURCE_UNAVAILABLE", "规则资源不可用")
        return response.content.decode("utf-8")

    async def require_project(
        self, project: str, user: str, *, write: bool = False, owner: bool = False
    ) -> dict[str, Any]:
        rows = await self.rows("extraction_projects", {"id": f"eq.{project}", "limit": "1"})
        if not rows:
            raise ServiceError(404, "PROJECT_NOT_FOUND", "项目不存在")
        if write and rows[0]["status"] == "archived":
            raise ServiceError(
                409, "PROJECT_ARCHIVED", "项目已归档或处于删除过程中，不能写入"
            )
        if rows[0]["owner_id"] == user:
            return rows[0]
        raise ServiceError(403, "ACCESS_DENIED", "没有项目操作权限")
