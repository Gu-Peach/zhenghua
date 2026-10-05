from __future__ import annotations

import asyncio
from pathlib import Path

from backend.app.agents.segment_decider import VLMSegmentDecider
from backend.app.agents.state import PageMeta
from backend.app.agents.wiring_graph import (
    GraphRuntime,
    _segment_node,
    run_wiring_agent,
)
from backend.app.core.config import Settings, default_prompt_path, default_segment_prompt_path
from backend.app.schemas.wire import WireRecord
from backend.app.services.vlm_client import ImagePayload


def _settings(tmp_path: Path, *, max_segment_pages: int = 20) -> Settings:
    return Settings(
        api_key="key",
        base_url="http://example.test/v1",
        chat_completions_endpoint=None,
        model="vlm",
        timeout_seconds=1,
        max_pdf_pages=20,
        concurrency=2,
        image_batch_size=4,
        use_response_format=False,
        prompt_path=default_prompt_path(),
        library_root=tmp_path,
        segment_prompt_path=default_segment_prompt_path(),
        segment_concurrency=3,
        segment_retry_count=1,
        max_segment_pages=max_segment_pages,
    )


def _decision(a: int, b: int, *, merge: bool = True) -> dict:
    return {
        "a": a,
        "b": b,
        "merge": merge,
        "project_no_a": "1002001708",
        "project_no_b": "1002001708",
        "drawing_prefix_a": "DQ1002001708",
        "drawing_prefix_b": "DQ1002001708",
        "reason": "项目号与图号前缀均一致" if merge else "项目号或前缀不同",
        "confidence": 0.95,
        "needs_review": False,
    }


def test_vlm_segment_decider_retries_schema_failure(tmp_path: Path) -> None:
    class FakeClient:
        def __init__(self) -> None:
            self.calls = 0

        async def complete(self, **_kwargs: object) -> str:
            self.calls += 1
            if self.calls == 1:
                return "not-json"
            return (
                '{"merge":true,"project_no_a":"P","project_no_b":"P",'
                '"drawing_prefix_a":"D","drawing_prefix_b":"D",'
                '"reason":"both fields match","confidence":0.8,"needs_review":false}'
            )

    first = tmp_path / "page-1.png"
    second = tmp_path / "page-2.png"
    first.write_bytes(b"a")
    second.write_bytes(b"b")
    payloads = {
        str(first): ImagePayload("a", "image/png", b"a"),
        str(second): ImagePayload("b", "image/png", b"b"),
    }
    client = FakeClient()
    decider = VLMSegmentDecider(
        client=client,  # type: ignore[arg-type]
        prompt="prompt",
        image_loader=lambda path: payloads[path],
        retry_count=1,
    )

    result = asyncio.run(
        decider.decide(
            {"page_number": 1, "image_path": str(first)},
            {"page_number": 2, "image_path": str(second)},
        )
    )

    assert client.calls == 2
    assert result["merge"] is True
    assert result["a"] == 1 and result["b"] == 2


def test_segment_node_uses_union_find_and_excludes_blank_pages(tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    class FakeExtractor:
        async def extract_images(self, _images: object) -> list[WireRecord]:
            return []

    class FakeDecider:
        def decide(self, page_a: PageMeta, page_b: PageMeta) -> dict:
            return _decision(page_a["page_number"], page_b["page_number"])

    runtime = GraphRuntime(
        settings=settings,
        extraction_client=FakeExtractor(),  # type: ignore[arg-type]
        segment_decider=FakeDecider(),
        segment_prompt="prompt",
        output_mode="single_xlsx",
    )
    pages: list[PageMeta] = []
    for number in range(1, 5):
        path = (tmp_path / f"page-{number}.png").resolve()
        path.write_bytes(str(number).encode())
        payload = ImagePayload(
            path.name,
            "image/png",
            str(number).encode(),
            blank=number == 3,
        )
        runtime.payload_by_path[str(path)] = payload  # type: ignore[index]
        pages.append({"page_number": number, "image_path": str(path)})

    result = asyncio.run(_segment_node({
        "pdf_path": "input.pdf",
        "pages": pages,
        "merge_decisions": [],
        "segments": [],
        "wiring_records": {},
        "output_path": str(tmp_path / "result.xlsx"),
    }, runtime))

    assert [decision["a"] for decision in result["merge_decisions"]] == [1, 2, 3]
    assert result["segments"] == [[1, 2], [4]]
    assert result["merge_decisions"][1]["merge"] is False
    assert result["merge_decisions"][1]["needs_review"] is True


def test_run_wiring_agent_writes_single_xlsx_and_diagnostics(tmp_path: Path) -> None:
    class FakeDecider:
        def decide(self, page_a: PageMeta, page_b: PageMeta) -> dict:
            return _decision(page_a["page_number"], page_b["page_number"])

    class FakeExtractor:
        async def extract_images(self, images: list[ImagePayload]) -> list[WireRecord]:
            return [
                WireRecord(
                    line_number="1",
                    start_device="-XD3",
                    start_terminal="3",
                    source_image=images[0].name,
                )
            ]

    images = [
        ImagePayload("page-1", "image/png", b"one"),
        ImagePayload("page-2", "image/png", b"two"),
    ]
    output_path = tmp_path / "wiring-table.xlsx"
    result = asyncio.run(
        run_wiring_agent(
            pdf_path=tmp_path / "source.pdf",
            output_path=output_path,
            settings=_settings(tmp_path),
            extraction_prompt="extract",
            segment_prompt="segment",
            preloaded_images=images,
            output_mode="single_xlsx",
            segment_decider=FakeDecider(),
            extraction_client=FakeExtractor(),  # type: ignore[arg-type]
        )
    )

    assert result.state["segments"] == [[1, 2]]
    assert result.state["wiring_records"]["wire-table-001"][0].start_terminal == "XD3:3"
    assert output_path.is_file()
    assert (tmp_path / "wiring-table.agent" / "merge_decisions.json").is_file()
    assert (tmp_path / "wiring-table.agent" / "segments.json").is_file()
