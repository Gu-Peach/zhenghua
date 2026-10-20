from __future__ import annotations

import hashlib
import json
import secrets
from typing import Any
from uuid import UUID, uuid5

from .assistant_contract import (
    AssistantActionRead,
    AssistantConversationCreate,
    AssistantConversationRead,
    AssistantScope,
    AssistantTurnInput,
    AssistantTurnRead,
)
from .repository import Repository, ServiceError


def public_fields(model: Any, row: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in row.items() if key in model.model_fields}


def fingerprint(value: Any) -> str:
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
        ).hexdigest()
    )


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class AssistantStore:
    def __init__(self, db: Repository) -> None:
        self.db = db

    async def owned(self, table: str, identifier: str, user: str) -> dict[str, Any]:
        rows = await self.db.rows(
            table, {"id": f"eq.{identifier}", "owner_id": f"eq.{user}", "limit": "1"}
        )
        if not rows:
            raise ServiceError(
                404, "ASSISTANT_NOT_FOUND", "会话或操作不存在，或无权访问"
            )
        return rows[0]

    async def create(
        self, body: AssistantConversationCreate, user: str
    ) -> AssistantConversationRead:
        rows = await self.db.rows(
            "assistant_conversations", {"id": f"eq.{body.id}", "limit": "1"}
        )
        if rows:
            if rows[0]["owner_id"] != user:
                raise ServiceError(403, "ACCESS_DENIED", "无权访问该会话")
            return await self.get(str(body.id), user)
        await self.db.insert(
            "assistant_conversations",
            {
                "id": str(body.id),
                "owner_id": user,
                "title": body.title,
                "context": {},
            },
        )
        return await self.get(str(body.id), user)

    async def list_conversations(self, user: str) -> list[AssistantConversationRead]:
        rows = await self.db.rows(
            "assistant_conversations",
            {
                "owner_id": f"eq.{user}",
                "order": "updated_at.desc,id.desc",
                "limit": "100",
            },
        )
        return [
            AssistantConversationRead.model_validate(
                public_fields(AssistantConversationRead, row)
            )
            for row in rows
        ]

    async def get(
        self, identifier: str, user: str, offset: int = 0
    ) -> AssistantConversationRead:
        row = await self.owned("assistant_conversations", identifier, user)
        turns = await self.db.rows(
            "assistant_turns",
            {
                "conversation_id": f"eq.{identifier}",
                "owner_id": f"eq.{user}",
                "order": "created_at.desc,id.desc",
                "limit": "51",
                "offset": str(offset),
            },
        )
        if turns:
            actions = await self.db.rows(
                "assistant_actions",
                {
                    "owner_id": f"eq.{user}",
                    "conversation_id": f"eq.{identifier}",
                    "turn_id": "in.("
                    + ",".join(item["id"] for item in turns[:50])
                    + ")",
                    "limit": "500",
                },
            )
            for item in turns[:50]:
                events = list(item.get("events") or [])
                known = {
                    (e.get("data") or {}).get("action_id")
                    for e in events
                    if e.get("type") in {"task_started", "proposal_ready"}
                }
                for action in actions:
                    result = action.get("result") or {}
                    if action["turn_id"] != item["id"] or action["id"] in known:
                        continue
                    kind = result.get("kind")
                    if kind in {"rescan", "connection_edit", "profile"}:
                        events.append(
                            {
                                "id": str(uuid5(UUID(action["id"]), "recover")),
                                "turn_id": item["id"],
                                "type": "task_started"
                                if kind == "rescan"
                                else "proposal_ready",
                                "data": result,
                            }
                        )
                item["events"] = events
        return AssistantConversationRead.model_validate(
            {
                **public_fields(AssistantConversationRead, row),
                "turns": [
                    AssistantTurnRead.model_validate(
                        public_fields(AssistantTurnRead, item)
                    )
                    for item in reversed(turns[:50])
                ],
                "has_more": len(turns) > 50,
                "next_offset": offset + 50 if len(turns) > 50 else None,
            }
        )

    async def begin(
        self, conversation: str, user: str, body: AssistantTurnInput
    ) -> tuple[dict[str, Any], str]:
        token = secrets.token_urlsafe(48)
        request = body.model_dump(mode="json")
        row = await self.db.rpc(
            "assistant_begin_turn",
            {
                "actor": user,
                "conversation": conversation,
                "turn": str(body.turn_id),
                "body": request,
                "body_hash": fingerprint(request),
                "token_hash": token_hash(token),
            },
        )
        return dict(row), token

    async def internal_turn(self, identifier: str, token: str) -> dict[str, Any]:
        if len(token) < 32:
            raise ServiceError(403, "ASSISTANT_TOOL_DENIED", "内部工具请求未授权")
        rows = await self.db.rows(
            "assistant_turns", {"id": f"eq.{identifier}", "limit": "1"}
        )
        if (
            not rows
            or rows[0]["status"] != "running"
            or not secrets.compare_digest(rows[0]["tool_token_hash"], token_hash(token))
        ):
            raise ServiceError(
                403, "ASSISTANT_TOOL_DENIED", "工具请求已失效或不属于当前轮次"
            )
        row = rows[0]
        await self.owned(
            "assistant_conversations", row["conversation_id"], row["owner_id"]
        )
        return row

    async def finish(
        self,
        turn: dict[str, Any],
        token: str,
        status: str,
        events: list[dict[str, Any]],
        answer: str,
        error: str | None,
        scope: AssistantScope,
    ) -> dict[str, Any]:
        return dict(
            await self.db.rpc(
                "assistant_finish_turn",
                {
                    "actor": turn["owner_id"],
                    "turn": turn["id"],
                    "token_hash": token_hash(token),
                    "outcome": status,
                    "event_list": events,
                    "public_answer": answer,
                    "failure": error,
                    "scope_context": scope.model_dump(mode="json"),
                },
            )
        )

    async def action(
        self, turn: dict[str, Any], name: str, arguments: dict[str, Any]
    ) -> tuple[dict[str, Any], bool]:
        identifier = str(
            uuid5(UUID(turn["id"]), f"tool:{name}:{fingerprint(arguments)}")
        )
        rows = await self.db.rows(
            "assistant_actions",
            {
                "id": f"eq.{identifier}",
                "owner_id": f"eq.{turn['owner_id']}",
                "limit": "1",
            },
        )
        if rows:
            return rows[0], rows[0]["status"] in {
                "completed",
                "awaiting_confirmation",
                "applied",
                "rejected",
            }
        row = await self.db.insert(
            "assistant_actions",
            {
                "id": identifier,
                "turn_id": turn["id"],
                "conversation_id": turn["conversation_id"],
                "owner_id": turn["owner_id"],
                "tool_name": name,
                "arguments": arguments,
            },
        )
        return row, False

    async def save_action(
        self, action: dict[str, Any], result: dict[str, Any], status: str = "completed"
    ) -> dict[str, Any]:
        checksum = fingerprint(
            {"id": action["id"], "arguments": action["arguments"], "result": result}
        )
        result = {**result, "action_id": action["id"], "checksum": checksum}
        scope = result.get("scope") or {}
        stored = dict(result)
        for field in ("records", "rows"):
            if field in stored:
                stored[field + "_references"] = [
                    {key: row.get(key) for key in ("id", "record_version", "batch_id")}
                    for row in stored.pop(field)
                ]
        if isinstance(stored.get("profile"), dict):
            stored["profile"] = {
                key: value for key, value in stored["profile"].items() if key != "rules"
            }
        updated = await self.db.update(
            "assistant_actions",
            {
                "id": f"eq.{action['id']}",
                "owner_id": f"eq.{action['owner_id']}",
            },
            {
                "result": stored,
                "status": status,
                "checksum": checksum,
                "project_id": scope.get("project_id"),
            },
        )
        if not updated:
            raise ServiceError(409, "ASSISTANT_ACTION_CHANGED", "操作状态已变化")
        return result

    @staticmethod
    def public_action(row: dict[str, Any]) -> AssistantActionRead:
        return AssistantActionRead.model_validate(
            public_fields(AssistantActionRead, row)
        )
