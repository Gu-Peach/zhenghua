"""Persistent guided authoring; a model may propose a candidate, never accept or publish it."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal, TypedDict
from uuid import UUID, uuid4

from langgraph.graph import END, START, StateGraph
from pydantic import Field, ValidationError

from src.agent.extraction_agent.infrastructure.document.model_images import prepare_vision_messages
from src.domain.models.common import StrictModel
from src.harness.model_gateway import ModelRequest
from src.profiles.package import checksum

from .models import PdfSampleInfo, ProfileActor, ProfileError
from .template import COMMON_POLICY
from .validation import validate_draft
from .wizard import (
    ORDER,
    ProfileWizard,
    Stage,
    StageCandidate,
    StageConfirm,
    StageGenerate,
    TargetImage,
    WizardState,
)

TITLES = {"classification": "拆分与页面分类", "scan": "本页提取", "completion": "跨页补全"}
QUESTIONS = {
    "classification": "请拖入图纸图片或PDF，我会对照实际样图说明工作区、业务页号和分页命名规则；"
    "PDF仅随机抽取两页。你可以补充或纠正。",
    "scan": "优先沿用已有样图识别放线标记、起点、同页终点和跨页引用；"
    "已有图无法说明接线时，再请补充包含标记的原图。",
    "completion": "请上传刚才原图对应的跨页目标图。我会核对业务页号、来源回指和实际终点，"
    "说明可核对的连接路径。",
}
CHAINS = {
    "classification": "读取样图标题栏 → 区分工作区、业务页号与PDF物理页 → 确定分组及命名映射。",
    "scan": "定位实际放线标记 → 沿两侧走线寻找直接端子 → 核对箭头方向 → 读取原理号、"
    "元件、电流及跨页引用；跨页终点暂留空。",
    "completion": "沿用已确认起点与引用 → 核对目标页身份和来源回指 → 沿对应接线找到终点；"
    "证据不足时留空，不改起点。",
}


class ConversationTurn(StrictModel):
    turn_id: UUID = Field(default_factory=uuid4)
    revision: int = Field(ge=1)
    message: str = Field(default="", max_length=8000)
    attachment_ids: list[UUID] = Field(default_factory=list, max_length=4)
    stage: Stage | None = None
    confirmation: StageConfirm | None = None


class ConversationMessage(StrictModel):
    id: UUID
    role: Literal["user", "assistant"]
    text: str
    stage: Stage
    attachment_ids: list[UUID] = Field(default_factory=list)
    created_at: str


class ConversationState(StrictModel):
    wizard: WizardState
    stage: Stage
    messages: list[ConversationMessage] = Field(default_factory=list)
    publish_ready: bool = False
    issues: list[str] = Field(default_factory=list)
    pdf_sample: PdfSampleInfo | None = None


class ConversationEvent(StrictModel):
    type: Literal["progress", "answer_delta", "completed"]
    turn_id: UUID
    message: str | None = None
    delta: str | None = None
    state: ConversationState | None = None


class DialogueDecision(StrictModel):
    reply: str = Field(min_length=1, max_length=5000)
    ready: bool = False
    description: str = Field(default="", max_length=8000)
    source_image: UUID | None = None
    targets: list[TargetImage] = Field(default_factory=list, max_length=4)
    negative_images: list[UUID] = Field(default_factory=list, max_length=3)
    action: Literal["continue", "revise_scan", "replace_scan_source"] = "continue"
    revision_stage: Stage | None = None


class TurnState(TypedDict, total=False):
    decision: DialogueDecision


EventSink = Callable[[ConversationEvent], Awaitable[None]]


class ProfileConversation:
    def __init__(self, wizard: ProfileWizard) -> None:
        self.wizard, self.store = wizard, wizard.store
        self._locks: dict[UUID, asyncio.Lock] = {}

    def state(self, draft: UUID, actor: ProfileActor) -> ConversationState:
        wizard = self.wizard.state(draft, actor)
        _, root, meta = self.store.snapshot(draft, actor, wizard.draft.revision)
        stage: Stage = next((s for s in ORDER if s not in wizard.confirmed), "completion")
        chat = meta.get("conversation", {})
        requested = chat.get("active_stage")
        if requested in ORDER and all(s in wizard.confirmed for s in ORDER[: ORDER.index(requested)]):
            stage = requested
        report = validate_draft(root, meta)
        return ConversationState(
            wizard=wizard,
            stage=stage,
            messages=chat.get("messages", []),
            publish_ready=report.ready,
            issues=[i.message for i in report.issues],
            pdf_sample=meta.get("latest_pdf_sample", meta.get("classification_pdf_sample")),
        )

    async def turn(
        self, draft: UUID, body: ConversationTurn, actor: ProfileActor, emit: EventSink | None = None
    ) -> ConversationState:
        # Ownership is checked before allocating a lock or accessing any stored transcript.
        await asyncio.to_thread(self.store.get, draft, actor)
        if len(self._locks) >= 128 and draft not in self._locks:
            idle = next((key for key, lock in self._locks.items() if not lock.locked()), None)
            if idle is None:
                raise ProfileError("AGENT_BUSY", "规则对话繁忙，请稍后重试", 429)
            del self._locks[idle]
        lock = self._locks.setdefault(draft, asyncio.Lock())
        if lock.locked():
            raise ProfileError("DRAFT_BUSY", "正在处理上一条消息，请稍候", 409)
        async with lock:
            return await self._turn(draft, body, actor, emit)

    async def _turn(
        self, draft: UUID, body: ConversationTurn, actor: ProfileActor, emit: EventSink | None
    ) -> ConversationState:
        current = await asyncio.to_thread(self.state, draft, actor)
        view, _, meta = await asyncio.to_thread(
            self.store.snapshot, draft, actor, current.wizard.draft.revision
        )
        fingerprint = checksum(body.model_dump_json().encode())
        chat = meta.get("conversation", {})
        receipt = chat.get("receipts", {}).get(str(body.turn_id))
        if receipt:
            if receipt["hash"] != fingerprint:
                raise ProfileError("OPERATION_CONFLICT", "同一消息标识的内容已变化", 409)
            if receipt["revision"] != view.revision:
                raise ProfileError("TURN_STALE", "该消息之后草稿已更新，请恢复最新对话", 409)
            if emit:
                await emit(ConversationEvent(type="completed", turn_id=body.turn_id, state=current))
            return current
        if view.revision != body.revision:
            raise ProfileError("VERSION_CONFLICT", "草稿已更新，请恢复对话后继续", 409)
        if not body.message.strip() and not body.attachment_ids and body.confirmation is None:
            raise ProfileError("MESSAGE_REQUIRED", "请输入说明或上传图片", 422)
        stage = body.stage or current.stage
        self.wizard.require_previous(meta, stage)
        known = {a.id: a for a in view.attachments}
        if not set(body.attachment_ids).issubset(known):
            raise ProfileError("IMAGE_NOT_FOUND", "只能使用当前草稿已上传的图片", 422)
        candidate = current.wizard.candidates.get(stage)
        last_user = next((m for m in reversed(current.messages) if m.role == "user"), None)
        confirmation = body.confirmation
        if body.attachment_ids and confirmation:
            raise ProfileError("CONFIRM_IMAGES_CHANGED", "新图片需要先读取核对，不能同时确认旧答案", 422)
        if (
            confirmation is None
            and not body.attachment_ids
            and candidate
            and last_user is not None
            and last_user.id == candidate.id
            and body.message.strip().strip("。！!")
            in {
                "确认",
                "没问题",
                "确认并继续",
                "确认本阶段",
                "同意",
                "都同意",
                "确认，同意",
                "确认,同意",
                "确认本阶段并保存",
            }
        ):
            confirmation = StageConfirm(
                revision=view.revision,
                candidate_id=candidate.id,
                rule_text=candidate.rule_text,
                expected=[c.expected for c in candidate.cases],
            )
        if confirmation and confirmation.revision != body.revision:
            raise ProfileError("VERSION_CONFLICT", "确认内容的修订与当前消息不一致", 409)
        answer = ""
        model_calls: list[dict[str, Any]] = []

        def record(metadata: dict[str, Any]) -> None:
            nonlocal answer
            if not confirmation:
                raw = metadata.get("wizard", {}).get("candidates", {}).get(stage)
                if raw and raw["id"] == str(body.turn_id):
                    evidence = []
                    for reading in raw.get("readings", [])[:4]:
                        if reading.get("summary"):
                            evidence.append(reading["summary"])
                        if reading.get("wire_marker"):
                            evidence.append("放线标记：" + reading["wire_marker"])
                        evidence.extend(reading.get("evidence_steps", [])[:6])
                    answer = (
                        f"### {TITLES[stage]}\n\n{answer}\n\n本阶段处理链路：{CHAINS[stage]}"
                        + (
                            "\n\n本次图纸依据：\n" + "\n".join(f"- {item}" for item in evidence)
                            if evidence else ""
                        )
                        + f"\n\n候选规则：\n{raw['rule_text']}\n\n"
                        "请核对规则和读图结果，可以直接提出修改意见；确认后才会继续，全部确认后可手动发布。"
                    )
            messages = [
                *chat.get("messages", []),
                ConversationMessage(
                    id=body.turn_id,
                    role="user",
                    text=body.message or "请读取这些图片",
                    stage=stage,
                    attachment_ids=body.attachment_ids,
                    created_at=datetime.now(timezone.utc).isoformat(),
                ).model_dump(mode="json"),
                ConversationMessage(
                    id=uuid4(),
                    role="assistant",
                    text=answer,
                    stage=stage,
                    created_at=datetime.now(timezone.utc).isoformat(),
                ).model_dump(mode="json"),
            ]
            receipts = dict(chat.get("receipts", {}))
            receipts[str(body.turn_id)] = {
                "hash": fingerprint,
                "revision": view.revision + 1,
                "model_calls": model_calls,
            }
            metadata["conversation"] = {
                "messages": messages[-120:],
                "receipts": dict(list(receipts.items())[-120:]),
                "active_stage": ORDER[min(ORDER.index(stage) + 1, 2)] if confirmation else stage,
            }

        if confirmation:
            if candidate is None:
                raise ProfileError("CANDIDATE_REQUIRED", "请先让我读取图片并生成候选", 409)
            next_index = ORDER.index(stage) + 1
            answer = f"已保存{TITLES[stage]}规则和人工确认的 Expected JSON。\n\n" + (
                QUESTIONS[ORDER[next_index]]
                if next_index < len(ORDER)
                else "三个阶段均已确认。请检查发布校验结果，准备好后点击发布规则。"
            )
            if stage == "scan" and not self._has_cross_page_tasks(candidate):
                answer = (
                    "已保存修正后的本页提取规则和 Expected JSON。当前样例没有跨页引用，"
                    "这些同页连接无需再提供目标图。若要继续建立第三阶段规则，请在第二阶段"
                    "补充一个真实含跨页引用的原图样例，再提供其对应目标页。"
                )
            await asyncio.to_thread(self.wizard.confirm, draft, stage, confirmation, actor, record=record)
        else:
            if emit:
                await emit(
                    ConversationEvent(
                        type="progress",
                        turn_id=body.turn_id,
                        message="正在读取对话与样图，判断还需补充哪些信息…",
                    )
                )

            async def decide(_: TurnState) -> dict[str, Any]:
                decision = await self._decide(draft, body, actor, current, stage, model_calls)
                return {"decision": decision}

            async def save(state: TurnState) -> dict[str, Any]:
                nonlocal answer, stage
                decision = state["decision"]
                answer = decision.reply
                if decision.revision_stage:
                    self.wizard.require_previous(meta, decision.revision_stage)
                    stage = decision.revision_stage
                revision_context: dict[str, Any] | None = None
                previous_scan = current.wizard.candidates.get("scan")
                previous_source = previous_scan.cases[0].images[0].attachment_id if previous_scan else None
                replacing_source = bool(
                    previous_source
                    and decision.source_image != previous_source
                    and decision.source_image in self._source_uploads(current, body)
                    and decision.source_image not in {t.attachment_id for t in decision.targets}
                )
                revise = decision.action in {"revise_scan", "replace_scan_source"}
                if revise or (stage in {"scan", "completion"} and replacing_source and decision.ready):
                    if stage == "completion" and previous_scan and "scan" in current.wizard.confirmed:
                        stage = "scan"
                        decision.ready = True
                    elif stage != "scan":
                        raise ProfileError(
                            "SCAN_CORRECTION_UNAVAILABLE", "尚无可修正的已确认初扫，请先完成前序阶段", 409
                        )
                    if decision.action == "replace_scan_source" and not replacing_source:
                        raise ProfileError(
                            "SOURCE_IMAGE_REQUIRED", "请明确选择本轮或此前提取对话中上传的新原页", 422
                        )
                    if previous_scan:
                        decision.targets = []
                        if not replacing_source:
                            decision.source_image = previous_source
                        decision.negative_images = (
                            []
                            if replacing_source
                            else (previous_scan.request.negative_images if previous_scan.request else [])
                        )
                        revision_context = {
                            "source_replacement": replacing_source,
                            "previous_expected": None
                            if replacing_source
                            else previous_scan.cases[0].expected,
                            "user_feedback": self._source_feedback(current, body, decision.source_image)
                            if replacing_source
                            else self._user_feedback(current, body),
                            "instruction": "用户更换了原页，仅依据新原图和本次样例说明重新初扫；"
                            "不得继承旧图页号、端子、引用或坐标，先生成候选供重新确认。"
                            if replacing_source
                            else "用户正在纠正原初扫判断。基于原图与用户原话生成修正候选，"
                            "保留未被纠正的事实。若终点确实在本页，填写end并移除误判的跨页引用，"
                            "不要再次要求用户确认同一事实或上传同一原图。",
                        }
                        answer = (
                            "已更换原页，返回第二阶段重新生成初扫候选。请先核对并确认新原页结果，再使用已上传的目标图补全。"
                            if replacing_source
                            else "已根据你的纠正返回第二阶段，用已有原图重新核对并生成修正候选，"
                            "请核对下方结果。"
                        )
                if decision.ready:
                    sample_images: list[UUID] = []
                    if stage == "classification":
                        sample_images = list(body.attachment_ids)
                        if not sample_images and current.pdf_sample and current.pdf_sample.stage == stage:
                            sample_images = [p.attachment_id for p in current.pdf_sample.pages]
                        if not sample_images:
                            existing = current.wizard.candidates.get(stage)
                            sample_images = (
                                list(existing.request.sample_images) if existing and existing.request else []
                            )
                        if not sample_images and stage not in current.wizard.candidates:
                            sample_images = [image.id for image in current.wizard.draft.attachments[-4:]]
                        sample_images = [i for i in sample_images if i not in decision.negative_images][:4]
                        if sample_images:
                            decision.source_image = sample_images[0]
                        decision.negative_images = [
                            i for i in decision.negative_images if i not in sample_images
                        ]
                    if stage == "completion":
                        scan = current.wizard.candidates["scan"]
                        # Source replacement must first rebuild and confirm scan, never silently complete.
                        decision.source_image = scan.cases[0].images[0].attachment_id
                        if not self._has_cross_page_tasks(scan):
                            decision.ready = False
                            answer = (
                                "已确认的初扫结果没有跨页引用，暂时无法生成补全任务。"
                                "如果你已更换原页，请说明哪张是新原页，我会返回第二阶段重新初扫；"
                                "确认新初扫中的跨页引用后，再使用已上传的目标图补全。"
                            )
                        elif not decision.targets:
                            decision.ready = False
                            answer += "\n\n请上传对应跨页图，并说明标题栏中的工作区和业务页号。"
                    if decision.ready and not decision.source_image:
                        decision.ready = False
                        answer += "\n\n还需要确定用于读取的原图，请说明哪张是原页；已有图片无需重复上传。"
                        logging.getLogger(__name__).warning(
                            "Profile decision needs source clarification stage=%s attachments=%s",
                            stage, len(body.attachment_ids),
                        )
                    if decision.ready and not decision.description.strip():
                        parts = [f"当前读取目标：{QUESTIONS[stage]}"]
                        if body.message.strip():
                            parts.append("用户本轮说明：\n" + body.message.strip()[:6000])
                        existing = current.wizard.candidates.get(stage)
                        if existing and existing.cases[0].images[0].attachment_id == decision.source_image:
                            parts.append("同一原图的既有读取说明：\n" + existing.description[:1400])
                        decision.description = "\n\n".join(parts)[:8000]
                        logging.getLogger(__name__).warning(
                            "Profile decision recovered missing=description stage=%s attachments=%s",
                            stage, len(body.attachment_ids),
                        )
                        model_calls[-1]["recovered_fields"] = ["description"]
                    if decision.ready and decision.source_image is not None:
                        if emit:
                            await emit(
                                ConversationEvent(
                                    type="progress",
                                    turn_id=body.turn_id,
                                    message=f"信息已齐，正在生成{TITLES[stage]}规则、读图结果及证据说明…",
                                )
                            )
                        await self.wizard.generate(
                            draft,
                            stage,
                            StageGenerate(
                                revision=view.revision,
                                request_id=body.turn_id,
                                description=decision.description,
                                source_image=decision.source_image,
                                sample_images=sample_images,
                                targets=decision.targets,
                                negative_images=decision.negative_images,
                            ),
                            actor,
                            record=record,
                            revision_context=revision_context,
                        )
                        return {}
                await asyncio.to_thread(
                    self.store.mutate,
                    draft,
                    actor,
                    view.revision,
                    f"conversation:{body.turn_id}",
                    lambda _root, metadata: self._save_record(metadata, record),
                    fingerprint,
                )
                return {}

            graph = StateGraph(TurnState)
            graph.add_node("understand_and_ask", decide)
            graph.add_node("generate_or_record", save)
            graph.add_edge(START, "understand_and_ask")
            graph.add_edge("understand_and_ask", "generate_or_record")
            graph.add_edge("generate_or_record", END)
            await graph.compile().ainvoke({})
        result = await asyncio.to_thread(self.state, draft, actor)
        if emit:
            for offset in range(0, len(answer), 40):
                await emit(
                    ConversationEvent(
                        type="answer_delta", turn_id=body.turn_id, delta=answer[offset : offset + 40]
                    )
                )
            await emit(ConversationEvent(type="completed", turn_id=body.turn_id, state=result))
        return result

    @staticmethod
    def _save_record(metadata: dict[str, Any], record: Callable[[dict[str, Any]], None]) -> dict[str, Any]:
        record(metadata)
        return {"action": "conversation_message"}

    @staticmethod
    def _has_cross_page_tasks(candidate: StageCandidate | None) -> bool:
        return bool(
            candidate
            and any(
                connection.get("references")
                for unit in candidate.cases[0].expected.get("units", [])
                for connection in unit.get("connections", [])
            )
        )

    @classmethod
    def _user_feedback(cls, current: ConversationState, body: ConversationTurn) -> list[str]:
        scan = current.wizard.candidates.get("scan")
        if scan:
            return cls._source_feedback(current, body, scan.cases[0].images[0].attachment_id)
        return [m.text for m in current.messages if m.role == "user" and m.stage in {"scan", "completion"}][
            -16:
        ] + [body.message]

    @staticmethod
    def _source_uploads(current: ConversationState, body: ConversationTurn) -> set[UUID]:
        """Only user-supplied extraction images may replace an accepted scan source."""
        supplied = {
            image
            for message in current.messages
            if message.role == "user" and message.stage in {"scan", "completion"}
            for image in message.attachment_ids
        } | set(body.attachment_ids)
        return {a.id for a in current.wizard.draft.attachments if a.id in supplied}

    @staticmethod
    def _source_feedback(
        current: ConversationState, body: ConversationTurn, source: UUID | None
    ) -> list[str]:
        """Do not carry a previous drawing's corrections into a replacement scan."""
        if source in body.attachment_ids:
            return [body.message]
        messages = [m for m in current.messages if m.role == "user" and m.stage in {"scan", "completion"}]
        start = next(
            (i for i in range(len(messages) - 1, -1, -1) if source in messages[i].attachment_ids),
            len(messages),
        )
        return [m.text for m in messages[start:]][-16:] + [body.message]

    async def _decide(
        self,
        draft: UUID,
        body: ConversationTurn,
        actor: ProfileActor,
        current: ConversationState,
        stage: Stage,
        model_calls: list[dict[str, Any]],
    ) -> DialogueDecision:
        candidate = current.wizard.candidates.get(stage)
        selected = list(body.attachment_ids)
        prior_images = [
            image
            for message in reversed(current.messages)
            if message.role == "user"
            and (
                message.stage == stage
                or stage in {"scan", "completion"}
                and message.stage in {"scan", "completion"}
            )
            for image in message.attachment_ids
        ]
        selected = list(dict.fromkeys([*selected, *prior_images]))[:4]
        if not selected and stage == "classification" and not candidate:
            # An interrupted first read may leave valid uploads but no persisted chat turn.
            selected = [image.id for image in current.wizard.draft.attachments[-4:]]
        classification = current.wizard.candidates.get("classification")
        if stage == "scan" and classification:
            reusable = [image.attachment_id for case in classification.cases for image in case.images]
            selected = list(dict.fromkeys(
                [*selected, *reusable] if candidate or body.attachment_ids else [*reusable, *selected]
            ))[:4]
        if candidate and candidate.request:
            selected = list(
                dict.fromkeys(
                    [
                        *selected,
                        candidate.request.source_image,
                        *(t.attachment_id for t in candidate.request.targets),
                    ]
                )
            )[:4]
        if stage == "completion":
            source = current.wizard.candidates["scan"].cases[0].images[0].attachment_id
            selected = list(dict.fromkeys([source, *selected]))[:5]
        if (
            stage == "classification" and not body.attachment_ids
            and current.pdf_sample and current.pdf_sample.stage == stage
        ):
            selected = list(dict.fromkeys([*(p.attachment_id for p in current.pdf_sample.pages), *selected]))[
                :4
            ]
        attachments = current.wizard.draft.attachments
        lookup = {a.id: a for a in attachments}
        pixels = await asyncio.to_thread(self.store.images, draft, actor, [lookup[i].path for i in selected])
        context = {
            "stage": stage,
            "stage_goal": QUESTIONS[stage],
            "user_message": body.message,
            "new_image_ids": [str(i) for i in body.attachment_ids],
            "attachments": [
                {"id": str(a.id), "filename": a.filename, "origin": a.origin}
                for a in attachments
            ],
            "current_candidate": candidate.model_dump(mode="json") if candidate else None,
            "pdf_sample": current.pdf_sample.model_dump(mode="json")
            if current.pdf_sample
            else None,
            "confirmed_classification": classification.model_dump(mode="json") if classification else None,
            "confirmed_scan": current.wizard.candidates["scan"].model_dump(mode="json")
            if stage == "completion"
            else None,
            "history": [m.model_dump(mode="json") for m in current.messages[-12:]],
            "user_feedback": self._user_feedback(current, body) if stage in {"scan", "completion"} else [],
            "completion_has_tasks": self._has_cross_page_tasks(current.wizard.candidates.get("scan")),
            "replacement_source_ids": [str(i) for i in selected if i in self._source_uploads(current, body)],
        }
        content: list[dict[str, Any]] = [{"type": "text", "text": json.dumps(context, ensure_ascii=False)}]
        for image_id, image in zip(selected, pixels, strict=True):
            content.extend(
                [
                    {"type": "text", "text": f"图片ID：{image_id}"},
                    {"type": "image_url", "image_url": {"url": image["data_url"]}},
                ]
            )
        system = (Path(__file__).parent / "prompts" / "conversation.md").read_text(encoding="utf-8")
        messages, _ = await asyncio.to_thread(
            prepare_vision_messages,
            [
                {
                    "role": "system",
                    "content": COMMON_POLICY
                    + "\n"
                    + system
                    + "\n输出JSON Schema："
                    + json.dumps(DialogueDecision.model_json_schema(), ensure_ascii=False),
                },
                {"role": "user", "content": content},
            ],
            input_max_side=2048,
            max_total_pixels=6_000_000,
            few_shot_min_side=768,
        )
        response = await self.wizard.agent.gateway.invoke(
            ModelRequest(
                agent_name="profile_agent",
                run_id=f"profile-conversation:{body.turn_id}",
                messages=messages,
                output_model=DialogueDecision,
                max_tokens=self.wizard.agent.max_tokens,
                metadata={"operation": "conversation_decide", "stage": stage, "revision": body.revision},
            )
        )
        model_calls.append(
            {
                "model": response.model,
                "duration_seconds": response.duration_seconds,
                "attempts": response.attempts,
                "usage": response.usage,
                "stage": stage,
                "input_images": [str(i) for i in selected],
                "prompt_checksum": checksum(system.encode()),
            }
        )
        if response.finish_reason == "length":
            raise ProfileError("MODEL_TRUNCATED", "规则对话输出被截断，请缩小样图范围后重试", 502)
        try:
            decision = (
                DialogueDecision.model_validate(response.parsed)
                if response.parsed
                else DialogueDecision.model_validate_json(response.content)
            )
        except ValidationError as exc:
            raise ProfileError("MODEL_SCHEMA_INVALID", "规则对话返回格式不正确，请重试", 502) from exc
        identifiers = {
            image
            for image in [
                decision.source_image,
                *decision.negative_images,
                *(t.attachment_id for t in decision.targets),
            ]
            if image is not None
        }
        if not identifiers.issubset(lookup):
            raise ProfileError("IMAGE_NOT_FOUND", "模型引用的图片不属于当前草稿，请重新选择图片", 422)
        effective_stage = decision.revision_stage or stage
        if (
            effective_stage == "scan" and body.attachment_ids and decision.source_image
            and decision.source_image not in body.attachment_ids
            and decision.action != "revise_scan"
        ):
            decision.ready = False
            decision.reply = "请以本轮新上传的原图为准，我需要重新核对来源图片。"
        if (
            effective_stage in {"scan", "completion"}
            and decision.source_image is not None
            and decision.source_image not in selected
            and (effective_stage == "scan" or decision.source_image in self._source_uploads(current, body))
        ):
            decision.ready = False
            decision.action = "continue"
            decision.reply = QUESTIONS[stage]
        if decision.ready and not selected:
            decision.ready = False
            decision.reply = QUESTIONS[stage]
        return decision
