from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from uuid import uuid4

import httpx
import pymupdf
from fastapi.testclient import TestClient
from test_simple_management_api import OTHER, OWNER, Backend, api

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services/agent"))
import asyncio

import pytest
from src.agent.profile_agent import create_profile_agent
from src.agent.profile_agent.wizard import StageGenerate, WizardState
from src.config import AgentSettings
from src.extraction_main import create_app as create_host
from src.harness.model_gateway import FakeModelGateway
from wiring_server.profile_contract import StageGenerate as ServerGenerate
from wiring_server.profile_contract import WizardState as ServerState
from wiring_server.profile_packages import digest, download, unpack
from wiring_server.repository import Repository, ServiceError


def test_conversation_contract_and_authenticated_stream(tmp_path):
    from src.agent.profile_agent.conversation import (
        ConversationEvent,
        ConversationState,
        ConversationTurn,
    )
    from wiring_server.profile_contract import ConversationEvent as PublicEvent
    from wiring_server.profile_contract import ConversationState as PublicState
    from wiring_server.profile_contract import ConversationTurn as PublicTurn

    assert ConversationTurn.model_json_schema() == PublicTurn.model_json_schema()
    assert ConversationState.model_json_schema() == PublicState.model_json_schema()
    assert ConversationEvent.model_json_schema() == PublicEvent.model_json_schema()
    gateway = FakeModelGateway(
        [json.dumps({"reply": "请上传标题栏样图，我会先核对分页规则。"})]
    )
    agent = create_profile_agent(
        AgentSettings(), state_root=tmp_path / "drafts", gateway=gateway
    )
    host = create_host(
        AgentSettings(environment="test", internal_token="trusted"), profile_agent=agent
    )
    backend = Backend()
    forwarded = []
    with TestClient(host) as agent_http:

        def handle(request):
            if request.url.host == "agent":
                forwarded.append(request)
                response = agent_http.request(
                    request.method,
                    request.url.path,
                    content=request.content,
                    headers={
                        "Authorization": request.headers["Authorization"],
                        "X-Profile-User-Id": request.headers["X-Profile-User-Id"],
                        "Content-Type": "application/json",
                    },
                )
                return httpx.Response(
                    response.status_code,
                    content=response.content,
                    headers=response.headers,
                )
            return backend.respond(request)

        settings = api.Settings(
            "http://database",
            "private-key",
            agent_url="http://agent",
            agent_token="trusted",
        )
        with TestClient(
            api.create_app(settings, httpx.MockTransport(handle))
        ) as client:
            headers = {"Authorization": "Bearer owner"}
            draft = client.post(
                "/api/v1/profile/drafts",
                headers=headers,
                json={"key": "chat_demo", "display_name": "聊天规则"},
            ).json()
            path = f"/api/v1/profile/drafts/{draft['draft_id']}/conversation"
            assert client.get(path).status_code == 401
            assert (
                client.get(path, headers={"Authorization": "Bearer other"}).status_code
                == 403
            )
            state = client.get(path, headers=headers).json()
            assert state["messages"] == [] and state["stage"] == "classification"
            response = client.post(
                path + "/turns/stream",
                headers=headers,
                json={
                    "turn_id": str(uuid4()),
                    "revision": draft["revision"],
                    "message": "创建分类规则",
                },
            )
            assert (
                response.status_code == 200
                and "text/event-stream" in response.headers["content-type"]
            )
            assert (
                "event: progress" in response.text
                and "event: answer_delta" in response.text
            )
            assert (
                "event: completed" in response.text
                and "data:image" not in response.text
            )
            restored = client.get(path, headers=headers).json()
            assert (
                len(restored["messages"]) == 2 and restored["wizard"]["confirmed"] == {}
            )
    assert all(r.headers["Authorization"] == "Bearer trusted" for r in forwarded)


def test_authoring_public_contract_is_generated_from_agent():
    assert StageGenerate.model_json_schema() == ServerGenerate.model_json_schema()
    assert WizardState.model_json_schema() == ServerState.model_json_schema()


def test_pdf_sampling_contract_and_authenticated_proxy(tmp_path):
    from src.agent.profile_agent.models import PdfSampleRequest, PdfSampleResult
    from wiring_server.profile_contract import PdfSampleRequest as PublicRequest
    from wiring_server.profile_contract import PdfSampleResult as PublicResult

    assert PdfSampleRequest.model_json_schema() == PublicRequest.model_json_schema()
    assert PdfSampleResult.model_json_schema() == PublicResult.model_json_schema()
    gateway = FakeModelGateway([])
    agent = create_profile_agent(
        AgentSettings(), state_root=tmp_path / "drafts", gateway=gateway
    )
    host = create_host(
        AgentSettings(environment="test", internal_token="trusted"), profile_agent=agent
    )
    backend = Backend()
    with TestClient(host) as agent_http:

        def handle(request):
            if request.url.host == "agent":
                response = agent_http.request(
                    request.method,
                    request.url.path,
                    content=request.content,
                    headers={
                        "Authorization": request.headers["Authorization"],
                        "X-Profile-User-Id": request.headers["X-Profile-User-Id"],
                        "Content-Type": "application/json",
                    },
                )
                return httpx.Response(
                    response.status_code,
                    content=response.content,
                    headers=response.headers,
                )
            return backend.respond(request)

        with TestClient(
            api.create_app(
                api.Settings(
                    "http://database",
                    "private-key",
                    agent_url="http://agent",
                    agent_token="trusted",
                ),
                httpx.MockTransport(handle),
            )
        ) as client:
            headers = {"Authorization": "Bearer owner"}
            draft = client.post(
                "/api/v1/profile/drafts",
                headers=headers,
                json={"key": "pdf_demo", "display_name": "PDF规则"},
            ).json()
            with pymupdf.open() as document:
                for number in range(3):
                    document.new_page().insert_text((40, 50), f"Sample {number + 1}")
                content = document.tobytes()
            path = f"/api/v1/profile/drafts/{draft['draft_id']}/pdf-samples"
            body = {
                "revision": draft["revision"],
                "request_id": str(uuid4()),
                "filename": "sample.pdf",
                "content_base64": base64.b64encode(content).decode(),
            }
            assert client.post(path, json=body).status_code == 401
            assert (
                client.post(
                    path, headers={"Authorization": "Bearer other"}, json=body
                ).status_code
                == 403
            )
            response = client.post(path, headers=headers, json=body)
            assert response.status_code == 200
            sampled = response.json()
            assert (
                len(sampled["sample"]["pages"]) == 2
                and sampled["sample"]["page_count"] == 3
            )
            assert client.post(path, headers=headers, json=body).json() == sampled
            assert (
                client.post(
                    path, headers=headers, json={**body, "stage": "scan"}
                ).status_code
                == 422
            )
            restored = client.get(
                path.replace("/pdf-samples", "/conversation"), headers=headers
            ).json()
            assert restored["pdf_sample"] == sampled["sample"]
            assert not gateway.calls and not list((tmp_path / "drafts").rglob("*.pdf"))


def test_storage_transport_and_invalid_archives_are_safe():
    async def check():
        def fail(request):
            raise httpx.ConnectError("private diagnostic", request=request)

        async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as http:
            db = Repository(api.Settings("http://database", "private-key"), http)
            with pytest.raises(ServiceError) as caught:
                await download(
                    db,
                    {
                        "resource_ref": f"storage://project-assets/profiles/{OWNER}/demo/1.0.0/"
                        + "0" * 64
                        + ".zip"
                    },
                )
            assert caught.value.status == 503 and "private" not in str(caught.value)

    asyncio.run(check())
    with pytest.raises(ServiceError) as caught:
        unpack(b"not a zip", digest(b"not a zip"))
    assert caught.value.code == "PROFILE_PACKAGE_INVALID"


def test_authoring_proxy_confirmation_publish_catalog_and_preview(tmp_path):
    gateway = FakeModelGateway(
        [
            json.dumps(answer)
            for answer in [
                {
                    "rule_text": "标题栏读取工作区与页号",
                    "expected": {"plant_function": "002.C", "drawing_page_number": 3},
                },
                {"rule_text": "封面不提取", "expected": {"non_wiring": True}},
                {
                    "rule_text": "斜线放线及箭头方向，等号跨页引用",
                    "expected": {
                        "units": [
                            {
                                "unit_id": "a",
                                "connections": [
                                    {
                                        "start": {"terminal": "X3:51"},
                                        "references": [
                                            {
                                                "raw": "=080.C/42",
                                                "target_function": "080.C",
                                                "target_drawing_page": 42,
                                            }
                                        ],
                                    }
                                ],
                            }
                        ]
                    },
                },
                {
                    "rule_text": "按回指匹配最近终点",
                    "expected": {"end": {"terminal": "XD21:60"}},
                },
            ]
        ]
    )
    agent = create_profile_agent(
        AgentSettings(workspace_root=ROOT),
        state_root=tmp_path / "drafts",
        gateway=gateway,
    )
    host = create_host(
        AgentSettings(environment="test", internal_token="trusted"), profile_agent=agent
    )
    backend = Backend()
    published = []
    forwarded = []
    with TestClient(host) as agent_http:

        def handle(request):
            if request.url.host == "agent":
                forwarded.append(request)
                response = agent_http.request(
                    request.method,
                    request.url.path,
                    content=request.content,
                    headers={
                        "Authorization": request.headers["Authorization"],
                        "X-Profile-User-Id": request.headers["X-Profile-User-Id"],
                        "Content-Type": "application/json",
                    },
                )
                return httpx.Response(
                    response.status_code,
                    content=response.content,
                    headers=response.headers,
                )
            if request.url.path == "/rest/v1/rpc/publish_extraction_profile":
                value = json.loads(request.content)
                rows = backend.tables["extraction_profiles"]
                previous = next(
                    (r for r in rows if r["profile_key"] == value["profile_key_value"]),
                    None,
                )
                if previous:
                    if previous["created_by"] != value["actor"]:
                        return httpx.Response(403, json={"code": "PT403"})
                    return httpx.Response(200, json=previous)
                row = {
                    "id": str(uuid4()),
                    "profile_key": value["profile_key_value"],
                    "profile_version": value["version_value"],
                    "display_name": value["name_value"],
                    "checksum": value["checksum_value"],
                    "resource_ref": value["ref_value"],
                    "created_by": value["actor"],
                }
                rows.append(row)
                published.append(row)
                return httpx.Response(200, json=row)
            if (
                request.url.path.startswith("/storage/v1/object/project-assets/")
                and request.method == "GET"
            ):
                content = backend.uploads.get(request.url.path)
                return (
                    httpx.Response(200, content=content)
                    if content
                    else httpx.Response(404)
                )
            return backend.respond(request)

        server = api.create_app(
            api.Settings(
                "http://database",
                "test",
                agent_url="http://agent",
                agent_token="trusted",
            ),
            httpx.MockTransport(handle),
        )
        with TestClient(
            server,
            headers={"Authorization": "Bearer owner", "X-Profile-User-Id": OTHER},
        ) as client:
            create = {"key": "new_drawing", "display_name": "新图纸规则"}
            assert (
                client.post(
                    "/api/v1/profile/drafts", json={**create, "user_id": OTHER}
                ).status_code
                == 422
            )
            draft = client.post("/api/v1/profile/drafts", json=create).json()
            path = "/api/v1/profile/drafts/" + draft["draft_id"]
            assert all(r.headers["X-Profile-User-Id"] == OWNER for r in forwarded)
            assert (
                client.get(
                    path + "/wizard", headers={"Authorization": "Bearer other"}
                ).status_code
                == 403
            )
            assert (
                client.get(
                    "/api/v1/profile/drafts", headers={"Authorization": "Bearer other"}
                ).json()
                == []
            )
            assert (
                client.post(
                    path + "/publish", json={"revision": draft["revision"]}
                ).status_code
                == 422
            )
            assert not published
            pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20))
            pix.clear_with(255)
            source, target = str(uuid4()), str(uuid4())
            for image in (source, target):
                response = client.post(
                    path + "/images",
                    json={
                        "revision": draft["revision"],
                        "image_id": image,
                        "filename": "drawing.png",
                        "content_base64": base64.b64encode(pix.tobytes("png")).decode(),
                    },
                )
                assert response.status_code == 200, response.text
                draft = response.json()
            assert client.get(path + "/images/" + source).status_code == 200
            for stage in ("classification", "scan", "completion"):
                response = client.post(
                    path + f"/stages/{stage}/generate",
                    json={
                        "revision": draft["revision"],
                        "description": "按用户图纸读取规则",
                        "source_image": source,
                        "negative_images": [target]
                        if stage == "classification"
                        else [],
                        "targets": [
                            {"attachment_id": target, "function": "080.C", "page": 42}
                        ]
                        if stage == "completion"
                        else [],
                    },
                )
                assert response.status_code == 200, response.text
                state = response.json()
                candidate = state["candidates"][stage]
                response = client.post(
                    path + f"/stages/{stage}/confirm",
                    json={
                        "revision": state["draft"]["revision"],
                        "candidate_id": candidate["id"],
                        "rule_text": candidate["rule_text"],
                        "expected": [c["expected"] for c in candidate["cases"]],
                    },
                )
                assert response.status_code == 200, response.text
                draft = response.json()["draft"]
            response = client.post(
                path + "/publish", json={"revision": draft["revision"]}
            )
            assert response.status_code == 200, response.text
            receipt = response.json()
            assert receipt["profile_key"] == "new_drawing" and receipt[
                "resource_ref"
            ].startswith("storage://")
            assert len(published) == 1
            assert (
                client.post(
                    path + "/publish", json={"revision": draft["revision"]}
                ).json()["id"]
                == receipt["id"]
            )
            options = client.get("/api/v1/rule-library/local").json()
            assert any(p["profile_key"] == "new_drawing" for p in options)
            package = client.get("/api/v1/rule-library/" + receipt["id"])
            assert package.status_code == 200, package.text
            assert len(package.json()["images"]) >= 2
            assert (
                client.post(
                    "/api/v1/rule-library", json={"profile_key": "new_drawing"}
                ).json()["id"]
                == receipt["id"]
            )
