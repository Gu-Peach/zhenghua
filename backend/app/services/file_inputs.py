from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import UploadFile

from .vlm_client import ImagePayload


SUPPORTED_IMAGE_TYPES = {"image/png", "image/jpeg", "image/webp", "image/bmp", "image/tiff"}

# A page whose dark-pixel ratio is below this is treated as blank (drawings are ~1-3%).
BLANK_INK_RATIO = 0.0005
BLANK_DARK_THRESHOLD = 160


class InputFileError(ValueError):
    """Raised when an uploaded file cannot be converted to VLM image input."""


async def upload_to_image_payloads(upload: UploadFile, max_pdf_pages: int, *, pdf_render_scale: float = 2.0) -> list[ImagePayload]:
    content = await upload.read()
    name = upload.filename or "uploaded-image"
    mime_type = _guess_mime_type(name, upload.content_type)

    if mime_type in SUPPORTED_IMAGE_TYPES:
        return [ImagePayload(name=name, mime_type=mime_type, content=content)]
    if mime_type == "application/pdf" or Path(name).suffix.lower() == ".pdf":
        return pdf_bytes_to_images(content, name, max_pdf_pages=max_pdf_pages, render_scale=pdf_render_scale)

    raise InputFileError(f"Unsupported file type for {name}: {mime_type or 'unknown'}")


def path_to_image_payloads(path: Path, max_pdf_pages: int, *, pdf_render_scale: float = 2.0) -> list[ImagePayload]:
    content = path.read_bytes()
    mime_type = _guess_mime_type(path.name, None)
    if mime_type in SUPPORTED_IMAGE_TYPES:
        return [ImagePayload(name=path.name, mime_type=mime_type, content=content)]
    if mime_type == "application/pdf" or path.suffix.lower() == ".pdf":
        return pdf_bytes_to_images(content, path.name, max_pdf_pages=max_pdf_pages, render_scale=pdf_render_scale)
    raise InputFileError(f"Unsupported file type for {path.name}: {mime_type or 'unknown'}")


def pdf_bytes_to_images(content: bytes, name: str, *, max_pdf_pages: int, render_scale: float = 2.0) -> list[ImagePayload]:
    try:
        import pymupdf as fitz  # type: ignore[import-not-found]
    except ImportError as exc:
        try:
            import fitz  # type: ignore[import-not-found]
        except ImportError:
            raise InputFileError("PDF input requires PyMuPDF. Install backend requirements or upload PNG/JPG images.") from exc

    document = fitz.open(stream=content, filetype="pdf")
    page_count = min(document.page_count, max_pdf_pages)
    images: list[ImagePayload] = []
    matrix = fitz.Matrix(render_scale, render_scale)
    for index in range(page_count):
        page = document.load_page(index)
        pixmap = page.get_pixmap(matrix=matrix, alpha=False)
        images.append(
            ImagePayload(
                name=f"{name}#page={index + 1}",
                mime_type="image/png",
                content=pixmap.tobytes("png"),
                blank=_is_blank_page(fitz, page),
                page_text=page.get_text("text"),
                page_number=index + 1,
            )
        )
    return images


def _is_blank_page(fitz: object, page: object) -> bool:
    """Detect empty pages by ink coverage on a low-res grayscale render."""
    pixmap = page.get_pixmap(matrix=fitz.Matrix(0.5, 0.5), colorspace=fitz.csGRAY, alpha=False)  # type: ignore[attr-defined]
    samples = pixmap.samples
    if not samples:
        return True
    step = 2
    sampled = samples[::step]
    dark = sum(1 for value in sampled if value < BLANK_DARK_THRESHOLD)
    return dark / max(len(sampled), 1) < BLANK_INK_RATIO


def _guess_mime_type(name: str, content_type: str | None) -> str:
    if content_type and content_type != "application/octet-stream":
        return content_type.split(";", 1)[0].strip().lower()
    guessed, _ = mimetypes.guess_type(name)
    return (guessed or "application/octet-stream").lower()
