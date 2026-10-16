"""Offline smoke tests only: no provider, database, Storage, or server calls."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import httpx
import pytest

from src.agent.extraction_agent.application.page_workflow_extraction import run_page_workflow_extraction
from src.agent.extraction_agent.application.stage_persistence import STAGES, DurableExtractionSession
from src.config import AgentSettings
from src.domain.enums import AgentStage
from src.agent.extraction_agent.domain.models.extraction_stages import (
    CrossPageCompletionData,
    CrossPageCompletionRequest,
    DrawingEndpoint,
    DrawingPageInput,
    PageClassificationData,
    PageScanData,
    ScannedConnection,
    ScannedWireUnit,
)
from src.domain.models.stage_persistence import StageInput, StageItem
from src.agent.extraction_agent.domain.models.wiring import WireRecord
from src.harness.model_gateway import FakeModelGateway
from src.agent.extraction_agent.infrastructure.zh_vlm_stages import ZhVlmExtractionStageAdapter
from src.profiles import ProfileRegistry
from src.agent.extraction_agent.profiles.zh.policy import ZhExtractionPolicy

ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def forbidden(*args, **kwargs):
        raise AssertionError("Smoke tests must not contact a model or database")

    monkeypatch.setattr(httpx.AsyncClient, "request", forbidden)
    monkeypatch.setattr(httpx.Client, "request", forbidden)


def binding():
    registry = ProfileRegistry(
        profile_root=ROOT / "services/agent/src/agent/extraction_agent/profiles", workspace_root=ROOT, allow_legacy_references=True
    )
    registry.load_all()
    return registry.bind("zh")


class FakeStages:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def classify_page(self, request):
        number = request.page.pdf_page_number
        return PageClassificationData(plant_function="002.C", drawing_page_number=number)

    async def scan_page(self, request):
        number = request.page.pdf_page_number
        self.calls.append(f"scan:{number}")
        if number != 1:
            return PageScanData(pdf_page_number=number)
        return PageScanData(
            pdf_page_number=1,
            units=[
                ScannedWireUnit(
                    unit_id="source",
                    connections=[
                        ScannedConnection(
                            line_number="L1",
                            start=DrawingEndpoint(device="-XD1", terminal="L1"),
                            references=[{"target_function": "002.C", "target_drawing_page": 2}],
                            is_cross_page="cross_page",
                            status="needs_reference",
                        ),
                        ScannedConnection(
                            line_number="missing",
                            start=DrawingEndpoint(device="-Q1", terminal="X9:2"),
                            references=[{"target_function": "080.C", "target_drawing_page": 999}],
                            is_cross_page="cross_page",
                            status="needs_reference",
                        ),
                        ScannedConnection(
                            line_number="cycle",
                            start=DrawingEndpoint(device="-Q1", terminal="X9:4"),
                            references=[{"target_function": "002.C", "target_drawing_page": 1}],
                            is_cross_page="cross_page",
                            status="needs_reference",
                        ),
                        ScannedConnection(
                            line_number="same",
                            start=DrawingEndpoint(device="-K2", terminal="X3:51"),
                            end=DrawingEndpoint(device="-XD21", terminal="60"),
                            is_cross_page="same_page",
                        ),
                        ScannedConnection(
                            line_number="receiver",
                            endpoint_role="receiver",
                            start=DrawingEndpoint(device="-Q1", terminal="X9:2"),
                        ),
                    ],
                )
            ],
        )

    async def resolve_cross_page(self, request):
        assert request.source_page.pdf_page_number == 1
        assert request.target_page.pdf_page_number == 2
        self.calls.append("complete:1->2")
        return CrossPageCompletionData(
            task_id=request.task_id, end=DrawingEndpoint(device="-Q1", terminal="L1"), status="resolved"
        )


def make_pdf(path: Path) -> None:
    from src.agent.extraction_agent.infrastructure.document.pdf_runtime import load_pdf_module

    document = load_pdf_module().open()
    for number in (1, 2):
        page = document.new_page(width=200, height=150)
        page.insert_text((20, 30), f"Plant Function: 002.C\nPage Number: {number}")
    document.save(path)
    document.close()


def test_document_closes_and_saves_page_before_next_scan_and_resumes(tmp_path: Path) -> None:
    async def check() -> None:
        pdf = tmp_path / "drawing.pdf"
        make_pdf(pdf)
        stages = FakeStages()
        progress: list[str] = []
        kwargs = dict(
            pdf_path=pdf,
            output_dir=tmp_path / "run",
            profile=binding(),
            settings=AgentSettings(workspace_root=ROOT),
            run_id="smoke",
            project_id="smoke-project",
            progress=progress.append,
        )
        with patch(
            "src.agent.extraction_agent.application.page_workflow_extraction.build_extraction_stage_dispatcher",
            return_value=stages,
        ):
            first = await run_page_workflow_extraction(**kwargs)
            assert stages.calls == ["scan:1", "complete:1->2", "scan:2"]
            records = {
                item.line_number: item
                for values in first.execution.state["wiring_records"].values()
                for item in values
            }
            assert set(records) == {"L1", "missing", "cycle", "same"}
            assert records["L1"].start_device == "-XD1"
            assert records["L1"].end_terminal == "L1"
            assert records["missing"].end_terminal is None
            assert records["cycle"].end_terminal is None
            assert records["same"].start_device == "-K2"
            assert records["same"].terminal_strip == "X21"
            assert not (tmp_path / "run/03_cross_page_completion").exists()
            saved = json.loads((tmp_path / "run/agent/completed-pages/1.json").read_text(encoding="utf-8"))
            assert saved["scan"]["needs_review"] is True
            assert saved["wire_units"]
            assert progress.index("page_extraction: persisted PDF page 1") < next(
                i for i, value in enumerate(progress) if value.startswith("page_scan: PDF page 2")
            )
            await run_page_workflow_extraction(**kwargs)
            assert stages.calls == ["scan:1", "complete:1->2", "scan:2"]

    asyncio.run(check())


def test_page_save_failure_stops_before_next_source_page(tmp_path: Path) -> None:
    async def check() -> None:
        pdf = tmp_path / "drawing.pdf"
        make_pdf(pdf)
        stages = FakeStages()
        from src.agent.extraction_agent.infrastructure.document.checkpoint import _write_json_atomic

        def save(path, value):
            if "completed-pages" in path.parts:
                raise OSError("simulated persistence failure")
            _write_json_atomic(path, value)

        with (
            patch(
                "src.agent.extraction_agent.application.page_workflow_extraction.build_extraction_stage_dispatcher",
                return_value=stages,
            ),
            patch("src.agent.extraction_agent.graphs.document_extraction.page_extraction._write_json_atomic", save),
        ):
            with pytest.raises(OSError, match="persistence failure"):
                await run_page_workflow_extraction(
                    pdf_path=pdf,
                    output_dir=tmp_path / "run",
                    profile=binding(),
                    settings=AgentSettings(workspace_root=ROOT),
                    run_id="smoke",
                    project_id="smoke-project",
                )
        assert "scan:2" not in stages.calls

    asyncio.run(check())


def test_target_image_completion_and_manifest_paths(tmp_path: Path) -> None:
    async def check() -> None:
        profile = binding()
        assert profile.profile.version == "2.1.1"
        gateway = FakeModelGateway(['{"end":{"device":"-Q1","terminal":"L1"},"status":"resolved"}'])
        adapter = ZhVlmExtractionStageAdapter(AgentSettings(default_model="fake"), gateway)
        pages = []
        for number in (1, 2):
            path = tmp_path / f"{number}.png"
            path.write_bytes(f"fake-image-{number}".encode())
            pages.append(DrawingPageInput(pdf_page_number=number, image_path=path))
        await adapter.resolve_cross_page(
            CrossPageCompletionRequest(
                run_id="smoke",
                project_id="smoke-project",
                profile=profile,
                task_id="line-1",
                source_page=pages[0],
                target_page=pages[1],
                task_context='{"line_number":"L1"}',
            )
        )
        content = gateway.calls[0].messages[-1]["content"]
        assert sum(part.get("type") == "image_url" for part in content) == 1
        assert gateway.calls[0].metadata["stage"] == "page_scan"
        manifest_root = profile.resource("wiring_examples")
        manifest = json.loads((manifest_root / "manifest.json").read_text(encoding="utf-8"))
        for section in ("stage2_cases", "stage3_cases"):
            for case in manifest[section]:
                assert (manifest_root / case["expected"]).is_file()
                for image in case["images"]:
                    assert (manifest_root / image["path"]).is_file()

    asyncio.run(check())


def test_actual_terminals_win_but_business_strip_is_computed_and_pe_end_stays_null() -> None:
    policy = ZhExtractionPolicy()
    observed = policy.normalize_record(
        WireRecord(
            start_device="-XD3",
            start_terminal="15",
            start_terminal_code="X9",
            terminal_strip="CUSTOM-X9",
            end_terminal="2",
        ),
        {},
    )
    assert observed.terminal_strip == "X3"
    assert observed.start_terminal == "XD3:15"
    assert observed.start_terminal_code == "X9"
    unknown = policy.normalize_record(WireRecord(line_number="PE", start_terminal="PE"), {})
    assert unknown.end_terminal is None
    assert unknown.color is None
    unmapped = policy.normalize_record(WireRecord(start_device="-XD1", start_terminal="L1"), {})
    assert unmapped.terminal_strip is None


def test_durable_completed_page_is_distinct_from_model_cache(tmp_path: Path) -> None:
    class Repository:
        def __init__(self):
            self.items = {}

        async def load_snapshot(self, run_id, stage):
            return SimpleNamespace(result_digest="sha256:classification")

        async def commit_item(self, item, *, model_cache=False):
            self.items[(item.item_id, model_cache)] = item

        async def load_item(self, run_id, stage, item_id, *, model_cache=False):
            return self.items.get((item_id, model_cache))

    async def check() -> None:
        repository = Repository()
        inputs = StageInput(
            run_id="smoke",
            project_id="project",
            source_document_id="source",
            source_checksum="sha256:source",
            profile=binding().profile,
            page_count=2,
            configuration={"workflow": "page_extraction_v2"},
        )
        session = DurableExtractionSession(repository, inputs, tmp_path, tmp_path / "source.pdf")
        await repository.commit_item(
            StageItem(
                run_id="smoke",
                stage=AgentStage.PAGE_SCAN,
                item_id="scan:pdf-page:1",
                input_fingerprint="raw",
                result={"units": []},
            ),
            model_cache=True,
        )
        assert await session.load_page(1) is None
        state = {
            "pages": [{"page_number": 1}],
            "page_scan_results": {"1": {"needs_review": True}},
            "wire_units": {},
            "cross_page_tasks": [],
            "cross_page_results": {},
        }
        await session.commit_page(1, state)
        assert (await session.load_page(1))["scan"]["needs_review"]
        assert STAGES == (
            AgentStage.RENDER,
            AgentStage.PAGE_CLASSIFICATION,
            AgentStage.PAGE_SCAN,
            AgentStage.VALIDATION,
        )

    asyncio.run(check())


def test_unclear_cross_page_output_keeps_null_and_continues(tmp_path: Path) -> None:
    class UnclearStages(FakeStages):
        async def resolve_cross_page(self, request):
            self.calls.append("unclear:1->2")
            raise ValueError("simulated unparseable endpoint")

    async def check() -> None:
        pdf = tmp_path / "drawing.pdf"
        make_pdf(pdf)
        stages = UnclearStages()
        with patch(
            "src.agent.extraction_agent.application.page_workflow_extraction.build_extraction_stage_dispatcher",
            return_value=stages,
        ):
            result = await run_page_workflow_extraction(
                pdf_path=pdf,
                output_dir=tmp_path / "run",
                profile=binding(),
                settings=AgentSettings(workspace_root=ROOT),
                run_id="smoke",
                project_id="project",
            )
        assert stages.calls == ["scan:1", "unclear:1->2", "scan:2"]
        records = [item for values in result.execution.state["wiring_records"].values() for item in values]
        assert next(item for item in records if item.line_number == "L1").end_terminal is None
        assert result.execution.extraction_errors == {}

    asyncio.run(check())


def test_cross_page_correction_uses_stage2_internal_completion(tmp_path: Path) -> None:
    from src.domain.enums import CorrectionIssueKind, CrossPageState, ScopeType
    from src.domain.models.correction import (
        CorrectionConstraints,
        CorrectionContext,
        CorrectionEvidenceBundle,
        CorrectionFacts,
        FeedbackTarget,
    )
    from src.agent.extraction_agent.domain.models.extraction_stages import PageScanRequest
    from src.tools.correction_router import CorrectionRoutePlanner
    from src.agent.extraction_agent.tools.extraction_runner import ScopedExtractionRunner

    class Stages:
        async def scan_page(self, request):
            return PageScanData(
                units=[
                    ScannedWireUnit(
                        unit_id="unit",
                        connections=[
                            ScannedConnection(
                                start=DrawingEndpoint(device="-Q1", location="+02", terminal="X3:51"),
                                is_cross_page="cross_page",
                                status="needs_reference",
                                references=[{"target_function": "002.C", "target_drawing_page": 2}],
                            )
                        ],
                    )
                ]
            )

        async def resolve_cross_page(self, request):
            assert request.source_page.pdf_page_number == 1
            assert request.target_page.pdf_page_number == 2
            return CrossPageCompletionData(
                end=DrawingEndpoint(device="-XD21", terminal="XD21:60"), status="resolved"
            )

    async def check() -> None:
        profile = binding()
        source = DrawingPageInput(
            pdf_page_number=1, image_path=tmp_path / "1.png", plant_function="002.C", drawing_page_number=1
        )
        target = source.model_copy(update={"pdf_page_number": 2, "drawing_page_number": 2})
        facts = CorrectionFacts(
            feedback_id="feedback",
            issue_kind=CorrectionIssueKind.RECOGNITION_ERROR,
            is_cross_page=CrossPageState.CROSS_PAGE,
            target=FeedbackTarget(
                type=ScopeType.CONNECTION,
                id="c1",
                project_id="project",
                result_version_id="v1",
                field="end_terminal",
            ),
        )
        bundle = CorrectionEvidenceBundle(
            facts=facts,
            profile=profile,
            base_result_version=1,
            evidence_ids=["drawing-1"],
            context=CorrectionContext(
                feedback_id="feedback",
                observed_problem="wrong endpoint",
                constraints=CorrectionConstraints(
                    allowed_connection_ids=["c1"], allowed_fields=["end_terminal"]
                ),
            ),
            current_records=[
                {
                    "connection_id": "c1",
                    "origin_pdf_page": 1,
                    "start": {"device": "-Q1", "location": "+02", "terminal": "X3:51"},
                    "end_terminal": "999",
                }
            ],
            page_scan_requests=[
                PageScanRequest(run_id="smoke", project_id="project", profile=profile, page=source)
            ],
            available_pages=[source, target],
        )
        plan = CorrectionRoutePlanner().plan(facts)
        assert AgentStage.CROSS_PAGE_COMPLETION not in plan.stages
        records = await ScopedExtractionRunner(Stages()).run(plan, bundle)
        assert records[0]["connection_id"] == "c1"
        assert records[0]["start"] == bundle.current_records[0]["start"]
        assert records[0]["end_terminal"] == "XD21:60"

    asyncio.run(check())


def test_origin_page_controls_mapping_and_evidence_even_when_target_is_earlier() -> None:
    from src.domain.enums import ScopeType
    from src.domain.models.proposals import ProposalOperation, ProposalValidation, ResultProposal
    from src.domain.models.runs import ModelRef, RunScope
    from src.infrastructure.result_mapping import proposal_to_normalized_units

    proposal = ResultProposal(
        agent_run_id="smoke",
        project_id="project",
        base_result_version=0,
        profile=binding().profile,
        model=ModelRef(name="fake"),
        scope=RunScope(type=ScopeType.PROJECT, id="project"),
        validation=ProposalValidation(schema_valid=True, business_rules_valid=True),
        operations=[
            ProposalOperation(
                op="add",
                target_type="CONNECTION",
                target_id="c1",
                evidence_ids=["page"],
                reason="smoke",
                confidence=1,
                after={
                    "pdf_page_number": 80,
                    "source_pages": [3, 80],
                    "is_cross_page": "cross_page",
                    "terminal_strip": None,
                    "start_terminal_strip": "X21",
                },
            )
        ],
    )
    units = proposal_to_normalized_units(
        proposal,
        drawings=[
            {"id": "target", "workspace_id": "w", "pdf_page_number": 3},
            {"id": "source", "workspace_id": "w", "pdf_page_number": 80},
        ],
        workspaces=[{"id": "w", "code": "002.C"}],
    )
    assert units[0]["drawing_id"] == "source"
    assert units[0]["terminal_strip"] is None
    evidence = units[0]["connections"][0]["evidence"]
    assert next(item for item in evidence if item["drawing_id"] == "source")["kind"] == "source"
    assert next(item for item in evidence if item["drawing_id"] == "target")["kind"] == "target"


def test_configuration_failure_stops_instead_of_becoming_an_empty_endpoint(tmp_path: Path) -> None:
    from src.domain.enums import ErrorCode
    from src.domain.errors import AgentServiceError

    class InvalidStages(FakeStages):
        async def resolve_cross_page(self, request):
            raise AgentServiceError(ErrorCode.PROFILE_INVALID, "simulated bad configuration")

    async def check() -> None:
        pdf = tmp_path / "drawing.pdf"
        make_pdf(pdf)
        stages = InvalidStages()
        with patch(
            "src.agent.extraction_agent.application.page_workflow_extraction.build_extraction_stage_dispatcher",
            return_value=stages,
        ):
            with pytest.raises(AgentServiceError, match="bad configuration"):
                await run_page_workflow_extraction(
                    pdf_path=pdf,
                    output_dir=tmp_path / "run",
                    profile=binding(),
                    settings=AgentSettings(workspace_root=ROOT),
                    run_id="smoke",
                    project_id="project",
                )
        assert "scan:2" not in stages.calls
        assert not (tmp_path / "run/agent/completed-pages/1.json").exists()

    asyncio.run(check())


def test_same_wire_number_in_separate_page_groups_keeps_distinct_connection_ids() -> None:
    from src.agent.extraction_agent.graphs.document_extraction.helpers import _merge_scanned_unit

    units = {}
    for index in (1, 2):
        unit = ScannedWireUnit(
            unit_id=f"group-{index}",
            wire_number="same-cable",
            connections=[
                ScannedConnection(
                    start=DrawingEndpoint(device="-Q1", terminal=f"X3:{index}"),
                    end=DrawingEndpoint(device="-XD21", terminal=str(index)),
                )
            ],
        )
        _merge_scanned_unit(
            units, unit, unit_id="merged", page={"page_number": 1}, page_number=1, unit_index=index
        )
    ids = [connection["connection_id"] for connection in units["merged"]["connections"]]
    assert len(set(ids)) == 2
