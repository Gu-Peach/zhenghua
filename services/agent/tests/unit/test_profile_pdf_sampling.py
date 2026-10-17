from __future__ import annotations

import asyncio
import base64
import json
from uuid import uuid4

import httpx
import pymupdf
import pytest

from src.agent.profile_agent import DraftCreate, ProfileActor, create_profile_agent
from src.agent.profile_agent import pdf_sampling
from src.agent.profile_agent.conversation import ConversationTurn, ProfileConversation
from src.agent.profile_agent.models import PdfSampleRequest, ProfileError
from src.agent.profile_agent.pdf_sampling import PdfSamplingTool
from src.agent.profile_agent.wizard import ProfileWizard, StageConfirm
from src.config import AgentSettings
from src.harness.model_gateway import FakeModelGateway


def pdf_bytes(count=5, encrypted=False):
    with pymupdf.open() as document:
        for index in range(count):
            page = document.new_page(width=840, height=594)
            page.draw_rect(pymupdf.Rect(24, 24, 816, 570))
            page.insert_text((45, 55), f"Schematic sample / Physical page {index + 1}", fontsize=18)
            page.draw_line((120, 200), (600, 200))
            page.insert_text((120, 185), "X3:51", fontsize=14)
            page.insert_text((540, 185), "XD21:60", fontsize=14)
            page.insert_text((560, 540), f"Function 002.C | Drawing {index + 20}", fontsize=12)
        return document.tobytes(
            **(
                {"encryption": pymupdf.PDF_ENCRYPT_AES_256, "owner_pw": "owner", "user_pw": "reader"}
                if encrypted
                else {}
            )
        )


@pytest.fixture
def ctx(tmp_path, monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("No network in PDF sampling tests")

    monkeypatch.setattr(httpx.AsyncClient, "request", forbidden)
    agent = create_profile_agent(
        AgentSettings(), state_root=tmp_path / "drafts", gateway=FakeModelGateway([])
    )
    actor = ProfileActor(user_id=uuid4())
    view = asyncio.run(agent.create(DraftCreate(key="pdf_sample", display_name="PDF样例规则"), actor))
    return agent, actor, view


def request(view, content=None, **kwargs):
    return PdfSampleRequest(
        revision=view.revision,
        filename="drawings.pdf",
        content_base64=base64.b64encode(content or pdf_bytes()).decode(),
        **kwargs,
    )


def test_renders_only_two_selected_pages_and_never_writes_pdf(ctx, monkeypatch):
    agent, actor, view = ctx
    monkeypatch.setattr(pdf_sampling, "choose_pages", lambda _: [1, 4])
    rendered = []
    original = pdf_sampling.render_page

    def render(document, index):
        rendered.append(index)
        return original(document, index)

    monkeypatch.setattr(pdf_sampling, "render_page", render)
    body = request(view)
    result = PdfSamplingTool(agent.store).sample(view.draft_id, body, actor)
    assert rendered == [1, 4]
    assert [p.pdf_page_number for p in result.sample.pages] == [2, 5]
    root, meta = agent.store.root_for(view.draft_id, actor)
    assert len(result.draft.attachments) == 2 and len(list(root.rglob("*.png"))) == 2
    assert not list(agent.store.root.rglob("*.pdf"))
    assert result.sample.page_count == 5 and meta["classification_pdf_sample"]["filename"] == "drawings.pdf"
    for attachment in result.draft.attachments:
        pixmap = pymupdf.Pixmap(str(root / attachment.path))
        assert max(pixmap.width, pixmap.height) <= 2049
    # Retry returns precisely the original sample and does not touch the renderer again.
    cached = PdfSamplingTool(agent.store).sample(view.draft_id, body, actor)
    assert cached == result and rendered == [1, 4]


def test_invalid_encrypted_and_render_failure_leave_no_new_files(ctx, monkeypatch):
    agent, actor, view = ctx
    tool = PdfSamplingTool(agent.store)
    for content in (b"%PDF-broken", pdf_bytes(encrypted=True)):
        with pytest.raises(ProfileError):
            tool.sample(view.draft_id, request(view, content), actor)
        assert agent.store.get(view.draft_id, actor) == view
    monkeypatch.setattr(pdf_sampling, "choose_pages", lambda _: [0, 1])
    original = pdf_sampling.render_page

    def fail_second(document, index):
        if index == 1:
            raise RuntimeError("fixture render failure")
        return original(document, index)

    monkeypatch.setattr(pdf_sampling, "render_page", fail_second)
    with pytest.raises(ProfileError, match="未保存"):
        tool.sample(view.draft_id, request(view), actor)
    assert not list(agent.store.root.rglob("*.png"))
    assert not list(agent.store.root.rglob("*.pdf"))
    assert agent.store.get(view.draft_id, actor).revision == view.revision


def test_single_page_idempotency_conflict_and_ownership(ctx):
    agent, actor, view = ctx
    tool = PdfSamplingTool(agent.store)
    body = request(view, pdf_bytes(1))
    result = tool.sample(view.draft_id, body, actor)
    assert len(result.sample.pages) == 1 and "只有1页" in result.sample.notice
    with pytest.raises(ProfileError, match="内容已变化"):
        tool.sample(
            view.draft_id,
            body.model_copy(update={"content_base64": base64.b64encode(pdf_bytes(3)).decode()}),
            actor,
        )
    with pytest.raises(ProfileError):
        tool.sample(view.draft_id, body, ProfileActor(user_id=uuid4()))


def test_two_sample_pages_become_distinct_classification_answers(ctx, monkeypatch):
    agent, actor, view = ctx
    monkeypatch.setattr(pdf_sampling, "choose_pages", lambda _: [1, 4])
    sample = PdfSamplingTool(agent.store).sample(view.draft_id, request(view), actor)
    agent.gateway = FakeModelGateway(
        [
            json.dumps(value, ensure_ascii=False)
            for value in [
                {
                    "reply": "两页右下角都有功能区和业务页号，可以按相同方式分类。",
                    "ready": True,
                    "description": "对照两页右下角标题栏，按功能区和图号识别，不用物理页号代替业务页号",
                },
                {
                    "rule_text": "工作区读标题栏Function，业务页号读Drawing",
                    "expected": {"plant_function": "002.C", "drawing_page_number": 21},
                },
                {
                    "rule_text": "工作区读标题栏Function，业务页号读Drawing",
                    "expected": {"plant_function": "002.C", "drawing_page_number": 24},
                },
            ]
        ]
    )
    chat = ProfileConversation(ProfileWizard(agent))
    state = asyncio.run(
        chat.turn(
            view.draft_id,
            ConversationTurn(
                revision=sample.draft.revision,
                message="请比较随机两页的分页方式",
                attachment_ids=[p.attachment_id for p in sample.sample.pages],
            ),
            actor,
        )
    )
    candidate = state.wizard.candidates["classification"]
    assert len(candidate.cases) == 2
    assert [c.expected["drawing_page_number"] for c in candidate.cases] == [21, 24]
    assert [c.input["source_pdf_page_number"] for c in candidate.cases] == [2, 5]
    assert len(candidate.request.sample_images) == 2
    assert state.pdf_sample == sample.sample and not state.wizard.confirmed
    accepted = ProfileWizard(agent).confirm(
        view.draft_id,
        "classification",
        StageConfirm(
            revision=state.wizard.draft.revision,
            candidate_id=candidate.id,
            rule_text=candidate.rule_text,
            expected=[c.expected for c in candidate.cases],
        ),
        actor,
    )
    assert "classification" in accepted.confirmed
    # Subsequent extraction cannot silently choose one of the PDF samples as its source.
    manual_id = uuid4()
    root, _ = agent.store.root_for(view.draft_id, actor)
    pixels = (root / accepted.draft.attachments[0].path).read_bytes()
    manual = agent.store.attach(
        view.draft_id, actor, accepted.draft.revision, manual_id, "manual.png", pixels
    )
    agent.gateway = FakeModelGateway(
        [
            json.dumps(
                {
                    "reply": "试图复用PDF样图",
                    "ready": True,
                    "description": "直接提取",
                    "source_image": str(sample.sample.pages[0].attachment_id),
                }
            )
        ]
    )
    after = asyncio.run(
        chat.turn(
            view.draft_id,
            ConversationTurn(
                revision=manual.revision,
                message="请读取我新上传的原图",
                stage="scan",
                attachment_ids=[manual_id],
            ),
            actor,
        )
    )
    assert "scan" not in after.wizard.candidates and "上传" in after.messages[-1].text


def test_random_selection_is_unique_and_within_pdf():
    for count in (1, 2, 10, 10000):
        indices = pdf_sampling.choose_pages(count)
        assert len(indices) == min(2, count) and len(set(indices)) == len(indices)
        assert all(0 <= index < count for index in indices)
