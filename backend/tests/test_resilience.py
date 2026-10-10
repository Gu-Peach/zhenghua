from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from backend.app.agents.state import PageMeta
from backend.app.agents.wiring_graph import run_wiring_agent
from backend.app.core.config import Settings, default_prompt_path, default_segment_prompt_path
from backend.app.schemas.wire import WireRecord
from backend.app.services.vlm_client import ImagePayload, VLMClient


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        api_key="key",
        base_url="http://example.test/v1",
        chat_completions_endpoint=None,
        model="vlm",
        timeout_seconds=1,
        max_pdf_pages=20,
        concurrency=1,
        image_batch_size=4,
        use_response_format=False,
        prompt_path=default_prompt_path(),
        retry_count=2,
        retry_backoff_seconds=0,
        retry_max_backoff_seconds=0,
        library_root=tmp_path,
        segment_prompt_path=default_segment_prompt_path(),
        segment_retry_count=0,
        max_segment_pages=20,
    )


def _decision(a: int, b: int) -> dict:
    return {
        "a": a,
        "b": b,
        "merge": False,
        "project_no_a": "P",
        "project_no_b": "P",
        "drawing_prefix_a": "D1",
        "drawing_prefix_b": "D2",
        "reason": "different drawing prefix",
        "confidence": 0.9,
        "needs_review": False,
    }


def test_vlm_client_retries_transport_failure(monkeypatch, tmp_path: Path) -> None:
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "[]"}}]}

    class Client:
        calls = 0

        def __init__(self, **_kwargs: object) -> None:
            pass

        async def __aenter__(self) -> "Client":
            return self

        async def __aexit__(self, *_args: object) -> None:
            return None

        async def post(self, *_args: object, **_kwargs: object) -> Response:
            Client.calls += 1
            if Client.calls == 1:
                raise httpx.ReadError("server disconnected")
            return Response()

    monkeypatch.setattr("backend.app.services.vlm_client.httpx.AsyncClient", Client)
    client = VLMClient(_settings(tmp_path), "prompt", few_shot_examples=[])

    content = asyncio.run(
        client.complete(
            images=[ImagePayload("page.png", "image/png", b"image")],
            user_text="Return JSON.",
        )
    )

    assert content == "[]"
    assert Client.calls == 2


def test_extraction_checkpoint_skips_completed_batches_on_resume(tmp_path: Path) -> None:
    class Decider:
        def decide(self, page_a: PageMeta, page_b: PageMeta) -> dict:
            return _decision(page_a["page_number"], page_b["page_number"])

    class Extractor:
        def __init__(self, fail_on_call: int | None = None) -> None:
            self.calls = 0
            self.fail_on_call = fail_on_call

        async def extract_images(self, images: list[ImagePayload], **_kwargs: object) -> list[WireRecord]:
            self.calls += 1
            if self.calls == self.fail_on_call:
                raise RuntimeError("simulated provider disconnect")
            return [
                WireRecord(
                    line_number=str(self.calls),
                    start_device="-XD3",
                    start_terminal="1",
                    end_device="-A1",
                    end_terminal="2",
                    source_image=images[0].name,
                )
            ]

    images = [
        ImagePayload("input-1.png", "image/png", b"one"),
        ImagePayload("input-2.png", "image/png", b"two"),
    ]
    output_path = tmp_path / "wiring-table.xlsx"
    first = Extractor(fail_on_call=2)
    first_result = asyncio.run(
        run_wiring_agent(
            pdf_path=tmp_path / "source.pdf",
            output_path=output_path,
            settings=_settings(tmp_path),
            extraction_prompt="extract",
            segment_prompt="segment",
            preloaded_images=images,
            output_mode="single_xlsx",
            segment_decider=Decider(),
            extraction_client=first,  # type: ignore[arg-type]
        )
    )

    checkpoint = tmp_path / "wiring-table.agent" / "extraction-checkpoint.json"
    assert first.calls == 2
    assert checkpoint.is_file()
    assert first_result.extraction_errors

    second = Extractor()
    second_result = asyncio.run(
        run_wiring_agent(
            pdf_path=tmp_path / "source.pdf",
            output_path=output_path,
            settings=_settings(tmp_path),
            extraction_prompt="extract",
            segment_prompt="segment",
            preloaded_images=images,
            output_mode="single_xlsx",
            segment_decider=Decider(),
            extraction_client=second,  # type: ignore[arg-type]
        )
    )

    assert second.calls == 1
    assert len(second_result.state["wiring_records"]) == 2
    assert all(second_result.state["wiring_records"].values())
