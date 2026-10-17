from __future__ import annotations

import asyncio
import json
from uuid import uuid4

import httpx
import pymupdf
import pytest

from src.agent.profile_agent import DraftCreate, ProfileActor, create_profile_agent
from src.agent.profile_agent.conversation import ConversationTurn, ProfileConversation
from src.agent.profile_agent.models import ProfileError
from src.agent.profile_agent.wizard import ProfileWizard, StageConfirm
from src.config import AgentSettings
from src.harness.model_gateway import FakeModelGateway


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("No network in profile conversation tests")

    monkeypatch.setattr(httpx.AsyncClient, "request", forbidden)
    gateway = FakeModelGateway([])
    agent = create_profile_agent(AgentSettings(), state_root=tmp_path / "drafts", gateway=gateway)
    actor = ProfileActor(user_id=uuid4())
    draft = asyncio.run(agent.create(DraftCreate(key="conversational", display_name="对话规则"), actor))
    return agent, ProfileConversation(ProfileWizard(agent)), actor, draft.draft_id, gateway


def reply(ctx, *answers):
    # Use a fresh fake with a deterministic sequence; no paid model is permitted.
    ctx[0].gateway = FakeModelGateway([json.dumps(a, ensure_ascii=False) for a in answers])
    return ctx[0].gateway


def attach(ctx, name="drawing.png"):
    agent, _, actor, draft, _ = ctx
    image = uuid4()
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 80, 60))
    pix.clear_with(255)
    agent.store.attach(draft, actor, agent.store.get(draft, actor).revision, image, name, pix.tobytes("png"))
    return image


def send(ctx, text, images=(), **kwargs):
    agent, chat, actor, draft, _ = ctx
    return asyncio.run(
        chat.turn(
            draft,
            ConversationTurn(
                revision=agent.store.get(draft, actor).revision,
                message=text,
                attachment_ids=list(images),
                **kwargs,
            ),
            actor,
        )
    )


def classify(ctx):
    image = attach(ctx)
    reply(
        ctx,
        {
            "reply": "我理解标题栏工作区为002.C、业务页号3，请核对。",
            "ready": True,
            "description": "标题栏读取功能区和业务页号",
            "source_image": str(image),
        },
        {
            "rule_text": "标题栏工作区和图号末尾读业务页",
            "expected": {"plant_function": "002.C", "drawing_page_number": 3},
            "reading_summary": "右下标题栏为002.C/3",
            "evidence_steps": ["标题栏读取工作区002.C", "图号读取业务页3"],
        },
    )
    state = send(ctx, "先读这张图", [image])
    return image, state


def test_missing_image_asks_without_generating_and_history_survives_restart(ctx):
    gateway = reply(ctx, {"reply": "请上传标题栏样图，我会判断工作区和页号。"})
    state = send(ctx, "帮我制定分页规则")
    assert not state.wizard.candidates and len(state.messages) == 2
    assert len(gateway.calls) == 1
    restored = ProfileConversation(ProfileWizard(ctx[0])).state(ctx[3], ctx[2])
    assert restored.messages == state.messages


def test_reading_candidate_requires_explicit_confirmation_and_caches_retry(ctx):
    _, state = classify(ctx)
    assert not state.wizard.confirmed and state.stage == "classification"
    assert state.wizard.candidates["classification"].readings[0].evidence_steps
    draft = state.wizard.draft
    body = ConversationTurn(revision=draft.revision, message="没问题")
    done = asyncio.run(ctx[1].turn(ctx[3], body, ctx[2]))
    assert done.stage == "scan" and "classification" in done.wizard.confirmed
    again = asyncio.run(ctx[1].turn(ctx[3], body, ctx[2]))
    assert again == done
    with pytest.raises(ProfileError, match="内容已变化"):
        asyncio.run(ctx[1].turn(ctx[3], body.model_copy(update={"message": "不同内容"}), ctx[2]))


def test_followup_keeps_uploaded_pixels_and_integrates_user_correction(ctx):
    image = attach(ctx)
    gateway = reply(
        ctx,
        {"reply": "看到了标题栏，业务页号后两位是否是3？"},
        {
            "reply": "已理解你的补充，先生成候选。",
            "ready": True,
            "description": "右下标题栏工作区002.C，业务页号3，按功能区建目录",
            "source_image": str(image),
        },
        {
            "rule_text": "按功能区和图号后三位组织分页",
            "expected": {"plant_function": "002.C", "drawing_page_number": 3},
        },
    )
    state = send(ctx, "这张图标题栏在右下", [image])
    assert not state.wizard.candidates
    state = send(ctx, "是3，按功能区建目录")
    assert state.wizard.candidates["classification"].request.source_image == image
    assert "标题栏在右下" in json.dumps(gateway.calls[1].messages, ensure_ascii=False)
    assert any(item.get("type") == "image_url" for item in gateway.calls[1].messages[-1]["content"])
    assert "按功能区建目录" in state.wizard.candidates["classification"].description


def test_yes_after_a_question_is_not_confirmation_of_an_older_candidate(ctx):
    classify(ctx)
    reply(
        ctx,
        {"reply": "你希望业务页号去掉前导零吗？"},
        {"reply": "我会将这个补充纳入读取规则，请再核对候选。"},
    )
    send(ctx, "业务页号要怎么处理？")
    state = send(ctx, "没问题")
    assert not state.wizard.confirmed


def test_three_stages_corrections_frozen_source_and_expected_files(ctx):
    source, state = classify(ctx)
    send(ctx, "确认")
    scan_image = attach(ctx)
    scan = {
        "drawing_function": "002.C",
        "drawing_page_number": 3,
        "units": [
            {
                "unit_id": "u1",
                "connections": [
                    {
                        "line_number": "002C0311",
                        "start": {"terminal": "X3:51"},
                        "end": {"terminal": "wrong"},
                        "references": [
                            {"raw": "=080.C/42", "target_function": "080.C", "target_drawing_page": 42}
                        ],
                    }
                ],
            }
        ],
    }
    reply(
        ctx,
        {
            "reply": "识别到斜线标记和跨页引用。",
            "ready": True,
            "description": "斜线放线，箭头确定来源",
            "source_image": str(scan_image),
        },
        {
            "rule_text": "按斜线放线标记沿线读取端子",
            "expected": scan,
            "wire_marker": "原图上方导线的一道斜线",
            "evidence_steps": ["斜线标记沿线到X3:51", "箭头旁引用080.C/42"],
        },
    )
    state = send(ctx, "这张是初扫原图", [scan_image])
    candidate = state.wizard.candidates["scan"]
    assert candidate.cases[0].expected["units"][0]["connections"][0]["end"] is None
    assert "斜线" in candidate.readings[0].wire_marker
    # User can correct the structured candidate before authorizing the stage.
    candidate.cases[0].expected["units"][0]["connections"][0]["start"]["terminal"] = "X3:75"
    state = send(
        ctx,
        "我已核对并修正起点",
        confirmation=StageConfirm(
            revision=state.wizard.draft.revision,
            candidate_id=candidate.id,
            rule_text=candidate.rule_text,
            expected=[c.expected for c in candidate.cases],
        ),
    )
    assert state.stage == "completion"
    target = attach(ctx, "target.png")
    reply(
        ctx,
        {
            "reply": "目标标题栏是080.C/42，将核对来源回指。",
            "ready": True,
            "description": "按回指沿线找最近终点",
            "source_image": str(source),
            "targets": [{"attachment_id": str(target), "function": "080.C", "page": 42}],
        },
        {
            "rule_text": "先匹配回指再沿线读端子",
            "expected": {"end": {"terminal": "XD21:60"}},
            "reading_summary": "原页引用080.C/42，目标页回指相符，沿线读到XD21:60",
            "evidence_steps": ["来源端X3:75引用080.C/42", "目标回指原页，终端XD21:60"],
        },
    )
    state = send(ctx, "这是对应跨页图", [target])
    completion = state.wizard.candidates["completion"]
    assert completion.request.source_image == scan_image
    assert completion.cases[0].input["source_connection"]["start"]["terminal"] == "X3:75"
    state = send(ctx, "确认并继续")
    assert len(state.wizard.confirmed) == 3
    assert any("expected.json" in path for path in state.wizard.draft.files)
    # All actual examples are positive; optional negatives must not prevent export.
    assert state.publish_ready and not state.issues
    receipt = asyncio.run(ctx[0].export(ctx[3], state.wizard.draft.revision, ctx[2]))
    assert receipt.checksum and not receipt.published


def test_model_cannot_confirm_or_reference_foreign_images(ctx):
    reply(
        ctx,
        {
            "reply": "模型说已确认也不会自动确认。",
            "ready": True,
            "description": "错误ID",
            "source_image": str(uuid4()),
        },
    )
    with pytest.raises(ProfileError, match="不属于当前草稿"):
        send(ctx, "开始")
    assert not ctx[1].state(ctx[3], ctx[2]).wizard.confirmed
    with pytest.raises(ProfileError):
        asyncio.run(
            ctx[1].turn(ctx[3], ConversationTurn(revision=1, message="读取"), ProfileActor(user_id=uuid4()))
        )


def test_stale_revision_no_model_call_and_missing_target_does_not_guess(ctx):
    _, state = classify(ctx)
    with pytest.raises(ProfileError, match="草稿已更新"):
        asyncio.run(ctx[1].turn(ctx[3], ConversationTurn(revision=1, message="确认"), ctx[2]))
    with pytest.raises(ProfileError, match="请先确认"):
        send(ctx, "跳到补全", stage="completion")


def test_sse_contains_only_public_progress_answer_and_persisted_state(ctx):
    reply(ctx, {"reply": "请上传样图，我还需要查看标题栏。"})
    events = []

    async def emit(event):
        events.append(event)

    body = ConversationTurn(revision=ctx[0].store.get(ctx[3], ctx[2]).revision, message="开始")
    state = asyncio.run(ctx[1].turn(ctx[3], body, ctx[2], emit))
    assert [e.type for e in events] == ["progress", "answer_delta", "completed"]
    assert events[-1].state == state
    assert "data:image" not in json.dumps([e.model_dump(mode="json") for e in events])


def confirmed_cross_scan(ctx):
    classify(ctx)
    send(ctx, "确认")
    image = attach(ctx)
    expected = {
        "drawing_function": "002.C",
        "drawing_page_number": 3,
        "units": [
            {
                "unit_id": "u1",
                "connections": [
                    {
                        "start": {"terminal": "X3:51"},
                        "end": None,
                        "is_cross_page": "cross_page",
                        "references": [
                            {"raw": "=080.C/42", "target_function": "080.C", "target_drawing_page": 42}
                        ],
                    }
                ],
            }
        ],
    }
    reply(
        ctx,
        {"reply": "生成初扫候选", "ready": True, "description": "初步识别为跨页", "source_image": str(image)},
        {"rule_text": "沿标记读取起点和跨页引用", "expected": expected},
    )
    send(ctx, "读取原图", [image])
    state = send(ctx, "确认")
    return image, state


def test_same_page_correction_returns_to_scan_without_requesting_target(ctx):
    image, state = confirmed_cross_scan(ctx)
    root, _ = ctx[0].store.root_for(ctx[3], ctx[2])
    original_rule = (root / "resources/scan.md").read_text(encoding="utf-8")
    corrected = {
        "drawing_function": "002.C",
        "drawing_page_number": 3,
        "units": [
            {
                "unit_id": "u1",
                "connections": [
                    {
                        "start": {"terminal": "X3:51"},
                        "end": {"terminal": "XD3:11"},
                        "is_cross_page": "same_page",
                        "references": [],
                    }
                ],
            }
        ],
    }
    gateway = reply(
        ctx,
        {
            "reply": "需要修正初扫",
            "ready": False,
            "action": "revise_scan",
            "description": "用户指出XD3:11就在当前页，应按同页连接核对",
        },
        {"rule_text": "本图可见两端时按同页连接读取，不因元件不同认定跨页", "expected": corrected},
    )
    revised = send(ctx, "终点XD3:11就在本页，不是跨页", stage="completion")
    assert revised.stage == "scan" and set(revised.wizard.confirmed) == {"classification"}
    candidate = revised.wizard.candidates["scan"]
    assert candidate.request.source_image == image and candidate.request.targets == []
    connection = candidate.cases[0].expected["units"][0]["connections"][0]
    assert connection["start"]["terminal"] == "X3:51" and connection["end"]["terminal"] == "XD3:11"
    assert connection["references"] == [] and connection["is_cross_page"] == "same_page"
    assert len(gateway.calls) == 2 and gateway.calls[-1].metadata["stage"] == "scan"
    data = json.dumps(gateway.calls[-1].messages, ensure_ascii=False)
    assert "revision_context" in data and "终点XD3:11就在本页" in data
    current_root, _ = ctx[0].store.root_for(ctx[3], ctx[2])
    assert (current_root / "resources/scan.md").read_text(encoding="utf-8") == original_rule
    accepted = send(ctx, "都同意")
    assert accepted.stage == "completion" and "scan" in accepted.wizard.confirmed
    assert "同页连接无需再提供目标图" in accepted.messages[-1].text
    assert not accepted.publish_ready


def test_legacy_repeated_agreement_uses_actual_user_feedback_to_propose_scan_revision(ctx):
    image, _ = confirmed_cross_scan(ctx)
    reply(
        ctx,
        {"reply": "是否确认同页，并上传目标图？", "description": "旧模型误判"},
        {"reply": "是否确认同页，并上传目标图？", "description": "旧模型重复"},
    )
    send(ctx, "XD3:11是本页上的", stage="completion")
    send(ctx, "确认，同意", stage="completion")
    corrected = {
        "units": [
            {
                "unit_id": "u1",
                "connections": [
                    {
                        "start": {"terminal": "X3:51"},
                        "end": {"terminal": "XD3:11"},
                        "is_cross_page": "same_page",
                        "references": [],
                    }
                ],
            }
        ]
    }
    gateway = reply(
        ctx,
        {"reply": "采用已有纠正", "action": "revise_scan", "description": "按用户纠正重新核对同页终点"},
        {"rule_text": "同页可见终点直接读取", "expected": corrected},
    )
    state = send(ctx, "都同意", stage="completion")
    assert state.stage == "scan" and state.wizard.candidates["scan"].request.source_image == image
    context = json.loads(gateway.calls[0].messages[-1]["content"][0]["text"])
    assert "XD3:11是本页上的" in context["user_feedback"]
    assert "确认，同意" in context["user_feedback"]
    assert "生成修正候选" in state.messages[-1].text and "scan" not in state.wizard.confirmed


def test_scan_revision_cannot_skip_missing_classification(ctx):
    reply(ctx, {"reply": "无效回退", "action": "revise_scan", "description": "尚无初扫"})
    with pytest.raises(ProfileError, match="尚无可修正"):
        send(ctx, "修改初扫", stage="classification")
    assert ctx[0].store.get(ctx[3], ctx[2]).revision == 1


def test_revising_scan_invalidates_an_existing_confirmed_completion(ctx):
    image, _ = confirmed_cross_scan(ctx)
    target = attach(ctx, "target.png")
    reply(
        ctx,
        {
            "reply": "已读到目标图",
            "ready": True,
            "description": "按引用匹配",
            "source_image": str(image),
            "targets": [{"attachment_id": str(target), "function": "080.C", "page": 42}],
        },
        {"rule_text": "匹配后读取目标", "expected": {"end": {"terminal": "XD3:11"}}},
    )
    send(ctx, "读取目标页", [target])
    accepted = send(ctx, "确认")
    assert set(accepted.wizard.confirmed) == {"classification", "scan", "completion"}
    reply(
        ctx,
        {"reply": "修正原判断", "action": "revise_scan", "description": "这条连接实际在同页"},
        {
            "rule_text": "两端本页可见时直接读取",
            "expected": {
                "units": [
                    {
                        "unit_id": "u1",
                        "connections": [
                            {
                                "start": {"terminal": "X3:51"},
                                "end": {"terminal": "XD3:11"},
                                "references": [],
                                "is_cross_page": "same_page",
                            }
                        ],
                    }
                ]
            },
        },
    )
    state = send(ctx, "终点就在本页，修正初扫", stage="completion")
    assert set(state.wizard.confirmed) == {"classification"}
    assert "completion" not in state.wizard.candidates


def confirmed_same_page_scan(ctx):
    image, _ = confirmed_cross_scan(ctx)
    reply(
        ctx,
        {"reply": "修正旧图", "action": "revise_scan", "description": "OLD图的XD3:11就在本页"},
        {
            "rule_text": "本图同页终点直接读取",
            "expected": {
                "drawing_function": "082.R",
                "drawing_page_number": 50,
                "units": [
                    {
                        "unit_id": "old",
                        "connections": [
                            {
                                "start": {"terminal": "XD3:211"},
                                "end": {"terminal": "XD3:11"},
                                "is_cross_page": "same_page",
                                "references": [],
                            }
                        ],
                    }
                ],
            },
        },
    )
    send(ctx, "OLD图的XD3:11就在本页，不是跨页")
    state = send(ctx, "确认")
    return image, state


@pytest.mark.parametrize("action", ["revise_scan", "replace_scan_source", "continue"])
@pytest.mark.parametrize("followup", [False, True, "scan"])
def test_replacing_source_rebuilds_scan_before_completion_without_old_facts(ctx, action, followup):
    old, _ = confirmed_same_page_scan(ctx)
    source = attach(ctx, "new-source.png")
    target = attach(ctx, "new-target.png")
    if followup:
        reply(ctx, {"reply": "第一张是新原页，第二张是对应跨页，是否按此核对？"})
        send(
            ctx,
            "之前处理错了，第一张才是原页，第二张是对应的跨页",
            [source, target],
            stage="scan" if followup == "scan" else "completion",
        )
    new_scan = {
        "drawing_function": "006.M",
        "drawing_page_number": 1,
        "units": [
            {
                "unit_id": "new",
                "connections": [
                    {
                        "start": {"terminal": "XD3:3"},
                        "end": None,
                        "is_cross_page": "cross_page",
                        "references": [
                            {"raw": "006C01", "target_function": "006.C", "target_drawing_page": 1}
                        ],
                    }
                ],
            }
        ],
    }
    gateway = reply(
        ctx,
        {
            "reply": "按新原页继续",
            "action": action,
            "ready": True,
            "description": "新原页006.M/1，XD3:3引用006C01",
            "source_image": str(source),
            "targets": [{"attachment_id": str(target), "function": "006.C", "page": 1}],
        },
        {"rule_text": "沿放线段读到离页引用", "expected": new_scan},
    )
    body = ConversationTurn(
        revision=ctx[0].store.get(ctx[3], ctx[2]).revision,
        message="同意" if followup else "第一张才是新原页，第二张是对应跨页",
        attachment_ids=[] if followup else [source, target],
    )
    state = asyncio.run(ctx[1].turn(ctx[3], body, ctx[2]))
    assert state.stage == "scan" and set(state.wizard.confirmed) == {"classification"}
    candidate = state.wizard.candidates["scan"]
    assert candidate.request.source_image == source != old
    assert candidate.request.targets == [] and candidate.request.negative_images == []
    assert candidate.cases[0].expected["drawing_function"] == "006.M"
    assert len(gateway.calls) == 2 and gateway.calls[-1].metadata["stage"] == "scan"
    context = json.loads(gateway.calls[-1].messages[-1]["content"][0]["text"])["revision_context"]
    assert context["source_replacement"] is True and context["previous_expected"] is None
    assert "OLD图" not in json.dumps(context, ensure_ascii=False)
    assert "更换" in state.messages[-1].text
    assert asyncio.run(ctx[1].turn(ctx[3], body, ctx[2])) == state
    assert len(gateway.calls) == 2  # Retrying the same turn cannot regenerate or confirm it.
    send(ctx, "确认")
    completion_gateway = reply(
        ctx,
        {
            "reply": "核对目标页",
            "ready": True,
            "description": "按006C01回指补全",
            "source_image": str(source),
            "targets": [{"attachment_id": str(target), "function": "006.C", "page": 1}],
        },
        {"rule_text": "沿回指定位目标端子", "expected": {"end": {"terminal": "X3:1"}}},
    )
    completed = send(ctx, "按刚才目标图继续补全")
    completion = completed.wizard.candidates["completion"]
    assert completion.request.source_image == source
    assert completion.cases[0].input["source_connection"]["start"]["terminal"] == "XD3:3"
    assert completion.cases[0].expected["end"]["terminal"] == "X3:1"
    completion_context = json.loads(completion_gateway.calls[0].messages[-1]["content"][0]["text"])
    assert "OLD图" not in json.dumps(completion_context["user_feedback"], ensure_ascii=False)


def test_completion_preflight_does_not_generate_without_structured_references(ctx):
    source, state = confirmed_same_page_scan(ctx)
    target = attach(ctx, "target.png")
    gateway = reply(
        ctx,
        {
            "reply": "文字里说有跨页，开始补全",
            "ready": True,
            "description": "旧描述声称有引用",
            "source_image": str(source),
            "targets": [{"attachment_id": str(target), "function": "006.C", "page": 1}],
        },
    )
    result = send(ctx, "同意用目标图补全", [target])
    assert len(gateway.calls) == 1 and result.stage == "completion"
    assert result.wizard.confirmed == state.wizard.confirmed
    assert "completion" not in result.wizard.candidates
    assert "已确认的初扫结果没有跨页引用" in result.messages[-1].text
    assert "开始补全" not in result.messages[-1].text
