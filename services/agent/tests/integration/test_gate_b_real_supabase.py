"""Explicit local Supabase + Fake model HTTP acceptance, never a paid VLM run."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from services.agent.tests.integration.test_detection_conversation_api import detection, intent
from services.agent.tests.integration.test_gate_a_real_supabase import FakeStages

from agent_service.config import AgentSettings
from agent_service.harness.model_gateway import FakeModelGateway
from agent_service.infrastructure.document.pdf_runtime import load_pdf_module
from agent_service.infrastructure.supabase_client import SupabaseClient
from agent_service.main import create_app

pytestmark = pytest.mark.skipif(os.getenv("AGENT_TEST_REAL_SUPABASE") != "true",
                                reason="explicit local Supabase flag required")


@pytest.mark.parametrize("unknown", [False, True])
def test_gate_b_http_upload_confirmation_persistence_and_restart(tmp_path: Path, unknown: bool) -> None:
    settings = replace(
        AgentSettings.from_env(), environment="test", internal_token="gate-b-isolated-test",
        persistence_backend="supabase", default_model="fake-gate-b", model_base_url="http://fake.test",
        inline_worker=False,
    )
    assert settings.supabase_url == "http://127.0.0.1:54321"
    db = SupabaseClient(base_url=settings.supabase_url,
                        service_role_key=settings.supabase_service_role_key or "")
    # Never let a Fake Worker consume unrelated business runs in the shared local stack.
    assert not asyncio.run(db.select("agent_run_queue")), "Stop: unrelated queued work; do not consume it."
    auth_headers = {"apikey": settings.supabase_service_role_key or "",
                    "Authorization": f"Bearer {settings.supabase_service_role_key}"}
    with httpx.Client(timeout=30) as auth:
        response = auth.post(f"{settings.supabase_url}/auth/v1/admin/users", headers=auth_headers, json={
            "email": f"gate-b-{uuid4().hex}@example.invalid", "password": f"GateB-{uuid4().hex}!",
            "email_confirm": True,
        })
        response.raise_for_status()
        user = response.json()["id"]
    project = None
    try:
        gateway = FakeModelGateway([
            intent("PROCESS_DOCUMENT"), detection(recognized=not unknown),
            *([intent("CONFIRM_INPUT")] if unknown else []),
            intent("CONFIRM_INPUT", {"profile_key": "zh"}), intent("CONFIRM_INPUT"),
        ])
        fake = FakeStages()
        with patch("agent_service.main.OpenAICompatibleModelGateway", return_value=gateway):
            app = create_app(settings=settings)
        with load_pdf_module().open() as document:
            for number in (1, 2):
                document.new_page().insert_text((72, 72), f"ZPMC Plant Function 002.C Page {number}")
            pdf = document.tobytes()
        headers = {"Authorization": "Bearer gate-b-isolated-test"}
        with TestClient(app, headers=headers) as http:
            params = {"conversation_id": "isolated-gate-b", "user_id": user,
                      "project_name": "Gate B isolated acceptance", "filename": "synthetic.pdf"}
            imported_response = http.post("/v1/imports", params=params, content=pdf,
                                          headers={"Idempotency-Key": "isolated-import"})
            assert imported_response.status_code == 201, imported_response.text
            imported = imported_response.json()
            project = imported["project_id"]
            assert http.post("/v1/imports", params=params, content=pdf,
                             headers={"Idempotency-Key": "isolated-import"}).json() == imported
            before = http.get(f"/v1/projects/{project}/tree", params={"user_id": user}).json()
            assert len(before["sources"]) == 1 and before["workspaces"] == []
            upload_conflict = http.post("/v1/imports", params=params, content=pdf + b"changed",
                                        headers={"Idempotency-Key": "isolated-import"})
            assert upload_conflict.status_code == 400

            def turn(message: str, turn_id: str | None = None) -> dict:
                response = http.post("/v1/supervisor/turns/stream", json={
                    "turn_id": turn_id or str(uuid4()), "conversation_id": "isolated-gate-b",
                    "user_id": user, "message": message,
                })
                messages = [json.loads(line[5:]) for line in response.text.splitlines()
                            if line.startswith("data:")]
                assert messages and "detail" not in messages[-1], messages
                return messages[-1]

            pending = turn("请识别并确认后完整提取")
            assert pending["receipt"]["status"] == "WAITING_INPUT"
            assert gateway.calls[1].metadata["pdf_page_number"] == 1
            assert http.portal.call(app.state.run_control.queue.size) == 0
            if unknown:
                assert turn("OK")["receipt"]["status"] == "WAITING_INPUT"
            confirm_id = str(uuid4())
            confirmed = turn("确认 ZH", confirm_id)
            run_id = confirmed["receipt"]["agent_run_id"]
            queued = http.get(f"/v1/runs/{run_id}").json()["run"]
            assert queued["protocol_version"] == 2
            assert queued["profile"]["key"] == "zh"
            assert queued["options"]["profile_confirmation"]["confirmed_by"] == user
            assert turn("确认 ZH", confirm_id)["receipt"]["agent_run_id"] == run_id
            assert http.portal.call(app.state.run_control.queue.size) == 1
            with patch("agent_service.application.three_stage_extraction.build_extraction_stage_dispatcher",
                       return_value=fake):
                assert http.portal.call(app.state.agent_worker.run_once)
            run = http.get(f"/v1/runs/{run_id}").json()["run"]
            assert run["status"] in {"SUCCEEDED", "NEEDS_REVIEW"}, run
            assert turn("OK")["receipt"]["agent_run_id"] == run_id
            assert http.portal.call(app.state.run_control.queue.size) == 0
            summary_response = http.get(f"/v1/runs/{run_id}/summary", params={"user_id": user})
            assert summary_response.status_code == 200, summary_response.text
            summary = summary_response.json()
            assert all(stage["committed"] for stage in summary["stages"])
            assert summary["final_receipt"]["finalized"]
            assert summary["model_name"] == "fake-gate-b"
            assert summary["cost"] is None
            tree_response = http.get(f"/v1/projects/{project}/tree", params={"user_id": user})
            assert tree_response.status_code == 200, tree_response.text
            tree = tree_response.json()
            assert tree["published_snapshot_id"] and len(tree["workspaces"]) == 1
            assert len(tree["workspaces"][0]["drawings"]) == 2
            version = summary["final_receipt"]["result_version_id"]
            rows_response = http.get(f"/v1/projects/{project}/results", params={
                "user_id": user, "result_version_id": version, "limit": 1})
            assert rows_response.status_code == 200, rows_response.text
            rows = rows_response.json()["items"]
            assert len(rows) == 1
            assert str(rows[0]["wire_number"]) == "1000"
            assert rows[0]["start_code"] == "-XD11" and rows[0]["end_code"] == "-M1"
            assert rows[0]["is_cross_page"] == "cross_page"
            stream = http.get(f"/v1/runs/{run_id}/events/stream", headers={"Last-Event-ID": "0"})
            assert "id: 0\n" not in stream.text and "RUN_COMPLETED" in stream.text
            assert http.get(f"/v1/projects/{project}/results",
                            params={"user_id": str(uuid4())}).status_code == 403
        # Fresh HTTP service has no conversation memory; persisted run/tree/result still work.
        replay_gateway = FakeModelGateway([intent("PROCESS_DOCUMENT"), detection(), intent("CONFIRM_INPUT")])
        with patch("agent_service.main.OpenAICompatibleModelGateway", return_value=replay_gateway):
            restarted = create_app(settings=settings)
        with TestClient(restarted, headers=headers) as http:
            assert http.get(f"/v1/runs/{run_id}/summary", params={"user_id": user}).json() == summary
            assert http.get(f"/v1/projects/{project}/tree", params={"user_id": user}).json() == tree
            assert http.post("/v1/imports", params=params, content=pdf,
                             headers={"Idempotency-Key": "isolated-import"}).json() == imported
            assert turn("提取")["receipt"]["status"] == "WAITING_INPUT"
            assert turn("OK")["receipt"]["agent_run_id"] == run_id
            replayed = http.get(f"/v1/runs/{run_id}").json()["run"]
            assert replayed["options"] == queued["options"]
            assert http.portal.call(restarted.state.run_control.queue.size) == 0
            assert len(fake.calls) == 5
    finally:
        async def clean() -> None:
            if project:
                existing = await db.select("projects", params={"id": f"eq.{project}", "limit": "1"})
                assert existing and existing[0]["name"] == "Gate B isolated acceptance"
                assert existing[0]["owner_id"] == user
                async with httpx.AsyncClient(timeout=30) as http:
                    async def paths(prefix: str) -> list[str]:
                        listing = await http.post(
                            f"{settings.supabase_url}/storage/v1/object/list/project-assets",
                            headers=auth_headers, json={"prefix": prefix, "limit": 1000})
                        listing.raise_for_status()
                        found = []
                        for item in listing.json():
                            path = f"{prefix}/{item['name']}"
                            if item.get("id"):
                                found.append(path)
                            else:
                                found.extend(await paths(path))
                        return found
                    objects = await paths(f"projects/{project}")
                assert all(path.startswith(f"projects/{project}/") for path in objects)
                await db.remove_objects(bucket="project-assets", object_paths=objects)
                await db.delete("projects", filters={"id": f"eq.{project}"})
            async with httpx.AsyncClient(timeout=30) as http:
                deleted = await http.delete(f"{settings.supabase_url}/auth/v1/admin/users/{user}",
                                            headers=auth_headers)
                deleted.raise_for_status()
        asyncio.run(clean())
