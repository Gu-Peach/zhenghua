"""Offline tests: only FakeModelGateway, MockTransport and in-process HTTP."""

from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient

from src.agent.explain_agent import ExplainActor, ExplainTurn, create_explain_agent
from src.agent.explain_agent.api import create_explain_router
from src.agent.explain_agent.graph import build_explain_graph
from src.agent.explain_agent.models import ExplainError
from src.agent.explain_agent.repository import SupabaseExplanationRepository
from src.config import AgentSettings
from src.harness.model_gateway import FakeModelGateway
from src.infrastructure.supabase_client import SupabaseClient

OWNER, OTHER, PROJECT, PROFILE, ROW = [uuid4() for _ in range(5)]


class Backend:
    def __init__(self) -> None:
        self.calls: list[httpx.Request] = []
        self.allowed = True
        self.fail_signing = False
        self.project = {
            "id": str(PROJECT),
            "owner_id": str(OWNER),
            "name": "验证项目",
            "profile_id": str(PROFILE),
            "status": "ready",
            "drawing_index": {
                "pages": [
                    {
                        "pdf_page_number": 3,
                        "drawing_page": "003C01",
                        "workspace_code": "003.C",
                        "image_path": f"projects/{PROJECT}/pages/3.png",
                    },
                    {
                        "pdf_page_number": 10,
                        "drawing_page": "004C01",
                        "workspace_code": "004.C",
                        "image_path": f"projects/{PROJECT}/pages/10.png",
                    },
                ]
            },
        }
        self.row = {
            "id": str(ROW),
            "project_id": str(PROJECT),
            "batch_id": "batch-a",
            "record_version": 1,
            "page_item_id": "scan-1",
            "workspace_code": "003.C",
            "source_pdf_page_number": 3,
            "source_drawing_page": "003C01",
            "target_pdf_page_number": 10,
            "target_drawing_page": "004C01",
            "principle_number": "003C0101",
            "start_code": "+01F10",
            "start_terminal": "XA:8",
            "end_terminal": "XD10:1",
            "is_cross_page": True,
            "needs_review": True,
            "start_terminal_coordinates": {"x": 0.2, "y": 0.3, "pdf_page_number": 3},
            "end_terminal_coordinates": {"x": 0.4, "y": 0.5, "pdf_page_number": 10},
            "evidence": {
                "profile": {"key": "zh", "version": "2.1.1", "checksum": "sha256:frozen"},
                "processing_status": "needs_review",
                "voltage_level": "400VAC",
                "record": {
                    "confidence": 0.91,
                    "source_note": "按原理号和页间引用匹配终点。",
                    "references": [{"raw": "=004.C/1.2", "target_pdf_page": 10}],
                    "authorization": "DO-NOT-PROMPT",
                },
                "review_reasons": [{"code": "LOW_CONFIDENCE", "field": "end_terminal", "message": "需核对"}],
            },
        }

    def request(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if request.url.path.startswith("/storage/v1/object/sign/"):
            if self.fail_signing:
                return httpx.Response(404, json={"message": "missing image"})
            return httpx.Response(200, json={"signedURL": "/object/sign/picture?token=PRIVATE-SIGNATURE"})
        assert request.method == "GET", "Explain must never mutate business tables"
        if request.url.path.endswith("/extraction_projects"):
            allowed = self.allowed and request.url.params.get("owner_id") == f"eq.{OWNER}"
            return httpx.Response(200, json=[deepcopy(self.project)] if allowed else [])
        if request.url.path.endswith("/extraction_connection_rows"):
            assert request.url.params["project_id"] == f"eq.{PROJECT}"
            return httpx.Response(200, json=[deepcopy(self.row)])
        if request.url.path.endswith("/extraction_profiles"):
            return httpx.Response(
                200,
                json=[
                    {
                        "id": str(PROFILE),
                        "profile_key": "zh",
                        "profile_version": "9.0.0",
                        "checksum": "latest",
                    }
                ],
            )
        raise AssertionError(f"Unexpected endpoint: {request.url.path}")


def setup(responses=None, **kwargs):
    backend = Backend()
    repository = SupabaseExplanationRepository(
        SupabaseClient(
            base_url="https://db.invalid",
            service_role_key="PRIVATE-KEY",
            transport=httpx.MockTransport(backend.request),
        )
    )
    gateway = FakeModelGateway(
        responses or ["这行由XA:8连接到XD10:1，来源为原页和跨页引用【row】【references】。"]
    )
    agent = create_explain_agent(AgentSettings(), repository=repository, gateway=gateway, **kwargs)
    return backend, repository, gateway, agent


def turn(**changes):
    return ExplainTurn(project_id=PROJECT, connection_id=ROW, **changes)


def test_langgraph_reads_row_sources_and_only_recorded_evidence() -> None:
    async def run():
        backend, repo, gateway, agent = setup()
        nodes = build_explain_graph(repo, gateway).get_graph().nodes
        assert {
            "load_authorized_context",
            "collect_evidence",
            "answer_question",
            "present_explanation",
        } <= nodes.keys()
        events = []

        async def emit(event):
            events.append(event)

        result = await agent.ask(turn(), ExplainActor(user_id=OWNER), on_event=emit)
        assert result.context.row.start_terminal == "XA:8"
        assert result.context.row.voltage_level == "400VAC"
        assert result.context.recorded["confidence"] == 0.91
        assert [d.pdf_page_number for d in result.context.drawings] == [3, 10]
        assert all(d.image_url for d in result.context.drawings)
        assert result.context.profile.version == "2.1.1"
        assert result.context.profile.source == "record_evidence"
        assert "references" in [step.id for step in result.context.evidence_path]
        assert any("内部思考" in gap for gap in result.context.gaps)
        assert [event.type for event in events[:3]] == ["tool_started", "tool_completed", "context"]
        assert events[-1].type == "completed"
        assert events[1].tool.result["row"]["start_terminal"] == "XA:8"
        assert "".join(e.delta or "" for e in events) == result.answer
        prompt = json.dumps(gateway.calls[0].messages, ensure_ascii=False)
        assert (
            "PRIVATE-SIGNATURE" not in prompt
            and "PRIVATE-KEY" not in prompt
            and "DO-NOT-PROMPT" not in prompt
        )
        assert "9.0.0" not in prompt
        assert not any(r.url.path.endswith("/extraction_profiles") for r in backend.calls)

    asyncio.run(run())


def test_unauthorized_or_cross_project_row_never_calls_model() -> None:
    async def run():
        backend, _, gateway, agent = setup()
        with pytest.raises(ExplainError, match="无权访问"):
            await agent.ask(turn(), ExplainActor(user_id=OTHER))
        assert len(backend.calls) == 1 and not gateway.calls
        backend.row["project_id"] = str(uuid4())
        with pytest.raises(ExplainError, match="不属于"):
            await agent.ask(turn(), ExplainActor(user_id=OWNER))
        assert not gateway.calls

    asyncio.run(run())


@pytest.mark.parametrize("changes", [{"batch_id": "wrong"}, {"record_version": 9}])
def test_expected_row_version_and_batch_are_checked_before_model(changes) -> None:
    async def run():
        _, _, gateway, agent = setup()
        with pytest.raises(ExplainError) as error:
            await agent.ask(turn(**changes), ExplainActor(user_id=OWNER))
        assert error.value.status == 409 and not gateway.calls

    asyncio.run(run())


def test_missing_target_and_notes_are_explicit_gaps() -> None:
    async def run():
        backend, _, _, agent = setup()
        backend.row.update(
            target_pdf_page_number=None, end_terminal=None, end_terminal_coordinates=None, evidence={}
        )
        backend.project["drawing_index"]["pages"] = []
        result = await agent.ask(turn(), ExplainActor(user_id=OWNER))
        assert result.context.profile.source == "project_reference"
        assert not result.context.drawings[0].image_url
        assert result.context.row.end_terminal is None
        gaps = " ".join(result.context.gaps)
        assert "跨页目标" in gaps and "未记录提取来源说明" in gaps and "不能证明" in gaps

    asyncio.run(run())


@pytest.mark.parametrize(
    "path,bucket",
    [
        (f"projects/{OTHER}/private.png", "project-assets"),
        (f"projects/{PROJECT}/../private.png", "project-assets"),
        (f"projects/{PROJECT}/%2e%2e/private.png", "project-assets"),
        (f"projects/{PROJECT}/3.png", "foreign-bucket"),
    ],
)
def test_unsafe_storage_paths_are_not_signed(path, bucket) -> None:
    async def run():
        backend, _, _, agent = setup()
        backend.project["drawing_index"]["pages"][0].update(image_path=path, image_bucket=bucket)
        backend.row["target_pdf_page_number"] = None
        result = await agent.ask(turn(), ExplainActor(user_id=OWNER))
        assert result.context.drawings[0].image_url is None
        signs = [r for r in backend.calls if "/object/sign/" in r.url.path]
        assert all("/pages/10.png" in r.url.path for r in signs)

    asyncio.run(run())


def test_signing_failure_keeps_row_but_invalid_coordinates_do_not_highlight() -> None:
    async def run():
        backend, _, _, agent = setup()
        backend.fail_signing = True
        backend.row["start_terminal_coordinates"]["pdf_page_number"] = 99
        result = await agent.ask(turn(), ExplainActor(user_id=OWNER))
        assert result.context.row.start_terminal == "XA:8"
        assert result.context.drawings[0].terminal_coordinates is None
        assert all(d.image_url is None for d in result.context.drawings)
        assert any("坐标所属页" in s for s in result.context.gaps)

    asyncio.run(run())


def test_conversation_refreshes_facts_and_idempotency_does_not_bypass_access() -> None:
    async def run():
        backend, _, gateway, agent = setup(["第一次回答。", "追问回答。", "数据更新后的回答。"])
        first = turn()
        actor = ExplainActor(user_id=OWNER)
        await agent.ask(first, actor)
        replay = await agent.ask(first, actor)
        assert replay.cached and len(gateway.calls) == 1
        follow = first.model_copy(update={"turn_id": uuid4(), "message": "跨页依据是什么？"})
        await agent.ask(follow, actor)
        assert any(m["content"] == "第一次回答。" for m in gateway.calls[1].messages)
        backend.row.update(record_version=2, end_terminal="XD10:2")
        next_turn = follow.model_copy(update={"turn_id": uuid4(), "message": "现在的终点呢？"})
        result = await agent.ask(next_turn, actor)
        assert result.history_reset and result.context.row.end_terminal == "XD10:2"
        assert not any(m["content"] == "第一次回答。" for m in gateway.calls[2].messages)
        backend.allowed = False
        with pytest.raises(ExplainError):
            await agent.ask(first, actor)
        assert len(gateway.calls) == 3

    asyncio.run(run())


def test_conversation_cannot_switch_target_and_turn_id_cannot_switch_message() -> None:
    async def run():
        _, _, _, agent = setup()
        first = turn()
        actor = ExplainActor(user_id=OWNER)
        await agent.ask(first, actor)
        with pytest.raises(ExplainError, match="新的会话"):
            await agent.ask(first.model_copy(update={"connection_id": uuid4()}), actor)
        with pytest.raises(ExplainError, match="turn_id"):
            await agent.ask(first.model_copy(update={"message": "另一个问题"}), actor)

    asyncio.run(run())


def test_router_requires_host_identity_and_exposes_only_public_events() -> None:
    _, _, _, agent = setup(["普通回答。", "流式回答。"])
    app = FastAPI()

    async def actor(authorization: str | None = Header(None)) -> ExplainActor:
        if authorization != "Bearer fixture-jwt":
            raise HTTPException(401, "Login required")
        return ExplainActor(user_id=OWNER)

    app.include_router(create_explain_router(agent, actor))
    with TestClient(app) as client:
        body = turn().model_dump(mode="json")
        assert client.post("/v1/explain/turns", json=body).status_code == 401
        headers = {"Authorization": "Bearer fixture-jwt"}
        assert (
            client.post(
                "/v1/explain/turns", json={**body, "user_id": str(OTHER)}, headers=headers
            ).status_code
            == 422
        )
        result = client.post("/v1/explain/turns", json=body, headers=headers)
        assert result.status_code == 200 and result.json()["answer"] == "普通回答。"
        body["turn_id"] = str(uuid4())
        stream = client.post("/v1/explain/turns/stream", json=body, headers=headers)
        assert stream.status_code == 200
        types = [
            line.removeprefix("event: ") for line in stream.text.splitlines() if line.startswith("event: ")
        ]
        assert types[:3] == ["tool_started", "tool_completed", "context"]
        assert types[-1] == "completed" and "answer_delta" in types
        assert "PRIVATE-KEY" not in stream.text and "owner_id" not in stream.text
        paths = client.get("/openapi.json").json()["paths"]
        assert set(paths) == {"/v1/explain/turns", "/v1/explain/turns/stream"}


def test_failed_model_answer_does_not_poison_followup_history() -> None:
    async def run():
        _, _, gateway, agent = setup([RuntimeError("provider failure"), "重试成功。"])
        first = turn()
        actor = ExplainActor(user_id=OWNER)
        with pytest.raises(RuntimeError):
            await agent.ask(first, actor)
        result = await agent.ask(first, actor)
        assert result.answer == "重试成功。"
        assert not any(m["role"] == "assistant" for m in gateway.calls[1].messages)

    asyncio.run(run())


def test_same_page_is_shown_once_and_changed_fields_are_not_claimed_as_original() -> None:
    async def run():
        backend, _, _, agent = setup()
        backend.row.update(is_cross_page=False, target_pdf_page_number=3)
        backend.row["evidence"]["record"]["end_terminal"] = "OLD:1"
        result = await agent.ask(turn(), ExplainActor(user_id=OWNER))
        assert [d.role for d in result.context.drawings] == ["source", "reference"]
        assert len([d for d in result.context.drawings if d.role == "source"]) == 1
        assert result.context.row.end_terminal == "XD10:1"
        difference = result.context.recorded["field_differences"][0]
        assert difference == {"field": "end_terminal", "recorded_value": "OLD:1", "current_value": "XD10:1"}
        assert any(step.id == "field_differences" for step in result.context.evidence_path)

    asyncio.run(run())


def test_busy_and_cancelled_conversation_releases_lock_without_storing_answer() -> None:
    async def run():
        _, _, _, agent = setup(max_sessions=1)
        started = asyncio.Event()
        cancelled = asyncio.Event()

        class SlowGateway:
            async def invoke(self, request):
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()

        agent.gateway = SlowGateway()
        first = turn()
        actor = ExplainActor(user_id=OWNER)
        task = asyncio.create_task(agent.ask(first, actor))
        await asyncio.wait_for(started.wait(), 3)
        with pytest.raises(ExplainError, match="仍在回复"):
            await agent.ask(first, actor)
        with pytest.raises(ExplainError) as capacity:
            await agent.ask(turn(), actor)
        assert capacity.value.status == 429
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert cancelled.is_set()
        gateway = FakeModelGateway(["取消后的新回答。"])
        agent.gateway = gateway
        result = await agent.ask(first, actor)
        assert result.answer == "取消后的新回答。" and not result.cached
        assert not any(m["role"] == "assistant" for m in gateway.calls[0].messages)

    asyncio.run(run())


def test_http_stream_masks_upstream_error_and_archived_project_is_not_read() -> None:
    backend, _, _, agent = setup([RuntimeError("SECRET-PROVIDER-DETAIL")])
    app = FastAPI()

    async def actor():
        return ExplainActor(user_id=OWNER)

    app.include_router(create_explain_router(agent, actor))
    with TestClient(app) as client:
        stream = client.post("/v1/explain/turns/stream", json=turn().model_dump(mode="json"))
        assert "event: context" in stream.text and "event: error" in stream.text
        assert "SECRET-PROVIDER-DETAIL" not in stream.text
        assert "event: completed" not in stream.text
        backend.project["status"] = "archived"
        response = client.post("/v1/explain/turns", json=turn().model_dump(mode="json"))
        assert response.status_code == 409
        assert response.json()["detail"]["code"] == "PROJECT_ARCHIVED"


def test_cli_requires_explicit_real_model_flag(monkeypatch) -> None:
    import src.agent.explain_agent.__main__ as cli

    def forbidden():
        pytest.fail("CLI must stop before loading model/database configuration")

    monkeypatch.setattr(cli.AgentSettings, "from_env", forbidden)
    monkeypatch.setattr(
        "sys.argv",
        ["explain", "--project-id", str(PROJECT), "--connection-id", str(ROW), "--actor-id", str(OWNER)],
    )
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2


def test_factory_requires_explicit_dependencies_or_configuration() -> None:
    _, repository, gateway, _ = setup()
    with pytest.raises(ValueError, match="Supabase"):
        create_explain_agent(AgentSettings(), gateway=gateway)
    with pytest.raises(ValueError, match="model configuration"):
        create_explain_agent(AgentSettings(), repository=repository)


def test_truncated_answer_is_not_cached_as_a_complete_explanation() -> None:
    from dataclasses import replace

    class TruncatedGateway(FakeModelGateway):
        async def invoke(self, request):
            return replace(await super().invoke(request), finish_reason="length")

    async def run():
        _, _, _, agent = setup()
        agent.gateway = TruncatedGateway(["未完整结束的回答"])
        first = turn()
        actor = ExplainActor(user_id=OWNER)
        with pytest.raises(ExplainError, match="截断"):
            await agent.ask(first, actor)
        agent.gateway = FakeModelGateway(["完整回答。"])
        result = await agent.ask(first, actor)
        assert not result.cached and result.answer == "完整回答。"

    asyncio.run(run())
