from __future__ import annotations

from typing import Any

from ..models import DrawingQuery, DrawingReadResult
from .retrieval import ConnectionSearchTool


class ViewDrawingsTool:
    name = "view_drawings"

    @classmethod
    def definition(cls) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": (
                    "读取已检索结果drawings中的PDF物理页图像供本轮视觉分析。"
                    "每次最多4页，每轮最多6页；只接受已有图纸的物理页号，不能传URL或路径。"
                    "看图用于当前证据核对，不证明历史模型如何推理。"
                ),
                "parameters": DrawingQuery.model_json_schema(),
            },
        }

    @staticmethod
    async def execute(
        search: ConnectionSearchTool, query: DrawingQuery, allowed: set[int]
    ) -> DrawingReadResult:
        requested = list(dict.fromkeys(query.pdf_page_numbers))
        if any(number not in allowed for number in requested):
            return DrawingReadResult(gaps=["只能读取已检索到的图纸，请先用search_connections检索相关页。"])
        return await search.repository.read_drawings(search.turn, search.actor, requested)
