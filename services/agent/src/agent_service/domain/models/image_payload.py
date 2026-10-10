from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ImagePayload:
    name: str
    mime_type: str
    content: bytes
    blank: bool = False
    page_text: str | None = None
    page_number: int | None = None
