from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_service.application.extraction_run_executor import FullExtractionRunExecutor
from agent_service.application.run_control import RunControlService
from agent_service.application.worker import AgentWorker
from agent_service.config import AgentSettings
from agent_service.domain.enums import EventType, RunStatus, RunType, ScopeType
from agent_service.domain.models.extraction_stages import (
    CrossPageCompletionData,
    PageClassificationData,
    PageScanData,
)
from agent_service.domain.models.runs import CreateRunRequest, RunScope
from agent_service.harness import (
    InMemoryArtifactRepository,
    InMemoryEventRepository,
    InMemoryProposalRepository,
    InMemoryRunRepository,
)
from agent_service.infrastructure.queue import InMemoryRunQueue
from agent_service.infrastructure.result_data import InMemoryResultDataRepository
from agent_service.infrastructure.source_documents import InMemorySourceDocumentProvider
from agent_service.profiles import ProfileRegistry

ROOT = Path(__file__).resolve().parents[4]


class FakeStages:
    async def classify_page(self, request):  # type: ignore[no-untyped-def]
        return PageClassificationData(
            plant_function="002.C",
            drawing_page_number=1,
            confidence=0.99,
        )

    async def scan_page(self, request):  # type: ignore[no-untyped-def]
        return PageScanData(
            pdf_page_number=request.page.pdf_page_number,
            drawing_function="002.C",
            drawing_page_number=1,
        )

    async def resolve_cross_page(self, request):  # type: ignore[no-untyped-def]
        return CrossPageCompletionData(task_id=request.task_id, needs_review=True)


class ExtractionWorkerTests(unittest.TestCase):
    def test_fake_extraction_worker_emits_stage_events_and_result_proposal(self) -> None:
        async def run() -> None:
            try:
                import pymupdf as fitz
            except ImportError:
                import fitz

            registry = ProfileRegistry(
                profile_root=ROOT / "services" / "agent" / "profiles",
                workspace_root=ROOT,
                allow_legacy_references=True,
            )
            registry.load_all()
            settings = AgentSettings(
                workspace_root=ROOT,
                profile_root=ROOT / "services" / "agent" / "profiles",
            )
            runs = InMemoryRunRepository()
            events = InMemoryEventRepository()
            artifacts = InMemoryArtifactRepository()
            proposals = InMemoryProposalRepository()
            queue = InMemoryRunQueue()
            control = RunControlService(runs=runs, events=events, artifacts=artifacts, queue=queue)
            documents = InMemorySourceDocumentProvider()
            result_data = InMemoryResultDataRepository()
            worker = AgentWorker(
                runs=runs,
                queue=queue,
                publisher=control.publisher,
                artifacts=artifacts,
                proposals=proposals,
                result_data=result_data,
            )
            with tempfile.TemporaryDirectory() as temporary:
                temp = Path(temporary)
                pdf = temp / "drawing.pdf"
                doc = fitz.open()
                page = doc.new_page()
                page.insert_text((72, 72), "Plant Function: 002.C\nPage Number: 1")
                doc.save(pdf)
                doc.close()
                await documents.register("document-1", "project-1", pdf)
                worker.register(
                    RunType.FULL_EXTRACTION,
                    FullExtractionRunExecutor(
                        settings=settings,
                        profiles=registry,
                        documents=documents,
                        artifacts=artifacts,
                        publisher=control.publisher,
                        runtime_root=temp / "runtime",
                    ),
                )
                request = CreateRunRequest(
                    run_type=RunType.FULL_EXTRACTION,
                    project_id="project-1",
                    source_document_id="document-1",
                    requested_by="user-1",
                    profile_hint="zh",
                    expected_result_version=0,
                    scope=RunScope(type=ScopeType.PROJECT, id="project-1"),
                )
                created = await control.create(request, "extraction-worker")
                with patch(
                    "agent_service.application.three_stage_extraction.build_extraction_stage_dispatcher",
                    return_value=FakeStages(),
                ):
                    self.assertTrue(await worker.run_once())

                completed = await runs.get(created.agent_run_id)
                self.assertEqual(completed.status, RunStatus.NEEDS_REVIEW)  # type: ignore[union-attr]
                run_events = await events.list_after(created.agent_run_id)
                stage_events = [
                    event for event in run_events if event.event_type == EventType.STAGE_COMPLETED
                ]
                self.assertEqual(
                    [event.stage.value for event in stage_events],
                    [
                        "RENDER",
                        "PAGE_CLASSIFICATION",
                        "PAGE_SCAN",
                        "BUILD_CROSS_PAGE_TASKS",
                        "CROSS_PAGE_COMPLETION",
                        "VALIDATION",
                    ],
                )
                proposal_event = next(
                    event for event in run_events if event.event_type == EventType.PROPOSAL_CREATED
                )
                proposal = await proposals.get(proposal_event.artifact_refs[0])
                self.assertIsNotNone(proposal)
                self.assertEqual(proposal.agent_run_id, created.agent_run_id)  # type: ignore[union-attr]
                artifact_items = await artifacts.list_for_run(created.agent_run_id)
                self.assertTrue(any(item.get("kind") == "final_xlsx" for item in artifact_items))
                result_artifact = next(
                    item for item in artifact_items if item.get("kind") == "result_version"
                )
                self.assertEqual(result_artifact["result_version"], 1)

        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
