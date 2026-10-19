"""Guided authoring evidence and confirmation boundaries; no live model or database."""

from __future__ import annotations

import asyncio
import base64
from uuid import uuid4

import pytest

from src.agent.profile_agent.conversation import ConversationTurn
from src.agent.profile_agent.models import PdfSampleRequest, ProfileError
from src.agent.profile_agent.pdf_sampling import PdfSamplingTool
from tests.unit.test_profile_conversation import attach, classify, reply, send
from tests.unit.test_profile_conversation import ctx as ctx
from tests.unit.test_profile_pdf_sampling import pdf_bytes


def test_manual_classification_images_each_get_an_expected_and_public_chain(ctx):
    first, second = attach(ctx, "one.png"), attach(ctx, "two.png")
    gateway = reply(
        ctx,
        {
            "reply": "两页标题栏位置相同",
            "ready": True,
            "description": "按标题栏识别",
            "source_image": str(first),
        },
        {
            "rule_text": "标题栏Function为工作区",
            "expected": {"plant_function": "C", "drawing_page_number": 1},
            "reading_summary": "第一页右下C/1",
            "evidence_steps": ["在右下读取页号1"],
        },
        {
            "rule_text": "标题栏Function为工作区",
            "expected": {"plant_function": "C", "drawing_page_number": 2},
            "reading_summary": "第二页右下C/2",
            "evidence_steps": ["在右下读取页号2"],
        },
    )
    state = send(ctx, "自动制定分页规则", [first, second])
    candidate = state.wizard.candidates["classification"]
    assert [case.expected["drawing_page_number"] for case in candidate.cases] == [1, 2]
    assert state.stage == "classification" and not state.wizard.confirmed
    assert "本阶段处理链路" in state.messages[-1].text
    assert "第一页右下C/1" in state.messages[-1].text and "第二页右下C/2" in state.messages[-1].text
    assert len(gateway.calls) == 3


def test_ready_with_images_but_no_internal_description_generates_and_retries_idempotently(ctx):
    first, second = attach(ctx, "source.png"), attach(ctx, "target.png")
    gateway = reply(
        ctx,
        {"reply": "收到原页和对应目标页，先读取标题栏", "ready": True},
        {
            "rule_text": "按图中标题栏识别业务页",
            "expected": {"plant_function": "C", "drawing_page_number": 1},
        },
        {
            "rule_text": "按图中标题栏识别业务页",
            "expected": {"plant_function": "C", "drawing_page_number": 2},
        },
    )
    agent, chat, actor, draft, _ = ctx
    body = ConversationTurn(
        turn_id=uuid4(),
        revision=agent.store.get(draft, actor).revision,
        message="这是一份原页及其对应的目标页",
        attachment_ids=[first, second],
    )
    result = asyncio.run(chat.turn(draft, body, actor))
    candidate = result.wizard.candidates["classification"]
    assert body.message in candidate.description
    assert len(candidate.cases) == 2 and not result.wizard.confirmed
    assert "本阶段处理链路" in result.messages[-1].text
    assert asyncio.run(chat.turn(draft, body, actor)) == result
    assert len(gateway.calls) == 3


def test_ready_without_a_resolvable_source_asks_and_persists_instead_of_throwing(ctx):
    image, _ = classify(ctx)
    send(ctx, "确认")
    reply(ctx, {"reply": "还需确认来源", "ready": True, "description": "读取来源接线"})
    result = send(ctx, "请继续提取", stage="scan")
    assert "scan" not in result.wizard.candidates
    assert result.messages[-1].text.strip()
    assert "原图" in result.messages[-1].text
    restored = ctx[1].state(ctx[3], ctx[2])
    assert restored.messages == result.messages


def test_not_ready_with_real_images_keeps_the_question_without_generating(ctx):
    image = attach(ctx)
    gateway = reply(ctx, {"reply": "标题栏模糊，请补充清晰图片", "ready": False})
    result = send(ctx, "这张图能识别吗", [image])
    assert not result.wizard.candidates
    assert result.messages[-1].text == "标题栏模糊，请补充清晰图片"
    assert len(gateway.calls) == 1


@pytest.mark.parametrize("question_first", [False, True])
def test_restore_after_failed_first_read_reuses_existing_uploads_without_reupload(ctx, question_first):
    first, second = attach(ctx, "source.png"), attach(ctx, "target.png")
    gateway = reply(
        ctx,
        *([{"reply": "请说明两张图的用途", "ready": False}] if question_first else []),
        {"reply": "用已保存的两张图先识别分页", "ready": True},
        {"rule_text": "标题栏读取页1", "expected": {"plant_function": "C", "drawing_page_number": 1}},
        {"rule_text": "标题栏读取页2", "expected": {"plant_function": "C", "drawing_page_number": 2}},
    )
    if question_first:
        waiting = send(ctx, "继续")
        assert not waiting.wizard.candidates
    result = send(ctx, "继续处理已上传的原页和目标页")
    assert result.wizard.candidates["classification"].request.sample_images == [first, second]
    content = gateway.calls[0].messages[-1]["content"]
    assert sum(item.get("type") == "image_url" for item in content) == 2
    assert len(result.wizard.draft.attachments) == 2


def test_completion_without_description_or_source_uses_frozen_source(ctx):
    source, _ = classify(ctx)
    send(ctx, "确认")
    reply(
        ctx,
        {"reply": "识别来源接线", "ready": True, "source_image": str(source), "description": "沿标记读取"},
        {
            "rule_text": "按标记读取来源和引用",
            "expected": {
                "drawing_function": "002.C",
                "drawing_page_number": 3,
                "units": [
                    {
                        "unit_id": "u1",
                        "connections": [
                            {
                                "line_number": "002C0311",
                                "start": {"terminal": "X3:51"},
                                "references": [
                                    {
                                        "raw": "=080.C/42",
                                        "target_function": "080.C",
                                        "target_drawing_page": 42,
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
        },
    )
    send(ctx, "继续读取来源", stage="scan")
    accepted = send(ctx, "确认", stage="scan")
    frozen = accepted.wizard.candidates["scan"].cases[0].expected
    target = attach(ctx, "target.png")
    reply(
        ctx,
        {
            "reply": "匹配目标回指后补全",
            "ready": True,
            "targets": [
                {"attachment_id": str(target), "function": "080.C", "page": 42},
            ],
        },
        {
            "rule_text": "匹配回指后沿线读终点",
            "expected": {
                "task_id": "wizard-0-0-0",
                "end": {"terminal": "XD21:60"},
            },
        },
    )
    result = send(ctx, "这是对应的目标页", [target], stage="completion")
    candidate = result.wizard.candidates["completion"]
    assert candidate.request.source_image == source
    assert candidate.cases[0].expected["end"]["terminal"] == "XD21:60"
    assert result.wizard.candidates["scan"].cases[0].expected == frozen
    assert "completion" not in result.wizard.confirmed


def test_pdf_can_be_uploaded_for_scan_and_reused_after_classification(ctx):
    agent, _, actor, draft, _ = ctx
    classify(ctx)
    confirmed = send(ctx, "确认")
    before = confirmed.wizard.confirmed.copy()
    body = PdfSampleRequest(
        revision=confirmed.wizard.draft.revision,
        stage="scan",
        filename="接线.pdf",
        content_base64=base64.b64encode(pdf_bytes(2)).decode(),
    )
    sampled = PdfSamplingTool(agent.store).sample(draft, body, actor)
    state = ctx[1].state(draft, actor)
    assert state.wizard.confirmed == before and state.stage == "scan"
    assert state.pdf_sample.stage == "scan"
    image = sampled.sample.pages[0].attachment_id
    reply(
        ctx,
        {
            "reply": "这页有可见放线标记",
            "ready": True,
            "description": "按斜线沿线找端子",
            "source_image": str(image),
        },
        {
            "rule_text": "斜线定位后沿两侧读端子",
            "expected": {"units": []},
            "reading_summary": "该页没有确认的来源记录",
            "evidence_steps": ["不凭空添加端子"],
        },
    )
    result = send(ctx, "请根据PDF样图生成提取规则", [image], stage="scan")
    assert result.wizard.candidates["scan"].request.source_image == image
    assert result.wizard.candidates["scan"].cases[0].input["source_pdf_page_number"] == (
        sampled.sample.pages[0].pdf_page_number
    )
    assert result.wizard.confirmed == before
    assert "定位实际放线标记" in result.messages[-1].text
    assert not list(agent.store.root.rglob("*.pdf"))


def test_next_scan_can_reuse_confirmed_classification_image(ctx):
    image, _ = classify(ctx)
    send(ctx, "确认")
    gateway = reply(
        ctx,
        {
            "reply": "沿用已有图片生成提取规则",
            "ready": True,
            "description": "沿斜线标记读取接线",
            "source_image": str(image),
        },
        {"rule_text": "先定位标记再沿线找端子", "expected": {"units": []}},
    )
    result = send(ctx, "上一阶段已确认，请自动生成当前规则", stage="scan")
    assert result.wizard.candidates["scan"].request.source_image == image
    assert "classification" in result.wizard.confirmed and "scan" not in result.wizard.confirmed
    content = gateway.calls[0].messages[-1]["content"]
    assert any(item.get("type") == "image_url" for item in content)


def test_user_can_revise_previous_classification_without_stage_tabs(ctx):
    image, _ = classify(ctx)
    send(ctx, "确认")
    reply(
        ctx,
        {
            "reply": "回到分页规则修正",
            "ready": True,
            "revision_stage": "classification",
            "description": "按用户纠正读取业务页5",
            "source_image": str(image),
        },
        {"rule_text": "业务页号读取5", "expected": {"plant_function": "002.C", "drawing_page_number": 5}},
    )
    result = send(ctx, "刚才分页有误，业务页应为5", stage="scan")
    assert result.stage == "classification" and not result.wizard.confirmed
    assert result.wizard.candidates["classification"].cases[0].expected["drawing_page_number"] == 5


def test_pdf_cannot_skip_unconfirmed_previous_stage(ctx):
    agent, _, actor, draft, _ = ctx
    body = PdfSampleRequest(
        revision=agent.store.get(draft, actor).revision,
        stage="completion",
        filename="target.pdf",
        content_base64=base64.b64encode(pdf_bytes(1)).decode(),
    )
    with pytest.raises(ProfileError, match="先确认"):
        PdfSamplingTool(agent.store).sample(draft, body, actor)
    assert not agent.store.get(draft, actor).attachments
