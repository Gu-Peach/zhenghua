from __future__ import annotations

import asyncio
import json
from pathlib import Path

from backend.app.agents.wiring_graph import run_wiring_agent, run_wiring_agent_stages_2_3
from backend.app.core.config import Settings, default_prompt_path
from backend.app.services.vlm_client import ImagePayload
from backend.app.services.vlm_client import VLMClient


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        api_key="key",
        base_url="http://example.test/v1",
        chat_completions_endpoint=None,
        model="vlm",
        timeout_seconds=1,
        max_pdf_pages=20,
        concurrency=1,
        image_batch_size=1,
        use_response_format=False,
        prompt_path=default_prompt_path(),
        retry_count=0,
        retry_backoff_seconds=0,
        retry_max_backoff_seconds=0,
        library_root=tmp_path,
        output_mode="library",
        keep_temp_images=True,
    )


def test_page_scan_groups_connections_and_keeps_cross_page_reference_in_same_stage(tmp_path: Path) -> None:
    class FakePageAgent:
        scan_calls = 0

        async def scan_page(self, image: ImagePayload, *, related_images=(), page_context: str = "") -> dict:
            self.scan_calls += 1
            if image.page_number == 2:
                return {"pdf_page_number": 2, "units": []}
            return {
                "pdf_page_number": 1,
                "units": [
                    {
                        "wire_number": "0272",
                        "model": "CJV/DA",
                        "connections": [
                            {
                                "core_number": 1,
                                "line_number": "003G0121",
                                "start": {"location": "+01F11.3", "device": "-XD3", "terminal": "3"},
                                    "end": {"location": "+01F26", "device": "-AIM1", "terminal": "X3:3"},
                                "references": [
                                    {
                                        "raw": "=.C+01F26/1.3",
                                        "target_function": "003.C",
                                        "target_drawing_page": 1,
                                        "target_pdf_page": 2,
                                    }
                                ],
                                    "status": "complete",
                            },
                            {
                                "core_number": 2,
                                "line_number": "003G0121",
                                "start": {"location": "+01F11.3", "device": "-XD3", "terminal": "30"},
                                "end": {"device": "-A1", "terminal": "2"},
                                "references": [],
                                "status": "complete",
                            },
                        ],
                    }
                ],
            }

    images = [
        ImagePayload("drawing.pdf#page=1", "image/png", b"one", page_number=1),
        ImagePayload("drawing.pdf#page=2", "image/png", b"two", page_number=2),
    ]
    client = FakePageAgent()
    output = tmp_path / "library"
    result = asyncio.run(
        run_wiring_agent(
            pdf_path=tmp_path / "drawing.pdf",
            output_path=output,
            settings=_settings(tmp_path),
            extraction_prompt="unused",
            segment_prompt="unused",
            preloaded_images=images,
            output_mode="library",
            extraction_client=client,  # type: ignore[arg-type]
        )
    )

    assert client.scan_calls == 2
    assert len(result.state["wire_units"]) == 1
    unit_id = next(iter(result.state["wire_units"]))
    records = result.state["wiring_records"][unit_id]
    assert len(records) == 2
    assert records[0].source_pages == [1, 2]
    assert records[0].end_terminal == "X3:3"
    assert records[0].status == "complete"
    assert records[1].start_terminal == "XD3:30"
    assert result.state["segments"] == [[1], [2]]
    assert (output / "agent" / "page-scan-checkpoint.json").is_file()
    assert (output / "agent" / "wire-units-checkpoint.json").is_file()
    assert (output / "groups" / unit_id / "table.json").is_file()
    table = json.loads((output / "groups" / unit_id / "table.json").read_text(encoding="utf-8"))
    assert len(table["headers"]) == 11


def test_page_scan_parser_keeps_multiple_same_line_connections() -> None:
    from backend.app.services.vlm_client import parse_page_scan_result

    result = parse_page_scan_result(
        '{"units":[{"wire_number":"0272","connections":['
        '{"core_number":1,"line_number":"003G0121","start":{"device":"-XD3","terminal":"3"}},'
        '{"core_number":2,"line_number":"003G0121","start":{"device":"-XD3","terminal":"30"}}]}]}'
    )

    assert len(result.units) == 1
    assert len(result.units[0].connections) == 2
    assert [connection.line_number for connection in result.units[0].connections] == ["003G0121", "003G0121"]


def test_cross_page_agent_completes_only_rows_left_open_by_page_scan(tmp_path: Path) -> None:
    class FakeThreeStageAgent:
        scan_calls = 0
        resolve_calls = 0

        async def scan_page(self, image: ImagePayload, *, page_context: str = "") -> dict:
            self.scan_calls += 1
            if image.page_number == 2:
                return {"pdf_page_number": 2, "units": []}
            return {
                "pdf_page_number": 1,
                "units": [{
                    "wire_number": "0272",
                    "connections": [{
                        "core_number": 1,
                        "line_number": "003G0121",
                        "start": {"location": "+01F11.3", "device": "-XD3", "terminal": "3"},
                        "end": None,
                        "references": [{
                            "raw": "=.C+01F26/1.3",
                            "target_function": "003.C",
                            "target_drawing_page": 1,
                            "target_column": 3,
                            "target_pdf_page": 2,
                        }],
                        "status": "needs_reference",
                    }],
                }],
            }

        async def resolve_cross_page(self, source_image, target_images, *, task_context: str = "") -> dict:
            self.resolve_calls += 1
            assert source_image.page_number == 1
            assert [image.page_number for image in target_images] == [2]
            return {
                "status": "resolved",
                "needs_review": False,
                "end": {"location": "+01F26", "device": "-AIM1", "terminal": "X3:3"},
                "intermediate_points": [],
                "confidence": 0.95,
            }

    images = [
        ImagePayload("drawing.pdf#page=1", "image/png", b"one", page_number=1),
        ImagePayload("drawing.pdf#page=2", "image/png", b"two", page_number=2),
    ]
    client = FakeThreeStageAgent()
    output = tmp_path / "library"
    result = asyncio.run(
        run_wiring_agent(
            pdf_path=tmp_path / "drawing.pdf",
            output_path=output,
            settings=_settings(tmp_path),
            extraction_prompt="unused",
            segment_prompt="unused",
            preloaded_images=images,
            output_mode="library",
            extraction_client=client,  # type: ignore[arg-type]
        )
    )

    assert client.scan_calls == 2
    assert client.resolve_calls == 1
    unit_id = next(iter(result.state["wire_units"]))
    record = result.state["wiring_records"][unit_id][0]
    assert record.end_terminal == "X3:3"
    assert record.source_pages == [1, 2]
    stage2_table = json.loads((output / "agent" / "stage2-table.json").read_text(encoding="utf-8"))
    assert stage2_table["rows_by_unit"][unit_id][0][8] is None
    assert len(json.loads((output / "agent" / "cross-page-tasks.json").read_text(encoding="utf-8"))) == 1


def test_page_agent_resume_reuses_classified_image_and_scan_checkpoint(tmp_path: Path) -> None:
    class FakePageAgent:
        def __init__(self) -> None:
            self.classify_calls = 0
            self.scan_calls = 0

        async def classify_page(self, image: ImagePayload, *, context_text: str = "") -> dict:
            self.classify_calls += 1
            return {
                "plant_function": "001",
                "page_number": 1,
                "blank": False,
                "non_wiring": False,
                "confidence": 0.99,
                "needs_review": False,
                "reason": "test",
            }

        async def scan_page(self, image: ImagePayload, *, page_context: str = "") -> dict:
            self.scan_calls += 1
            return {"pdf_page_number": 1, "units": []}

    images = [ImagePayload("drawing.pdf#page=1", "image/png", b"one", page_number=1)]
    output = tmp_path / "library"
    first = FakePageAgent()
    asyncio.run(
        run_wiring_agent(
            pdf_path=tmp_path / "drawing.pdf",
            output_path=output,
            settings=_settings(tmp_path),
            extraction_prompt="unused",
            segment_prompt="unused",
            preloaded_images=images,
            output_mode="library",
            extraction_client=first,  # type: ignore[arg-type]
        )
    )

    second = FakePageAgent()
    asyncio.run(
        run_wiring_agent(
            pdf_path=tmp_path / "drawing.pdf",
            output_path=output,
            settings=_settings(tmp_path),
            extraction_prompt="unused",
            segment_prompt="unused",
            preloaded_images=images,
            output_mode="library",
            extraction_client=second,  # type: ignore[arg-type]
        )
    )

    assert first.classify_calls == 1
    assert first.scan_calls == 1
    assert second.classify_calls == 0
    assert second.scan_calls == 0
    assert [path.name for path in (output / "pages" / "001").glob("*.png")] == ["1.png"]


def test_stages_2_3_scans_only_selected_source_pages(tmp_path: Path) -> None:
    class FakePageAgent:
        def __init__(self) -> None:
            self.scan_pages: list[int] = []

        async def scan_page(self, image: ImagePayload, *, page_context: str = "") -> dict:
            self.scan_pages.append(int(image.page_number or 0))
            return {"pdf_page_number": image.page_number, "units": []}

    image1 = tmp_path / "001" / "1.png"
    image2 = tmp_path / "002.C" / "1.png"
    image1.parent.mkdir(parents=True)
    image2.parent.mkdir(parents=True)
    image1.write_bytes(b"one")
    image2.write_bytes(b"two")
    pages = [
        {"page_number": 1, "image_path": str(image1), "function": "001", "internal_page": 1},
        {"page_number": 2, "image_path": str(image2), "function": "002.C", "internal_page": 1},
    ]
    client = FakePageAgent()
    result = asyncio.run(
        run_wiring_agent_stages_2_3(
            pages=pages,  # type: ignore[arg-type]
            source_page_numbers=[2],
            drawing_index={"pages": [], "page_lookup": {}, "references": []},
            output_path=tmp_path / "result",
            settings=_settings(tmp_path),
            extraction_prompt="unused",
            extraction_client=client,  # type: ignore[arg-type]
        )
    )

    assert client.scan_pages == [2]
    assert result.state["processed_pages"] == [2]
    assert set(result.state["page_scan_results"]) == {"2"}


def test_explicit_current_is_preserved_in_final_table_row() -> None:
    from backend.app.agents.wiring_graph import _record_to_table_row
    from backend.app.schemas.wire import WireRecord

    row = _record_to_table_row(
        WireRecord(
            line_number="005C4201",
            current="2A",
            terminal_strip="X3",
            start_device="-XD3",
            start_terminal="3",
            end_device="-A1",
            end_terminal="L",
        )
    )

    assert row[9] == "2A"


def test_breaker_current_requires_basis_and_source_evidence() -> None:
    from backend.app.agents.wiring_graph import _validated_breaker_current

    assert _validated_breaker_current("400A", "Ir", "Ir=400A") == "400A"
    assert _validated_breaker_current("125 A", "Ir", "Ir = 125A") == "125A"
    assert _validated_breaker_current("400A", None, "Ir=400A") is None
    assert _validated_breaker_current("400A", "Ir", None) is None
    assert _validated_breaker_current("300mA", "IΔ", "IΔ=300mA") is None
    assert _validated_breaker_current("30kA", "Icu", "Icu=30kA") is None
    assert _validated_breaker_current("0.7-1*400A", "Ie", "Ie:(0.7-1)*400A") is None


def test_allowed_terminal_endpoint_is_oriented_as_start() -> None:
    from backend.app.agents.wiring_graph import _orient_allowed_start_terminal
    from backend.app.schemas.wire import Endpoint, WireConnection

    connection = WireConnection(
        line_number="002C0301",
        start=Endpoint(device="-K2", terminal="X3:23"),
        end=Endpoint(device="-XD21", terminal="XD21:7"),
    )
    oriented, reversed_direction = _orient_allowed_start_terminal(connection)

    assert oriented is not None
    assert reversed_direction is True
    assert oriented.start.device == "-XD21"
    assert oriented.start.terminal == "XD21:7"
    assert oriented.end is not None and oriented.end.device == "-K2"


def test_connection_without_allowed_start_terminal_is_rejected() -> None:
    from backend.app.agents.wiring_graph import _orient_allowed_start_terminal
    from backend.app.schemas.wire import Endpoint, WireConnection

    connection = WireConnection(
        line_number="002C0201",
        start=Endpoint(device="-TA1", terminal="U1"),
        end=Endpoint(device="-K2", terminal="L1"),
    )

    assert _orient_allowed_start_terminal(connection) == (None, False)


def test_table_ignores_terminal_strip_category_for_current_contract() -> None:
    from backend.app.agents.wiring_graph import _record_to_table_row
    from backend.app.schemas.wire import WireRecord

    row = _record_to_table_row(
        WireRecord(
            terminal_strip="X3",
            start_device="-XD3",
            start_terminal="3",
            end_device="-A1",
            end_terminal="2",
        )
    )

    assert row[2] is None


def test_final_table_records_sort_by_drawing_page() -> None:
    from backend.app.agents.wiring_graph import _table_record_page_sort_key
    from backend.app.schemas.wire import WireRecord

    records = [
        WireRecord(drawing_function="002.C", drawing_page_number=21, source_pages=[54]),
        WireRecord(drawing_function="002.C", drawing_page_number=3, source_pages=[50]),
        WireRecord(drawing_function="002.C", drawing_page_number=11, source_pages=[53]),
    ]

    ordered = sorted(records, key=_table_record_page_sort_key)
    assert [record.drawing_page_number for record in ordered] == [3, 11, 21]


def test_page_classification_few_shot_and_table_contracts() -> None:
    from backend.app.core.config import load_settings
    from backend.app.services.prompt_loader import (
        load_page_classification_few_shot_examples,
        load_page_scan_few_shot_examples,
    )

    settings = load_settings(model="test-model")
    assert len(load_page_classification_few_shot_examples(settings.classification_few_shot_examples_dir)) == 2
    assert len(load_page_scan_few_shot_examples(settings.page_scan_few_shot_examples_dir)) == 4


def test_relative_reference_inherits_function_prefix() -> None:
    from backend.app.services.drawing_index import parse_drawing_page, parse_references

    page = parse_drawing_page(10, "Plant Function: =005.C\nPage Number: 42\n=.M+01F13/28.1")
    references = parse_references(page)
    assert references[0].target_function == "005.M"
    assert references[0].target_internal_page == 28
    assert references[0].target_column == 1


def test_vlm_page_scan_retries_schema_and_sends_real_image_few_shot(tmp_path: Path) -> None:
    client = VLMClient(_settings(tmp_path), "legacy prompt", few_shot_examples=[])
    calls: list[dict] = []

    async def fake_complete(**kwargs):
        calls.append(kwargs)
        if len(calls) == 1:
            return "not-json"
        return '{"pdf_page_number":1,"units":[]}'

    client.complete = fake_complete  # type: ignore[method-assign]
    result = asyncio.run(client.scan_page(ImagePayload("page.png", "image/png", b"page", page_number=1)))

    assert result.pdf_page_number == 1
    assert len(calls) == 2
    prefix = calls[0]["prefix_messages"]
    assert any(
        part.get("type") == "image_url"
        for message in prefix
        for part in message.get("content", [])
        if isinstance(part, dict)
    )


def test_vlm_page_scan_sends_indexed_target_images_in_same_call(tmp_path: Path) -> None:
    client = VLMClient(_settings(tmp_path), "legacy prompt", few_shot_examples=[])
    calls: list[dict] = []

    async def fake_complete(**kwargs):
        calls.append(kwargs)
        return '{"pdf_page_number":1,"units":[]}'

    client.complete = fake_complete  # type: ignore[method-assign]
    source = ImagePayload("source.png", "image/png", b"source", page_number=1)
    target = ImagePayload("target.png", "image/png", b"target", page_number=9)
    asyncio.run(client.scan_page(source, related_images=[target]))

    assert len(calls) == 1
    assert len(calls[0]["images"]) == 2
    assert "current" in calls[0]["user_text"]
    assert "target.png" in calls[0]["user_text"]


def test_vlm_cross_page_completion_sends_source_target_and_image_few_shot(tmp_path: Path) -> None:
    client = VLMClient(_settings(tmp_path), "legacy prompt", few_shot_examples=[])
    calls: list[dict] = []

    async def fake_complete(**kwargs):
        calls.append(kwargs)
        return (
            '{"task_id":"task-1","end":{"device":"-AIM1","terminal":"X3:3"},'
            '"intermediate_points":[],"status":"resolved","needs_review":false,"confidence":0.95}'
        )

    client.complete = fake_complete  # type: ignore[method-assign]
    source = ImagePayload("source.png", "image/png", b"source", page_number=1)
    target = ImagePayload("target.png", "image/png", b"target", page_number=9)
    result = asyncio.run(client.resolve_cross_page(source, [target], task_context='{"line_number":"003G0121"}'))

    assert result.end is not None and result.end.terminal == "X3:3"
    assert len(calls) == 1
    assert [image.name for image in calls[0]["images"]] == ["source.png", "target.png"]
    assert any(
        part.get("type") == "image_url"
        for message in calls[0]["prefix_messages"]
        for part in message.get("content", [])
        if isinstance(part, dict)
    )


def test_upload_pipeline_adapts_new_units_to_library_groups(tmp_path: Path, monkeypatch) -> None:
    from io import BytesIO
    from fastapi import UploadFile
    from backend.app.services.pdf_pipeline import process_pdf_upload

    class FakeClient:
        def __init__(self, settings, prompt):
            self.settings = settings
            self.prompt = prompt

        async def scan_page(self, image, *, page_context=""):
            if image.page_number == 2:
                return {"pdf_page_number": 2, "units": []}
            return {
                "units": [{
                    "wire_number": "0272",
                    "connections": [{
                        "core_number": 1,
                        "line_number": "003G0121",
                        "start": {"device": "-XD3", "terminal": "3"},
                        "end": {"device": "-A1", "terminal": "2"},
                        "status": "complete",
                    }],
                }]
            }

    monkeypatch.setenv("VLM_MODEL", "test-model")
    monkeypatch.setenv("VLM_API_KEY", "key")
    monkeypatch.setenv("VLM_LIBRARY_ROOT", str(tmp_path))
    monkeypatch.setenv("SUPABASE_ENABLED", "false")
    monkeypatch.setattr("backend.app.services.pdf_pipeline.VLMClient", FakeClient)
    monkeypatch.setattr(
        "backend.app.agents.wiring_graph.path_to_image_payloads",
        lambda path, max_pdf_pages, pdf_render_scale=2.0: [
            ImagePayload(f"{path.name}#page=1", "image/png", b"one", page_number=1),
            ImagePayload(f"{path.name}#page=2", "image/png", b"two", page_number=2),
        ],
    )

    response = asyncio.run(
        process_pdf_upload(
            file=UploadFile(filename="demo.pdf", file=BytesIO(b"pdf"), headers={"content-type": "application/pdf"})
        )
    )

    assert response.job.status == "success"
    assert response.job.group_count == 1
    assert response.job.record_count == 1
    unit_id = response.job.groups[0].group_id
    job_dir = tmp_path / response.job.job_id
    assert (job_dir / "groups" / unit_id / "records.json").is_file()
