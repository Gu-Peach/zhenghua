"""Keep queue receipts distinct from model narration and previous conversation tasks."""

from __future__ import annotations

import re
from typing import Any

from .models import ExplainContext, ExplainTurn, RescanRun, SearchResult


def rescan_tool_context(
    turn: ExplainTurn, context: ExplainContext | SearchResult, retrievals: list[SearchResult]
) -> dict[str, Any]:
    """Keep exact identities and pagination without repeating raw historic model output."""
    contexts = [context] if isinstance(context, ExplainContext) else context.rows
    contexts = [*contexts, *[row for result in retrievals for row in result.rows]]
    rows = {str(item.row.id): item.row.model_dump(mode="json") for item in contexts}
    queries = ([context] if isinstance(context, SearchResult) else []) + retrievals
    drawings = {
        (item.pdf_page_number, item.role): item
        for item in [*context.drawings, *[drawing for result in retrievals for drawing in result.drawings]]
    }
    return {
        "selection": {
            "connection_id": str(turn.connection_id) if turn.connection_id else None,
            "query": turn.query.model_dump(mode="json") if turn.query else None,
        },
        "rows": list(rows.values()),
        "drawings": [
            d.model_dump(mode="json", exclude={"image_url", "url_expires_in"}) for d in drawings.values()
        ],
        "queries": [
            {
                "query": item.query.model_dump(mode="json"),
                "has_more": item.has_more,
                "next_offset": item.next_offset,
            }
            for item in queries
        ],
        "detail_attachment_ids": [str(value) for value in turn.attachment_ids],
    }


def claims_rescan_execution(text: str) -> bool:
    """Recognize execution claims, excluding quoted examples and explicit negations."""
    plain = re.sub(r'“[^”]*”|「[^」]*」|"[^"\n]*"', "", text).replace("*", "").replace("`", "")
    pattern = (
        r"(?:已|已经)[^\n。！？]{0,40}(?:创建|提交|启动|发起|建立|开始)[^\n。！？]{0,20}(?:任务|重扫|重提|重新提取|重新识别)"
        r"|(?:任务|重扫|重提取|重新提取|重新识别)[^\n。！？]{0,16}(?:已创建|已提交|已启动|已入队|已完成)"
        r"|(?:已入队|正在重扫|正在重新提取|已完成重扫|已完成(?:重新)?提取)"
        r"|(?:已|已经)(?:重新|再次)(?:提取|识别|扫描)"
        r"|任务状态\s*[：:]\s*(?:queued|running|ready)"
    )
    return any(
        not re.search(
            r"(?:不能|不要|禁止|不得|不是|未曾|尚未|并未)[^。\n]{0,8}$",
            plain[max(0, match.start() - 16) : match.start()],
        )
        for match in re.finditer(pattern, plain, flags=re.IGNORECASE)
    )


def rescan_receipt_text(runs: list[RescanRun]) -> str:
    """Render only persisted task facts; recognition values remain in the candidate UI."""
    lines = [f"重扫任务：{run.id}；状态：{run.status}；阶段：{run.stage}。" for run in runs]
    if any(run.status in {"queued", "running"} for run in runs):
        lines.append("正式线表未改动，候选尚未就绪。请在任务卡查看进度，候选生成后核对并确认。")
    else:
        lines.append("请在任务卡查看实际结果、缺口及确认状态。")
    return "\n".join(lines)
