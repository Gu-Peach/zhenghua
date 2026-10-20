from __future__ import annotations

import base64
import json
from uuid import uuid4

import httpx
import pymupdf
import pytest
from fastapi.testclient import TestClient
from test_simple_management_api import OTHER, OWNER, PROJECT, ROW, STAMP, Backend, api
from wiring_server.assistant_store import token_hash


class AssistantBackend(Backend):
    def __init__(self):
        super().__init__()
        self.tables.update(
            {
                table: []
                for table in (
                    "assistant_conversations",
                    "assistant_turns",
                    "assistant_actions",
                    "assistant_attachments",
                    "assistant_asset_gc",
                    "agent_artifacts",
                )
            }
        )
        self.agent_calls = 0
        self.rescans = 0
        self.events = None

    def respond(self, request):
        path = request.url.path
        if path.endswith("/rpc/assistant_begin_turn"):
            value = json.loads(request.content)
            rows = self.tables["assistant_turns"]
            prior = next((r for r in rows if r["id"] == value["turn"]), None)
            if prior and prior["request_hash"] != value["body_hash"]:
                return httpx.Response(409, json={"code": "PT409"})
            if prior and prior["status"] == "completed":
                return httpx.Response(200, json=prior)
            row = {
                "id": value["turn"],
                "owner_id": value["actor"],
                "conversation_id": value["conversation"],
                "request": value["body"],
                "request_hash": value["body_hash"],
                "tool_token_hash": value["token_hash"],
                "status": "running",
                "events": [],
                "answer": "",
                "created_at": STAMP,
            }
            rows.append(row)
            return httpx.Response(200, json=row)
        if path.endswith("/rpc/assistant_finish_turn"):
            value = json.loads(request.content)
            row = next(
                r for r in self.tables["assistant_turns"] if r["id"] == value["turn"]
            )
            assert row["tool_token_hash"] == value["token_hash"]
            row.update(
                status=value["outcome"],
                events=value["event_list"],
                answer=value["public_answer"],
                error=value["failure"],
            )
            return httpx.Response(200, json=row)
        if path == "/v1/assistant/turns/stream":
            self.agent_calls += 1
            value = json.loads(request.content)
            self.last_internal = (request, value)
            events = self.events or [
                {"type": "answer_delta", "message": "已读取当前工作区"},
                {
                    "type": "completed",
                    "data": {
                        "completion_verified": True,
                        "verification_version": 1,
                        "required_tool": None,
                        "disposition": "answered",
                    },
                },
            ]
            content = "".join(
                "data: "
                + json.dumps({"id": str(uuid4()), "turn_id": value["turn_id"], **e})
                + "\n\n"
                for e in events
            )
            return httpx.Response(
                200, content=content, headers={"content-type": "text/event-stream"}
            )
        if path.endswith("/rpc/enqueue_connection_rescan"):
            self.rescans += 1
            self.last_rescan = json.loads(request.content)["value"]
            return httpx.Response(
                200, json={"id": self.last_rescan["id"], "status": "queued"}
            )
        return super().respond(request)


def client_for(backend):
    return TestClient(
        api.create_app(
            api.Settings("http://database", "fake-key", agent_url="http://agent"),
            httpx.MockTransport(backend.respond),
        ),
        headers={"Authorization": "Bearer owner"},
    )


def seed_turn(backend, scope=None):
    conversation, turn = str(uuid4()), str(uuid4())
    backend.tables["assistant_conversations"].append(
        {
            "id": conversation,
            "owner_id": OWNER,
            "title": "对话",
            "context": scope or {},
            "created_at": STAMP,
            "updated_at": STAMP,
        }
    )
    backend.tables["assistant_turns"].append(
        {
            "id": turn,
            "owner_id": OWNER,
            "conversation_id": conversation,
            "request": {
                "message": "重扫",
                "turn_id": turn,
                "scope": scope or {},
                "attachment_ids": [],
            },
            "request_hash": "",
            "tool_token_hash": token_hash("x" * 48),
            "status": "running",
            "events": [],
            "created_at": STAMP,
        }
    )
    return conversation, turn, {"X-Assistant-Turn-Token": "x" * 48}


def test_main_rescan_passes_exact_target_binding_to_enqueue():
    backend = AssistantBackend()
    _, turn, headers = seed_turn(backend, {"project_id": PROJECT, "pdf_page_number": 1})
    binding = {"connection_ids": [ROW], "drawing_page": "004C01", "pdf_page_number": 2}
    with client_for(backend) as client:
        response = client.post(
            f"/api/internal/assistant/turns/{turn}/tools", headers=headers,
            json={"name": "start_rescan", "arguments": {
                "fields": "end", "target_bindings": [binding],
                "scope": {"project_id": PROJECT, "pdf_page_number": 1, "connection_ids": [ROW]},
            }},
        )
    assert response.status_code == 200, response.text
    assert backend.last_rescan["request"]["target_bindings"] == [binding]
    assert backend.last_rescan["request"]["fields"] == "end"


@pytest.mark.parametrize("same_project", [False, True])
def test_model_history_has_current_action_status_and_explicit_project_boundaries(
    same_project,
):
    backend = AssistantBackend()
    previous_project = PROJECT if same_project else str(uuid4())
    conversation, previous, _ = seed_turn(backend, {"project_id": previous_project})
    previous_turn = backend.tables["assistant_turns"][0]
    previous_turn.update(
        status="failed",
        error="无关的线表工具缺少范围",
        answer="",
        request={**previous_turn["request"], "message": "修改规则"},
    )
    action = str(uuid4())
    backend.tables["assistant_actions"].append(
        {
            "id": action,
            "turn_id": previous,
            "conversation_id": conversation,
            "owner_id": OWNER,
            "tool_name": "diagnose_profile",
            "status": "applied",
            "result": {
                "kind": "profile",
                "scope": {"project_id": previous_project},
                "receipt": {
                    "profile_version": "1.0.1",
                    "profile_key": "custom_test",
                    "resource_ref": "private-storage-path",
                },
            },
        }
    )
    backend.tables["assistant_actions"].append(
        {
            "id": str(uuid4()),
            "turn_id": previous,
            "conversation_id": conversation,
            "owner_id": OTHER,
            "tool_name": "diagnose_profile",
            "status": "applied",
            "result": {"receipt": {"profile_version": "private-other-owner"}},
        }
    )
    with client_for(backend) as client:
        result = client.post(
            f"/api/v1/assistant/conversations/{conversation}/turns/stream",
            json={"message": "这个规则改好了吗", "scope": {"project_id": PROJECT}},
        )
    assert result.status_code == 200
    history = backend.last_internal[1]["history"]
    text = "\n".join(item["content"] for item in history)
    assert '"status": "applied"' in text
    assert '"profile_version": "1.0.1"' in text
    assert "无关的线表工具缺少范围" in text
    assert "private-storage-path" not in text
    assert "private-other-owner" not in text
    assert f'"same_project": {str(same_project).lower()}' in text


def test_public_history_sse_replay_hash_and_owner_are_bound():
    backend = AssistantBackend()
    with client_for(backend) as client:
        conversation = client.post(
            "/api/v1/assistant/conversations", json={"title": "测试"}
        ).json()
        identifier = conversation["id"]
        assert "owner_id" not in conversation
        turn = {
            "turn_id": str(uuid4()),
            "message": "解释工作区",
            "scope": {"project_id": PROJECT, "workspace_code": "003.C"},
        }
        path = f"/api/v1/assistant/conversations/{identifier}/turns/stream"
        response = client.post(path, json=turn)
        assert response.status_code == 200, response.text
        assert "answer_delta" in response.text
        assert backend.agent_calls == 1
        assert (
            client.post(path, json=turn).status_code == 200 and backend.agent_calls == 1
        )
        assert (
            client.post(path, json={**turn, "message": "different"}).status_code == 409
        )
        saved = client.get(f"/api/v1/assistant/conversations/{identifier}").json()
        assert saved["turns"][0]["answer"] == "已读取当前工作区"
        assert "tool_token_hash" not in json.dumps(saved)
        assert (
            client.get(
                f"/api/v1/assistant/conversations/{identifier}",
                headers={"Authorization": "Bearer other"},
            ).status_code
            == 404
        )
        internal_request, _ = backend.last_internal
        stale = client.post(
            f"/api/internal/assistant/turns/{turn['turn_id']}/tools",
            headers={
                "X-Assistant-Turn-Token": internal_request.headers[
                    "X-Assistant-Turn-Token"
                ]
            },
            json={"name": "find_targets"},
        )
        assert stale.status_code == 403


def test_tools_include_zero_rows_and_idempotent_rescan_with_bound_user():
    backend = AssistantBackend()
    _, turn, headers = seed_turn(
        backend, {"project_id": PROJECT, "workspace_code": "003.C"}
    )
    path = f"/api/internal/assistant/turns/{turn}/tools"
    with client_for(backend) as client:

        def tool(name, arguments):
            return client.post(
                path, headers=headers, json={"name": name, "arguments": arguments}
            )

        found = tool("find_targets", {"workspace_code": "004.C"}).json()
        assert found["targets"][0]["scope"]["workspace_code"] == "004.C"
        assert (
            tool("navigate_to", {"scope": found["targets"][0]["scope"]}).status_code
            == 200
        )
        # Empty scope follows the explicitly navigated target, not the old GUI snapshot.
        request = {"scope": {}, "fields": "all"}
        first = tool("start_rescan", request)
        assert first.status_code == 200, first.text
        assert tool("start_rescan", request).json()["run_id"] == first.json()["run_id"]
        assert backend.rescans == 1
        assert backend.last_rescan["actor"] == OWNER
        assert backend.last_rescan["request"]["scope"]["workspace_code"] == "004.C"
        assert backend.last_rescan["request"]["result_mode"] == "replace_scope"
        assert tool("start_rescan", {"scope": {}, "owner_id": OTHER}).status_code == 422
        assert tool("publish_profile", {}).status_code == 422
        foreign = tool("read_scope", {"scope": {"project_id": str(uuid4())}})
        assert foreign.status_code in {403, 404}
        # Task reference survives an SSE interruption before its task_started frame arrived.
        saved = client.get(
            f"/api/v1/assistant/conversations/{backend.tables['assistant_conversations'][0]['id']}"
        ).json()
        assert any(e["type"] == "task_started" for e in saved["turns"][0]["events"])


def test_private_attachment_is_only_readable_inside_its_conversation():
    backend = AssistantBackend()
    conversation, _, _ = seed_turn(backend)
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 30))
    pix.clear_with(255)
    value = {
        "id": str(uuid4()),
        "filename": "参考.png",
        "content_base64": base64.b64encode(pix.tobytes("png")).decode(),
    }
    with client_for(backend) as client:
        path = f"/api/v1/assistant/conversations/{conversation}/attachments"
        response = client.post(path, json=value)
        assert response.status_code == 200, response.text
        assert "storage_path" not in response.json()
        assert client.post(path, json=value).json()["id"] == value["id"]
        assert len(backend.uploads) == 1
        assert (
            client.post(
                path, json=value, headers={"Authorization": "Bearer other"}
            ).status_code
            == 404
        )
        invalid = client.post(
            path, json={**value, "id": str(uuid4()), "content_base64": "eA=="}
        )
        assert invalid.status_code == 422


def test_reference_image_binding_does_not_narrow_workspace_rescan():
    backend = AssistantBackend()
    conversation, turn, headers = seed_turn(
        backend, {"project_id": PROJECT, "workspace_code": "003.C"}
    )
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 30))
    pix.clear_with(255)
    value = {
        "id": str(uuid4()),
        "filename": "局部图.png",
        "role": "target",
        "content_base64": base64.b64encode(pix.tobytes("png")).decode(),
    }
    with client_for(backend) as client:
        uploaded = client.post(
            f"/api/v1/assistant/conversations/{conversation}/attachments", json=value
        )
        assert uploaded.status_code == 200
        backend.tables["assistant_turns"][0]["request"]["attachment_ids"] = [
            value["id"]
        ]
        path = f"/api/internal/assistant/turns/{turn}/tools"
        # A reference for a multi-page scope needs an explicit physical-page binding.
        args = {"scope": {}, "fields": "all"}
        assert (
            client.post(
                path, headers=headers, json={"name": "start_rescan", "arguments": args}
            ).status_code
            == 422
        )
        response = client.post(
            path,
            headers=headers,
            json={
                "name": "start_rescan",
                "arguments": {
                    **args,
                    "bindings": [
                        {
                            "attachment_id": value["id"],
                            "pdf_page_number": 2,
                            "role": "target",
                        }
                    ],
                },
            },
        )
        assert response.status_code == 200, response.text
        assert backend.last_rescan["request"]["scope"]["workspace_code"] == "003.C"
        assert backend.last_rescan["request"]["scope"]["pdf_page_numbers"] == []
        assert len(backend.last_rescan["attachment_ids"]) == 1
        assert backend.tables["connection_rescan_assets"][0]["pdf_page_number"] == 2


def test_project_delete_cleans_bound_assistant_storage_before_cascading_metadata():
    backend = AssistantBackend()
    conversation, _, _ = seed_turn(backend)
    identifier = str(uuid4())
    path = f"assistant/{OWNER}/{conversation}/{identifier}/hash"
    backend.tables["assistant_attachments"].append(
        {
            "id": identifier,
            "owner_id": OWNER,
            "conversation_id": conversation,
            "project_id": PROJECT,
            "storage_path": path,
        }
    )
    with client_for(backend) as client:
        response = client.delete(
            f"/api/v1/projects/{PROJECT}",
            params={"confirmed": "true", "expected_updated_at": STAMP},
        )
        assert response.status_code == 204, response.text
        deleted = [
            json.loads(request.content)["prefixes"]
            for request in backend.calls
            if request.method == "DELETE"
            and request.url.path == "/storage/v1/object/project-assets"
        ]
        assert any(path in batch for batch in deleted)


def test_empty_project_keeps_indexed_active_batch_for_explanation():
    import asyncio

    from wiring_server.assistant_contract import AssistantScope
    from wiring_server.assistant_evidence import AssistantEvidence

    backend = AssistantBackend()
    active = str(uuid4())
    backend.tables["extraction_projects"][0]["drawing_index"]["active_batch_id"] = (
        active
    )
    backend.tables["extraction_connection_rows"] = []
    with client_for(backend) as client:
        scope, _ = asyncio.run(
            AssistantEvidence(client.app.state.db).resolve(
                AssistantScope(
                    project_id=PROJECT, workspace_code="004.C", batch_id=active
                ),
                OWNER,
            )
        )
        assert scope.batch_id == active and scope.workspace_id


def test_server_withholds_unverified_answer_and_does_not_save_fake_success():
    backend = AssistantBackend()
    backend.events = [
        {
            "type": "answer_delta",
            "message": "任务ID：02262025-000001，已创建重扫，queued",
        },
        {"type": "completed"},
    ]
    with client_for(backend) as client:
        conversation = client.post(
            "/api/v1/assistant/conversations", json={"title": "测试"}
        ).json()["id"]
        response = client.post(
            f"/api/v1/assistant/conversations/{conversation}/turns/stream",
            json={"message": "重新扫描GCR102"},
        )
        assert response.status_code == 200 and "error" in response.text
        assert "02262025-000001" not in response.text
        row = backend.tables["assistant_turns"][0]
        assert row["status"] == "failed" and row["answer"] == ""
        assert not any(event["type"] == "answer_delta" for event in row["events"])


def test_completion_metadata_without_business_action_is_rejected():
    backend = AssistantBackend()
    backend.events = [
        {"type": "answer_delta", "message": "伪造成功"},
        {
            "type": "completed",
            "data": {
                "completion_verified": True,
                "verification_version": 1,
                "required_tool": "start_rescan",
                "disposition": "executed",
                "action_id": str(uuid4()),
                "run_id": str(uuid4()),
            },
        },
    ]
    with client_for(backend) as client:
        conversation = client.post(
            "/api/v1/assistant/conversations", json={"title": "测试"}
        ).json()["id"]
        response = client.post(
            f"/api/v1/assistant/conversations/{conversation}/turns/stream",
            json={"message": "重扫"},
        )
        assert "伪造成功" not in response.text and "error" in response.text
        assert backend.tables["assistant_turns"][0]["status"] == "failed"


def test_old_completed_reply_without_verification_is_not_replayed_as_success():
    backend = AssistantBackend()
    with client_for(backend) as client:
        conversation = client.post(
            "/api/v1/assistant/conversations", json={"title": "测试"}
        ).json()["id"]
        path = f"/api/v1/assistant/conversations/{conversation}/turns/stream"
        body = {"turn_id": str(uuid4()), "message": "重扫"}
        assert client.post(path, json=body).status_code == 200
        row = backend.tables["assistant_turns"][0]
        row["events"] = [
            {
                "id": str(uuid4()),
                "turn_id": body["turn_id"],
                "type": "answer_delta",
                "message": "旧的虚假任务号",
            },
            {
                "id": str(uuid4()),
                "turn_id": body["turn_id"],
                "type": "completed",
                "data": {},
            },
        ]
        response = client.post(path, json=body)
        assert (
            "旧的虚假任务号" not in response.text
            and "历史回复没有执行核验" in response.text
        )
        assert backend.agent_calls == 1


@pytest.mark.parametrize("mismatch", [None, "owner", "conversation", "turn", "run_id"])
def test_task_ack_is_built_from_verified_database_receipt(mismatch):
    backend = AssistantBackend()
    action_id, run_id = str(uuid4()), str(uuid4())

    def respond(request):
        if request.url.path == "/v1/assistant/turns/stream":
            value = json.loads(request.content)
            result = {
                "event": "task_started",
                "kind": "rescan",
                "action_id": action_id,
                "run_id": run_id,
                "status": "queued",
                "scope": {"project_id": PROJECT},
            }
            backend.tables["assistant_actions"].append(
                {
                    "id": action_id,
                    "turn_id": str(uuid4()) if mismatch == "turn" else value["turn_id"],
                    "owner_id": OWNER,
                    "conversation_id": value["conversation_id"],
                    "tool_name": "start_rescan",
                    "status": "completed",
                    "result": result,
                }
            )
            backend.tables["connection_rescan_runs"].append(
                {
                    "id": run_id,
                    "project_id": PROJECT,
                    "created_by": OTHER if mismatch == "owner" else OWNER,
                    "conversation_id": str(uuid4())
                    if mismatch == "conversation"
                    else value["conversation_id"],
                    "status": "queued",
                }
            )
            sent = {
                **result,
                "run_id": str(uuid4()) if mismatch == "run_id" else run_id,
            }
            backend.events = [
                {"type": "task_started", "data": sent},
                {
                    "type": "answer_delta",
                    "message": "伪造的模型任务ID：02262025-000001，running",
                },
                {
                    "type": "completed",
                    "data": {
                        "completion_verified": True,
                        "verification_version": 1,
                        "required_tool": "start_rescan",
                        "disposition": "executed",
                        "action_id": action_id,
                        "run_id": sent["run_id"],
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
            "/api/v1/assistant/conversations", json={"title": "测试"}
        ).json()["id"]
        response = client.post(
            f"/api/v1/assistant/conversations/{conversation}/turns/stream",
            json={"message": "重扫当前页"},
        )
        assert "02262025-000001" not in response.text
        row = backend.tables["assistant_turns"][0]
        if mismatch:
            assert row["status"] == "failed" and row["answer"] == ""
        else:
            assert (
                row["status"] == "completed"
                and run_id in row["answer"]
                and "排队中" in row["answer"]
            )
