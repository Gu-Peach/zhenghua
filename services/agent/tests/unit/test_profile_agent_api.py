from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI, Header
from fastapi.testclient import TestClient

from src.agent.profile_agent import DraftCreate, ProfileActor, ProfileTurn, create_profile_agent
from src.agent.profile_agent.api import create_profile_router
from src.agent.profile_agent.models import ProfileError
from src.config import AgentSettings
from src.harness.model_gateway import FakeModelGateway, ModelResponse, ModelToolCall

ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture
def api(tmp_path, monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("API tests must not reach a real model or database")

    monkeypatch.setattr(httpx.AsyncClient, "request", forbidden)
    actor = ProfileActor(user_id=uuid4())
    gateway = FakeModelGateway(["当前资料不足以确定是规则问题还是模型偏离，请提供实际输出与原图。"])
    agent = create_profile_agent(
        AgentSettings(workspace_root=ROOT), state_root=tmp_path / "drafts", gateway=gateway
    )
    app = FastAPI()

    async def identity(x_test_actor: Annotated[UUID, Header()]) -> ProfileActor:
        return ProfileActor(user_id=x_test_actor)

    app.include_router(create_profile_router(agent, identity))
    with TestClient(app, headers={"X-Test-Actor": str(actor.user_id)}) as client:
        yield client, agent, actor, gateway


def new(client):
    response = client.post("/v1/profile/drafts", json={"key": "sample", "display_name": "测试草稿"})
    assert response.status_code == 200
    return response.json()


def test_delete_conversation_requires_owner_confirmation_and_current_revision(api):
    client, agent, actor, gateway = api
    draft = new(client)
    path = f"/v1/profile/drafts/{draft['draft_id']}"
    body = {"revision": draft["revision"], "confirmed": True}
    assert client.request("DELETE", path, json={"revision": 1}).status_code == 422
    assert client.request("DELETE", path, json={**body, "confirmed": False}).status_code == 422
    assert client.request(
        "DELETE", path, json=body, headers={"X-Test-Actor": str(uuid4())}
    ).status_code == 403
    updated = agent.store.mutate(
        UUID(draft["draft_id"]), actor, draft["revision"], "another-window", lambda *_: {}
    ).model_dump(mode="json")
    response = client.request("DELETE", path, json=body)
    assert response.status_code == 409 and response.json()["detail"]["code"] == "VERSION_CONFLICT"
    assert client.get(path).json() == updated
    body["revision"] = updated["revision"]
    response = client.request("DELETE", path, json=body)
    assert response.status_code == 204 and response.content == b""
    assert client.request("DELETE", path, json=body).status_code == 204
    assert client.get(path).status_code == 404
    assert client.get(path + "/conversation").status_code == 404
    assert client.get("/v1/profile/drafts").json() == []
    assert gateway.calls == []


def test_deleted_draft_cannot_be_recreated_or_changed_by_an_in_flight_request(api):
    client, agent, actor, gateway = api
    draft = new(client)
    other = client.post(
        "/v1/profile/drafts", json={"key": "remaining", "display_name": "保留会话"}
    ).json()
    identifier = UUID(draft["draft_id"])
    root, _ = agent.store.root_for(identifier, actor)
    files = {path: agent.store.file(root, path).read_bytes() for path in agent.store.inventory(root)}
    history = agent.store.audit(identifier, actor)
    agent.store.delete(identifier, actor, draft["revision"])
    with pytest.raises(ProfileError, match="已删除"):
        agent.store.mutate(identifier, actor, draft["revision"], "late-turn", lambda *_: {})
    response = client.post(
        "/v1/profile/drafts",
        json={"draft_id": str(identifier), "key": draft["key"], "display_name": "测试草稿"},
    )
    assert response.status_code == 404
    assert client.get("/v1/profile/drafts").json() == [other]
    assert {path: agent.store.file(root, path).read_bytes() for path in files} == files
    with agent.store._db() as db:
        count = db.execute(
            "select count(*) from revisions where draft=?", (str(identifier),)
        ).fetchone()[0]
        assert count == len(history)
    # Reopening the repository must retain the tombstone across process restarts.
    from src.agent.profile_agent.store import DraftStore

    reopened = DraftStore(agent.store.root, agent.store.registry)
    assert [item.draft_id for item in reopened.list_drafts(actor)] == [UUID(other["draft_id"])]
    assert gateway.calls == []


def test_router_is_independently_mountable_and_caller_identity_is_not_model_input(api):
    client, agent, actor, gateway = api
    draft = new(client)
    path = f"/v1/profile/drafts/{draft['draft_id']}"
    assert client.get(path).status_code == 200
    assert client.get(path, headers={"X-Test-Actor": str(uuid4())}).status_code == 403
    assert client.get(path + "/files", params={"path": "../secret.json"}).status_code == 422
    assert (
        client.post(
            path + "/turns", json={"message": "问题", "expected_revision": 1, "user_id": str(actor.user_id)}
        ).status_code
        == 422
    )
    response = client.post(path + "/turns", json={"message": "为何会加GTR？", "expected_revision": 1})
    assert response.status_code == 200 and response.json()["revision"] == 1
    assert not response.json()["changed_files"]
    assert len(gateway.calls) == 1


def test_stream_outputs_public_answer_and_committed_result_with_no_private_reasoning(api):
    client, _, _, _ = api
    draft = new(client)
    path = f"/v1/profile/drafts/{draft['draft_id']}"
    result = client.post(path + "/turns/stream", json={"message": "为什么有前缀？", "expected_revision": 1})
    assert result.status_code == 200
    assert "event: answer_delta" in result.text and "event: completed" in result.text
    assert "reasoning_content" not in result.text
    assert client.get(path + "/audit").json()[0]["revision"] == 1
    assert client.post(path + "/export", json={"revision": 1}).status_code == 422


def test_upload_is_validated_and_expected_confirmation_cannot_be_invented(api):
    client, _, _, _ = api
    draft = new(client)
    path = f"/v1/profile/drafts/{draft['draft_id']}"
    invalid = client.post(
        path + "/images", json={"revision": 1, "filename": "wrong.png", "content_base64": "!!!"}
    )
    assert invalid.status_code == 422
    invalid = client.post(
        path + "/images",
        json={
            "revision": 1,
            "filename": "wrong.png",
            "content_base64": base64.b64encode(b"fake PNG").decode(),
        },
    )
    assert invalid.status_code == 422
    assert client.get(path).json()["revision"] == 1
    assert (
        client.post(
            path + "/expected/confirm",
            json={"revision": 1, "files": {"arbitrary.json": "sha256:" + "a" * 64}},
        ).status_code
        == 409
    )


def test_image_tool_really_adds_owned_pixels_to_vlm_input(api):
    client, agent, actor, _ = api
    draft = new(client)
    file = (
        ROOT
        / "services/agent/src/agent/extraction_agent/prompts/zh"
        / "examples_page_classification/006m01_identity/page_006m01.png"
    )
    view = client.post(
        f"/v1/profile/drafts/{draft['draft_id']}/images",
        json={
            "revision": 1,
            "filename": file.name,
            "content_base64": base64.b64encode(file.read_bytes()).decode(),
        },
    ).json()
    image_path = view["attachments"][0]["path"]
    gateway = FakeModelGateway(
        [
            ModelResponse(
                content="",
                parsed=None,
                model="fake",
                duration_seconds=0,
                attempts=1,
                tool_calls=(ModelToolCall("image", "view_images", json.dumps({"paths": [image_path]})),),
            ),
            "已读取用户原图，仍需实际提取输出以进一步归因。",
        ]
    )
    agent.gateway = gateway
    response = client.post(
        f"/v1/profile/drafts/{draft['draft_id']}/turns",
        json={"message": "看看原图判断为什么加前缀", "expected_revision": view["revision"]},
    )
    assert response.status_code == 200
    images = [
        part
        for message in gateway.calls[-1].messages
        if isinstance(message.get("content"), list)
        for part in message["content"]
        if part.get("type") == "image_url"
    ]
    assert len(images) == 1 and images[0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert response.json()["changed_files"] == []


def test_new_turns_refresh_head_and_old_turns_are_not_reused_after_edits(api):
    _, agent, actor, _ = api
    view = asyncio.run(agent.create(DraftCreate(key="demo", display_name="Demo"), actor))
    turn = ProfileTurn(message="介绍当前规则", expected_revision=1)
    first = asyncio.run(agent.ask(view.draft_id, turn, actor))
    assert first.revision == 1
    assert asyncio.run(agent.ask(view.draft_id, turn, actor)).cached
    with pytest.raises(ProfileError, match="输入已变化"):
        asyncio.run(agent.ask(view.draft_id, turn.model_copy(update={"message": "changed"}), actor))
    file = (
        ROOT
        / "services/agent/src/agent/extraction_agent/prompts/zh"
        / "examples_page_classification/006m01_identity/page_006m01.png"
    )
    agent.store.attach(view.draft_id, actor, 1, uuid4(), file.name, file.read_bytes())
    with pytest.raises(ProfileError, match="旧回复"):
        asyncio.run(agent.ask(view.draft_id, turn, actor))
