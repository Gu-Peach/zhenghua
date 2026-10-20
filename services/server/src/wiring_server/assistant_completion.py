"""Verify completion against durable business facts before releasing assistant prose."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from .repository import Repository, ServiceError


class AssistantCompletion:
    def __init__(self, db: Repository, turn: dict[str, Any]) -> None:
        self.db, self.turn = db, turn

    @staticmethod
    def denied() -> ServiceError:
        return ServiceError(
            409,
            "ASSISTANT_EXECUTION_UNVERIFIED",
            "未取得可核验的业务执行回执，不能确认重扫已启动。请重试；服务刚更新时需重载8000和8100。",
        )

    async def action(self, value: Any) -> dict[str, Any]:
        try:
            identifier = str(UUID(str(value)))
        except (ValueError, TypeError):
            raise self.denied() from None
        rows = await self.db.rows(
            "assistant_actions",
            {
                "id": f"eq.{identifier}",
                "turn_id": f"eq.{self.turn['id']}",
                "conversation_id": f"eq.{self.turn['conversation_id']}",
                "owner_id": f"eq.{self.turn['owner_id']}",
                "limit": "1",
            },
        )
        if not rows or rows[0]["status"] not in {
            "completed",
            "awaiting_confirmation",
            "applied",
            "rejected",
        }:
            raise self.denied()
        return rows[0]

    async def rescan(self, data: dict[str, Any]) -> dict[str, Any]:
        action = await self.action(data.get("action_id"))
        result = action["result"]
        if (
            action["tool_name"] != "start_rescan"
            or result.get("kind") != "rescan"
            or result.get("run_id") != data.get("run_id")
        ):
            raise self.denied()
        project = (result.get("scope") or {}).get("project_id")
        rows = await self.db.rows(
            "connection_rescan_runs",
            {
                "id": f"eq.{result['run_id']}",
                "project_id": f"eq.{project}",
                "conversation_id": f"eq.{self.turn['conversation_id']}",
                "created_by": f"eq.{self.turn['owner_id']}",
                "limit": "1",
                "select": "id,status",
            },
        )
        if not rows:
            raise self.denied()
        return {**result, "status": rows[0]["status"]}

    async def completed(self, data: dict[str, Any]) -> dict[str, Any] | None:
        if data.get("completion_verified") is not True or data.get(
            "verification_version"
        ) not in {1, 2}:
            raise self.denied()
        if data.get("verification_version") == 2:
            return await self.multiple(data)
        required, disposition = data.get("required_tool"), data.get("disposition")
        if disposition == "answered" and required is None:
            return None
        action = await self.action(data.get("action_id"))
        if disposition == "clarification":
            result = action["result"]
            if action["tool_name"] != "find_targets" or not (
                result.get("event") == "selection_required"
                or result.get("targets") == []
            ):
                raise self.denied()
            return None
        if disposition != "executed" or action["tool_name"] != required:
            raise self.denied()
        if required == "start_rescan":
            return await self.rescan(data)
        return None

    async def multiple(self, data: dict[str, Any]) -> dict[str, Any] | None:
        required, receipts = data.get("required_tools"), data.get("action_receipts")
        if (
            data.get("disposition") != "executed"
            or not isinstance(required, list)
            or not 1 < len(required) <= 6
            or any(not isinstance(name, str) for name in required)
            or len(set(required)) != len(required)
            or not isinstance(receipts, list)
            or len(receipts) != len(required)
        ):
            raise self.denied()
        if any(
            not isinstance(item, dict) or not isinstance(item.get("tool_name"), str)
            for item in receipts
        ):
            raise self.denied()
        by_name = {item["tool_name"]: item for item in receipts}
        if set(by_name) != set(required):
            raise self.denied()
        if data.get("required_tool") != required[0] or data.get("action_id") != by_name[
            required[0]
        ].get("action_id"):
            raise self.denied()
        answers = []
        for name in required:
            proof = by_name[name]
            action = await self.action(proof.get("action_id"))
            if action["tool_name"] != name:
                raise self.denied()
            if name == "start_rescan":
                answers.append(self.rescan_answer(await self.rescan(proof)))
            elif action["result"].get("delegated") and action["result"].get("answer"):
                answers.append(str(action["result"]["answer"]))
        return (
            {"verified_answer": "\n\n".join(answers)}
            if len(answers) == len(required)
            else None
        )

    @staticmethod
    def rescan_answer(result: dict[str, Any]) -> str:
        labels = {
            "queued": "排队中",
            "running": "执行中",
            "ready": "候选已就绪",
            "failed": "失败",
            "cancelled": "已取消",
            "applied": "已应用",
            "rejected": "已拒绝",
        }
        status = result["status"]
        return (
            f"已取得重扫任务回执。\n\n任务 ID：`{result['run_id']}`\n\n"
            f"当前状态：{labels.get(status, status)}（{status}）。\n\n"
            "请在下方任务卡查看实际进度与候选差异；候选需要你确认后才写入正式线表。"
        )
