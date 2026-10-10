from __future__ import annotations

from pathlib import Path
from typing import Any

from agent_service.tools.pdf_first_page import PdfFirstPageRenderer


class FakePixmap:
    width = 1200
    height = 800

    def tobytes(self, output: str) -> bytes:
        assert output == "png"
        return b"fake-first-page-png"


class FakePage:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def get_pixmap(self, **kwargs: Any) -> FakePixmap:
        self.calls.append(kwargs)
        return FakePixmap()


class FakeDocument:
    page_count = 10

    def __init__(self) -> None:
        self.loaded_pages: list[int] = []
        self.page = FakePage()
        self.closed = False

    def load_page(self, page_index: int) -> FakePage:
        self.loaded_pages.append(page_index)
        return self.page

    def close(self) -> None:
        self.closed = True


class FakeBackend:
    def __init__(self, document: FakeDocument) -> None:
        self.document = document
        self.opened_path: str | None = None

    def open(self, path: str) -> FakeDocument:
        self.opened_path = path
        return self.document

    def matrix(self, scale: float) -> tuple[float, float]:
        return (scale, scale)


def test_renderer_reads_only_pdf_physical_first_page(tmp_path: Path) -> None:
    pdf_path = tmp_path / "drawing.pdf"
    pdf_path.write_bytes(b"fake-pdf")
    document = FakeDocument()
    backend = FakeBackend(document)
    renderer = PdfFirstPageRenderer(dpi=144, backend=backend)

    image = renderer.render(pdf_path)

    assert document.loaded_pages == [0]
    assert document.closed is True
    assert image.pdf_page_number == 1
    assert image.width == 1200
    assert image.height == 800
    assert image.checksum.startswith("sha256:")
    assert document.page.calls == [{"matrix": (2.0, 2.0), "alpha": False}]
