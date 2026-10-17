"""No network or paid models: exercise the actual page Graph and publication session."""

from __future__ import annotations

import asyncio
import copy
from pathlib import Path
from unittest.mock import patch

import pymupdf

from src.agent.extraction_agent.application.page_workflow_extraction import run_page_workflow_extraction
from src.agent.extraction_agent.domain.models.extraction_stages import (
    CrossPageCompletionData,
    DrawingEndpoint,
    PageClassificationData,
    PageScanData,
    ScannedConnection,
    ScannedWireUnit,
)
from src.agent.extraction_agent.infrastructure.incremental_repository import IncrementalSession
from src.config import AgentSettings
from src.profiles import ProfileRegistry

ROOT = Path(__file__).resolve().parents[4]


class MemoryPublication:
    def __init__(self):
        self.steps = {}
        self.objects = {}
        self.rows = {}
        self.history = []

    async def artifact(self, run, item):
        return copy.deepcopy(self.steps.get(item))

    async def request(self, method, path, **kwargs):
        import httpx

        assert method == "GET" and path == "/rest/v1/extraction_profiles"
        return httpx.Response(200, json=[])

    async def put(self, bucket, path, content, mime):
        assert content.startswith(b"\x89PNG") or (mime == "application/zip" and content.startswith(b"PK"))
        self.objects[path] = content

    async def get(self, bucket, path):
        return self.objects[path]

    async def rpc(self, name, value):
        assert name == "commit_simple_extraction"
        key, step = value["item_key"], value["value"]
        if key in self.steps:
            assert self.steps[key] == step
            return {}
        self.steps[key] = copy.deepcopy(step)
        if step.get("page"):
            assert step["page"]["image_path"] in self.objects
        for row in step.get("rows", []):
            self.rows[row["id"]] = row
        self.history.append(copy.deepcopy(step))
        return {}


class Stages:
    def __init__(self, sink):
        self.sink = sink
        self.calls = []

    async def classify_page(self, request):
        return PageClassificationData(
            plant_function="002.C", drawing_page_number=request.page.pdf_page_number
        )

    async def scan_page(self, request):
        number = request.page.pdf_page_number
        self.calls.append(f"scan:{number}")
        if number == 2:
            assert "page:1" in self.sink.steps
            return PageScanData(pdf_page_number=2)
        return PageScanData(
            pdf_page_number=1,
            units=[
                ScannedWireUnit(
                    unit_id="unit",
                    connections=[
                        ScannedConnection(
                            connection_id="one",
                            direction_basis="outgoing arrow",
                            start=DrawingEndpoint(device="-Q1", terminal="X3:1"),
                            line_number="002C01",
                            references=[{"target_function": "002.C", "target_drawing_page": 2}],
                        ),
                    ],
                )
            ],
        )

    async def resolve_cross_page(self, request):
        self.calls.append("complete")
        provisional = list(self.sink.rows.values())
        assert len(provisional) == 1
        assert provisional[0]["end_terminal"] is None
        assert provisional[0]["evidence"]["processing_status"] == "pending_completion"
        assert provisional[0]["needs_review"] is False
        return CrossPageCompletionData(
            task_id=request.task_id,
            source_note="Target wire terminates at XD21:7",
            end=DrawingEndpoint(device="-K1", terminal="XD21:7"),
        )


def test_scan_completion_and_resume_keep_identity_and_publish_before_next_page(tmp_path: Path):
    async def run():
        pdf = tmp_path / "source.pdf"
        with pymupdf.open() as document:
            for number in (1, 2):
                page = document.new_page(width=180, height=150)
                page.insert_text((15, 20), f"Plant Function: 002.C\nPage Number: {number}")
            document.save(pdf)
        registry = ProfileRegistry(
            profile_root=ROOT / "services/agent/src/agent/extraction_agent/profiles",
            workspace_root=ROOT,
            allow_legacy_references=True,
        )
        registry.load_all()
        sink = MemoryPublication()
        session = IncrementalSession(
            sink,
            {
                "run": {"id": "run", "profile": {"key": "zh"}},
                "project": {"id": "project"},
                "lease": {"token": "token"},
            },
            "worker",
        )
        stages = Stages(sink)
        with patch(
            "src.agent.extraction_agent.application.page_workflow_extraction.build_extraction_stage_dispatcher",
            return_value=stages,
        ):
            arguments = dict(
                pdf_path=pdf,
                output_dir=tmp_path / "run",
                profile=registry.bind("zh"),
                settings=AgentSettings(workspace_root=ROOT),
                run_id="run",
                project_id="project",
                durable=session,
            )
            await run_page_workflow_extraction(**arguments)
            scan = next(s for s in sink.history if s["kind"] == "scan" and s.get("rows"))
            complete = next(s for s in sink.history if s["kind"] == "completion" and s.get("rows"))
            final = sink.steps["page:1"]
            assert scan["rows"][0]["id"] == complete["rows"][0]["id"] == final["rows"][0]["id"]
            assert complete["rows"][0]["end_terminal"] == "XD21:7"
            assert final["rows"][0]["target_pdf_page_number"] == 2
            assert final["rows"][0]["needs_review"] is False
            assert final["rows"][0]["evidence"]["processing_status"] == "completed"
            assert stages.calls == ["scan:1", "complete", "scan:2"]
            before = len(sink.history)
            await run_page_workflow_extraction(**arguments)
            assert len(sink.history) == before
            assert stages.calls == ["scan:1", "complete", "scan:2"]

    asyncio.run(run())


def test_profile_snapshot_can_resume_without_local_profile_and_detects_corruption(tmp_path: Path):
    import hashlib
    from dataclasses import replace

    import pytest

    from src.agent.extraction_agent.application.incremental_worker import frozen_profile

    async def run():
        registry = ProfileRegistry(
            profile_root=ROOT / "services/agent/src/agent/extraction_agent/profiles",
            workspace_root=ROOT,
            allow_legacy_references=True,
        )
        registry.load_all()
        snapshot = registry.resolve("zh")
        files = {snapshot.manifest_path}
        for resource in snapshot.resolved_resources.values():
            files.update(p for p in resource.rglob("*") if p.is_file()) if resource.is_dir() else files.add(
                resource
            )
        digest = hashlib.sha256()
        for file in sorted(files, key=lambda p: str(p).lower()):
            digest.update(file.relative_to(ROOT).as_posix().encode())
            digest.update(b"\0")
            digest.update(file.read_bytes())
        sink = MemoryPublication()
        session = IncrementalSession(
            sink,
            {
                "run": {
                    "id": "run",
                    "profile": {
                        "key": "zh",
                        "version": snapshot.manifest.version,
                        "checksum": "sha256:" + digest.hexdigest(),
                    },
                },
                "project": {"id": "project"},
                "lease": {"token": "token"},
            },
            "worker",
        )
        settings = AgentSettings(workspace_root=ROOT)
        first = await frozen_profile(session, settings, tmp_path)
        assert first.resource("page_scan_prompt").is_file()
        second = await frozen_profile(session, replace(settings, profile_root=tmp_path / "missing"), tmp_path)
        assert second.profile == first.profile
        key = sink.steps["profile-package"]["snapshot"]["path"]
        sink.objects[key] = b"corrupt"
        with pytest.raises(ValueError, match="checksum"):
            await frozen_profile(session, settings, tmp_path)

    asyncio.run(run())


def test_storage_permission_errors_are_fatal_and_not_retried():
    import httpx
    import pytest

    from src.agent.extraction_agent.graphs.document_extraction.helpers import _is_fatal_model_request_error
    from src.agent.extraction_agent.infrastructure.incremental_repository import IncrementalRepository
    from src.domain.errors import AgentServiceError

    async def run():
        calls = []

        def respond(request):
            calls.append(request)
            return httpx.Response(403, json={"message": "forbidden"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as http:
            repository = IncrementalRepository(
                AgentSettings(supabase_url="http://fixture", supabase_service_role_key="fixture"), http
            )
            with pytest.raises(AgentServiceError) as error:
                await repository.rpc("commit_simple_extraction", {})
            assert _is_fatal_model_request_error(error.value)
            assert len(calls) == 1

    asyncio.run(run())


def test_claim_validates_owner_and_storage_scope_before_path_use():
    from uuid import uuid4

    import pytest
    from pydantic import ValidationError

    from src.agent.extraction_agent.application.incremental import WorkerClaim

    project, actor, run = [str(uuid4()) for _ in range(3)]
    value = {
        "run": {
            "id": run,
            "project_id": project,
            "requested_by": actor,
            "profile": {"key": "zh", "version": "2.1.1", "checksum": "sha256:" + "a" * 64},
            "options": {"workflow": "simple_extraction_v1"},
        },
        "project": {
            "id": project,
            "owner_id": actor,
            "source_pdf_bucket": "project-assets",
            "source_pdf_path": f"projects/{project}/source.pdf",
            "drawing_index": {},
        },
        "lease": {"worker": "test", "token": str(uuid4())},
    }
    assert str(WorkerClaim.model_validate(value).project.id) == project
    value["project"]["source_pdf_path"] += "/../foreign.pdf"
    with pytest.raises(ValidationError, match="scope"):
        WorkerClaim.model_validate(value)
    value["project"]["owner_id"] = str(uuid4())
    with pytest.raises(ValidationError, match="owner"):
        WorkerClaim.model_validate(value)
