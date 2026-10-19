"""Deletion bridge acceptance without contacting a live Agent, model, or business database."""

from __future__ import annotations

import json
from copy import deepcopy
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from test_simple_management_api import OWNER, Backend, api
from wiring_server.profile_contract import DraftDeleteInput


@pytest.mark.parametrize("agent_status", [204, 403, 404, 409])
def test_delete_auth_contract_and_empty_success_response(agent_status):
    backend = Backend()
    before = deepcopy(backend.tables)
    forwarded = []
    draft = str(uuid4())

    def handle(request):
        if request.url.host != "agent":
            return backend.respond(request)
        forwarded.append(request)
        assert request.method == "DELETE"
        assert request.url.path == f"/v1/profile/drafts/{draft}"
        assert request.headers["X-Profile-User-Id"] == OWNER
        assert request.headers["Authorization"] == "Bearer trusted"
        assert json.loads(request.content) == {"revision": 3, "confirmed": True}
        if agent_status == 204:
            return httpx.Response(204)
        return httpx.Response(
            agent_status, json={"detail": {"code": "DRAFT_ERROR", "message": "会话不可删除"}}
        )

    settings = api.Settings(
        "http://database", "private-key", agent_url="http://agent", agent_token="trusted"
    )
    with TestClient(api.create_app(settings, httpx.MockTransport(handle))) as client:
        path = f"/api/v1/profile/drafts/{draft}"
        body = DraftDeleteInput(revision=3, confirmed=True).model_dump(mode="json")
        assert client.request("DELETE", path, json=body).status_code == 401
        headers = {"Authorization": "Bearer owner"}
        assert client.request(
            "DELETE", path, json={**body, "confirmed": False}, headers=headers
        ).status_code == 422
        assert client.request(
            "DELETE", path, json={**body, "owner": str(uuid4())}, headers=headers
        ).status_code == 422
        assert forwarded == []
        response = client.request("DELETE", path, json=body, headers=headers)
        assert response.status_code == agent_status
        if agent_status == 204:
            assert response.content == b""
        else:
            assert response.json()["detail"]["code"] == "DRAFT_ERROR"
    assert len(forwarded) == 1
    assert backend.tables == before
