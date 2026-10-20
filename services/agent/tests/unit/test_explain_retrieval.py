from __future__ import annotations

import asyncio
import json
from copy import deepcopy
from uuid import uuid4

import httpx
import pymupdf
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.agent.explain_agent import ConnectionQuery, ExplainActor, ExplainAgent, ExplainTurn
from src.agent.explain_agent.api import create_explain_router
from src.agent.explain_agent.models import ExplainError
from src.agent.explain_agent.repository import SupabaseExplanationRepository
from src.harness.model_gateway import FakeModelGateway, ModelResponse, ModelToolCall
from src.infrastructure.supabase_client import SupabaseClient

from .test_explain_agent import OTHER, OWNER, PROJECT, Backend


class SearchBackend(Backend):
    def __init__(self):
        super().__init__()
        self.project["drawing_index"]["active_batch_id"] = "batch-a"
        self.rows = []
        for index in range(3):
            row = deepcopy(self.row)
            row.update(
                id=str(uuid4()),
                row_order=index,
                principle_number=f"003C010{index + 1}",
                start_terminal=f"XA:{index + 8}",
                end_terminal=f"XD10:{index + 1}",
            )
            self.rows.append(row)
        self.bad_scope = False
        self.image_value = 255
        self.fail_download = False

    def request(self, request):
        if request.url.path.endswith("/extraction_connection_rows"):
            self.calls.append(request)
            assert request.method == "GET"
            assert request.url.params["project_id"] == f"eq.{PROJECT}"
            if self.bad_scope:
                return httpx.Response(200, json=[{**self.rows[0], "project_id": str(OTHER)}])
            rows = deepcopy(self.rows)
            for key, value in request.url.params.items():
                if value.startswith("eq."):
                    rows = [row for row in rows if str(row.get(key)) == value[3:]]
            start = int(request.url.params.get("offset", "0"))
            size = int(request.url.params.get("limit", "100"))
            return httpx.Response(200, json=rows[start : start + size])
        if "/storage/v1/object/project-assets/" in request.url.path:
            self.calls.append(request)
            assert request.method == "GET"
            if self.fail_download:
                return httpx.Response(404, json={"message": "missing"})
            pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 20))
            pixmap.clear_with(self.image_value)
            return httpx.Response(200, content=pixmap.tobytes("png"))
        return super().request(request)


def setup_search(responses=None):
    backend = SearchBackend()
    repo = SupabaseExplanationRepository(
        SupabaseClient(
            base_url="https://db.invalid",
            service_role_key="PRIVATE-KEY",
            transport=httpx.MockTransport(backend.request),
        )
    )
    gateway = FakeModelGateway(responses or ["根据数据库记录，这页有3条连接。"])
    return backend, repo, gateway, ExplainAgent(repo, gateway)


def page_turn(**filters):
    return ExplainTurn(
        project_id=PROJECT,
        query=ConnectionQuery(drawing_page="003C01", **filters),
        message="这一页的所有端子是怎么提取的？",
    )


def call(name, arguments):
    return ModelResponse(
        content="",
        parsed=None,
        model="fake",
        duration_seconds=0,
        attempts=1,
        tool_calls=(ModelToolCall(str(uuid4()), name, json.dumps(arguments)),),
    )


@pytest.mark.parametrize(
    "query",
    [
        {},
        {"limit": 0},
        {"drawing_page": ""},
        {"drawing_page": " "},
        {"drawing_page": "x", "offset": -1},
        {"drawing_page": "x", "project_id": str(OTHER)},
        {"sql": "SELECT * FROM x"},
    ],
)
def test_query_schema_rejects_unbounded_or_unsafe_inputs(query):
    with pytest.raises(ValidationError):
        ConnectionQuery.model_validate(query)


def test_request_accepts_page_only_but_cannot_confuse_row_and_query():
    assert page_turn().query.drawing_page == "003C01"
    for changes in (
        {},
        {"connection_id": uuid4(), "query": {"drawing_page": "x"}},
        {"query": {"drawing_page": "x"}, "record_version": 2},
    ):
        with pytest.raises(ValidationError):
            ExplainTurn(project_id=PROJECT, **changes)


def test_repository_combines_exact_filters_and_collects_all_related_images():
    async def run():
        backend, repo, _, _ = setup_search()
        actor = ExplainActor(user_id=OWNER)
        selected = page_turn()
        result = await repo.search(selected, actor, selected.query)
        assert len(result.rows) == 3 and not result.has_more
        assert [d.pdf_page_number for d in result.drawings] == [3, 10]
        assert len(result.drawings[0].connection_ids) == 3
        assert len([r for r in backend.calls if "/object/sign/" in r.url.path]) == 2
        params = next(
            r.url.params for r in backend.calls if r.url.path.endswith("/extraction_connection_rows")
        )
        assert params["batch_id"] == "eq.batch-a" and params["source_drawing_page"] == "eq.003C01"
        assert params["order"] == "source_pdf_page_number.asc,row_order.asc,id.asc"
        query = ConnectionQuery(
            drawing_page="003C01",
            principle_number="003C0102",
            start_terminal="XA:9",
            end_terminal="XD10:2",
            workspace_code="003.C",
        )
        result = await repo.search(selected, actor, query)
        assert len(result.rows) == 1
        assert str(result.rows[0].row.id) == backend.rows[1]["id"]
        target = await repo.search(selected, actor, ConnectionQuery(target_drawing_page="004C01"))
        assert len(target.rows) == 3
        empty = await repo.search(selected, actor, ConnectionQuery(start_terminal="xa:9"))
        assert not empty.rows and empty.gaps
        assert all(r.method == "GET" or "/object/sign/" in r.url.path for r in backend.calls)

    asyncio.run(run())


def test_zero_record_workspace_can_still_read_indexed_originals_without_edit_tools():
    async def run():
        backend, repo, gateway, agent = setup_search([
            call("view_drawings", {"pdf_page_numbers": [3]}),
            "此工作区没有已提取记录；已核对PDF物理页3，无法还原当时模型内部过程。",
        ])
        backend.rows = []
        selected = ExplainTurn(project_id=PROJECT, query=ConnectionQuery(workspace_code="003.C"),
            allow_rescan=False, allow_edits=False)
        result = await agent.ask(selected, ExplainActor(user_id=OWNER))
        assert result.visual_pages == [3]
        assert result.context.drawings[0].pdf_page_number == 3
        definitions = {tool["function"]["name"] for tool in gateway.calls[0].tools}
        assert "rescan_connections" not in definitions and "propose_connection_edit" not in definitions
        assert all(request.method == "GET" for request in backend.calls)
    asyncio.run(run())


def test_model_calls_native_search_tool_and_paginates_before_explaining_page():
    async def run():
        responses = [
            call("search_connections", {"drawing_page": "003C01", "offset": 1, "limit": 2}),
            "这页3条连接均已获取，原页与跨页信息已列出。",
        ]
        _, _, gateway, agent = setup_search(responses)
        events = []

        async def emit(event):
            events.append(event)

        result = await agent.ask(page_turn(limit=1), ExplainActor(user_id=OWNER), on_event=emit)
        assert result.context.has_more and len(result.retrievals[0].rows) == 2
        assert result.coverage[0].complete and result.coverage[0].returned_count == 3
        assert not result.gaps and [d.pdf_page_number for d in result.drawings] == [3, 10]
        assert [event.type for event in events[:3]] == ["tool_started", "tool_completed", "context"]
        assert any(event.type == "retrieval" for event in events)
        completed_tools = [event.tool for event in events if event.type == "tool_completed"]
        assert len(completed_tools) == 2 and len(completed_tools[-1].result["rows"]) == 2
        assert events[-1].type == "completed"
        assert "".join(event.delta or "" for event in events) == result.answer
        assert {t["function"]["name"] for t in gateway.calls[0].tools} == {
            "search_connections",
            "view_drawings",
            "propose_connection_edit",
            "rescan_connections",
        }
        tool_message = next(m for m in gateway.calls[1].messages if m["role"] == "tool")
        assert len(json.loads(tool_message["content"])["rows"]) == 2
        sent = json.dumps(gateway.calls[1].messages)
        assert "PRIVATE-KEY" not in sent and "PRIVATE-SIGNATURE" not in sent and "image_path" not in sent

    asyncio.run(run())


def test_deleted_rows_and_project_audit_are_not_reused_as_current_model_facts():
    async def run():
        backend, _, gateway, agent = setup_search(["已读取本页。", "现在只剩两条连接。"])
        selected = page_turn()
        actor = ExplainActor(user_id=OWNER)
        await agent.ask(selected, actor)
        removed = backend.rows.pop()
        backend.project["drawing_index"]["management"] = {
            "audit": [{"action": "remove", "before": {**removed, "end_terminal": "DELETED-SECRET"}}]
        }
        result = await agent.ask(
            selected.model_copy(update={"turn_id": uuid4(), "message": "再看一下当前页"}), actor
        )
        assert result.history_reset and len(result.context.rows) == 2
        messages = json.dumps(gateway.calls[-1].messages)
        assert removed["id"] not in messages and "DELETED-SECRET" not in messages
        assert all(str(row.row.id) != removed["id"] for row in result.context.rows)

    asyncio.run(run())


def test_endpoint_swap_coordinates_match_actual_pages_without_changing_origin():
    async def run():
        backend, repo, _, _ = setup_search()
        backend.rows[0].update(
            start_terminal_coordinates={"x": 0.4, "y": 0.5, "pdf_page_number": 10},
            end_terminal_coordinates={"x": 0.2, "y": 0.3, "pdf_page_number": 3},
        )
        result = await repo.search(
            page_turn(), ExplainActor(user_id=OWNER), ConnectionQuery(drawing_page="003C01")
        )
        context = result.rows[0]
        assert context.row.source_pdf_page_number == 3
        drawings = {drawing.pdf_page_number: drawing for drawing in context.drawings}
        assert drawings[3].terminal_coordinates == context.row.end_terminal_coordinates
        assert drawings[10].terminal_coordinates == context.row.start_terminal_coordinates
        assert not any("坐标所属页" in gap for gap in context.gaps)

    asyncio.run(run())


def test_incomplete_page_is_explicit_even_if_model_stops_early():
    async def run():
        _, _, _, agent = setup_search(["已读取这些记录。"])
        result = await agent.ask(page_turn(limit=1), ExplainActor(user_id=OWNER))
        assert not result.coverage[0].complete and "尚未完整覆盖" in result.answer
        assert result.context.next_offset == 1

    asyncio.run(run())


def test_tool_can_query_page_from_row_but_cannot_set_project_or_identity():
    async def run():
        backend, _, gateway, agent = setup_search(
            [
                call("search_connections", {"drawing_page": "003C01", "project_id": str(OTHER)}),
                call("search_connections", {"drawing_page": "003C01"}),
                "本页共3条。",
            ]
        )
        selected = ExplainTurn(project_id=PROJECT, connection_id=backend.rows[0]["id"])
        result = await agent.ask(selected, ExplainActor(user_id=OWNER))
        error = next(m for m in gateway.calls[1].messages if m["role"] == "tool")
        assert json.loads(error["content"])["error"] == "INVALID_QUERY"
        assert len(result.retrievals[0].rows) == 3
        assert len([r for r in backend.calls if r.url.path.endswith("/extraction_connection_rows")]) == 2

    asyncio.run(run())


def test_tools_recheck_permission_and_fail_closed_on_wrong_project_rows():
    async def run():
        backend, repo, gateway, agent = setup_search()
        actor = ExplainActor(user_id=OTHER)
        with pytest.raises(ExplainError, match="无权访问"):
            await agent.ask(page_turn(), actor)
        assert not gateway.calls
        backend.bad_scope = True
        with pytest.raises(ExplainError, match="不属于"):
            await repo.search(
                page_turn(), ExplainActor(user_id=OWNER), ConnectionQuery(drawing_page="003C01")
            )
        backend.bad_scope = False

        class RevokeGateway(FakeModelGateway):
            async def invoke(self, request):
                response = await super().invoke(request)
                backend.allowed = False
                return response

        agent.gateway = RevokeGateway([call("search_connections", {"drawing_page": "003C01"})])
        with pytest.raises(ExplainError, match="无权访问"):
            await agent.ask(page_turn(), ExplainActor(user_id=OWNER))

    asyncio.run(run())


def test_tool_results_are_refreshed_before_cache_replay_or_followup():
    async def run():
        backend, _, gateway, agent = setup_search(
            [
                call("search_connections", {"drawing_page": "003C01"}),
                "本页有3条。",
                "更新后本页有4条。",
            ]
        )
        selected = ExplainTurn(project_id=PROJECT, connection_id=backend.rows[0]["id"])
        actor = ExplainActor(user_id=OWNER)
        await agent.ask(selected, actor)
        cached = await agent.ask(selected, actor)
        assert cached.cached and len(gateway.calls) == 2
        backend.rows.append({**deepcopy(backend.rows[-1]), "id": str(uuid4()), "row_order": 4})
        updated = await agent.ask(selected, actor)
        assert not updated.cached and updated.history_reset and len(updated.retrievals[0].rows) == 4
        assert len(gateway.calls) == 3
        backend.allowed = False
        with pytest.raises(ExplainError):
            await agent.ask(selected, actor)

    asyncio.run(run())


def test_query_batch_changes_and_session_scope_changes_are_reported():
    async def run():
        backend, _, gateway, agent = setup_search()
        selected = page_turn()
        actor = ExplainActor(user_id=OWNER)
        await agent.ask(selected, actor)
        with pytest.raises(ExplainError, match="新的会话"):
            await agent.ask(
                selected.model_copy(update={"query": ConnectionQuery(drawing_page="004C01")}), actor
            )
        backend.project["drawing_index"]["active_batch_id"] = "batch-b"
        with pytest.raises(ExplainError, match="批次"):
            await agent.ask(selected.model_copy(update={"batch_id": "batch-a", "turn_id": uuid4()}), actor)
        assert len(gateway.calls) == 1

    asyncio.run(run())


def test_view_tool_supplies_real_image_inputs_and_revalidates_bytes_before_cache():
    async def run():
        backend, _, gateway, agent = setup_search(
            [
                call("view_drawings", {"pdf_page_numbers": [3, 10]}),
                "本轮已看到原页与目标页。",
                "图片更新后的解释。",
            ]
        )
        selected = page_turn()
        actor = ExplainActor(user_id=OWNER)
        result = await agent.ask(selected, actor)
        assert result.visual_pages == [3, 10]
        images = [
            part
            for message in gateway.calls[1].messages
            if isinstance(message["content"], list)
            for part in message["content"]
            if part["type"] == "image_url"
        ]
        assert len(images) == 2 and all(
            p["image_url"]["url"].startswith("data:image/png;base64,") for p in images
        )
        assert "data:image" not in result.model_dump_json()
        assert (await agent.ask(selected, actor)).cached
        backend.image_value = 0
        refreshed = await agent.ask(selected, actor)
        assert not refreshed.cached and refreshed.history_reset
        assert "PRIVATE-SIGNATURE" not in json.dumps(gateway.calls[1].messages)

    asyncio.run(run())


@pytest.mark.parametrize("page,fail", [(999, False), (3, True)])
def test_view_tool_handles_unknown_or_missing_image_without_claiming_visual_access(page, fail):
    async def run():
        backend, _, _, agent = setup_search(
            [
                call("view_drawings", {"pdf_page_numbers": [page]}),
                "只能根据记录解释。",
            ]
        )
        backend.fail_download = fail
        result = await agent.ask(page_turn(), ExplainActor(user_id=OWNER))
        assert not result.visual_pages and result.gaps
        if page == 999:
            assert not any("/object/project-assets/" in r.url.path for r in backend.calls)

    asyncio.run(run())


def test_bounded_tool_loop_ends_and_does_not_hang_page():
    async def run():
        _, _, gateway, agent = setup_search(
            [
                *[call("search_connections", {"drawing_page": "003C01"}) for _ in range(8)],
                "根据已获取的信息回答。",
            ]
        )
        selected = page_turn()
        result = await agent.ask(selected, ExplainActor(user_id=OWNER))
        assert result.retrieval_limited and "调用上限" in result.answer
        assert not gateway.calls[-1].tools and len(gateway.calls) == 9
        cached = await agent.ask(selected, ExplainActor(user_id=OWNER))
        assert cached.cached and cached.retrieval_limited

    asyncio.run(run())


@pytest.mark.parametrize(
    "path,bucket",
    [
        (f"projects/{OTHER}/private.png", "project-assets"),
        (f"projects/{PROJECT}/%2e%2e/private.png", "project-assets"),
        (f"projects/{PROJECT}/pages/3.png", "foreign-bucket"),
    ],
)
def test_visual_download_rejects_foreign_or_unsafe_storage(path, bucket):
    async def run():
        backend, repo, _, _ = setup_search()
        backend.project["drawing_index"]["pages"][0].update(image_path=path, image_bucket=bucket)
        result = await repo.read_drawings(page_turn(), ExplainActor(user_id=OWNER), [3])
        assert not result.images and result.gaps
        assert not any("/object/project-assets/" in r.url.path for r in backend.calls)

    asyncio.run(run())


def test_unresolved_cross_page_reference_is_displayed_as_candidate_without_inventing_endpoint():
    async def run():
        backend, _, _, agent = setup_search()
        backend.rows[0].update(target_pdf_page_number=None, end_terminal=None)
        result = await agent.ask(page_turn(), ExplainActor(user_id=OWNER))
        first = result.context.rows[0]
        assert first.row.end_terminal is None
        assert [(d.pdf_page_number, d.role) for d in first.drawings] == [(3, "source"), (10, "reference")]
        assert any("候选" in step.description for step in first.evidence_path)
        assert first.drawings[-1].terminal_coordinates is None

    asyncio.run(run())


def test_retrieval_sse_and_openapi_expose_data_and_images_without_private_state():
    _, _, _, agent = setup_search(
        [
            call("search_connections", {"drawing_page": "003C01"}),
            "本页解释。",
        ]
    )
    app = FastAPI()
    app.include_router(create_explain_router(agent, lambda: ExplainActor(user_id=OWNER)))
    with TestClient(app) as client:
        result = client.post("/v1/explain/turns/stream", json=page_turn().model_dump(mode="json"))
        assert "event: retrieval" in result.text and "event: completed" in result.text
        assert "image_url" in result.text and "PRIVATE-KEY" not in result.text
        assert '"messages"' not in result.text and '"actor"' not in result.text
        schemas = client.get("/openapi.json").json()["components"]["schemas"]
        assert "query" in schemas["ExplainTurn"]["properties"]
        assert "target_drawing_page" in schemas["ConnectionQuery"]["properties"]
        assert "retrievals" in schemas["ExplainResponse"]["properties"]
