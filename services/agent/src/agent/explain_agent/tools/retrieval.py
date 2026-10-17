from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..evidence import prepare_evidence
from ..models import (
    ConnectionQuery,
    DrawingEvidence,
    ExplainActor,
    ExplainContext,
    ExplainTurn,
    SearchCoverage,
    SearchResult,
)

if TYPE_CHECKING:
    from ..repository import ExplanationRepository


def merge_drawings(contexts: list[ExplainContext]) -> list[DrawingEvidence]:
    """Keep per-row highlights in contexts and unique display images in the gallery."""
    result: dict[int, DrawingEvidence] = {}
    for context in contexts:
        for drawing in context.drawings:
            current = result.get(drawing.pdf_page_number)
            if current is None:
                current = drawing.model_copy(deep=True)
                current.terminal_coordinates = None
                current.connection_ids = []
                result[drawing.pdf_page_number] = current
            if context.row.id not in current.connection_ids:
                current.connection_ids.append(context.row.id)
            if current.role == "reference" and drawing.role != "reference":
                current.role = drawing.role
    return list(result.values())


def query_coverage(results: list[SearchResult]) -> list[SearchCoverage]:
    groups: dict[str, list[SearchResult]] = {}
    import json

    for item in results:
        key = json.dumps(item.query.exact_filters(), sort_keys=True)
        groups.setdefault(key, []).append(item)
    coverage = []
    for pages in groups.values():
        cursor = 0
        complete = False
        for page in sorted(pages, key=lambda item: item.query.offset):
            if page.query.offset > cursor:
                break
            if page.query.offset + len(page.rows) >= cursor:
                cursor = page.query.offset + len(page.rows)
                if not page.has_more:
                    complete = True
        coverage.append(
            SearchCoverage(
                filters=pages[0].query.exact_filters(),
                returned_count=len({row.row.id for page in pages for row in page.rows}),
                complete=complete,
            )
        )
    return coverage


class ConnectionSearchTool:
    """Bind identity/project/batch in code; the model supplies only validated exact filters."""

    name = "search_connections"

    def __init__(self, repository: ExplanationRepository, turn: ExplainTurn, actor: ExplainActor) -> None:
        self.repository, self.turn, self.actor = repository, turn, actor

    @classmethod
    def definition(cls) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": cls.name,
                "description": (
                    "在当前授权项目和批次只读检索线表、原页及关联跨页图纸。所有条件精确匹配且AND组合。"
                    "drawing_page/pdf_page_number匹配来源页，target_*匹配目标页；工作区可消除重名页。"
                    "只传页码可查整页，查该页作为终点的连接请用target_drawing_page。"
                    "返回has_more时按next_offset继续相同查询，未取完不能声称整页覆盖。"
                ),
                "parameters": ConnectionQuery.model_json_schema(),
            },
        }

    async def execute(self, query: ConnectionQuery) -> SearchResult:
        result = await self.repository.search(self.turn, self.actor, query)
        result.rows = [prepare_evidence(context) for context in result.rows]
        result.drawings = merge_drawings(result.rows)
        return result
