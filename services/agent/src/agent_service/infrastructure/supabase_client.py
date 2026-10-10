from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import quote

import httpx

from ..domain.enums import ErrorCode
from ..domain.errors import AgentServiceError


class SupabaseClient:
    """Small service-role PostgREST/Storage client with sanitized failures."""

    def __init__(
        self,
        *,
        base_url: str,
        service_role_key: str,
        timeout_seconds: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not base_url.strip() or not service_role_key.strip():
            raise ValueError("Supabase URL and service-role key are required.")
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
        }
        self._timeout = httpx.Timeout(timeout_seconds, connect=min(timeout_seconds, 30.0))
        self._transport = transport

    async def select(
        self,
        table: str,
        *,
        params: Mapping[str, str] | None = None,
    ) -> list[dict[str, Any]]:
        response = await self._request("GET", self._rest_url(table), params=params)
        payload = response.json()
        if not isinstance(payload, list):
            raise self._invalid_response("select", table)
        return [dict(item) for item in payload if isinstance(item, Mapping)]

    async def insert(
        self,
        table: str,
        rows: Mapping[str, Any] | Sequence[Mapping[str, Any]],
        *,
        on_conflict: str | None = None,
        upsert: bool = False,
    ) -> list[dict[str, Any]]:
        params = {"on_conflict": on_conflict} if on_conflict else None
        prefer = "return=representation"
        if upsert:
            prefer = f"resolution=merge-duplicates,{prefer}"
        response = await self._request(
            "POST",
            self._rest_url(table),
            params=params,
            json=rows,
            headers={"Prefer": prefer},
        )
        payload = response.json()
        if not isinstance(payload, list):
            raise self._invalid_response("insert", table)
        return [dict(item) for item in payload if isinstance(item, Mapping)]

    async def update(
        self,
        table: str,
        values: Mapping[str, Any],
        *,
        filters: Mapping[str, str],
    ) -> list[dict[str, Any]]:
        response = await self._request(
            "PATCH",
            self._rest_url(table),
            params=filters,
            json=values,
            headers={"Prefer": "return=representation"},
        )
        payload = response.json()
        if not isinstance(payload, list):
            raise self._invalid_response("update", table)
        return [dict(item) for item in payload if isinstance(item, Mapping)]

    async def delete(self, table: str, *, filters: Mapping[str, str]) -> None:
        await self._request(
            "DELETE",
            self._rest_url(table),
            params=filters,
            headers={"Prefer": "return=minimal"},
        )

    async def rpc(self, function: str, payload: Mapping[str, Any]) -> Any:
        response = await self._request("POST", f"{self._base_url}/rest/v1/rpc/{function}", json=payload)
        return response.json()

    async def upload(
        self,
        *,
        bucket: str,
        object_path: str,
        content: bytes,
        content_type: str,
        upsert: bool = True,
    ) -> None:
        path = f"{quote(bucket, safe='')}/{quote(object_path, safe='/')}"
        await self._request(
            "POST",
            f"{self._base_url}/storage/v1/object/{path}",
            content=content,
            headers={"Content-Type": content_type, "x-upsert": str(upsert).lower()},
        )

    async def download(self, *, bucket: str, object_path: str) -> bytes:
        path = f"{quote(bucket, safe='')}/{quote(object_path, safe='/')}"
        response = await self._request("GET", f"{self._base_url}/storage/v1/object/{path}")
        return response.content

    async def remove_objects(self, *, bucket: str, object_paths: Sequence[str]) -> None:
        if not object_paths:
            return
        await self._request(
            "DELETE",
            f"{self._base_url}/storage/v1/object/{quote(bucket, safe='')}",
            json={"prefixes": list(object_paths)},
        )

    async def create_signed_url(
        self,
        *,
        bucket: str,
        object_path: str,
        expires_in: int = 300,
    ) -> str:
        path = f"{quote(bucket, safe='')}/{quote(object_path, safe='/')}"
        response = await self._request(
            "POST",
            f"{self._base_url}/storage/v1/object/sign/{path}",
            json={"expiresIn": expires_in},
        )
        payload = response.json()
        signed = payload.get("signedURL") if isinstance(payload, Mapping) else None
        if not isinstance(signed, str) or not signed:
            raise self._invalid_response("signed URL", bucket)
        return signed if signed.startswith("http") else f"{self._base_url}/storage/v1{signed}"

    def _rest_url(self, table: str) -> str:
        if not table.replace("_", "").isalnum():
            raise ValueError("Invalid Supabase table name.")
        return f"{self._base_url}/rest/v1/{table}"

    async def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        headers = dict(self._headers)
        headers.update(kwargs.pop("headers", {}))
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout,
                transport=self._transport,
            ) as client:
                response = await client.request(method, url, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise AgentServiceError(
                ErrorCode.PERSISTENCE_UNAVAILABLE,
                "Supabase request failed before receiving a response.",
                retryable=True,
            ) from exc
        if response.status_code >= 300:
            retryable = response.status_code >= 500 or response.status_code == 429
            code = ErrorCode.PERSISTENCE_UNAVAILABLE if retryable else ErrorCode.INVALID_REQUEST
            raise AgentServiceError(
                code,
                f"Supabase request failed with HTTP {response.status_code}.",
                retryable=retryable,
                details={"status_code": response.status_code},
            )
        return response

    @staticmethod
    def _invalid_response(operation: str, resource: str) -> AgentServiceError:
        return AgentServiceError(
            ErrorCode.INTERNAL_ERROR,
            f"Supabase returned an invalid {operation} response for {resource}.",
            retryable=False,
        )
