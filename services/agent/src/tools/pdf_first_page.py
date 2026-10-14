from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class PdfBackend(Protocol):
    def open(self, path: str) -> Any: ...

    def matrix(self, scale: float) -> Any: ...


class PyMuPdfBackend:
    def open(self, path: str) -> Any:
        try:
            import pymupdf
        except ImportError as exc:  # pragma: no cover - dependency is part of the service package
            raise RuntimeError("PyMuPDF is required to render PDF first pages.") from exc
        return pymupdf.open(path)

    def matrix(self, scale: float) -> Any:
        import pymupdf

        return pymupdf.Matrix(scale, scale)


@dataclass(frozen=True, slots=True)
class FirstPageImage:
    content: bytes
    mime_type: str
    width: int
    height: int
    checksum: str
    pdf_page_number: int = 1


class PdfFirstPageRenderer:
    """Render exactly PDF physical page 1 from a trusted local document path."""

    def __init__(
        self,
        *,
        dpi: int = 180,
        max_pdf_bytes: int = 200 * 1024 * 1024,
        backend: PdfBackend | None = None,
    ) -> None:
        if dpi < 72:
            raise ValueError("dpi must be at least 72.")
        if max_pdf_bytes < 1:
            raise ValueError("max_pdf_bytes must be positive.")
        self.dpi = dpi
        self.max_pdf_bytes = max_pdf_bytes
        self._backend = backend or PyMuPdfBackend()

    def render(self, pdf_path: Path) -> FirstPageImage:
        resolved = pdf_path.resolve()
        if resolved.suffix.lower() != ".pdf":
            raise ValueError("Profile detection accepts PDF files only.")
        if not resolved.is_file():
            raise FileNotFoundError(f"PDF not found: {resolved}")
        if resolved.stat().st_size > self.max_pdf_bytes:
            raise ValueError("PDF exceeds the configured profile detection size limit.")

        document = self._backend.open(str(resolved))
        try:
            if int(document.page_count) < 1:
                raise ValueError("PDF contains no pages.")
            page = document.load_page(0)
            scale = self.dpi / 72.0
            pixmap = page.get_pixmap(matrix=self._backend.matrix(scale), alpha=False)
            content = bytes(pixmap.tobytes("png"))
            return FirstPageImage(
                content=content,
                mime_type="image/png",
                width=int(pixmap.width),
                height=int(pixmap.height),
                checksum=f"sha256:{hashlib.sha256(content).hexdigest()}",
            )
        finally:
            document.close()
