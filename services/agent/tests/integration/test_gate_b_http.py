"""Offline HTTP boundary tests; production database execution is separately opt-in."""

from __future__ import annotations

import ast
import asyncio
import importlib.util
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import httpx
import pytest
from agent_service.agents.supervisor import SupervisorAgent
from agent_service.application.extraction_run_executor import FullExtractionRunExecutor
from agent_service.application.profile_detection import create_profile_detection_runtime
from agent_service.application.supervisor_conversation import SupervisorConversationService
from agent_service.application.workflow_registry import WorkflowRegistry
from agent_service.config import AgentSettings
from agent_service.domain.enums import EventType, RunStatus, RunType
from agent_service.domain.models.runs import AgentEvent
from agent_service.harness.model_gateway import FakeModelGateway
from agent_service.infrastructure.business_imports import SupabaseBusinessImports
from agent_service.infrastructure.conversation_memory import ShortTermConversationStore
from agent_service.infrastructure.document.pdf_runtime import load_pdf_module
from agent_service.infrastructure.project_assets import SupabaseSourceDocumentProvider
from agent_service.infrastructure.supabase_client import SupabaseClient
from agent_service.main import create_app
from agent_service.profiles import ProfileRegistry
from agent_service.tools.profile_detection import ProfileDetectionTool
from fastapi.testclient import TestClient

from services.agent.tests.integration.test_detection_conversation_api import detection, intent
from services.agent.tests.integration.test_gate_a_real_supabase import FakeStages

ROOT = Path(__file__).resolve().parents[4]


class FakeRest:
    def __init__(self) -> None:
        self.rows: dict[str, list[dict]] = {}
        self.objects: dict[str, bytes] = {}
        self.fail_upload = False

    def request(self, request: httpx.Request) -> httpx.Response:
        if "/storage/v1/object/" in request.url.path:
            key = request.url.path
            if request.method == "POST":
                if self.fail_upload:
                    return httpx.Response(503, json={"message": "injected storage failure"})
                if key in self.objects:
                    return httpx.Response(409, json={"message": "already exists"})
                self.objects[key] = request.content
                return httpx.Response(200, json={})
            return (
                httpx.Response(200, content=self.objects[key])
                if key in self.objects
                else (httpx.Response(404, json={}))
            )
        table = request.url.path.rsplit("/", 1)[-1]
        rows = self.rows.setdefault(table, [])
        if request.method == "POST":
            item = json.loads(request.content)
            if any(row["id"] == item["id"] for row in rows):
                return httpx.Response(409, json={})
            rows.append(item)
            return httpx.Response(201, json=[item])
        selected = rows
        for field, value in request.url.params.items():
            if value.startswith("eq."):
                selected = [row for row in selected if str(row.get(field)) == value[3:]]
        offset = int(request.url.params.get("offset", 0))
        limit = int(request.url.params.get("limit", 1000))
        return httpx.Response(200, json=selected[offset : offset + limit])


def setup(tmp_path: Path, responses: list[str]):
    rest = FakeRest()
    db = SupabaseClient(
        base_url="http://fake.test", service_role_key="fake", transport=httpx.MockTransport(rest.request)
    )
    backend = SupabaseBusinessImports(db)
    documents = SupabaseSourceDocumentProvider(db, cache_root=tmp_path / "sources")
    profiles = ProfileRegistry(
        profile_root=ROOT / "services/agent/profiles", workspace_root=ROOT, allow_legacy_references=True
    )
    profiles.load_all()
    settings = AgentSettings(environment="test", internal_token="gate-b-test", workspace_root=ROOT)
    app = create_app(settings=settings, profile_registry=profiles)
    gateway = FakeModelGateway(responses)
    app.state.business_imports = backend
    app.state.supervisor_conversations = SupervisorConversationService(
        agent=SupervisorAgent(gateway=gateway, prompt_path=ROOT / "services/agent/prompts/supervisor.md"),
        workflows=WorkflowRegistry(),
        profiles=profiles,
        detection=ProfileDetectionTool(
            create_profile_detection_runtime(settings=settings, registry=profiles, gateway=gateway)
        ),
        memory=ShortTermConversationStore(),
        attachment_root=tmp_path / "attachments",
        business_imports=backend,
        documents=documents,
        run_control=app.state.run_control,
    )
    executor = FullExtractionRunExecutor(
        settings=settings,
        profiles=profiles,
        documents=documents,
        artifacts=app.state.run_control.artifacts,
        publisher=app.state.run_control.publisher,
        runtime_root=tmp_path / "runtime",
    )
    # Replace only the fixture's full executor; the real AgentWorker and Graph still execute.
    app.state.agent_worker._executors[RunType.FULL_EXTRACTION] = executor
    with load_pdf_module().open() as document:
        for number in (1, 2):
            document.new_page().insert_text((72, 72), f"ZPMC page {number}")
        pdf = document.tobytes()
    return app, TestClient(app, headers={"Authorization": "Bearer gate-b-test"}), rest, gateway, pdf


def upload(client, pdf, user, **overrides):
    params = {
        "user_id": user,
        "conversation_id": "gate-b",
        "project_name": "Test import",
        "filename": "x.pdf",
    }
    params.update(overrides)
    return client.post("/v1/imports", params=params, content=pdf, headers={"Idempotency-Key": "import-1"})


def turn(client, user, message, turn_id=None):
    return client.post(
        "/v1/supervisor/turns",
        json={
            "user_id": user,
            "conversation_id": "gate-b",
            "message": message,
            "turn_id": turn_id or str(uuid4()),
        },
    )


def test_http_import_confirm_real_worker_and_duplicate_confirmation(tmp_path: Path) -> None:
    app, client, rest, gateway, pdf = setup(
        tmp_path,
        [
            intent("PROCESS_DOCUMENT"),
            detection(),
            intent("CONFIRM_INPUT"),
            intent("CONFIRM_INPUT"),
            intent("CONFIRM_INPUT"),
        ],
    )
    user = str(uuid4())
    with client:
        imported = upload(client, pdf, user).json()
        assert imported["page_count"] == 2
        assert upload(client, pdf, user).json() == imported
        assert len(rest.rows["projects"]) == len(rest.rows["document_files"]) == 1
        assert len(rest.objects) == 1
        first = turn(client, user, "请确认后提取")
        assert first.json()["receipt"]["status"] == "WAITING_INPUT"
        assert client.portal.call(app.state.run_control.queue.size) == 0
        assert gateway.calls[1].metadata["pdf_page_number"] == 1
        confirm_id = str(uuid4())
        confirmed = turn(client, user, "OK", confirm_id).json()
        run_id = confirmed["receipt"]["agent_run_id"]
        repeated = turn(client, user, "OK", confirm_id).json()
        assert repeated["receipt"]["agent_run_id"] == run_id
        late = turn(client, user, "OK")
        assert late.status_code == 200, (late.text, [call.agent_name for call in gateway.calls])
        assert late.json()["receipt"]["agent_run_id"] == run_id
        assert client.portal.call(app.state.run_control.queue.size) == 1
        queued = client.get(f"/v1/runs/{run_id}").json()["run"]
        assert queued["expected_result_version"] == 0
        assignment = confirmed["receipt"]["payload"]["profile_assignment"]
        assert queued["profile"]["version"] == assignment["binding"]["profile"]["version"]
        assert queued["options"]["profile_confirmation"]["source_checksum"] == imported["checksum"]
        fake = FakeStages()
        with patch(
            "agent_service.application.page_workflow_extraction.build_extraction_stage_dispatcher",
            return_value=fake,
        ):
            assert client.portal.call(app.state.agent_worker.run_once)
        assert [stage for stage, _ in fake.calls] == ["classify", "classify", "scan", "scan", "cross"]
        assert client.get(f"/v1/runs/{run_id}").json()["run"]["status"] in {"SUCCEEDED", "NEEDS_REVIEW"}
        completed_reply = turn(client, user, "OK")
        assert completed_reply.status_code == 200, (
            completed_reply.text,
            [call.agent_name for call in gateway.calls],
        )
        assert completed_reply.json()["receipt"]["agent_run_id"] == run_id
        assert client.portal.call(app.state.run_control.queue.size) == 0
        stream = client.get(f"/v1/runs/{run_id}/events/stream", headers={"Last-Event-ID": "0"})
        assert "id: 0\n" not in stream.text
        assert "PROPOSAL_CREATED" in stream.text
        assert client.get(f"/v1/runs/{run_id}/summary", params={"user_id": str(uuid4())}).status_code == 403
        assert (
            client.get(
                f"/v1/projects/{imported['project_id']}/tree", params={"user_id": str(uuid4())}
            ).status_code
            == 403
        )


def test_import_conflicts_invalid_pdf_auth_and_storage_retry(tmp_path: Path) -> None:
    _, client, rest, _, pdf = setup(tmp_path, [])
    user = str(uuid4())
    with client:
        assert upload(client, b"%PDF-invalid", user).status_code == 400
        assert not rest.rows
        rest.fail_upload = True
        assert upload(client, pdf, user).status_code == 409
        rest.fail_upload = False
        assert upload(client, pdf, user).status_code == 201
        assert upload(client, pdf, user, project_name="changed").status_code == 400
        assert upload(client, pdf + b"\nchanged", user).status_code == 400
        assert len(rest.objects) == 1
        denied = client.post(
            "/v1/imports",
            params={"user_id": user, "conversation_id": "x", "project_name": "x", "filename": "x.pdf"},
            content=pdf,
            headers={"Authorization": "Bearer wrong", "Idempotency-Key": "x"},
        )
        assert denied.status_code == 401


def test_unknown_requires_confirmation_then_ready_abb_enqueues(tmp_path: Path) -> None:
    app, client, _, _, pdf = setup(
        tmp_path,
        [
            intent("PROCESS_DOCUMENT"),
            detection(recognized=False),
            intent("CONFIRM_INPUT"),
            intent("CONFIRM_INPUT", {"profile_key": "abb"}),
        ],
    )
    user = str(uuid4())
    with client:
        upload(client, pdf, user)
        assert turn(client, user, "提取").json()["receipt"]["status"] == "WAITING_INPUT"
        assert turn(client, user, "OK").json()["receipt"]["status"] == "WAITING_INPUT"
        selected = turn(client, user, "是 ABB")
        assert selected.status_code == 200
        assert selected.json()["receipt"]["status"] == "QUEUED"
        assert client.portal.call(app.state.run_control.queue.size) == 1


def test_business_upload_does_not_inherit_temporary_pdf_confirmation(tmp_path: Path) -> None:
    app, client, _, gateway, pdf = setup(
        tmp_path,
        [
            intent("DETECT_PROFILE"),
            detection(),
            intent("CONFIRM_INPUT"),
            intent("PROCESS_DOCUMENT"),
            detection(),
        ],
    )
    user = str(uuid4())
    with client:
        temporary = client.post(
            "/v1/supervisor/conversations/gate-b/attachments",
            params={"user_id": user, "filename": "temporary.pdf"},
            content=pdf,
        ).json()
        first = client.post(
            "/v1/supervisor/turns",
            json={
                "conversation_id": "gate-b",
                "user_id": user,
                "message": "只检测",
                "attachment_ids": [temporary["attachment_id"]],
            },
        )
        assert first.json()["receipt"]["status"] == "WAITING_INPUT"
        assert turn(client, user, "OK").json()["receipt"]["payload"]["detection_only"] is True
        assert upload(client, pdf, user).status_code == 201
        assert turn(client, user, "完整提取").json()["receipt"]["status"] == "WAITING_INPUT"
        assert [call.agent_name for call in gateway.calls].count("profile_router") == 2
        assert client.portal.call(app.state.run_control.queue.size) == 0


def test_published_tree_and_result_pagination(tmp_path: Path) -> None:
    async def check() -> None:
        rest = FakeRest()
        backend = SupabaseBusinessImports(
            SupabaseClient(
                base_url="http://fake.test",
                service_role_key="fake",
                transport=httpx.MockTransport(rest.request),
            )
        )
        project, owner, version = str(uuid4()), str(uuid4()), str(uuid4())
        rest.rows["projects"] = [{"id": project, "owner_id": owner, "name": "x"}]
        rest.rows["workspaces"] = [
            {"id": "old", "project_id": project, "classification_snapshot_id": "unpublished"}
        ]
        assert (await backend.tree(project, owner)).workspaces == []
        rest.rows["projects"][0]["published_classification_snapshot_id"] = "published"
        rest.rows["workspaces"].append(
            {"id": "new", "project_id": project, "classification_snapshot_id": "published"}
        )
        rest.rows["drawings"] = [
            {
                "id": "page",
                "workspace_id": "new",
                "project_id": project,
                "classification_snapshot_id": "published",
                "pdf_page_number": 1,
            }
        ]
        assert (await backend.tree(project, owner)).workspaces[0]["drawings"][0]["id"] == "page"
        rest.rows["result_versions"] = [{"id": version, "project_id": project, "version": 1}]
        rest.rows["wiring_connection_rows"] = [
            {"project_id": project, "result_version_id": version, "wire_number": n}
            for n in (1000, 1001, 1002)
        ]
        page = await backend.results(project, owner, version=version, offset=0, limit=2)
        assert page.has_more and len(page.items) == 2
        with pytest.raises(ValueError):
            await backend.results(project, owner, version=str(uuid4()), offset=0, limit=2)

    asyncio.run(check())


def test_acceptance_client_has_no_agent_tools_and_openapi_contract(tmp_path: Path) -> None:
    tree = ast.parse((ROOT / "services/agent/agent_test/1.3stage/run_acceptance.py").read_text("utf-8"))
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
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(alias.name.split(".")[0] in allowed for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            assert node.module.split(".")[0] in allowed
    app, _, _, _, _ = setup(tmp_path, [])
    schema = app.openapi()
    assert "/v1/imports" in schema["paths"]
    assert "/v1/runs/{agent_run_id}/summary" in schema["paths"]
    assert "ProfileConfirmation" in schema["components"]["schemas"]


def test_terminal_script_http_only_upload_and_confirmation(tmp_path: Path) -> None:
    app, client, _, _, pdf = setup(
        tmp_path,
        [
            intent("PROCESS_DOCUMENT"),
            detection(),
            intent("CONFIRM_INPUT"),
        ],
    )
    script = ROOT / "services/agent/agent_test/1.3stage/run_acceptance.py"
    spec = importlib.util.spec_from_file_location("gate_b_acceptance_fixture", script)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    case = tmp_path / "source.pdf"
    case.write_bytes(pdf)
    output = tmp_path / "report"
    original_stream = client.stream
    fake = FakeStages()

    def server_worker(method, url, **kwargs):
        # Harness runs the server Worker; the unmodified client never selects a stage/tool.
        if method == "GET" and url.endswith("/events/stream"):
            with patch(
                "agent_service.application.page_workflow_extraction.build_extraction_stage_dispatcher",
                return_value=fake,
            ):
                client.portal.call(app.state.agent_worker.run_once)
        return original_stream(method, url, **kwargs)

    with (
        patch.object(module.httpx, "Client", return_value=client),
        patch.object(client, "stream", side_effect=server_worker),
        patch("builtins.input", return_value="OK"),
        patch("sys.argv", [str(script), str(case), "--user-id", str(uuid4()), "--output-dir", str(output)]),
        patch.dict("os.environ", {"AGENT_ACCEPTANCE_ALLOW_REAL_MODEL": "true"}),
    ):
        assert module.main() == 0
    report = json.loads((output / "summary.json").read_text("utf-8"))
    assert report["run"]["status"] in {"SUCCEEDED", "NEEDS_REVIEW"}
    assert report["acceptance"] == "manual_review_required" and report["cost"] is None
    assert report["import"]["page_count"] == 2
    assert len(fake.calls) == 5
    assert module.field_diff([{"start_code": "X"}], [{"start_code": "Y"}])[0]["field"] == "start_code"


def test_sse_drains_event_committed_after_first_fetch(tmp_path: Path) -> None:
    app, client, _, _, _ = setup(tmp_path, [])
    with client:
        created = client.post(
            "/v1/runs",
            headers={"Idempotency-Key": "race"},
            json={
                "run_type": "FULL_EXTRACTION",
                "project_id": "p",
                "source_document_id": "d",
                "requested_by": "u",
                "scope": {"type": "PROJECT", "id": "p"},
            },
        ).json()["run"]
        run_id = created["agent_run_id"]

        async def terminate():
            run = await app.state.run_control.get_required(run_id)
            run.status = RunStatus.SUCCEEDED
            await app.state.run_control.runs.save(run)

        client.portal.call(terminate)
        event = AgentEvent(agent_run_id=run_id, seq=1, event_type=EventType.RUN_COMPLETED)
        with patch.object(
            app.state.run_control.events, "list_after", new=AsyncMock(side_effect=[[], [event], [], []])
        ):
            response = client.get(f"/v1/runs/{run_id}/events/stream", headers={"Last-Event-ID": "0"})
        assert "RUN_COMPLETED" in response.text
