from __future__ import annotations

import json
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from test_assistant_number_search import NumberBackend
from test_main_assistant_api import AssistantBackend, seed_turn
from test_simple_management_api import OWNER, PROJECT, api


@pytest.mark.parametrize("missing_second", [False, True])
def test_compound_completion_requires_all_receipts_and_uses_saved_child_answers(
    missing_second,
):
    backend = AssistantBackend()
    ids = [str(uuid4()), str(uuid4())]
    tools = ["propose_connection_edit", "diagnose_profile"]

    def respond(request):
        if request.url.path == "/v1/assistant/turns/stream":
            value = json.loads(request.content)
            for index, name in enumerate(tools):
                if index == 1 and missing_second:
                    continue
                backend.tables["assistant_actions"].append(
                    {
                        "id": ids[index],
                        "owner_id": OWNER,
                        "conversation_id": value["conversation_id"],
                        "turn_id": value["turn_id"],
                        "tool_name": name,
                        "status": "awaiting_confirmation",
                        "result": {
                            "delegated": True,
                            "answer": "数据候选未提交"
                            if index == 0
                            else "规则建议未发布",
                        },
                    }
                )
            backend.events = [
                {"type": "answer_delta", "message": "错误模型摘要：已修改并发布"},
                {
                    "type": "completed",
                    "data": {
                        "completion_verified": True,
                        "verification_version": 2,
                        "disposition": "executed",
                        "required_tool": tools[0],
                        "action_id": ids[0],
                        "required_tools": tools,
                        "action_receipts": [
                            {"tool_name": name, "action_id": identifier}
                            for name, identifier in zip(tools, ids)
                        ],
                    },
                },
            ]
        return backend.respond(request)

    app = api.create_app(
        api.Settings("http://database", "fake-key", agent_url="http://agent"),
        httpx.MockTransport(respond),
    )
    with TestClient(app, headers={"Authorization": "Bearer owner"}) as client:
        conversation = client.post(
            "/api/v1/assistant/conversations", json={"title": "复合任务"}
        ).json()["id"]
        result = client.post(
            f"/api/v1/assistant/conversations/{conversation}/turns/stream",
            json={"message": "修改数据然后更新规则"},
        )
        assert "错误模型摘要" not in result.text
        row = backend.tables["assistant_turns"][0]
        if missing_second:
            assert row["status"] == "failed" and row["answer"] == ""
        else:
            assert (
                row["status"] == "completed"
                and "数据候选未提交" in row["answer"]
                and "规则建议未发布" in row["answer"]
            )


@pytest.mark.parametrize("outside", [False, True])
def test_multirow_edit_handoff_cannot_return_proposal_outside_selected_records(outside):
    backend = NumberBackend()
    selected = [row["id"] for row in backend.tables["extraction_connection_rows"][:2]]
    _, turn, headers = seed_turn(backend, {"project_id": PROJECT, "pdf_page_number": 1})

    def respond(request):
        if request.url.path == "/v1/explain/turns":
            body = json.loads(request.content)
            assert body["allow_edits"] is True and body["allow_rescan"] is False
            return httpx.Response(
                200,
                json={
                    "answer": "仅生成候选",
                    "proposals": [
                        {
                            "proposal_id": str(uuid4()),
                            "checksum": "sha256:" + "a" * 64,
                            "matched_count": 2,
                            "changes": [
                                {
                                    "connection_id": backend.tables[
                                        "extraction_connection_rows"
                                    ][2]["id"]
                                    if outside
                                    else selected[0]
                                }
                            ],
                        }
                    ],
                },
            )
        return backend.respond(request)

    app = api.create_app(
        api.Settings("http://database", "fake-key", agent_url="http://agent"),
        httpx.MockTransport(respond),
    )
    with TestClient(app, headers={"Authorization": "Bearer owner"}) as client:
        response = client.post(
            f"/api/internal/assistant/turns/{turn}/tools",
            headers=headers,
            json={
                "name": "propose_connection_edit",
                "arguments": {
                    "scope": {
                        "project_id": PROJECT,
                        "pdf_page_number": 1,
                        "connection_ids": selected,
                    },
                    "question": "核对这两条记录的终点",
                },
            },
        )
        assert response.status_code == (409 if outside else 200), response.text
        assert not any(
            "decide_explain_connection_edit" in request.url.path
            for request in backend.calls
        )
