"""Confirm exact child-agent proposals. This endpoint is never exposed as a model tool."""

from __future__ import annotations

import hashlib
import json
import secrets

from .assistant_contract import AssistantActionDecision, AssistantActionRead
from .assistant_store import AssistantStore
from .explain_contract import ConnectionEditDecision, RescanDecision
from .explain_edits import ExplainEdits
from .explain_rescan import ExplainRescan
from .profile_authoring import ProfileAuthoring
from .repository import Repository, ServiceError


class AssistantActions:
    def __init__(self, db: Repository) -> None:
        self.db, self.store = db, AssistantStore(db)

    async def get(self, identifier: str, user: str) -> AssistantActionRead:
        row = await self.store.owned("assistant_actions", identifier, user)
        result = dict(row["result"])
        project = str((result.get("scope") or {}).get("project_id") or "")
        if project:
            await self.db.require_project(project, user)
        if result.get("kind") == "rescan":
            run = await ExplainRescan(self.db).get(project, result["run_id"], user)
            result["detail"] = run.model_dump(mode="json")
        elif result.get("kind") == "connection_edit":
            proposal = await ExplainEdits(self.db).get(
                project, result["proposal_id"], user
            )
            result["detail"] = proposal.model_dump(mode="json")
        elif result.get("kind") == "profile":
            result["detail"] = await ProfileAuthoring(self.db).call(
                "GET",
                f"/drafts/{result['draft_id']}/proposals/{result['proposal_id']}",
                user,
            )
        return self.store.public_action({**row, "result": result})

    async def decide(
        self, identifier: str, user: str, body: AssistantActionDecision
    ) -> AssistantActionRead:
        row = await self.store.owned("assistant_actions", identifier, user)
        if not row["checksum"] or not secrets.compare_digest(
            body.checksum, row["checksum"]
        ):
            raise ServiceError(
                409, "ASSISTANT_ACTION_CHANGED", "方案已变化，请重新查看差异"
            )
        desired = "applied" if body.accepted else "rejected"
        if row["status"] in {"applied", "rejected"}:
            if row["status"] != desired:
                raise ServiceError(409, "ASSISTANT_ACTION_DECIDED", "该方案已经处理")
            return await self.get(identifier, user)
        view = await self.get(identifier, user)
        result = dict(view.result)
        detail = result.pop("detail", {})
        kind = result.get("kind")
        project = str((result.get("scope") or {}).get("project_id") or "")
        if kind == "rescan":
            if detail.get("status") not in {
                "ready",
                "applied",
                "rejected",
            } or not detail.get("checksum"):
                raise ServiceError(
                    409, "RESCAN_NOT_READY", "重扫候选尚未就绪或已结束，请刷新任务状态"
                )
            run_receipt = await ExplainRescan(self.db).decide(
                project,
                result["run_id"],
                user,
                RescanDecision(
                    checksum=detail.get("checksum") or "", accepted=body.accepted
                ),
            )
            result["receipt"] = {
                "status": run_receipt.status,
                "run_id": str(run_receipt.id),
            }
        elif kind == "connection_edit":
            receipt = await ExplainEdits(self.db).decide(
                project,
                result["proposal_id"],
                user,
                ConnectionEditDecision(
                    checksum=result["proposal_checksum"], accepted=body.accepted
                ),
            )
            result["receipt"] = receipt.model_dump(mode="json")
        elif kind == "profile":
            author = ProfileAuthoring(self.db)
            checksum = hashlib.sha256(
                json.dumps(detail["diffs"], sort_keys=True).encode()
            ).hexdigest()
            if (
                checksum != result["proposal_fingerprint"]
                or detail["base_checksum"] != result["base_checksum"]
            ):
                raise ServiceError(
                    409, "PROFILE_SOURCE_CHANGED", "规则方案已变化，请重新诊断"
                )
            await author.call(
                "POST",
                f"/drafts/{result['draft_id']}/proposals/{result['proposal_id']}/confirm",
                user,
                {"revision": result["base_revision"], "accepted": body.accepted},
            )
            if body.accepted:
                # A retry resumes the accepted proposal, but cannot approve unrelated later edits.
                proposal = await author.call(
                    "GET",
                    f"/drafts/{result['draft_id']}/proposals/{result['proposal_id']}",
                    user,
                )
                if not result.get("review_revision"):
                    # ProfileEditor review is itself idempotent at this exact revision.
                    # Repeating it recovers a lost Server receipt without approving later edits.
                    reviewed = await author.call(
                        "POST",
                        f"/drafts/{result['draft_id']}/editor/accept",
                        user,
                        {"revision": proposal["applied_revision"]},
                    )
                    result["review_revision"] = reviewed["draft"]["revision"]
                    await self.db.update(
                        "assistant_actions",
                        {"id": f"eq.{identifier}", "checksum": f"eq.{body.checksum}"},
                        {"result": result},
                    )
                result["receipt"] = await author.publish(
                    result["draft_id"], result["review_revision"], user
                )
        else:
            raise ServiceError(
                422,
                "ASSISTANT_CONFIRMATION_NOT_SUPPORTED",
                "该操作没有可确认的修改方案",
            )
        result["status"] = desired
        await self.db.update(
            "assistant_actions",
            {"id": f"eq.{identifier}", "owner_id": f"eq.{user}"},
            {"status": desired, "result": result},
        )
        return await self.get(identifier, user)
