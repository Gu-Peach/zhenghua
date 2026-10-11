"""Explicit local Supabase acceptance; never calls a real/paid model."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest

from agent_service.application.extraction_run_executor import FullExtractionRunExecutor
from agent_service.application.run_control import RunControlService
from agent_service.application.worker import AgentWorker
from agent_service.config import AgentSettings
from agent_service.domain.enums import AgentStage, EventType, RunType, ScopeType
from agent_service.domain.errors import AgentServiceError
from agent_service.domain.models.extraction_stages import (
    CrossPageCompletionData,
    DrawingEndpoint,
    DrawingReference,
    PageClassificationData,
    PageScanData,
    ScannedConnection,
    ScannedWireUnit,
)
from agent_service.domain.models.runs import AgentEvent, CreateRunRequest, RunScope
from agent_service.domain.models.stage_persistence import StageInput, StageItem, digest
from agent_service.infrastructure.document.pdf_runtime import load_pdf_module
from agent_service.infrastructure.project_assets import (
    SupabaseProjectAssetStore,
    SupabaseSourceDocumentProvider,
)
from agent_service.infrastructure.run_lease_context import current_run_lease
from agent_service.infrastructure.supabase_client import SupabaseClient
from agent_service.infrastructure.supabase_repositories import (
    SupabaseArtifactRepository,
    SupabaseEventRepository,
    SupabaseProposalRepository,
    SupabaseRunQueue,
    SupabaseRunRepository,
)
from agent_service.infrastructure.supabase_result_data import SupabaseResultDataRepository
from agent_service.infrastructure.supabase_stage_repository import SupabaseStageRepository
from agent_service.profiles import ProfileRegistry

ROOT = Path(__file__).resolve().parents[4]
pytestmark = pytest.mark.skipif(
    os.getenv("AGENT_TEST_REAL_SUPABASE") != "true", reason="explicit local Supabase flag required"
)


class InjectedCrash(BaseException):
    """A process-loss boundary, not an application exception or paid model."""


class FakeStages:
    def __init__(self, crash: str = "") -> None:
        self.calls: list[tuple[str, int]] = []
        self.crash = crash

    async def classify_page(self, request):  # type: ignore[no-untyped-def]
        if self.crash == "classify_crash" and request.page.pdf_page_number == 2:
            raise InjectedCrash()
        self.calls.append(("classify", request.page.pdf_page_number))
        return PageClassificationData(
            plant_function="002.C", drawing_page_number=request.page.pdf_page_number, confidence=0.99
        )

    async def scan_page(self, request):  # type: ignore[no-untyped-def]
        if self.crash == "scan_crash" and request.page.pdf_page_number == 2:
            raise InjectedCrash()
        self.calls.append(("scan", request.page.pdf_page_number))
        units = []
        if request.page.pdf_page_number == 1:
            units = [
                ScannedWireUnit(
                    unit_id="unit-1",
                    source_pages=[1],
                    connections=[
                        ScannedConnection(
                            connection_id="c1",
                            origin_pdf_page=1,
                            line_number="002C0101",
                            start=DrawingEndpoint(device="-XD11", terminal_strip="XD11", terminal="1"),
                            end=None,
                            references=[
                                DrawingReference(
                                    target_pdf_page=2, target_function="002.C", target_drawing_page=2
                                )
                            ],
                            is_cross_page="cross_page",
                        ),
                    ],
                )
            ]
        return PageScanData(
            pdf_page_number=request.page.pdf_page_number,
            drawing_function="002.C",
            drawing_page_number=request.page.pdf_page_number,
            units=units,
        )

    async def resolve_cross_page(self, request):  # type: ignore[no-untyped-def]
        if self.crash == "cross_crash":
            raise InjectedCrash()
        self.calls.append(("cross", request.target_page.pdf_page_number))
        return CrossPageCompletionData(
            task_id=request.task_id,
            end=DrawingEndpoint(device="-M1", terminal="U1"),
            status="resolved",
            needs_review=False,
        )


@pytest.mark.parametrize(
    "scenario",
    [
        "normal",
        "classify_crash",
        "scan_crash",
        "cross_crash",
        "result_crash",
        "ack_crash",
        "coverage",
        "tree_epoch",
        "retry_cancel",
        "process_crash",
    ],
)
def test_gate_a_database_fake_model_pipeline(tmp_path: Path, scenario: str) -> None:
    async def run() -> None:
        settings = replace(AgentSettings.from_env(), default_model="fake-gate-a", extraction_render_dpi=300)
        assert settings.supabase_url == "http://127.0.0.1:54321", "only the named local test stack is allowed"
        client = SupabaseClient(
            base_url=settings.supabase_url, service_role_key=settings.supabase_service_role_key or ""
        )
        project_id, document_id = str(uuid4()), str(uuid4())
        headers = {
            "apikey": settings.supabase_service_role_key or "",
            "Authorization": f"Bearer {settings.supabase_service_role_key}",
        }
        async with httpx.AsyncClient(timeout=30) as http:
            created = await http.post(
                f"{settings.supabase_url}/auth/v1/admin/users",
                headers=headers,
                json={
                    "email": f"gate-a-{uuid4().hex}@example.invalid",
                    "password": f"GateA-{uuid4().hex}!",
                    "email_confirm": True,
                },
            )
            created.raise_for_status()
            user_id = created.json()["id"]
        try:
            await client.insert(
                "projects",
                {
                    "id": project_id,
                    "owner_id": user_id,
                    "name": "Gate A isolated acceptance",
                    "status": "processing",
                },
            )
            pdf = tmp_path / "source.pdf"
            with load_pdf_module().open() as document:
                for number in (1, 2):
                    page = document.new_page()
                    page.insert_text((72, 72), f"Plant Function: 002.C\nPage Number: {number}")
                document.save(str(pdf))
            assets = SupabaseProjectAssetStore(client)
            access = await assets.upload_source_pdf(
                project_id=project_id, document_id=document_id, original_filename="source.pdf", pdf_path=pdf
            )
            registry = ProfileRegistry(
                profile_root=settings.profile_root, workspace_root=ROOT, allow_legacy_references=True
            )
            registry.load_all()
            runs, events = (
                SupabaseRunRepository(client, durable_extraction=True),
                SupabaseEventRepository(client),
            )
            artifacts, proposals = SupabaseArtifactRepository(client), SupabaseProposalRepository(client)
            queue = SupabaseRunQueue(client)
            control = RunControlService(runs=runs, events=events, artifacts=artifacts, queue=queue)
            stages = SupabaseStageRepository(
                client, lease_seconds=30 if scenario in {"normal", "coverage", "retry_cancel"} else 5
            )
            result_data = SupabaseResultDataRepository(
                client, profiles=registry, drawing_cache_root=tmp_path / "drawing-cache"
            )
            worker = AgentWorker(
                runs=runs,
                queue=queue,
                publisher=control.publisher,
                artifacts=artifacts,
                proposals=proposals,
                result_data=result_data,
                durable_stages=stages,
            )
            worker.register(
                RunType.FULL_EXTRACTION,
                FullExtractionRunExecutor(
                    settings=settings,
                    profiles=registry,
                    documents=SupabaseSourceDocumentProvider(client, cache_root=tmp_path / "sources"),
                    artifacts=artifacts,
                    publisher=control.publisher,
                    runtime_root=tmp_path / "runtime",
                    project_assets=assets,
                    durable_stages=stages,
                ),
            )
            saved = await control.create(
                CreateRunRequest(
                    run_type=RunType.FULL_EXTRACTION,
                    project_id=project_id,
                    source_document_id=document_id,
                    requested_by=user_id,
                    profile_hint="zh",
                    expected_result_version=0,
                    scope=RunScope(type=ScopeType.PROJECT, id=project_id),
                ),
                f"gate-a-{uuid4()}",
            )
            if scenario in {"coverage", "retry_cancel"}:
                lease = await stages.claim()
                assert lease and lease.run_id == saved.agent_run_id
                context = current_run_lease.set(lease)
                try:
                    inputs = StageInput(
                        run_id=saved.agent_run_id,
                        project_id=project_id,
                        source_document_id=document_id,
                        source_checksum=access.checksum,
                        profile=registry.bind("zh").profile,
                        page_count=2,
                        configuration={},
                    )
                    await stages.initialize(inputs)
                    item = StageItem(
                        run_id=saved.agent_run_id,
                        stage=AgentStage.RENDER,
                        item_id="pdf-page:1",
                        input_fingerprint=digest(
                            {
                                "root": inputs.fingerprint,
                                "stage": "RENDER",
                                "item_id": "pdf-page:1",
                                "upstream_result_digest": None,
                            }
                        ),
                        result={"page": {"page_number": 1}},
                    )
                    await stages.commit_item(item)
                    if scenario == "retry_cancel":
                        try:
                            await stages.action(
                                lease,
                                "fail",
                                {
                                    "retryable": True,
                                    "error": {
                                        "code": "PERSISTENCE_UNAVAILABLE",
                                        "message": "synthetic retry",
                                        "retryable": True,
                                    },
                                },
                            )
                        except AgentServiceError as exc:
                            raise AssertionError(exc.details) from exc
                        assert (await runs.get(saved.agent_run_id)).status.value == "QUEUED"
                        assert await client.select(
                            "agent_run_queue", params={"agent_run_id": f"eq.{saved.agent_run_id}"}
                        )
                        await asyncio.sleep(2.1)
                        replacement_lease = await stages.claim()
                        assert replacement_lease and replacement_lease.generation > lease.generation
                        assert await stages.load_item(saved.agent_run_id, AgentStage.RENDER, "pdf-page:1")
                        await control.cancel(saved.agent_run_id)
                        assert (await runs.get(saved.agent_run_id)).status.value == "CANCELLED"
                        with pytest.raises(AgentServiceError):
                            await stages.action(replacement_lease, "renew", {"seconds": 30})
                        return
                    with pytest.raises(AgentServiceError):
                        await stages.seal(
                            saved.agent_run_id,
                            AgentStage.RENDER,
                            {"expected_item_ids": ["pdf-page:1"], "ready": True},
                        )
                    assert await stages.load_snapshot(saved.agent_run_id, AgentStage.RENDER) is None
                    with pytest.raises(AgentServiceError):
                        await stages.commit_item(item.model_copy(update={"result": {"different": True}}))
                    persisted = await stages.load_item(saved.agent_run_id, AgentStage.RENDER, "pdf-page:1")
                    assert persisted and persisted.result == item.result
                    await stages.action(lease, "pause", {"status": "WAITING_INPUT"})
                    await stages.action(lease, "ack")
                finally:
                    current_run_lease.reset(context)
                return
            fake = FakeStages(scenario)
            if scenario == "process_crash":

                async def child(runtime: Path, crash: bool) -> tuple[int, list[tuple[str, int]]]:
                    argv = [
                        sys.executable,
                        str(ROOT / "services/agent/scripts/run_gate_a_fake_worker.py"),
                        saved.agent_run_id,
                        str(runtime),
                    ]
                    if crash:
                        argv += ["--crash", "scan_crash"]
                    process = await asyncio.create_subprocess_exec(
                        *argv, cwd=ROOT, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
                    )
                    stdout, stderr = await process.communicate()
                    assert process.returncode in {0, 42}, stderr.decode("utf-8", errors="replace")[-1500:]
                    calls = json.loads(stdout.decode("utf-8").strip().splitlines()[-1])["calls"]
                    return process.returncode, [tuple(value) for value in calls]

                first_code, first_calls = await child(tmp_path / "process-one", True)
                assert first_code == 42
                assert (await runs.get(saved.agent_run_id)).status.value == "RUNNING"
                await asyncio.sleep(5.1)
                second_code, second_calls = await child(tmp_path / "process-two-empty", False)
                assert second_code == 0
                assert not set(first_calls) & set(second_calls)
                receipt = await stages.final_receipt(saved.agent_run_id)
                assert receipt and receipt.finalized
                assert await client.select(
                    "wiring_connection_rows", params={"project_id": f"eq.{project_id}"}
                )
                return
            if scenario == "tree_epoch":
                beta = await control.create(
                    CreateRunRequest(
                        run_type=RunType.FULL_EXTRACTION,
                        project_id=project_id,
                        source_document_id=document_id,
                        requested_by=user_id,
                        profile_hint="zh",
                        expected_result_version=0,
                        scope=RunScope(type=ScopeType.PROJECT, id=project_id),
                    ),
                    f"gate-a-beta-{uuid4()}",
                )
                original_seal = stages.seal

                async def crash_after_classification(run_id, stage, snapshot):  # type: ignore[no-untyped-def]
                    result = await original_seal(run_id, stage, snapshot)
                    if stage == AgentStage.PAGE_CLASSIFICATION:
                        assert not result.tree_published
                        raise InjectedCrash()
                    return result

                with (
                    patch(
                        "agent_service.application.three_stage_extraction.build_extraction_stage_dispatcher",
                        return_value=fake,
                    ),
                    patch.object(stages, "seal", side_effect=crash_after_classification),
                ):
                    with pytest.raises(InjectedCrash):
                        await worker.run_once()
                project = (await client.select("projects", params={"id": f"eq.{project_id}"}))[0]
                assert project["published_classification_snapshot_id"] is None
                assert not await client.select("drawings", params={"project_id": f"eq.{project_id}"})
                await control.cancel(saved.agent_run_id)
                with patch(
                    "agent_service.application.three_stage_extraction.build_extraction_stage_dispatcher",
                    return_value=FakeStages(),
                ):
                    assert await worker.run_once()
                project = (await client.select("projects", params={"id": f"eq.{project_id}"}))[0]
                assert project["published_classification_snapshot_id"].startswith(beta.agent_run_id)
                assert (
                    await stages.load_snapshot(saved.agent_run_id, AgentStage.PAGE_CLASSIFICATION)
                ).tree_published is False
                return
            captured_leases = []
            original_claim = stages.claim

            async def capture_claim():  # type: ignore[no-untyped-def]
                lease = await original_claim()
                captured_leases.append(lease)
                return lease

            async def lost_finalization(_run_id: str):  # type: ignore[no-untyped-def]
                raise InjectedCrash()

            original_action = stages.action

            async def lost_ack(lease, action, value=None):  # type: ignore[no-untyped-def]
                if action == "ack":
                    raise InjectedCrash()
                return await original_action(lease, action, value)

            with (
                patch(
                    "agent_service.application.three_stage_extraction.build_extraction_stage_dispatcher",
                    return_value=fake,
                ),
                patch.object(stages, "claim", side_effect=capture_claim),
            ):
                if scenario == "normal":
                    assert await worker.run_once()
                else:
                    patcher = (
                        patch.object(stages, "finalize", side_effect=lost_finalization)
                        if scenario == "result_crash"
                        else patch.object(stages, "action", side_effect=lost_ack)
                        if scenario == "ack_crash"
                        else patch.object(fake, "crash", scenario)
                    )
                    with patcher, pytest.raises(InjectedCrash):
                        await worker.run_once()
            resumed_calls: list[tuple[str, int]] = []
            if scenario != "normal":
                await asyncio.sleep(5.1)
                replacement = SupabaseStageRepository(client, lease_seconds=300)
                lease = await replacement.claim()
                assert lease and lease.run_id == saved.agent_run_id
                assert lease.mode == ("cleanup" if scenario == "ack_crash" else "recover")
                old = captured_leases[0]
                assert old and old.generation < lease.generation
                for action in ("fail", "ack", "renew"):
                    with pytest.raises(AgentServiceError):
                        await stages.action(old, action, {"seconds": 30, "retryable": False})
                obsolete = current_run_lease.set(old)
                try:
                    run_to_modify = await runs.get(saved.agent_run_id)
                    with pytest.raises(AgentServiceError):
                        await runs.save(run_to_modify)
                    with pytest.raises(AgentServiceError):
                        await events.append(
                            AgentEvent(
                                agent_run_id=saved.agent_run_id, seq=999, event_type=EventType.RUN_FAILED
                            )
                        )
                    with pytest.raises(AgentServiceError):
                        await artifacts.put(
                            f"{saved.agent_run_id}:old-worker",
                            {
                                "agent_run_id": saved.agent_run_id,
                                "artifact_id": f"{saved.agent_run_id}:old-worker",
                                "kind": "obsolete_worker",
                                "test_only": True,
                            },
                        )
                    with pytest.raises(AgentServiceError):
                        await stages.finalize(saved.agent_run_id)
                    with pytest.raises(AgentServiceError):
                        await client.rpc(
                            "gate_a_commit_result",
                            {
                                "target": saved.agent_run_id,
                                "token": old.model_dump(mode="json"),
                                "value": {},
                                "run_status": "SUCCEEDED",
                            },
                        )
                    with pytest.raises(AgentServiceError):
                        await client.delete(
                            "agent_run_queue", filters={"agent_run_id": f"eq.{saved.agent_run_id}"}
                        )
                finally:
                    current_run_lease.reset(obsolete)
                context = current_run_lease.set(lease)
                successor_fake = FakeStages()
                try:
                    assert (await runs.get(saved.agent_run_id)).status.value != "FAILED"
                    fresh_executor = FullExtractionRunExecutor(
                        settings=settings,
                        profiles=registry,
                        documents=SupabaseSourceDocumentProvider(client, cache_root=tmp_path / "new-sources"),
                        artifacts=artifacts,
                        publisher=control.publisher,
                        runtime_root=tmp_path / "no-cache",
                        project_assets=assets,
                        durable_stages=replacement,
                    )
                    successor = AgentWorker(
                        runs=runs,
                        queue=queue,
                        publisher=control.publisher,
                        artifacts=artifacts,
                        proposals=proposals,
                        result_data=result_data,
                        durable_stages=replacement,
                    )
                    successor.register(RunType.FULL_EXTRACTION, fresh_executor)
                    with patch(
                        "agent_service.application.three_stage_extraction.build_extraction_stage_dispatcher",
                        return_value=successor_fake,
                    ):
                        assert await successor._run_durable(lease)
                    resumed_calls = successor_fake.calls
                finally:
                    current_run_lease.reset(context)
                for previous in fake.calls:
                    assert previous not in resumed_calls, "committed model item must not execute twice"
            final = await runs.get(saved.agent_run_id)
            assert final is not None
            diagnostic_events = await events.list_after(saved.agent_run_id)
            assert final.status.value in {"SUCCEEDED", "NEEDS_REVIEW"}, (
                str(final.error),
                fake.calls,
                [(event.stage, event.event_type) for event in diagnostic_events],
            )
            for stage in (
                AgentStage.RENDER,
                AgentStage.PAGE_CLASSIFICATION,
                AgentStage.PAGE_SCAN,
                AgentStage.BUILD_CROSS_PAGE_TASKS,
                AgentStage.CROSS_PAGE_COMPLETION,
                AgentStage.VALIDATION,
            ):
                snapshot = await stages.load_snapshot(saved.agent_run_id, stage)
                assert snapshot and snapshot.ready_for_next_stage
            receipt = await stages.final_receipt(saved.agent_run_id)
            assert receipt and receipt.finalized
            result_rows = await client.select(
                "wiring_connection_rows", params={"project_id": f"eq.{project_id}"}
            )
            assert result_rows, "acceptance must persist nonempty wiring data"
            assert result_rows[0]["wire_number"] == 1000
            assert result_rows[0]["start_code"] == "-XD11"
            assert result_rows[0]["end_code"] == "-M1"
            assert ("cross", 2) in fake.calls + resumed_calls
            completed_events = [
                event
                for event in await events.list_after(saved.agent_run_id)
                if event.event_type.value in {"RUN_COMPLETED", "HUMAN_INPUT_REQUIRED"}
            ]
            assert len(completed_events) == 1
        finally:
            # Remove only this test's unique UUID project and its referenced objects.
            async with httpx.AsyncClient(timeout=30) as http:
                listing = await http.post(
                    f"{settings.supabase_url}/storage/v1/object/list/project-assets",
                    headers=headers,
                    json={"prefix": f"projects/{project_id}", "limit": 1000},
                )
                _ = listing  # Nested objects are cleaned by the prefix walker below.

            async def objects(prefix: str) -> list[str]:
                async with httpx.AsyncClient(timeout=30) as http:
                    response = await http.post(
                        f"{settings.supabase_url}/storage/v1/object/list/project-assets",
                        headers=headers,
                        json={"prefix": prefix, "limit": 1000},
                    )
                    response.raise_for_status()
                values: list[str] = []
                for entry in response.json():
                    path = prefix + "/" + entry["name"]
                    if entry.get("id"):
                        values.append(path)
                    else:
                        values.extend(await objects(path))
                return values

            await client.remove_objects(
                bucket="project-assets", object_paths=await objects(f"projects/{project_id}")
            )
            try:
                await client.delete("projects", filters={"id": f"eq.{project_id}"})
            except Exception as exc:
                raise AssertionError(getattr(exc, "details", {})) from exc
            async with httpx.AsyncClient(timeout=30) as http:
                response = await http.delete(
                    f"{settings.supabase_url}/auth/v1/admin/users/{user_id}", headers=headers
                )
                response.raise_for_status()

    asyncio.run(run())
