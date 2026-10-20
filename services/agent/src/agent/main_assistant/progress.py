"""Per-turn read reuse and bounded handoff from verified lookup evidence."""

from __future__ import annotations

import json
import re
from typing import Any

from .models import AssistantScope, AssistantToolCall

READ_TOOLS = {"search_connections", "read_scope", "find_targets", "list_rule_packages"}
DELEGATES = {"propose_connection_edit", "diagnose_profile", "explain_scope"}


class ReadProgress:
    def __init__(self) -> None:
        self.cache: dict[str, dict[str, Any]] = {}
        self.blocked: set[str] = set()
        self.repeats = 0

    @staticmethod
    def key(name: str, arguments: dict[str, Any]) -> str:
        return json.dumps([name, arguments], sort_keys=True, ensure_ascii=False)

    def recall(self, name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
        key = self.key(name, arguments)
        if name not in READ_TOOLS or key not in self.cache:
            return None
        self.blocked.add(name)
        self.repeats += 1
        return {
            **self.cache[key],
            "repeat_guard": {
                "reused": True,
                "count": self.repeats,
                "hint": (
                    "同参数检索已有结果，本次未再次访问业务工具。"
                    "请转入用户要求的修改候选/规则诊断；不要重复该查询。"
                ),
            },
        }

    def remember(self, name: str, arguments: dict[str, Any], result: dict[str, Any]) -> None:
        if name == "navigate_to" and not result.get("error"):
            self.cache.clear()
            self.blocked.clear()
            self.repeats = 0
        elif name in READ_TOOLS and not result.get("error"):
            self.cache[self.key(name, arguments)] = result

    @staticmethod
    def summary(name: str, result: dict[str, Any]) -> str:
        if name not in {"search_connections", "read_scope"}:
            targets = result.get("targets") or []
            return "检索结果：\n" + "\n".join(str(item.get("label", "")) for item in targets)
        rows = result.get("rows", result.get("records", []))
        if not rows:
            return "当前精确检索条件下没有匹配记录。请修改编号或选择图纸；没有生成修改候选。"

        def cell(value: Any) -> str:
            return str(value if value is not None else "-").replace("|", "\\|").replace("\n", " ")[:512]

        lines = ["已读取实际记录：", "", "| 原理号 | 起点端子 | 终点端子 |", "| --- | --- | --- |"]
        lines += [
            "| "
            + " | ".join(cell(row.get(key)) for key in ("principle_number", "start_terminal", "end_terminal"))
            + " |"
            for row in rows[:50]
        ]
        if result.get("has_more") or result.get("has_more_records"):
            lines.append("当前仅展示已读取的这一页结果，仍有后续记录；不能视为全部范围。")
        return "\n".join(lines)

    def handoffs(self, message: str, required: list[str], propose_changes: bool) -> list[AssistantToolCall]:
        """Only a complete, explicit numeric-range lookup may bind a deterministic handoff."""
        pending = [name for name in required if name in DELEGATES]
        if len(pending) != len(required):
            return []
        normalized = re.sub(r"\s+", "", message)
        for result in reversed(list(self.cache.values())):
            interpretation = result.get("query_interpretation") or {}
            rows = result.get("rows") or []
            literal = re.sub(r"\s+", "", str(interpretation.get("input") or ""))
            if (
                interpretation.get("kind") != "number_range"
                or not literal
                or literal not in normalized
                or result.get("has_more")
                or not rows
                or len(rows) > 50
            ):
                continue
            scope = AssistantScope.model_validate(result["scope"])
            scope.connection_ids = [row["id"] for row in rows]
            numbers = list(dict.fromkeys(row["principle_number"] for row in rows))
            question = (
                message[:2500]
                + "\n已由业务工具核对的原理号集合："
                + json.dumps(numbers, ensure_ascii=False)[:1100]
                + "\n只处理限定记录；不同记录可能包含不同元件，不要一并删除。"
                "正确终点不能确认时说明证据缺口，不补造。"
            )[:4000]
            return [
                AssistantToolCall(
                    name=name,
                    arguments={
                        "scope": scope.model_dump(mode="json"),
                        "question": question,
                        **({"propose_changes": propose_changes} if name == "diagnose_profile" else {}),
                    },
                )
                for name in pending
            ]
        return []
