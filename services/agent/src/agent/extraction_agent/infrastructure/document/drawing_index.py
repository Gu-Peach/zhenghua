from __future__ import annotations

from pathlib import Path

from src.agent.extraction_agent.domain.models.drawing_index import DrawingIndex
from src.agent.extraction_agent.infrastructure.document.checkpoint import _write_json_atomic


def write_drawing_index(index: DrawingIndex, path: Path) -> None:
    _write_json_atomic(path, index.to_dict())
