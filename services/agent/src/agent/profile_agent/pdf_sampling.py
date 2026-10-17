"""PDF page sampling tool: no original PDF or unselected page is ever written to disk."""

from __future__ import annotations

import base64
import binascii
import math
import random
from pathlib import Path
from uuid import UUID, uuid4

import pymupdf

from src.profiles.package import checksum

from .models import (
    PdfSampleInfo,
    PdfSampleRequest,
    PdfSampleResult,
    ProfileActor,
    ProfileError,
    SampledPdfPage,
)
from .store import DraftStore

MAX_PDF_BYTES = 50 * 1024 * 1024
MAX_SIDE = 2048


def choose_pages(page_count: int) -> list[int]:
    """Zero-based unique random indices; order only affects presentation, not selection."""
    return sorted(random.SystemRandom().sample(range(page_count), min(2, page_count)))


def render_page(document: pymupdf.Document, index: int) -> bytes:
    page = document.load_page(index)
    rect = page.rect
    if not all(math.isfinite(v) and v > 0 for v in (rect.width, rect.height)):
        raise ProfileError("PDF_PAGE_INVALID", "抽中页面的尺寸无效，请更换PDF", 422)
    scale = min(MAX_SIDE / rect.width, MAX_SIDE / rect.height)
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), colorspace=pymupdf.csRGB, alpha=False)
    return bytes(pixmap.tobytes("png"))


class PdfSamplingTool:
    def __init__(self, store: DraftStore) -> None:
        self.store = store

    def sample(self, draft: UUID, body: PdfSampleRequest, actor: ProfileActor) -> PdfSampleResult:
        view = self.store.get(draft, actor)
        _, _, metadata = self.store.snapshot(draft, actor, view.revision)
        try:
            content = base64.b64decode(body.content_base64, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ProfileError("INVALID_PDF", "PDF编码无效，请重新上传", 422) from exc
        if not content or len(content) > MAX_PDF_BYTES:
            raise ProfileError("PDF_TOO_LARGE", "PDF必须非空且不超过50MiB", 413)
        digest = checksum(content)
        filename = Path(body.filename).name
        cached = metadata.get("pdf_samples", {}).get(str(body.request_id))
        if cached:
            sample = PdfSampleInfo.model_validate(cached)
            if sample.checksum != digest or sample.filename != filename:
                raise ProfileError("OPERATION_CONFLICT", "同一抽样请求的PDF内容已变化", 409)
            return PdfSampleResult(draft=view, sample=sample)
        if body.revision != view.revision:
            raise ProfileError("VERSION_CONFLICT", "草稿已更新，请恢复对话再上传PDF", 409)
        if not filename.lower().endswith(".pdf") or b"%PDF-" not in content[:1024]:
            raise ProfileError("INVALID_PDF", "请上传有效的PDF文件", 422)
        try:
            with pymupdf.open(stream=content, filetype="pdf") as document:
                if document.needs_pass:
                    raise ProfileError("PDF_PASSWORD_REQUIRED", "请先解除PDF密码后再上传", 422)
                count = document.page_count
                if count < 1:
                    raise ProfileError("PDF_EMPTY", "PDF没有可读取页面", 422)
                indices = choose_pages(count)
                # Both pages must render successfully before any draft file is created.
                images = [render_page(document, index) for index in indices]
        except ProfileError:
            raise
        except Exception as exc:
            raise ProfileError("PDF_RENDER_FAILED", "无法读取或渲染PDF，未保存新的抽样图片", 422) from exc
        sample = PdfSampleInfo(
            request_id=body.request_id,
            filename=filename,
            checksum=digest,
            page_count=count,
            pages=[SampledPdfPage(attachment_id=uuid4(), pdf_page_number=i + 1) for i in indices],
            notice="PDF只有1页，仅使用这一页，不重复抽取。" if count == 1 else None,
        )
        updated = self.store.attach_pdf_sample(draft, actor, body.revision, sample, images)
        return PdfSampleResult(draft=updated, sample=sample)
