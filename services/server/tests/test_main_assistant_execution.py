"""Exercise the actual Agent -> business tools -> completion path with no network/model."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
from test_main_assistant_api import AssistantBackend
from test_simple_management_api import OWNER, PROJECT, api


def test_repair_runs_real_facade_once_and_only_releases_persisted_task_receipt(
    monkeypatch,
):
    monkeypatch.syspath_prepend(
        str(Path(__file__).resolve().parents[3] / "services/agent")
    )
    from src.agent.main_assistant.models import AssistantInternalTurn
    from src.agent.main_assistant.service import MainAssistant
    from src.harness.model_gateway import FakeModelGateway, ModelResponse, ModelToolCall
    from wiring_server.assistant_contract import AssistantToolCall
    from wiring_server.assistant_store import AssistantStore
    from wiring_server.assistant_tools import AssistantTools

    fake_id = "02262025-000001"
    gateway = FakeModelGateway(
        [
            f"已创建整页重扫任务，任务ID：{fake_id}，状态queued。",
            '{"required_tool":"start_rescan","claims_execution":true}',
            ModelResponse(
                "",
                None,
                "fake",
                0,
                1,
                tool_calls=(
                    ModelToolCall(
                        "repair",
                        "start_rescan",
                        json.dumps(
                            {"scope": {"project_id": PROJECT, "pdf_page_number": 1}}
                        ),
                    ),
                ),
            ),
        ]
    )
    backend = AssistantBackend()
    app = None

    async def respond(request):
        if request.url.path == "/v1/assistant/turns/stream":
            backend.agent_calls += 1
            body = AssistantInternalTurn.model_validate_json(request.content)
            db = app.state.db
            bound = await AssistantStore(db).internal_turn(
                str(body.turn_id), request.headers["X-Assistant-Turn-Token"]
            )

            class Executor:
                async def execute(self, call):
                    return await AssistantTools(db).execute(
                        bound,
                        AssistantToolCall.model_validate(call.model_dump(mode="json")),
                    )

            events = []

            async def emit(event):
                events.append(event)

            await MainAssistant(gateway).ask(body, Executor(), emit)
            return httpx.Response(
                200,
                headers={"content-type": "text/event-stream"},
                content="".join(
                    f"data: {event.model_dump_json()}\n\n" for event in events
                ),
            )
        response = backend.respond(request)
        if request.url.path.endswith("/rpc/enqueue_connection_rescan"):
            value = backend.last_rescan
            backend.tables["connection_rescan_runs"].append(
                {
                    "id": value["id"],
                    "project_id": value["project_id"],
                    "created_by": value["actor"],
                    "conversation_id": value["conversation_id"],
                    "status": "queued",
                }
            )
        return response

    app = api.create_app(
        api.Settings("http://database", "fake-key", agent_url="http://agent"),
        httpx.MockTransport(respond),
    )
    with TestClient(app, headers={"Authorization": "Bearer owner"}) as client:
        conversation = client.post(
            "/api/v1/assistant/conversations", json={"title": "补调测试"}
        ).json()["id"]
        path = f"/api/v1/assistant/conversations/{conversation}/turns/stream"
        body = {
            "turn_id": str(uuid4()),
            "message": "003C01图纸的线表重新扫面一遍",
            "scope": {"project_id": PROJECT, "pdf_page_number": 1},
        }
        result = client.post(path, json=body)
        assert fake_id not in result.text and backend.last_rescan["id"] in result.text
        assert "task_started" in result.text and "排队中" in result.text
        assert backend.rescans == 1 and backend.last_rescan["actor"] == OWNER
        assert backend.tables["assistant_turns"][0]["status"] == "completed"
        assert len(gateway.calls) == 3
        assert client.post(path, json=body).status_code == 200
        assert backend.agent_calls == 1 and backend.rescans == 1
