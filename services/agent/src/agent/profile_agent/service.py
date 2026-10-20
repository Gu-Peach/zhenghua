from __future__ import annotations

import asyncio
import json
import os
import tempfile
import time
import zipfile
from collections import OrderedDict
from pathlib import Path
from uuid import UUID

from src.domain.models.profiles import ProfileManifest, ProfileSnapshot
from src.harness.model_gateway import ModelGateway
from src.profiles.package import build_package, checksum, verify_package

from .graph import EventSink, build_profile_graph
from .models import (
    DraftCreate,
    DraftView,
    ExportReceipt,
    ProfileActor,
    ProfileError,
    ProfileEvent,
    ProfileReply,
    ProfileTurn,
)
from .store import DraftStore
from .tools import ProfileTools
from .validation import validate_draft


class ProfileAgent:
    """Independent assistant with persistent, caller-owned drafts and explicit edit permissions."""

    def __init__(self, store: DraftStore, gateway: ModelGateway, *, max_tokens: int = 8000) -> None:
        self.store, self.gateway, self.max_tokens = store, gateway, max_tokens
        self._locks: OrderedDict[tuple[UUID, UUID], asyncio.Lock] = OrderedDict()

    async def create(self, request: DraftCreate, actor: ProfileActor) -> DraftView:
        return await asyncio.to_thread(self.store.create, request, actor)

    async def ask(
        self, draft: UUID, turn: ProfileTurn, actor: ProfileActor, *, on_event: EventSink | None = None
    ) -> ProfileReply:
        view = await asyncio.to_thread(self.store.get, draft, actor)
        request_hash = checksum(turn.model_dump_json().encode())
        cached = await asyncio.to_thread(self.store.cached_turn, draft, actor, turn.turn_id, request_hash)
        if cached:
            reply = ProfileReply.model_validate(cached)
            if view.revision != reply.revision:
                raise ProfileError("TURN_STALE", "旧回复对应的草稿已更新，请使用新turn_id继续", 409)
            reply.cached = True
            if on_event:
                await on_event(ProfileEvent(type="completed", reply=reply))
            return reply
        if view.revision != turn.expected_revision:
            raise ProfileError("VERSION_CONFLICT", "草稿修订已变化，请刷新后提问", 409)
        if not set(turn.attachment_ids).issubset({a.id for a in view.attachments}):
            raise ProfileError("IMAGE_NOT_FOUND", "本轮图片不属于当前草稿", 422)
        _, _, metadata = await asyncio.to_thread(self.store.snapshot, draft, actor, view.revision)
        if metadata.get("editor") and turn.intent != "discuss":
            raise ProfileError("PROPOSAL_REQUIRED", "请先提出修改建议，再由用户确认应用", 422)
        key = (actor.user_id, draft)
        if key not in self._locks:
            if len(self._locks) >= 128:
                old = next((item for item, lock in self._locks.items() if not lock.locked()), None)
                if old is None:
                    raise ProfileError("AGENT_BUSY", "规则助手会话繁忙", 429)
                del self._locks[old]
            self._locks[key] = asyncio.Lock()
        lock = self._locks[key]
        if lock.locked():
            raise ProfileError("DRAFT_BUSY", "当前草稿仍在处理上一轮请求", 409)
        self._locks.move_to_end(key)
        async with lock:
            tools = ProfileTools(self.store, draft, actor, turn)
            history = await asyncio.to_thread(self.store.history, draft, actor)
            # Fresh document facts supersede conversational memory on every turn.
            while len(history) > 2 and sum(len(item["content"]) for item in history) > 20000:
                history = history[2:]
            try:
                result = await build_profile_graph(
                    self.gateway, tools, on_event=on_event, max_tokens=self.max_tokens
                ).ainvoke({"messages": history}, config={"recursion_limit": 32})
                answer = result["answer"]
                limited = result.get("tool_limited", False)
            except Exception:
                if not tools.written and not tools.proposals:
                    raise
                # An already committed edit must remain visible even if final model narration fails.
                answer = (
                    "已提交本轮明确授权的草稿修改，模型总结未完成。请查看变更文件和校验结果；尚未发布。"
                    if tools.written
                    else "修改建议已保存，模型总结未完成。请查看before/after后确认或拒绝；草稿尚未修改。"
                )
                limited = True
            current = await asyncio.to_thread(self.store.get, draft, actor)
            if current.revision != tools.revision:
                raise ProfileError("VERSION_CONFLICT", "本轮期间草稿已被其他操作更新，请重新读取", 409)
            _, root, meta = await asyncio.to_thread(self.store.snapshot, draft, actor, tools.revision)
            report = await asyncio.to_thread(validate_draft, root, meta)
            reply = ProfileReply(
                draft_id=draft,
                turn_id=turn.turn_id,
                revision=current.revision,
                answer=answer,
                findings=tools.findings,
                proposals=tools.proposals,
                changed_files=sorted(set(tools.changed_files)),
                validation=report,
                tool_limited=limited,
                model_calls=tools.model_calls,
                viewed_images=sorted(tools.viewed),
            )
            await asyncio.to_thread(
                self.store.save_turn,
                draft,
                actor,
                turn.turn_id,
                request_hash,
                json.dumps(
                    {
                        "text": turn.message,
                        "attachment_ids": [str(i) for i in turn.attachment_ids],
                        "observations": turn.observations,
                    },
                    ensure_ascii=False,
                )
                if turn.attachment_ids or turn.observations
                else turn.message,
                reply.model_dump(mode="json"),
            )
            if on_event:
                await on_event(ProfileEvent(type="completed", reply=reply))
            return reply

    async def confirm(
        self, draft: UUID, proposal: UUID, revision: int, accepted: bool, actor: ProfileActor
    ) -> DraftView:
        return await asyncio.to_thread(self.store.confirm, draft, actor, proposal, revision, accepted)

    async def export(self, draft: UUID, revision: int, actor: ProfileActor) -> ExportReceipt:
        return await asyncio.to_thread(self._export, draft, revision, actor)

    def _export(self, draft: UUID, revision: int, actor: ProfileActor) -> ExportReceipt:
        view, root, meta = self.store.snapshot(draft, actor, revision)
        if (meta.get("source") or {}).get("read_only") == "true":
            raise ProfileError("PROFILE_READ_ONLY", "只读诊断草稿不能发布", 403)
        report = validate_draft(root, meta)
        if not report.ready:
            raise ProfileError(
                "PROFILE_INCOMPLETE",
                "规则包尚未就绪：" + "；".join(item.message for item in report.issues)[:2000],
                422,
            )
        manifest = ProfileManifest.model_validate_json((root / "profile.json").read_text(encoding="utf-8"))
        snapshot = ProfileSnapshot(
            manifest=manifest,
            profile_root=root,
            manifest_path=root / "profile.json",
            resolved_resources={name: root / value for name, value in manifest.resources.items()},
            checksum=view.checksum,
        )
        directory = self.store._path(f"{actor.user_id}/{draft}/exports/{revision}-{view.checksum[7:]}")
        directory.mkdir(parents=True, exist_ok=True)
        archive_path = self.store.file(directory, "profile.zip")
        receipt_path = self.store.file(directory, "receipt.json")
        if receipt_path.is_file():
            receipt = ExportReceipt.model_validate_json(receipt_path.read_text(encoding="utf-8"))
            if (
                receipt.archive_path != str(archive_path)
                or receipt.draft_id != draft
                or receipt.revision != revision
                or receipt.key != manifest.key
                or receipt.version != manifest.version
                or checksum(archive_path.read_bytes()) != receipt.checksum
            ):
                raise ProfileError("EXPORT_CHANGED", "导出文件已在工具外修改", 409)
            return receipt
        package = directory / f"package-{os.urandom(8).hex()}"
        inventory = build_package(snapshot, package)
        verify_package(package, inventory)
        # Canonical ZIP timestamps make re-export/recovery content-addressed.
        with tempfile.NamedTemporaryFile(dir=directory, suffix=".tmp", delete=False) as temporary:
            temporary_path = Path(temporary.name)
        with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(package.rglob("*")):
                if path.is_file():
                    info = zipfile.ZipInfo(
                        path.relative_to(package).as_posix(), date_time=(2020, 1, 1, 0, 0, 0)
                    )
                    info.compress_type = zipfile.ZIP_DEFLATED
                    archive.writestr(info, path.read_bytes())
        for attempt in range(3):
            try:
                os.replace(temporary_path, archive_path)
                break
            except PermissionError:
                if attempt == 2:
                    raise
                time.sleep(0.05 * (attempt + 1))
        receipt = ExportReceipt(
            draft_id=draft,
            revision=revision,
            key=manifest.key,
            version=manifest.version,
            checksum=checksum(archive_path.read_bytes()),
            archive_path=str(archive_path),
        )
        with tempfile.NamedTemporaryFile(
            dir=directory, suffix=".tmp", mode="w", encoding="utf-8", delete=False
        ) as temporary:
            temporary.write(receipt.model_dump_json(indent=2))
            temporary.flush()
            os.fsync(temporary.fileno())
            receipt_temporary = Path(temporary.name)
        os.replace(receipt_temporary, receipt_path)
        return receipt
