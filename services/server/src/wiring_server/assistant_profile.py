from __future__ import annotations

import base64
import hashlib
import json
from typing import Any
from uuid import UUID, uuid5

from .assistant_attachments import AssistantAttachments
from .assistant_contract import AssistantScope, ProfileDiagnosis
from .assistant_evidence import AssistantEvidence
from .profile_authoring import ProfileAuthoring
from .profile_references import PROFILE_EDIT_SUCCESSORS, ProfileReferences
from .repository import Repository, ServiceError


class AssistantProfile:
    def __init__(self, db: Repository) -> None:
        self.db, self.author = db, ProfileAuthoring(db)
        self.evidence, self.assets = AssistantEvidence(db), AssistantAttachments(db)

    async def attach(
        self,
        turn: dict[str, Any],
        draft: str,
        scope: AssistantScope,
        state: dict[str, Any],
    ) -> int:
        project = await self.db.require_project(str(scope.project_id), turn["owner_id"])
        facts = await self.evidence.overview(scope, turn["owner_id"])
        numbers = (
            [scope.pdf_page_number]
            if scope.pdf_page_number
            else [p["pdf_page_number"] for p in facts["pages"][:2]]
        )
        # Include actual destination pages from the records; cap the visual evidence budget.
        numbers += [
            r["target_pdf_page_number"]
            for r in facts["records"]
            if r.get("target_pdf_page_number")
        ]
        originals = [
            (f"pdf-{page}.png", data)
            for page, data in await self.evidence.drawing_bytes(
                project, list(dict.fromkeys(numbers))[:4]
            )
        ]
        images = []
        for item in await self.assets.rows(
            turn["conversation_id"],
            [str(i) for i in turn["request"].get("attachment_ids", [])],
            turn["owner_id"],
        ):
            if item["mime_type"].startswith("image/"):
                if item.get("project_id") and item["project_id"] != str(
                    scope.project_id
                ):
                    raise ServiceError(
                        403, "ATTACHMENT_SCOPE_MISMATCH", "参考图不属于诊断项目"
                    )
                images.append((item["filename"], await self.assets.content(item)))
        images = images[:2] + originals[: max(0, 4 - min(len(images), 2))]
        view = state.get("draft", state)
        revision = view["revision"]
        for index, (name, data) in enumerate(images[:4]):
            view = await self.author.call(
                "POST",
                f"/drafts/{draft}/images",
                turn["owner_id"],
                {
                    "revision": revision,
                    "image_id": str(uuid5(UUID(draft), f"evidence:{index}:{name}")),
                    "filename": name,
                    "content_base64": base64.b64encode(data).decode(),
                },
            )
            revision = view["revision"]
        return int(revision)

    async def diagnose(
        self,
        turn: dict[str, Any],
        action: dict[str, Any],
        scope: AssistantScope,
        args: ProfileDiagnosis,
    ) -> dict[str, Any]:
        user = turn["owner_id"]
        bound = await self.evidence.bound_profile(scope, user)
        facts = await self.evidence.overview(scope, user)
        draft = str(uuid5(UUID(action["id"]), "frozen-diagnosis"))
        state = await self.author.call(
            "POST",
            "/imports",
            user,
            {
                "draft_id": draft,
                "profile_id": bound.row["id"],
                "profile_key": bound.manifest["key"],
                "profile_version": bound.manifest["version"],
                "source_checksum": bound.checksum,
                "display_name": bound.manifest["display_name"],
                "content_base64": base64.b64encode(bound.content).decode(),
                "read_only": True,
            },
        )
        revision = await self.attach(turn, draft, scope, state)
        evidence = {
            "scope": facts["scope"],
            "records": facts["records"],
            "gaps": facts["gaps"],
            "profile_source": bound.origin,
            "profile_checksum": bound.checksum,
        }
        diagnosis = await self.author.call(
            "POST",
            f"/drafts/{draft}/turns",
            user,
            {
                "turn_id": str(uuid5(UUID(action["id"]), "diagnosis-turn")),
                "expected_revision": revision,
                "message": (
                    "只读诊断。先核对冻结规则、真实图纸、现有结果和用户期望，区分规则问题、模型偏差、图像可读性、引用解析或证据不足。"
                    "这是当次规则的副本，不能写入、创建或应用修改。明确可证明的依据和缺口。用户问题："
                    + args.question
                )[:12000],
                "intent": "discuss",
                "observations": [evidence],
            },
        )
        result: dict[str, Any] = {
            "scope": scope.model_dump(mode="json"),
            "answer": diagnosis["answer"],
            "delegated": True,
            "diagnosis_draft_id": draft,
            "findings": diagnosis.get("findings", []),
            "frozen_profile": {k: v for k, v in bound.facts().items() if k != "rules"},
        }
        if not args.propose_changes:
            return result
        catalog = await ProfileReferences(self.db).list(user)
        source_key = bound.manifest["key"]
        edit_key = (
            source_key
            if any(row["profile_key"] == source_key for row in catalog)
            else (PROFILE_EDIT_SUCCESSORS.get(source_key, source_key))
        )
        latest = next(
            (p for p in catalog if p["profile_key"] == edit_key),
            None,
        )
        if not latest:
            result["answer"] += (
                "\n诊断已保留，但原规则已停用且没有已登记的可编辑继任包，尚未生成规则修改建议。请先选择或建立目标规则。"
            )
            result["needs_profile_selection"] = True
            return result
        if edit_key != source_key:
            result["answer"] += (
                f"\n诊断使用历史{source_key}冻结包；修改建议基于已合并的正式{edit_key}最新版本，旧项目不改绑。"
            )
            result["editing_profile"] = {
                "id": latest["id"],
                "key": edit_key,
                "checksum": latest["checksum"],
            }
        if latest["created_by"] != user:
            result["answer"] += (
                "\n该规则由其他用户维护。当前诊断已保留；请先在规则配置中创建自己的规则副本再修改。"
            )
            return result
        editable = str(uuid5(UUID(action["id"]), "editable-latest"))
        state = await self.author.fork(latest["id"], editable, latest["checksum"], user)
        revision = await self.attach(turn, editable, scope, state)
        reply = await self.author.call(
            "POST",
            f"/drafts/{editable}/turns",
            user,
            {
                "turn_id": str(uuid5(UUID(action["id"]), "proposal-turn")),
                "expected_revision": revision,
                "intent": "discuss",
                "observations": [
                    evidence,
                    {
                        "frozen_diagnosis": diagnosis["answer"],
                        "findings": diagnosis.get("findings", []),
                    },
                ],
                "message": (
                    "用户要求改进规则。此草稿来自最新可编辑版本，与诊断时的冻结包可能不同。先复核最新版本是否已有修复；"
                    "只有存在证据支持的规则问题才调用propose_edits，生成一个包含所有必要修改的完整差异方案。不得调用apply_edits，不能自行发布。"
                    "没有规则问题或证据不足时说明原因。用户要求：" + args.question
                )[:12000],
            },
        )
        result["answer"] += "\n\n" + reply["answer"]
        proposals = [p for p in reply.get("proposals", []) if p["status"] == "pending"]
        if len(proposals) > 1:
            raise ServiceError(
                409,
                "MULTIPLE_PROFILE_PROPOSALS",
                "规则建议包含多个方案，请缩小修改范围",
            )
        if proposals:
            proposal = proposals[0]
            result.update(
                event="proposal_ready",
                kind="profile",
                draft_id=editable,
                proposal_id=proposal["id"],
                base_revision=proposal["base_revision"],
                base_checksum=proposal["base_checksum"],
                proposal_fingerprint=hashlib.sha256(
                    json.dumps(proposal["diffs"], sort_keys=True).encode()
                ).hexdigest(),
                latest_profile_id=latest["id"],
            )
        return result
