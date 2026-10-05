from __future__ import annotations

import asyncio

from fastapi import HTTPException, UploadFile

from ..core.config import ConfigError, load_settings
from ..schemas.wire import WireRecord
from .file_inputs import InputFileError, upload_to_image_payloads
from .prompt_loader import load_prompt
from .vlm_client import ImagePayload, VLMClient, VLMError


async def extract_from_uploads(
    *,
    files: list[UploadFile],
    model: str | None,
    base_url: str | None,
    api_key: str | None,
    prompt: str | None,
    max_pdf_pages: int | None,
) -> tuple[list[WireRecord], list[str]]:
    if not files:
        raise HTTPException(status_code=400, detail="At least one drawing image is required.")

    try:
        settings = load_settings(api_key=api_key, base_url=base_url, model=model, max_pdf_pages=max_pdf_pages)
        system_prompt = load_prompt(settings.prompt_path, override=prompt)
    except (ConfigError, OSError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        image_payloads: list[ImagePayload] = []
        for upload in files:
            image_payloads.extend(
                await upload_to_image_payloads(
                    upload,
                    settings.max_pdf_pages,
                    pdf_render_scale=settings.pdf_render_scale,
                )
            )
    except InputFileError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    client = VLMClient(settings, system_prompt)
    records = await _extract_batches(
        client,
        image_payloads,
        concurrency=settings.concurrency,
        batch_size=settings.image_batch_size,
    )
    return records, [image.name for image in image_payloads]


async def _extract_batches(
    client: VLMClient,
    images: list[ImagePayload],
    *,
    concurrency: int,
    batch_size: int,
) -> list[WireRecord]:
    semaphore = asyncio.Semaphore(concurrency)
    batches = [images[index : index + batch_size] for index in range(0, len(images), batch_size)]

    async def run_one(batch: list[ImagePayload]) -> list[WireRecord]:
        async with semaphore:
            batch_name = ", ".join(image.name for image in batch)
            try:
                return await client.extract_images(batch)
            except VLMError as exc:
                raise HTTPException(status_code=502, detail=f"{batch_name}: {exc}") from exc

    chunks = await asyncio.gather(*(run_one(batch) for batch in batches))
    return [record for chunk in chunks for record in chunk]
