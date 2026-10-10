from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_service.agents.supervisor import SupervisorAgent
from agent_service.application.profile_detection import create_profile_detection_runtime
from agent_service.application.supervisor_conversation import SupervisorConversationService
from agent_service.application.workflow_registry import WorkflowRegistry
from agent_service.config import AgentSettings
from agent_service.harness.model_gateway import FakeModelGateway
from agent_service.infrastructure.conversation_memory import ShortTermConversationStore
from agent_service.infrastructure.document.pdf_runtime import load_pdf_module
from agent_service.main import create_app
from agent_service.profiles import ProfileRegistry
from agent_service.tools.profile_detection import ProfileDetectionTool

ROOT = Path(__file__).resolve().parents[4]
HEADERS = {"Authorization": "Bearer acceptance-test"}


def intent(name: str, hints: dict[str, str] | None = None) -> str:
    return json.dumps(
        {
            "intent": name,
            "confidence": 0.99,
            "reason": "根据当前输入和会话上下文执行用户请求。",
            "requires_input": False,
            "question": None,
            "extracted_hints": hints or {},
        }
    )


def detection(*, recognized: bool = True) -> str:
    return json.dumps(
        {
            "recognized": recognized,
            "selected_profile_key": "zh" if recognized else None,
            "confidence": 0.99 if recognized else 0.2,
            "candidates": [],
            "observed_signals": ["ZPMC"] if recognized else [],
            "reason": "按首页可见标识识别。",
        }
    )


def setup_api(tmp_path: Path, responses: list[str]) -> tuple[TestClient, FakeModelGateway, bytes]:
    registry = ProfileRegistry(
        profile_root=ROOT / "services/agent/profiles",
        workspace_root=ROOT,
        allow_legacy_references=True,
    )
    registry.load_all()
    settings = AgentSettings(
        workspace_root=ROOT,
        profile_root=ROOT / "services/agent/profiles",
        environment="test",
        internal_token="acceptance-test",
    )
    app = create_app(settings=settings, profile_registry=registry)
    gateway = FakeModelGateway(responses)
    app.state.supervisor_conversations = SupervisorConversationService(
        agent=SupervisorAgent(gateway=gateway, prompt_path=ROOT / "services/agent/prompts/supervisor.md"),
        workflows=WorkflowRegistry(),
        profiles=registry,
        detection=ProfileDetectionTool(
            create_profile_detection_runtime(settings=settings, registry=registry, gateway=gateway)
        ),
        memory=ShortTermConversationStore(),
        attachment_root=tmp_path / "attachments",
    )
    document = load_pdf_module().open()
    for text in ("ZPMC first page", "ABB second page must not be used"):
        page = document.new_page()
        page.insert_text((72, 72), text)
    pdf = document.tobytes()
    document.close()
    return TestClient(app, headers=HEADERS), gateway, pdf


def upload(client: TestClient, pdf: bytes, conversation: str = "session-1") -> str:
    response = client.post(
        f"/v1/supervisor/conversations/{conversation}/attachments",
        params={"user_id": "user-1", "filename": "case.pdf"},
        content=pdf,
    )
    assert response.status_code == 200
    return str(response.json()["attachment_id"])


def test_detection_confirmation_memory_and_idempotency_through_http(tmp_path: Path) -> None:
    client, gateway, pdf = setup_api(
        tmp_path,
        [
            intent("DETECT_PROFILE"),
            detection(),
            intent("CONFIRM_INPUT"),
            intent("QUERY_CONTEXT"),
        ],
    )
    with client:
        attachment = upload(client, pdf)
        first = {
            "turn_id": "turn-1",
            "conversation_id": "session-1",
            "user_id": "user-1",
            "message": "只识别图纸类型",
            "attachment_ids": [attachment],
        }
        response = client.post("/v1/supervisor/turns/stream", json=first)
        assert response.status_code == 200
        messages = [json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")]
        assert [item["event_type"] for item in messages[:-1]] == ["SUPERVISOR_PLAN", "WORKFLOW_DISPATCHED"]
        result = messages[-1]
        assert result["decision"]["requires_input"] is True
        assert result["receipt"]["payload"]["profile_detection"]["needs_user_confirmation"] is True
        assert "zh" in result["user_event"]["user_message"]
        assert gateway.calls[1].metadata["pdf_page_number"] == 1
        assert gateway.calls[1].agent_name == "profile_router"
        retry = client.post("/v1/supervisor/turns", json=first)
        assert retry.status_code == 200
        assert len(gateway.calls) == 2
        confirmed = client.post(
            "/v1/supervisor/turns",
            json={
                "conversation_id": "session-1",
                "user_id": "user-1",
                "message": "确认",
            },
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["decision"]["status"] == "ANSWERED"
        assignment = confirmed.json()["receipt"]["payload"]["profile_assignment"]
        assert assignment["source"] == "user_confirmation"
        assert assignment["confirmed_by"] == "user-1"
        assert assignment["binding"]["profile"]["key"] == "zh"
        assert "只识别图纸类型" in gateway.calls[2].messages[1]["content"]["context_summary"]
        assert "pending_detection" in gateway.calls[2].messages[1]["content"]["context_summary"]
        recalled = client.post(
            "/v1/supervisor/turns",
            json={
                "conversation_id": "session-1",
                "user_id": "user-1",
                "message": "刚才确认的是什么类型？",
            },
        )
        assert recalled.status_code == 200
        assert "zh" in recalled.json()["user_event"]["user_message"]
        assert [call.agent_name for call in gateway.calls] == [
            "supervisor",
            "profile_router",
            "supervisor",
            "supervisor",
        ]
        snapshot = client.get("/v1/supervisor/conversations/session-1", params={"user_id": "user-1"}).json()
        assert snapshot["pending_detection"] is None
        assert snapshot["profile_assignment"]["binding"]["profile"]["key"] == "zh"
        assert snapshot["survives_restart"] is False


def test_unknown_profile_requires_explicit_selection_and_allows_override(tmp_path: Path) -> None:
    client, gateway, pdf = setup_api(
        tmp_path,
        [
            intent("DETECT_PROFILE"),
            detection(recognized=False),
            intent("CONFIRM_INPUT"),
            intent("CONFIRM_INPUT", {"profile_key": "abb"}),
        ],
    )
    with client:
        attachment = upload(client, pdf)
        first = client.post(
            "/v1/supervisor/turns",
            json={
                "conversation_id": "session-1",
                "user_id": "user-1",
                "message": "识别类型",
                "attachment_ids": [attachment],
            },
        )
        assert first.json()["decision"]["status"] == "WAITING_INPUT"
        ambiguous = client.post(
            "/v1/supervisor/turns",
            json={
                "conversation_id": "session-1",
                "user_id": "user-1",
                "message": "确认",
            },
        )
        assert ambiguous.json()["decision"]["status"] == "WAITING_INPUT"
        selected = client.post(
            "/v1/supervisor/turns",
            json={
                "conversation_id": "session-1",
                "user_id": "user-1",
                "message": "是 ABB 图纸",
            },
        )
        assert (
            selected.json()["receipt"]["payload"]["profile_assignment"]["binding"]["profile"]["key"] == "abb"
        )
        assert len(gateway.calls) == 4


def test_user_isolation_and_cross_conversation_attachment_rejection(tmp_path: Path) -> None:
    client, gateway, pdf = setup_api(tmp_path, [intent("DETECT_PROFILE")])
    with client:
        attachment = upload(client, pdf)
        forbidden = client.get("/v1/supervisor/conversations/session-1", params={"user_id": "other-user"})
        assert forbidden.status_code == 403
        crossed = client.post(
            "/v1/supervisor/turns",
            json={
                "conversation_id": "session-2",
                "user_id": "user-1",
                "message": "只识别类型",
                "attachment_ids": [attachment],
            },
        )
        assert crossed.status_code == 403
        assert len(gateway.calls) == 1  # Supervisor only; no PDF is disclosed to the detector.
        unauthorized = client.get(
            "/v1/supervisor/conversations/session-1",
            params={"user_id": "user-1"},
            headers={"Authorization": "Bearer wrong"},
        )
        assert unauthorized.status_code == 401


def test_stage_zero_attachments_cannot_start_extraction(tmp_path: Path) -> None:
    client, gateway, pdf = setup_api(tmp_path, [intent("PROCESS_DOCUMENT")])
    with client:
        attachment = upload(client, pdf)
        response = client.post(
            "/v1/supervisor/turns",
            json={
                "conversation_id": "session-1",
                "user_id": "user-1",
                "message": "提取线表",
                "attachment_ids": [attachment],
            },
        )
        assert response.json()["decision"]["status"] == "WAITING_INPUT"
        assert response.json()["receipt"]["agent_run_id"] is None
        assert len(gateway.calls) == 1


def test_short_memory_is_bounded_and_not_long_term() -> None:
    store = ShortTermConversationStore(max_conversations=2)
    store.get("one", "user")
    store.get("two", "user")
    store.get("three", "user")
    assert store.get("one", "user").history == []
    with pytest.raises(PermissionError):
        store.get("one", "different-user")


def test_acceptance_script_only_uses_http_and_terminal_inputs() -> None:
    script = ROOT / "services/agent/agent_test/0.detection_test/run_acceptance.py"
    allowed = {
        "__future__",
        "argparse",
        "json",
        "os",
        "sys",
        "time",
        "datetime",
        "pathlib",
        "typing",
        "uuid",
        "httpx",
    }
    for node in ast.walk(ast.parse(script.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] in allowed
        elif isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0] in allowed for alias in node.names)


def test_main_factory_wires_memory_service_when_model_is_configured() -> None:
    from unittest.mock import patch

    settings = AgentSettings(
        workspace_root=ROOT,
        profile_root=ROOT / "services/agent/profiles",
        environment="test",
        model_base_url="http://fake.model",
        default_model="fake-vlm",
    )
    with patch("agent_service.main.OpenAICompatibleModelGateway", return_value=FakeModelGateway([])):
        app = create_app(settings=settings)
    assert isinstance(app.state.supervisor_conversations, SupervisorConversationService)
    assert (
        app.state.supervisor_conversations.snapshot("new-session", "user-1")["memory_backend"]
        == "process_short_term"
    )
