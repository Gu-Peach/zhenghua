from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Any


def load_pdf_module() -> Any:
    """Load the optional PDF engine behind an untyped third-party boundary."""
    try:
        return import_module("pymupdf")
    except ImportError:
        return import_module("fitz")


def read_pdf_text_pages(path: Path) -> list[tuple[int, str]]:
    document = load_pdf_module().open(path)
    try:
        return [
            (number, "\n".join(line.strip() for line in page.get_text("text").splitlines() if line.strip()))
            for number, page in enumerate(document, start=1)
        ]
    finally:
        document.close()
