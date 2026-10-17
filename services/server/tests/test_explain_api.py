from __future__ import annotations

import json
import sys
from pathlib import Path
from uuid import UUID, uuid4

import httpx
from fastapi.testclient import TestClient
from test_simple_management_api import OTHER, OWNER, PROJECT, ROW, Backend, api

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "services/agent"))
from src.agent.explain_agent import ExplainAgent
from src.agent.explain_agent.models import ExplainEvent, ExplainTurn
from src.agent.explain_agent.repository import SupabaseExplanationRepository
from src.config import AgentSettings
from src.extraction_main import create_app as create_agent_app
from src.harness.model_gateway import FakeModelGateway, ModelResponse, ModelToolCall
from src.infrastructure.supabase_client import SupabaseClient
from wiring_server.explain_contract import ExplainEvent as ServerEvent
from wiring_server.explain_contract import ExplainTurn as ServerTurn


def body():
    return {
        "project_id": PROJECT,
        "connection_id": ROW,
        "conversation_id": str(uuid4()),
        "turn_id": str(uuid4()),
        "message": "解释端子的来源",
    }


def test_generated_public_contract_matches_agent_models():
    assert ExplainTurn.model_json_schema() == ServerTurn.model_json_schema()
    assert ExplainEvent.model_json_schema() == ServerEvent.model_json_schema()


def test_authenticated_server_agent_stream_is_read_only_and_identity_cannot_be_spoofed():
    backend = Backend()
    repository = SupabaseExplanationRepository(
        SupabaseClient(
            base_url="http://database",
            service_role_key="PRIVATE-KEY",
            transport=httpx.MockTransport(backend.respond),
        )
    )
    gateway = FakeModelGateway(
        [
            ModelResponse(
                content="",
                parsed=None,
                model="fake",
                duration_seconds=0,
                attempts=1,
                tool_calls=(
                    ModelToolCall(
                        "query_1", "search_connections", '{"drawing_page":"003C01"}'
                    ),
                ),
            ),
            "原页003C01的XA:8经跨页引用连接到004C01的XD10:1。",
        ]
    )
    agent = ExplainAgent(repository, gateway)
    host = create_agent_app(
        AgentSettings(environment="test", internal_token="service-token"), agent
    )
    forwarded = []
    with TestClient(host) as agent_http:

        def handle(request):
            if request.url.host == "agent":
                forwarded.append(request)
                response = agent_http.post(
                    request.url.path,
                    content=request.content,
                    headers={
                        "Authorization": request.headers["Authorization"],
                        "X-Explain-User-Id": request.headers["X-Explain-User-Id"],
                        "Content-Type": "application/json",
                    },
                )
                return httpx.Response(
                    response.status_code,
                    content=response.content,
                    headers=response.headers,
                )
            return backend.respond(request)

        server = api.create_app(
            api.Settings(
                "http://database",
                "test-key",
                agent_url="http://agent",
                agent_token="service-token",
            ),
            httpx.MockTransport(handle),
        )
        with TestClient(server) as client:
            request = body()
            response = client.post(
                "/api/v1/explain/turns/stream",
                json=request,
                headers={"Authorization": "Bearer owner", "X-Explain-User-Id": OTHER},
            )
            assert response.status_code == 200 and "event: completed" in response.text
            packets = [
                json.loads(line[6:])
                for line in response.text.splitlines()
                if line.startswith("data: ")
            ]
            assert [event["type"] for event in packets[:3]] == [
                "tool_started",
                "tool_completed",
                "context",
            ]
            completed = packets[-1]["result"]
            assert len(completed["drawings"]) == 2 and "XA:8" in completed["answer"]
            assert (
                "image_path" not in response.text and "PRIVATE-KEY" not in response.text
            )
            assert all("data:image" not in json.dumps(event) for event in packets)
            assert forwarded[0].headers["X-Explain-User-Id"] == OWNER
            assert forwarded[0].headers["Authorization"] == "Bearer service-token"
            assert "user_id" not in json.loads(forwarded[0].content)
            count = len(forwarded)
            assert (
                client.post("/api/v1/explain/turns/stream", json=body()).status_code
                == 401
            )
            assert (
                client.post(
                    "/api/v1/explain/turns/stream",
                    json=body(),
                    headers={"Authorization": "Bearer other"},
                ).status_code
                == 403
            )
            assert (
                client.post(
                    "/api/v1/explain/turns/stream",
                    json={**body(), "actor": {"user_id": OTHER}},
                    headers={"Authorization": "Bearer owner"},
                ).status_code
                == 422
            )
            assert len(forwarded) == count
            assert all(
                call.method == "GET" or "/object/sign/" in call.url.path
                for call in backend.calls
            )


def test_agent_host_requires_internal_auth_and_does_not_initialize_model_for_unauthorized_requests():
    host = create_agent_app(
        AgentSettings(environment="production", internal_token="service-token")
    )
    with TestClient(host) as client:
        assert (
            client.post(
                "/v1/explain/turns", json=body(), headers={"X-Explain-User-Id": OWNER}
            ).status_code
            == 401
        )
        response = client.post(
            "/v1/explain/turns",
            json=body(),
            headers={
                "Authorization": "Bearer service-token",
                "X-Explain-User-Id": OWNER,
            },
        )
        assert (
            response.status_code == 503
            and response.json()["detail"]["code"] == "EXPLAIN_NOT_CONFIGURED"
        )
        assert client.get("/health").json()["worker_running"] is False
    with TestClient(
        create_agent_app(AgentSettings(environment="production"))
    ) as client:
        assert (
            client.post(
                "/v1/explain/turns",
                json=body(),
                headers={"X-Explain-User-Id": str(UUID(OWNER))},
            ).status_code
            == 503
        )


def test_server_masks_agent_failure_and_exports_event_schema():
    backend = Backend()

    def handle(request):
        if request.url.host == "agent":
            return httpx.Response(500, json={"detail": "PRIVATE-UPSTREAM-DETAIL"})
        return backend.respond(request)

    app = api.create_app(
        api.Settings("http://database", "test", agent_url="http://agent"),
        httpx.MockTransport(handle),
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/explain/turns/stream",
            json=body(),
            headers={"Authorization": "Bearer owner"},
        )
        assert (
            response.status_code == 500
            and "PRIVATE-UPSTREAM-DETAIL" not in response.text
        )
        schema = client.get("/openapi.json").json()
        assert "ExplainEvent" in schema["components"]["schemas"]
        assert "/api/v1/explain/turns/stream" in schema["paths"]
