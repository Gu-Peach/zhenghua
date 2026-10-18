from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

from src.agent.extraction_agent.domain.models.extraction_stages import (
    CrossPageCompletionRequest,
    DrawingPageInput,
)
from src.agent.extraction_agent.graphs.document_extraction.cross_page import (
    _apply_cross_page_completion,
    _build_cross_page_tasks_node,
    _resolve_cross_page_node,
)
from src.agent.extraction_agent.infrastructure.abb_vlm_stages import AbbVlmExtractionStageAdapter
from src.agent.extraction_agent.infrastructure.zh_gantry_reel_vlm_stages import ZhGantryReelVlmAdapter
from src.agent.extraction_agent.infrastructure.zh_vlm_stages import ZhVlmExtractionStageAdapter
from src.agent.extraction_agent.profiles.zh.completion_context import (
    TargetOnlyCompletionContext,
    target_only_context,
)
from src.agent.extraction_agent.profiles.zh.policy import ZhExtractionPolicy
from src.config import AgentSettings
from src.harness.model_gateway import FakeModelGateway
from src.profiles import ProfileRegistry

ROOT = Path(__file__).resolve().parents[4]


def _binding(key="zh"):
    registry = ProfileRegistry(
        profile_root=ROOT / "services/agent/src/agent/extraction_agent/profiles",
        workspace_root=ROOT,
        allow_legacy_references=True,
    )
    registry.load_all()
    return registry.bind(key, allow_experimental=True)


def _request(tmp_path, *, key="zh"):
    return CrossPageCompletionRequest(
        run_id="offline",
        project_id="offline",
        profile=_binding(key),
        task_id="one",
        source_page=DrawingPageInput(pdf_page_number=60, image_path=tmp_path / "missing-source.png"),
        target_page=DrawingPageInput(pdf_page_number=403, image_path=tmp_path / "target.png"),
        task_context=json.dumps(
            {
                "task_id": "one",
                "source_pdf_page": 60,
                "target_pdf_page": 403,
                "source_page_context": {
                    "pdf_page_number": 60,
                    "drawing_function": "003.C",
                    "drawing_page_number": 1,
                    "object_location": "+01F11.1",
                },
                "source_record": {
                    "start_terminal": "XA:8",
                    "start_device": "+01F10",
                    "start_terminal_coordinates": {"x": 0.12345, "y": 0.23456, "pdf_page_number": 60},
                    "direction_basis": "放线段从XA:8离开本页",
                    "signal_name": "FC11_L1",
                    "current": "160A",
                    "current_basis": "Ie",
                    "current_source_text": "Ie:(0.7-1)*160A",
                },
                "line_number": "003C0101",
                "references": [{"raw": "=080.C+01F12.1/10.1 / +01F12.1-FC11_L1"}],
            }
        ),
    )


def test_mode_is_profile_scoped_and_old_rules_default_to_two_images(tmp_path):
    settings = AgentSettings(default_model="fake")
    gateway = FakeModelGateway([])
    request = _request(tmp_path)
    assert ZhVlmExtractionStageAdapter(settings, gateway).completion_images(request) == [request.target_page]
    for key, adapter in [("abb", AbbVlmExtractionStageAdapter), ("zh_gantry_reel", ZhGantryReelVlmAdapter)]:
        other = _request(tmp_path, key=key)
        assert other.profile.rules.extraction.cross_page_input_mode == "target_only"
        assert adapter(settings, gateway).completion_images(other) == [other.target_page]
        legacy_extraction = other.profile.rules.extraction.model_copy(
            update={"cross_page_input_mode": "source_and_target"}
        )
        legacy = other.model_copy(update={"profile": other.profile.model_copy(update={
            "rules": other.profile.rules.model_copy(update={"extraction": legacy_extraction}),
        })})
        assert adapter(settings, gateway).completion_images(legacy) == [
            legacy.source_page, legacy.target_page,
        ]
    old_rules = request.profile.rules.extraction.model_dump(exclude={"cross_page_input_mode"})
    assert (
        type(request.profile.rules.extraction).model_validate(old_rules).cross_page_input_mode
        == "source_and_target"
    )


def test_compact_context_retains_source_identity_without_confusing_object_and_device(tmp_path):
    context = target_only_context(_request(tmp_path).model_copy(update={"source_page": None}))
    assert context.source_page.drawing_page_number == 1
    assert context.source_page.pdf_page_number == 60
    assert context.source_page.object_location == "+01F11.1"
    assert context.source_component.device == "+01F10"
    assert context.context_version == 2
    assert "start" not in context.model_dump()
    assert "XA:8" not in context.model_dump_json()
    assert "0.12345" not in context.model_dump_json()
    assert context.signal_name == "FC11_L1"
    assert context.line_number == "003C0101"
    assert context.target_page.pdf_page_number == 403
    assert "source_record" not in context.model_dump()


def test_target_only_model_request_never_reads_missing_source_and_preserves_current(tmp_path):
    async def check():
        import pymupdf

        request = _request(tmp_path)
        pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 32, 16), False)
        pix.clear_with(255)
        request.target_page.image_path.write_bytes(pix.tobytes("png"))
        gateway = FakeModelGateway(
            [
                json.dumps(
                    {
                        "end": {"terminal": "XD10:1"},
                        "status": "resolved",
                        "source_note": "003C0101及来源回指唯一匹配，沿线到XD10:1",
                        "current": "999A",
                        "current_basis": "Ir",
                        "current_source_text": "Ir=999A",
                    }
                )
            ]
        )
        result = await ZhVlmExtractionStageAdapter(
            AgentSettings(default_model="fake"), gateway
        ).resolve_cross_page(request)
        content = gateway.calls[0].messages[-1]["content"]
        assert sum(item.get("type") == "image_url" for item in content) == 1
        assert '"signal_name":"FC11_L1"' in content[0]["text"]
        assert '"drawing_page_number":1' in content[0]["text"]
        assert "XA:8" not in content[0]["text"]
        assert "0.12345" not in content[0]["text"]
        assert result.current is None and result.current_basis is None and result.current_source_text is None
        assert result.end.terminal == "XD10:1"

    asyncio.run(check())


def test_graph_passes_scan_facts_and_skips_loading_source_payload(tmp_path):
    async def check():
        calls = []

        async def resolve(target_image, *, source_image=None, task_context=""):
            calls.append(json.loads(task_context))
            assert source_image is None
            return {"end": None, "status": "needs_review", "needs_review": True}

        def payload(path):
            assert path == "target.png"
            return path

        runtime = SimpleNamespace(
            policy=ZhExtractionPolicy(),
            settings=SimpleNamespace(terminal_strip_mapping={}),
            extraction_client=SimpleNamespace(completion_uses_source_image=False, resolve_cross_page=resolve),
            output_mode="library",
            durable=None,
            validation_warnings=[],
            extraction_errors={},
            payload_for=payload,
            log=lambda message: None,
        )
        state = {
            "output_path": str(tmp_path),
            "pages": [
                {
                    "page_number": 60,
                    "image_path": "missing-source.png",
                    "function": "003.C",
                    "internal_page": 1,
                    "object_loc": "+01F11.1",
                },
                {"page_number": 403, "image_path": "target.png", "function": "080.C", "internal_page": 10},
            ],
            "drawing_index": {"page_lookup": {"080.C:10": 403}},
            "wire_units": {
                "u": {
                    "unit_id": "u",
                    "source_pages": [60],
                    "connections": [
                        {
                            "connection_id": "one",
                            "origin_pdf_page": 60,
                            "line_number": "003C0101",
                            "signal_name": "FC11_L1",
                            "start": {"terminal": "XA:8"},
                            "references": [{"raw": "=080.C+01F12.1/10.1"}],
                        }
                    ],
                }
            },
        }
        state.update(_build_cross_page_tasks_node(state, runtime))
        result = await _resolve_cross_page_node(state, runtime, use_checkpoint=False)
        assert calls[0]["source_page_context"]["drawing_page_number"] == 1
        assert calls[0]["source_record"]["signal_name"] == "FC11_L1"
        row = result["wire_units"]["u"]["connections"][0]
        assert row["start"]["terminal"] == "XA:8" and row["end"] is None
        assert row["status"] == "needs_review"

    asyncio.run(check())


def test_target_only_examples_match_contract_and_frozen_coordinates():
    assets = _binding().resource("wiring_examples")
    manifest = json.loads((assets / "manifest.json").read_text(encoding="utf-8"))
    for case in manifest["stage3_cases"]:
        assert [image["role"] for image in case["images"]] == ["target_page"]
        context = TargetOnlyCompletionContext.model_validate_json(
            (assets / case["input"]).read_text(encoding="utf-8")
        )
        result = json.loads((assets / case["expected"]).read_text(encoding="utf-8"))
        start = {
            "terminal": "XD3:17",
            "terminal_coordinates": {
                "x": 0.123,
                "y": 0.234,
                "pdf_page_number": context.source_page.pdf_page_number or 1,
            },
        }
        units = {
            "u": {
                "connections": [
                    {"connection_id": "one", "start": start.copy(), "line_number": context.line_number}
                ]
            }
        }
        _apply_cross_page_completion(
            units,
            {
                "unit_id": "u",
                "connection_id": "one",
                "source_pdf_page": context.source_page.pdf_page_number,
                "target_pdf_page": context.target_page.pdf_page_number,
            },
            result,
        )
        row = units["u"]["connections"][0]
        assert row["start"]["terminal"] == start["terminal"]
        assert row["start"]["terminal_coordinates"] == start["terminal_coordinates"]
        assert row["line_number"] == context.line_number
