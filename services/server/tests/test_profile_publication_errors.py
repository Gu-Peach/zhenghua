from __future__ import annotations

import asyncio
import base64

import httpx
import pytest
from test_simple_management_api import api
from wiring_server.profile_authoring import ProfileAuthoring
from wiring_server.profile_packages import digest
from wiring_server.repository import Repository, ServiceError


def test_missing_rpc_has_safe_classification(caplog):
    async def check():
        with caplog.at_level("WARNING"):
            async with httpx.AsyncClient(
                transport=httpx.MockTransport(
                    lambda _: httpx.Response(
                        404,
                        json={"code": "PGRST202", "message": "private-database-detail"},
                    )
                )
            ) as http:
                db = Repository(
                    api.Settings("http://database", "private-service-key"), http
                )
                with pytest.raises(ServiceError) as caught:
                    await db.rpc(
                        "publish_extraction_profile", {"actor": "private-user"}
                    )
        assert caught.value.code == "DATABASE_FUNCTION_MISSING"
        assert caught.value.status == 503
        assert "private-" not in str(caught.value) + caplog.text

    asyncio.run(check())


def test_publish_after_missing_migration_reuses_uploaded_package(monkeypatch):
    content = b"verified-package-for-transport-test"
    checksum = digest(content)
    monkeypatch.setattr(
        "wiring_server.profile_authoring.unpack",
        lambda *_: (
            {"key": "sample", "version": "1.0.0", "display_name": "测试规则"},
            {},
        ),
    )
    missing = True
    uploads = {}
    registrations = []

    def handle(request):
        if request.url.host == "agent":
            return httpx.Response(
                200,
                json={
                    "content_base64": base64.b64encode(content).decode(),
                    "checksum": checksum,
                },
            )
        if request.url.path.startswith("/storage/v1/object/"):
            path = request.url.path
            if request.method == "GET":
                return httpx.Response(200, content=uploads[path])
            if path in uploads:
                return httpx.Response(409)
            uploads[path] = request.content
            return httpx.Response(200, json={})
        if request.url.path == "/rest/v1/rpc/publish_extraction_profile":
            if missing:
                return httpx.Response(
                    404, json={"code": "PGRST202", "message": "private-detail"}
                )
            row = {"id": "published", "created_by": "owner"}
            registrations.append(row)
            return httpx.Response(200, json=row)
        raise AssertionError(request.url.path)

    async def check():
        nonlocal missing
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            db = Repository(
                api.Settings(
                    "http://database", "private-key", agent_url="http://agent"
                ),
                http,
            )
            authoring = ProfileAuthoring(db)
            with pytest.raises(ServiceError) as caught:
                await authoring.publish("draft", 32, "owner")
            assert caught.value.code == "PROFILE_PUBLICATION_NOT_READY"
            assert caught.value.status == 503 and "迁移" in caught.value.message
            assert len(uploads) == 1 and not registrations
            missing = False
            result = await authoring.publish("draft", 32, "owner")
            assert result["can_delete"] is True and len(registrations) == 1
            assert len(uploads) == 1 and next(iter(uploads.values())) == content

    asyncio.run(check())
