"""Offline Fake VLM tests for unchanged Stage2 with candidate-only persistence."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
from pathlib import Path
from uuid import uuid4

import httpx
import pymupdf
import pytest

from src.agent.explain_agent import ExplainActor, ExplainTurn
from src.agent.explain_agent.rescan_candidates import build_candidate
from src.agent.explain_agent.rescan_execution import CandidateSession, execute_rescan, frozen_binding
from src.config import AgentSettings
from src.harness.model_gateway import FakeModelGateway
from src.profiles import ProfileRegistry
from src.profiles.package import checksum

from .test_explain_agent import OWNER, PROJECT, ROW
from .test_explain_attachments import AttachmentBackend
from .test_explain_edits import agent, tool

ROOT = Path(__file__).resolve().parents[4]


@pytest.mark.parametrize("reply", ["已提交重扫任务，正式线表未改动。", "已生成修改预览，请直接确认。"])
def test_rescan_tool_binds_attachment_ids_and_only_enqueues(reply):
    class Backend(AttachmentBackend):
        def request(self, request):
            if request.url.path.endswith("/rpc/enqueue_connection_rescan"):
                value = json.loads(request.content)["value"]
                self.received = value
                return httpx.Response(
                    200,
                    json={
                        "id": value["id"],
                        "project_id": str(PROJECT),
                        "conversation_id": value["conversation_id"],
                        "batch_id": "batch-a",
                        "request": value["request"],
                        "status": "queued",
                        "stage": "queued",
                        "profile": {"key": "zh", "version": "1.0.0"},
                        "created_at": "now",
                        "updated_at": "now",
                    },
                )
            if request.url.path.endswith("/connection_rescan_runs"):
                return httpx.Response(200, json=[])
            return super().request(request)

    async def run():
        backend = Backend()
        assistant, gateway = agent(
            backend,
            [
                tool(
                    "rescan_connections",
                    {"scope": {"connection_ids": [str(ROW)]}, "fields": "end", "instructions": "核对细节"},
                ),
                reply,
            ],
        )
        attachment = uuid4()
        events = []

        async def emit(value):
            events.append(value)

        result = await assistant.ask(
            ExplainTurn(
                project_id=PROJECT, connection_id=ROW, message="重扫这个终点", attachment_ids=[attachment]
            ),
            ExplainActor(user_id=OWNER),
            on_event=emit,
        )
        assert result.rescans[0].status == "queued"
        assert backend.received["attachment_ids"] == [str(attachment)] and backend.received["actor"] == str(
            OWNER
        )
        assert any(event.type == "rescan_started" for event in events)
        assert not backend.preparations and len(gateway.calls) == 2
        assert "已生成修改预览" not in result.answer

    asyncio.run(run())


def test_wrong_target_workspace_is_corrected_in_same_turn_before_enqueue():
    class Backend(AttachmentBackend):
        def __init__(self):
            super().__init__()
            self.project["drawing_index"] = {
                "pages": [
                    {"drawing_page": "002M03", "workspace_code": "002.M", "pdf_page_number": 56},
                ]
            }
            self.enqueued = []

        def request(self, request):
            if request.url.path.endswith("/rpc/enqueue_connection_rescan"):
                value = json.loads(request.content)["value"]
                self.enqueued.append(value)
                return httpx.Response(
                    200,
                    json={
                        "id": value["id"],
                        "project_id": str(PROJECT),
                        "conversation_id": value["conversation_id"],
                        "batch_id": "batch-a",
                        "request": value["request"],
                        "status": "queued",
                        "stage": "queued",
                        "profile": {"key": "zh", "version": "1.0.0"},
                        "created_at": "now",
                        "updated_at": "now",
                    },
                )
            if request.url.path.endswith("/connection_rescan_runs"):
                return httpx.Response(200, json=[])
            return super().request(request)

    async def run():
        backend = Backend()
        bad = {
            "scope": {"connection_ids": [str(ROW)]},
            "fields": "end",
            "instructions": "只补终点",
            "target_bindings": [
                {"connection_ids": [str(ROW)], "drawing_page": "002M03", "workspace_code": "002.C"}
            ],
        }
        corrected = copy.deepcopy(bad)
        corrected["target_bindings"][0].update(workspace_code="002.M", pdf_page_number=56)
        assistant, gateway = agent(
            backend,
            [tool("rescan_connections", bad), tool("rescan_connections", corrected), "已创建重扫任务。"],
        )
        events = []

        async def emit(event):
            events.append(event)

        result = await assistant.ask(
            ExplainTurn(project_id=PROJECT, connection_id=ROW, message="起点正确，终点在002M03，重新提取"),
            ExplainActor(user_id=OWNER),
            on_event=emit,
        )
        assert len(backend.enqueued) == 1 and len(result.rescans) == 1
        assert backend.enqueued[0]["request"]["target_bindings"] == corrected["target_bindings"]
        failed = [event for event in events if event.type == "tool_failed"]
        assert len(failed) == 1 and "002.M / PDF 56" in str(failed[0])
        assert len(gateway.calls) == 3 and not backend.preparations

    asyncio.run(run())


class MemoryRescan:
    def __init__(self, image, detail):
        self.image, self.detail = image, detail
        self.events = []

    async def artifact(self, run, key):
        number = int(key.rsplit(":", 1)[-1])
        return {"snapshot": {"plant_function": "002.C", "drawing_page_number": number}}

    async def get(self, bucket, path):
        return self.detail if "/assets/" in path else self.image

    async def request(self, method, path, **kwargs):
        assert method == "GET"
        if path == "/rest/v1/agent_artifacts":
            return httpx.Response(
                200,
                json=[
                    {
                        "page": {
                            "page_number": number,
                            "function": "002.C",
                            "internal_page": number,
                            "object_loc": "+01F11.3",
                        }
                    }
                    for number in (1, 2)
                ],
            )
        return httpx.Response(200, json=[self.asset])

    async def rpc(self, name, parameters):
        assert name == "advance_connection_rescan", "candidate adapter must never call business publication"
        self.events.append(copy.deepcopy(parameters["value"]))
        return {}


@pytest.mark.parametrize("profile_key", ["zh", "abb"])
@pytest.mark.parametrize("mode", ["all", "end", "end_same", "end_missing", "replace"])
def test_real_page_graph_scans_completes_and_only_saves_candidates(tmp_path, profile_key, mode):
    async def run():
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 200, 150))
        pix.clear_with(255)
        image = pix.tobytes("png")
        pix.clear_with(220)
        detail = pix.tobytes("png")
        repo = MemoryRescan(image, detail)
        convo = str(uuid4())
        aid = str(uuid4())
        project = str(PROJECT)
        repo.asset = {
            "id": aid,
            "pdf_page_number": 2,
            "role": "target",
            "storage_path": f"projects/{project}/explain/{convo}/assets/{aid}.png",
            "checksum": checksum(detail),
        }
        settings = AgentSettings(default_model="fake")
        registry = ProfileRegistry(
            profile_root=settings.profile_root,
            workspace_root=ROOT,
            allow_legacy_references=True,
        )
        registry.load_all()
        binding = registry.bind(profile_key, allow_experimental=True)
        old = {
            "id": str(ROW),
            "source_pdf_page_number": 1,
            "source_drawing_page": "002C01",
            "workspace_code": "002.C",
            "record_version": 1,
            "principle_number": "002C0101",
            "start_terminal": "X3:1",
            "start_terminal_coordinates": {"x": 0.2, "y": 0.3, "pdf_page_number": 1},
            "end_terminal": "OLD",
            "target_pdf_page_number": 2,
            "is_cross_page": True,
        }
        job = {
            "id": str(uuid4()),
            "project_id": project,
            "created_by": str(OWNER),
            "conversation_id": convo,
            "batch_id": "batch-a",
            "lease_token": str(uuid4()),
            "attachment_ids": [aid],
            "profile": binding.profile.model_dump(mode="json"),
            "baseline": [old],
            "request": {
                "scope": {"drawing_page": "002C01"} if mode == "replace" else {"connection_ids": [str(ROW)]},
                "fields": "all" if mode in {"all", "replace"} else "end",
                "result_mode": "replace_scope" if mode == "replace" else "patch",
                "instructions": "核对上传细节",
            },
            "project_snapshot": {
                "pages": [
                    {
                        "pdf_page_number": n,
                        "workspace_code": "002.C",
                        "drawing_page": f"002C0{n}",
                        "image_path": f"projects/{project}/pages/{n}.png",
                    }
                    for n in (1, 2)
                ],
                "scan_pages": [{"pdf_page_number": 1}],
            },
        }
        scan = {
            "units": [
                {
                    "unit_id": "u",
                    "connections": [
                        {
                            "connection_id": "c",
                            "endpoint_role": "source",
                            "direction_basis": "visible outgoing wire",
                            "line_number": "002C0101",
                            "start": {
                                "terminal": "X3:1",
                                "terminal_coordinates": {"x": 0.2, "y": 0.3, "pdf_page_number": 1},
                            },
                            "is_cross_page": "cross_page",
                            "references": [{"target_function": "002.C", "target_drawing_page": 2}],
                        }
                    ],
                }
            ]
        }
        if "scan_evidence_rules" in binding.resolved_resources:
            scan["units"][0]["connections"][0].update(start_marker_number="1", end_marker_number="2")
        end = {
            "end": {"terminal": "XD21:7", "terminal_coordinates": {"x": 0.6, "y": 0.5, "pdf_page_number": 2}},
            "source_note": "匹配原页引用并沿导线到实际端子",
        }
        if mode == "end_same":
            old["is_cross_page"] = False
            old["target_pdf_page_number"] = None
            end["end"]["terminal_coordinates"]["pdf_page_number"] = 1
            scan["units"][0]["connections"][0].update(
                is_cross_page="same_page",
                references=[],
                end={
                    "terminal": "XD21:7",
                    "terminal_coordinates": {"x": 0.6, "y": 0.5, "pdf_page_number": 1},
                },
            )
        if mode == "end_missing":
            old["target_pdf_page_number"] = None
            repo.asset["role"] = "source"
        gateway = FakeModelGateway(
            [json.dumps(scan), json.dumps(end)]
            if mode in {"all", "replace"}
            else [json.dumps(scan)]
            if mode == "end_same"
            else []
            if mode == "end_missing"
            else [json.dumps(end)]
        )
        session = CandidateSession(repo, job)
        await execute_rescan(session, settings, gateway=gateway, binding=binding)
        completed = next(event["candidate"] for event in repo.events if "candidate" in event)
        if mode == "end_missing":
            assert not completed["changes"] and not gateway.calls
            assert completed["unmatched_ids"] == [str(ROW)] and completed["warnings"]
            return
        assert len(completed["changes"]) == 1
        if mode == "replace":
            assert completed["changes"][0]["action"] == "insert"
            assert completed["replacement"]["removed"][0]["connection_id"] == str(ROW)
        else:
            assert completed["changes"][0]["connection_id"] == str(ROW)
        assert completed["changes"][0]["after"]["end_terminal"] == "XD21:7"
        assert old["end_terminal"] == "OLD" and len(gateway.calls) == (2 if mode in {"all", "replace"} else 1)
        if mode not in {"all", "replace"}:
            assert "start_terminal" not in completed["changes"][0]["after"]
            assert (gateway.calls[0].metadata["rescan_task"] is None) == (mode == "end_same")
        text = json.dumps(gateway.calls[-1].messages, ensure_ascii=False)
        assert (
            "原始完整图，PDF物理页1" in text
            and ("原始完整图，PDF物理页2" in text) == (mode != "end_same")
            and "用户target细节" in text
        )
        assert gateway.calls[-1].metadata["rescan"] is True

    asyncio.run(run())


def test_ambiguous_identity_is_reviewed_without_picking_or_deleting():
    original = {
        "id": str(ROW),
        "record_version": 1,
        "source_pdf_page_number": 1,
        "principle_number": "SAME",
        "start_terminal": "X1:1",
    }
    job = {
        "id": str(uuid4()),
        "baseline": [original],
        "request": {"scope": {"connection_ids": [str(ROW)]}, "fields": "all"},
    }
    result = build_candidate(job, [{**original, "end_terminal": "A"}, {**original, "end_terminal": "B"}], [])
    assert not result.changes and str(result.unmatched_ids[0]) == str(ROW)
    assert result.warnings


def test_end_mask_never_rewrites_start_or_origin():
    original = {
        "id": str(ROW),
        "record_version": 4,
        "source_pdf_page_number": 1,
        "source_drawing_page": "001A",
        "workspace_code": "A",
        "principle_number": "P1",
        "start_terminal": "KEEP",
        "end_terminal": "OLD",
    }
    job = {
        "id": str(uuid4()),
        "baseline": [original],
        "request": {"scope": {"connection_ids": [str(ROW)]}, "fields": "end"},
    }
    result = build_candidate(job, [{**original, "start_code": "BAD", "end_terminal": "NEW"}], [])
    assert "start_terminal" not in result.changes[0].after.model_fields_set
    assert "start_code" not in result.changes[0].after.model_fields_set
    assert result.changes[0].source_drawing_page == "001A" and result.changes[0].record_version == 4


def test_local_historical_profile_can_be_packaged_and_rebound_without_latest_fallback(tmp_path):
    async def run():
        settings = AgentSettings(default_model="fake")
        registry = ProfileRegistry(
            profile_root=settings.profile_root,
            workspace_root=ROOT,
            allow_legacy_references=True,
        )
        registry.load_all()
        binding = registry.bind("zh", allow_experimental=True)

        class Repo:
            async def artifact(self, *args):
                return None

        job = {
            "id": str(uuid4()),
            "batch_id": "old-batch",
            "profile": binding.profile.model_dump(mode="json"),
            "project_snapshot": {"profile_ref": "local://zh/profile.json"},
        }
        snapshot = registry.resolve("zh", binding.profile.version, allow_experimental=True)
        files = {snapshot.manifest_path}
        for resource in snapshot.resolved_resources.values():
            files.update(resource.rglob("*")) if resource.is_dir() else files.add(resource)
        digest = hashlib.sha256()
        for file in sorted((file for file in files if file.is_file()), key=lambda file: str(file).lower()):
            digest.update(file.relative_to(settings.workspace_root).as_posix().encode())
            digest.update(b"\0")
            digest.update(file.read_bytes())
        job["profile"]["checksum"] = "sha256:" + digest.hexdigest()
        result = await frozen_binding(CandidateSession(Repo(), job), settings, tmp_path)
        assert result.profile.key == binding.profile.key and result.profile.version == binding.profile.version
        job["profile"]["checksum"] = "sha256:" + "0" * 64
        with pytest.raises(ValueError, match="changed"):
            await frozen_binding(CandidateSession(Repo(), job), settings, tmp_path / "other")

    asyncio.run(run())
