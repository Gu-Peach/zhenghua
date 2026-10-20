"""Conversation text is context; durable action state describes what actually happened."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from .assistant_contract import AssistantConversationRead, AssistantScope
from .repository import Repository


async def build_history(
    db: Repository,
    saved: AssistantConversationRead,
    scope: AssistantScope,
    current_turn: UUID,
    user: str,
) -> list[dict[str, str]]:
    items = [item for item in saved.turns if item.id != current_turn][-8:]
    if not items:
        return []
    actions = await db.rows(
        "assistant_actions",
        {
            "owner_id": f"eq.{user}",
            "conversation_id": f"eq.{saved.id}",
            "turn_id": "in.(" + ",".join(str(item.id) for item in items) + ")",
            "order": "created_at.asc,id.asc",
            "limit": "500",
        },
    )
    history = []
    for item in items:
        references: list[dict[str, Any]] = []
        for action in actions:
            if action["turn_id"] != str(item.id):
                continue
            result = action.get("result") or {}
            receipt = result.get("receipt") or {}
            references.append(
                {
                    "action_id": action["id"],
                    "tool_name": action["tool_name"],
                    "status": action["status"],
                    "scope": result.get("scope"),
                    "kind": result.get("kind"),
                    "run_id": result.get("run_id"),
                    "publication": {
                        key: receipt[key]
                        for key in ("id", "profile_key", "profile_version")
                        if key in receipt
                    }
                    or None,
                }
            )
        history.append({"role": "user", "content": item.request.message})
        if item.answer:
            history.append({"role": "assistant", "content": item.answer[:8000]})
        historical_scope = next(
            (
                ref["scope"]
                for ref in reversed(references)
                if (ref.get("scope") or {}).get("project_id")
            ),
            item.request.scope.model_dump(mode="json"),
        )
        historical_project = historical_scope.get("project_id")
        status = {
            "scope": historical_scope,
            "same_project": str(historical_project) == str(scope.project_id)
            if historical_project
            else None,
            "turn_status": item.status,
            "error": item.error,
            "actions": references,
        }
        history.append(
            {
                "role": "assistant",
                "content": "历史轮次的当前业务状态（非本轮待办；跨项目范围不得默认沿用）："
                + json.dumps(status, ensure_ascii=False),
            }
        )
    return history
