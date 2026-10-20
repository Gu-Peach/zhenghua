"""Keep queue receipts distinct from model narration and previous conversation tasks."""

from __future__ import annotations

import re
from typing import Any

from .models import ExplainContext, ExplainTurn, RescanRun, SearchResult


def requests_rescan(text: str) -> bool:
    """Recognize direct commands only; explanation, history and negations remain read-only."""
    plain = re.sub(r'“[^”]*”|‘[^’]*’|「[^」]*」|"[^"\n]*"|`[^`\n]*`', "", text)
    for clause in re.split(r"[。，,；;！？!?\n]", plain):
        for match in re.finditer(r"重新(?:识别|提取|扫描)|重扫|重提取|再次(?:识别|提取|扫描)", clause):
            before, after = clause[: match.start()], clause[match.end() :]
            if re.search(
                r"无需|无须|不要|不用|不必|不需要|不想|不允许|请勿|不是|取消|停止|暂停"
                r"|(?<!识)别|禁止|不得|只解释|不执行|没有|尚未|还没|未曾",
                before,
            ):
                continue
            if re.search(r"为什么|为何|怎么|如何|是否|有没有|是不是|上轮|上次|之前|历史|已经|刚才", before):
                continue
            if re.match(
                r"(?:的)?(?:流程|链路|原理|方式|原因|状态|进度|结果|意思|怎么|如何|为什么|是否"
                r"|失败|成功|完成|卡住|耗时|费用|次数)",
                after,
            ):
                continue
            if clause.endswith("吗") and not re.search(r"请|帮我|给我|一下", clause):
                continue
            return True
    return False


def claims_tool_progress(text: str) -> bool:
    """A final answer cannot pretend a textual tool marker is a live background operation."""
    plain = re.sub(r'“[^”]*”|「[^」]*」|"[^"\n]*"|`[^`\n]*`', "", text)
    return bool(
        re.search(
            r"\[(?:turn\s*\d+\s+)?tool[ _]call\]"
            r"|(?:正在|即将|马上)(?:读取|查看|加载|检索)(?:图纸|PDF|原图|目标页)[^\n。]*[…。]*$",
            plain.strip(),
            flags=re.IGNORECASE,
        )
    )


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
