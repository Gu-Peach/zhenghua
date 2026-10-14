from __future__ import annotations

import asyncio
import json
from uuid import uuid4

from fastapi.testclient import TestClient

from src.application.model_output_view import model_output_view
from src.config import AgentSettings
from src.domain.enums import RunType, ScopeType
from src.domain.models.runs import CreateRunRequest, RunOptions, RunScope
from src.main import create_app


def test_projection_does_not_expose_hidden_reasoning_or_request_context() -> None:
    result = model_output_view(
        "run",
        0,
        {
            "agent": "page_scan",
            "model": "fake",
            "response_content": ('<think>PRIVATE_CHAIN</think>\n'
                                 '{"units":[],"reasoning_content":"PRIVATE_CHAIN"}'),
            "metadata": {"stage": "page_scan", "authorization": "SECRET", "prompt": "PRIVATE_PROMPT"},
        },
    )
    assert result["output"] == {"units": []}
    assert "PRIVATE" not in json.dumps(result)
    assert "SECRET" not in json.dumps(result)


def test_run_outputs_require_run_owner_and_include_feedback_diagnosis_calls() -> None:
    app = create_app(AgentSettings(environment="test", internal_token="test-token"))
    request = CreateRunRequest(
        run_type=RunType.IMPROVEMENT_CANDIDATE,
        project_id="project",
        source_document_id="pdf",
        requested_by="owner",
        feedback_id="feedback-a",
        scope=RunScope(type=ScopeType.PROFILE, id="zh"),
        options=RunOptions(correction_feedback_ids=["feedback-a", "feedback-b"]),
    )
    run = asyncio.run(app.state.run_control.create(request, "observe"))
    for key in ("feedback-a", "feedback-b"):
        asyncio.run(
            app.state.trace_store.append(
                f"improvement:{key}",
                {"agent": "improvement_diagnoser", "model": "fake", "response_content": '{"confidence":0.9}'},
            )
        )
    headers = {"Authorization": "Bearer test-token"}
    with TestClient(app) as client:
        path = f"/v1/runs/{run.agent_run_id}/model-outputs"
        assert client.get(path, params={"user_id": "other"}, headers=headers).status_code == 403
        response = client.get(path, params={"user_id": "owner"}, headers=headers)
        assert response.status_code == 200
        assert len(response.json()["items"]) == 2
        assert response.json()["reasoning_exposed"] is False


def test_supervisor_output_is_scoped_to_recorded_user_and_conversation() -> None:
    app = create_app(AgentSettings(environment="test", internal_token="test-token"))
    turn = str(uuid4())
    asyncio.run(
        app.state.trace_store.append(
            f"turn:{turn}",
            {
                "agent": "supervisor",
                "model": "fake",
                "response_content": '{"reason":"公开任务计划"}',
                "metadata": {"user_id": "owner", "conversation_id": "case"},
            },
        )
    )
    with TestClient(app) as client:
        path = f"/v1/supervisor/conversations/case/turns/{turn}/model-output"
        headers = {"Authorization": "Bearer test-token"}
        assert client.get(path, params={"user_id": "other"}, headers=headers).json()["items"] == []
        assert len(client.get(path, params={"user_id": "owner"}, headers=headers).json()["items"]) == 1
