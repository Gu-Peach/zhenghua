from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from agent_service.agents.cross_page_resolver import CrossPageResolverAgent
from agent_service.agents.page_classifier import PageClassifierAgent
from agent_service.agents.page_scanner import PageScannerAgent
from agent_service.application.extraction_stage_dispatcher import ProfileBoundStageDispatcher
from agent_service.config import AgentSettings
from agent_service.domain.models.extraction_stages import (
    CrossPageCompletionData,
    CrossPageCompletionRequest,
    DrawingEndpoint,
    DrawingPageInput,
    PageClassificationData,
    PageClassificationRequest,
    PageScanData,
    PageScanRequest,
)
from agent_service.harness.model_gateway import FakeModelGateway
from agent_service.graphs.extraction import (
    run_cross_page_completion,
    run_page_classification,
    run_page_scan,
)
from agent_service.infrastructure.zh_vlm_stages import ZhVlmExtractionStageAdapter
from agent_service.profiles import ProfileRegistry

ROOT = Path(__file__).resolve().parents[4]


def zh_binding():
    registry = ProfileRegistry(
        profile_root=ROOT / "services" / "agent" / "profiles",
        workspace_root=ROOT,
        allow_legacy_references=True,
    )
    registry.load_all()
    return registry.bind("zh")


def page(number: int, *, blank: bool = False, non_wiring: bool = False) -> DrawingPageInput:
    return DrawingPageInput(
        pdf_page_number=number,
        image_path=Path(f"page-{number}.png"),
        plant_function="002.C",
        drawing_page_number=number,
        blank=blank,
        non_wiring=non_wiring,
    )


class FakeStages:
    def __init__(self) -> None:
        self.classification_requests: list[PageClassificationRequest] = []
        self.scan_requests: list[PageScanRequest] = []
        self.cross_page_requests: list[CrossPageCompletionRequest] = []

    async def classify_page(self, request: PageClassificationRequest) -> PageClassificationData:
        self.classification_requests.append(request)
        return PageClassificationData(
            plant_function="003.C",
            drawing_page_number=9,
            confidence=0.94,
            reason="title block",
        )

    async def scan_page(self, request: PageScanRequest) -> PageScanData:
        self.scan_requests.append(request)
        return PageScanData(
            pdf_page_number=999,
            units=[{"unit_id": "unit-1", "wire_number": "0272", "connections": []}],
        )

    async def resolve_cross_page(
        self,
        request: CrossPageCompletionRequest,
    ) -> CrossPageCompletionData:
        self.cross_page_requests.append(request)
        return CrossPageCompletionData(
            task_id="model-returned-wrong-task",
            end=DrawingEndpoint(device="-TA2", terminal="U2"),
            status="resolved",
            confidence=0.97,
        )


def test_page_classifier_graph_keeps_physical_and_drawing_page_numbers() -> None:
    async def run() -> None:
        stages = FakeStages()
        result = await run_page_classification(
            agent=PageClassifierAgent(stages=stages),
            request=PageClassificationRequest(
                run_id="run-1",
                project_id="project-1",
                profile=zh_binding(),
                page=page(31),
            ),
        )
        assert result.pdf_page_number == 31
        assert result.drawing_page_number == 9
        assert result.plant_function == "003.C"
        assert stages.classification_requests[0].page.pdf_page_number == 31

    asyncio.run(run())


def test_blank_page_classification_skips_profile_vlm_adapter() -> None:
    async def run() -> None:
        stages = FakeStages()
        result = await PageClassifierAgent(stages=stages).run(
            PageClassificationRequest(
                run_id="run-1",
                project_id="project-1",
                profile=zh_binding(),
                page=page(2, blank=True),
            )
        )
        assert result.blank is True
        assert result.confidence == 1.0
        assert stages.classification_requests == []

    asyncio.run(run())


def test_page_scanner_is_one_page_only_and_overrides_model_page_number() -> None:
    async def run() -> None:
        stages = FakeStages()
        request = PageScanRequest(
            run_id="run-1",
            project_id="project-1",
            profile=zh_binding(),
            page=page(48),
            page_context='{"drawing_page_number": 1}',
        )
        result = await run_page_scan(agent=PageScannerAgent(stages=stages), request=request)
        assert result.pdf_page_number == 48
        assert result.units[0].wire_number == "0272"
        assert len(stages.scan_requests) == 1
        assert not hasattr(stages.scan_requests[0], "target_pages")

    asyncio.run(run())


def test_blank_or_non_wiring_scan_skips_adapter() -> None:
    async def run() -> None:
        stages = FakeStages()
        result = await PageScannerAgent(stages=stages).run(
            PageScanRequest(
                run_id="run-1",
                project_id="project-1",
                profile=zh_binding(),
                page=page(5, non_wiring=True),
            )
        )
        assert result.units == []
        assert result.blank is False
        assert stages.scan_requests == []

    asyncio.run(run())


def test_cross_page_graph_scopes_one_task_and_cannot_return_start() -> None:
    async def run() -> None:
        stages = FakeStages()
        result = await run_cross_page_completion(
            agent=CrossPageResolverAgent(stages=stages),
            request=CrossPageCompletionRequest(
                run_id="run-1",
                project_id="project-1",
                profile=zh_binding(),
                task_id="task-1",
                target_page=page(6),
                task_context="connection=conn-1; start=XA:1; line=002C0601",
            ),
        )
        assert result.task_id == "task-1"
        assert result.end is not None and result.end.terminal == "U2"
        assert result.status == "resolved"
        assert "start" not in type(result).model_fields
        assert stages.cross_page_requests[0].target_page.pdf_page_number == 6

    asyncio.run(run())


def test_blank_cross_page_targets_degrade_to_review() -> None:
    async def run() -> None:
        stages = FakeStages()
        result = await CrossPageResolverAgent(stages=stages).run(
            CrossPageCompletionRequest(
                run_id="run-1",
                project_id="project-1",
                profile=zh_binding(),
                task_id="task-1",
                target_page=page(6, blank=True),
                task_context="one connection",
            )
        )
        assert result.needs_review is True
        assert result.end is None
        assert stages.cross_page_requests == []

    asyncio.run(run())


def test_profile_bound_dispatcher_rejects_missing_adapter() -> None:
    async def run() -> None:
        request = PageScanRequest(
            run_id="run-1",
            project_id="project-1",
            profile=zh_binding(),
            page=page(1),
        )
        with pytest.raises(ValueError, match="No extraction stage adapter"):
            await ProfileBoundStageDispatcher().scan_page(request)

    asyncio.run(run())


def test_experimental_abb_cannot_fall_through_to_zh_adapter() -> None:
    async def run() -> None:
        registry = ProfileRegistry(
            profile_root=ROOT / "services" / "agent" / "profiles",
            workspace_root=ROOT,
            allow_legacy_references=True,
        )
        registry.load_all()
        request = PageClassificationRequest(
            run_id="run-1",
            project_id="project-1",
            profile=registry.bind("abb", allow_experimental=True),
            page=page(1),
        )
        dispatcher = ProfileBoundStageDispatcher()
        dispatcher.register("zh_native", FakeStages())
        with pytest.raises(ValueError, match="native_pending"):
            await dispatcher.classify_page(request)

    asyncio.run(run())


def test_native_zh_stage_adapter_uses_multimodal_examples_for_all_stages(tmp_path: Path) -> None:
    async def run() -> None:
        image_path = tmp_path / "source.png"
        image_path.write_bytes(b"test-image-bytes")
        target_path = tmp_path / "target.png"
        target_path.write_bytes(b"target-image-bytes")
        gateway = FakeModelGateway(
            [
                '{"plant_function":"002.C","page_number":3,"confidence":0.9}',
                '{"pdf_page_number":12,"units":[{"unit_id":"u-1","wire_number":"0272","connections":[]}]}',
                '{"end":{"device":"-TA2","terminal":"U2"},"status":"resolved","needs_review":false}',
            ]
        )
        adapter = ZhVlmExtractionStageAdapter(
            AgentSettings(model_base_url="http://model.invalid/v1", default_model="fake-vlm"),
            gateway,
        )
        binding = zh_binding()
        result = await adapter.classify_page(
            PageClassificationRequest(
                run_id="run-1",
                project_id="project-1",
                profile=binding,
                page=DrawingPageInput(pdf_page_number=12, image_path=image_path),
                known_context="physical page 12",
            )
        )
        assert result.plant_function == "002.C"
        assert result.drawing_page_number == 3

        scanned = await adapter.scan_page(
            PageScanRequest(
                run_id="run-1",
                project_id="project-1",
                profile=binding,
                page=DrawingPageInput(pdf_page_number=12, image_path=image_path),
                page_context="source context",
            )
        )
        assert scanned.pdf_page_number == 12
        assert scanned.units[0].wire_number == "0272"

        completion = await adapter.resolve_cross_page(
            CrossPageCompletionRequest(
                run_id="run-1",
                project_id="project-1",
                profile=binding,
                task_id="task-1",
                target_page=DrawingPageInput(pdf_page_number=13, image_path=target_path),
                task_context="connection=connection-1",
            )
        )
        assert completion.task_id == "task-1"
        assert completion.end is not None and completion.end.terminal == "U2"
        assert len(gateway.calls) == 3
        for call in gateway.calls:
            assert any(
                isinstance(part, dict) and part.get("type") == "image_url"
                for message in call.messages
                if message["role"] == "user"
                for part in (message["content"] if isinstance(message["content"], list) else [])
            )

    asyncio.run(run())
