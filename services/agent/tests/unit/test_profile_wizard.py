from __future__ import annotations

import asyncio
import json
from pathlib import Path
from uuid import uuid4

import httpx
import pymupdf
import pytest

from src.agent.profile_agent import DraftCreate, ProfileActor, create_profile_agent
from src.agent.profile_agent.models import ProfileError
from src.agent.profile_agent.template import RESOURCES
from src.agent.profile_agent.validation import validate_draft
from src.agent.profile_agent.wizard import ProfileWizard, StageConfirm, StageGenerate, TargetImage
from src.config import AgentSettings
from src.harness.model_gateway import FakeModelGateway

ROOT = Path(__file__).resolve().parents[4]
SCAN = {
    "drawing_function": "002.C",
    "drawing_page_number": 3,
    "units": [
        {
            "unit_id": "u1",
            "connections": [
                {
                    "line_number": "002C0311",
                    "start": {"terminal": "X3:51"},
                    "end": {"terminal": "SHOULD_BE_CLEARED"},
                    "references": [
                        {"raw": "=080.C/42", "target_function": "080.C", "target_drawing_page": 42}
                    ],
                },
                {
                    "line_number": "002C0312",
                    "start": {"terminal": "X3:75"},
                    "references": [
                        {"raw": "=080.C/43", "target_function": "080.C", "target_drawing_page": 43}
                    ],
                },
            ],
        }
    ],
}


@pytest.fixture
def context(tmp_path, monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("No real model/DB in authoring tests")

    monkeypatch.setattr(httpx.AsyncClient, "request", forbidden)
    answers = [
        {
            "rule_text": "按标题栏识别工作区和业务页号",
            "expected": {"plant_function": "002.C", "drawing_page_number": 3},
        },
        {"rule_text": "斜线是放线标记，按箭头定位来源，等号后读取跨页地址", "expected": SCAN},
        {
            "rule_text": "匹配来源回指后读取最近终点，不改来源",
            "expected": {"task_id": "model_wrong_id", "end": {"terminal": "XD21:60"}},
        },
    ]
    gateway = FakeModelGateway([json.dumps(a, ensure_ascii=False) for a in answers])
    agent = create_profile_agent(
        AgentSettings(workspace_root=ROOT), state_root=tmp_path / "drafts", gateway=gateway
    )
    actor = ProfileActor(user_id=uuid4())
    view = asyncio.run(agent.create(DraftCreate(key="sample_rules", display_name="用户规则"), actor))
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 30, 20))
    pix.clear_with(255)
    source, target = uuid4(), uuid4()
    for image in (source, target):
        view = agent.store.attach(
            view.draft_id, actor, view.revision, image, "drawing.png", pix.tobytes("png")
        )
    return agent, ProfileWizard(agent), actor, view, source, target, gateway


def generate_confirm(ctx, stage, *, edited=None):
    agent, wizard, actor, _, source, target, _ = ctx
    draft = ctx[3].draft_id
    view = agent.store.get(draft, actor)
    result = asyncio.run(
        wizard.generate(
            draft,
            stage,
            StageGenerate(
                revision=view.revision,
                description="用户提供图纸读取说明",
                source_image=source,
                targets=[TargetImage(attachment_id=target, function="080.C", page=42)]
                if stage == "completion"
                else [],
            ),
            actor,
        )
    )
    candidate = result.candidates[stage]
    if edited:
        edited(candidate)
    return wizard.confirm(
        draft,
        stage,
        StageConfirm(
            revision=result.draft.revision,
            candidate_id=candidate.id,
            rule_text=candidate.rule_text,
            expected=[c.expected for c in candidate.cases],
        ),
        actor,
    )


def test_three_stages_require_confirmation_and_export_exact_user_answers(context):
    agent, wizard, actor, view, source, _, gateway = context
    with pytest.raises(ProfileError, match="先确认"):
        asyncio.run(
            wizard.generate(
                view.draft_id,
                "scan",
                StageGenerate(revision=view.revision, description="说明", source_image=source),
                actor,
            )
        )
    assert not gateway.calls
    generate_confirm(context, "classification")
    state = generate_confirm(context, "scan")
    assert state.candidates["scan"].cases[0].expected["units"][0]["connections"][0]["end"] is None
    with pytest.raises(ProfileError, match="尚未就绪"):
        asyncio.run(agent.export(view.draft_id, state.draft.revision, actor))

    def edit(candidate):
        candidate.cases[0].expected["end"]["terminal"] = "XD21:61"

    result = generate_confirm(context, "completion", edited=edit)
    assert len(gateway.calls) == 3  # Missing second target is deterministic null, no model guess.
    candidate = result.candidates["completion"]
    assert candidate.cases[0].expected["task_id"] == "wizard-0-0-0"
    assert candidate.cases[0].expected["end"]["terminal"] == "XD21:61"
    assert candidate.cases[1].expected["end"] is None
    root, meta = agent.store.root_for(view.draft_id, actor)
    assert validate_draft(root, meta).ready
    receipt = asyncio.run(agent.export(view.draft_id, result.draft.revision, actor))
    assert Path(receipt.archive_path).is_file() and not receipt.published
    assert "data:image/" in json.dumps(gateway.calls[0].messages)
    assert agent.store.list_drafts(actor)[0].draft_id == view.draft_id
    assert not agent.store.list_drafts(ProfileActor(user_id=uuid4()))
    again = wizard.confirm(
        view.draft_id,
        "completion",
        StageConfirm(
            revision=result.draft.revision,
            candidate_id=candidate.id,
            rule_text=candidate.rule_text,
            expected=[c.expected for c in candidate.cases],
        ),
        actor,
    )
    assert again.draft.revision == result.draft.revision and set(again.confirmed) == {
        "classification",
        "scan",
        "completion",
    }
    # The HTTP publication path must never trust an externally edited export receipt's file path.
    path = Path(receipt.archive_path).with_name("receipt.json")
    metadata = json.loads(path.read_text(encoding="utf-8"))
    metadata["archive_path"] = str(ROOT / "outside-secret.txt")
    path.write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(ProfileError, match="工具外修改"):
        asyncio.run(agent.export(view.draft_id, result.draft.revision, actor))


def test_reconfirming_scan_invalidates_completion_and_old_answers(context):
    generate_confirm(context, "classification")
    generate_confirm(context, "scan")
    result = generate_confirm(context, "completion")
    agent, wizard, actor, view, *_ = context
    scan = result.candidates["scan"]
    result = wizard.confirm(
        view.draft_id,
        "scan",
        StageConfirm(
            revision=result.draft.revision,
            candidate_id=scan.id,
            rule_text=scan.rule_text + "修订",
            expected=[scan.cases[0].expected],
        ),
        actor,
    )
    assert "completion" not in result.confirmed and "completion" not in result.candidates
    root, meta = agent.store.root_for(view.draft_id, actor)
    assert not validate_draft(root, meta).ready
    with pytest.raises(ProfileError):
        wizard.state(view.draft_id, ProfileActor(user_id=uuid4()))


def test_scan_cannot_confirm_cross_page_end_and_invalid_input_is_atomic(context):
    generate_confirm(context, "classification")
    agent, wizard, actor, view, source, *_ = context
    current = agent.store.get(view.draft_id, actor)
    result = asyncio.run(
        wizard.generate(
            view.draft_id,
            "scan",
            StageGenerate(revision=current.revision, description="斜线", source_image=source),
            actor,
        )
    )
    candidate = result.candidates["scan"]
    candidate.cases[0].expected["units"][0]["connections"][0]["end"] = {"terminal": "BAD"}
    with pytest.raises(ProfileError, match="初扫跨页终点"):
        wizard.confirm(
            view.draft_id,
            "scan",
            StageConfirm(
                revision=result.draft.revision,
                candidate_id=candidate.id,
                rule_text=candidate.rule_text,
                expected=[candidate.cases[0].expected],
            ),
            actor,
        )
    assert agent.store.get(view.draft_id, actor).revision == result.draft.revision


def test_editing_confirmed_prompt_requires_reconfirmation(context):
    for stage in ("classification", "scan", "completion"):
        generate_confirm(context, stage)
    agent, wizard, actor, view, *_ = context
    root, meta = agent.store.root_for(view.draft_id, actor)
    # Simulate an authorized alternative editing tool, then check the stage seal.
    from src.agent.profile_agent.models import FileEdit
    from src.profiles.package import checksum

    path = RESOURCES["page_scan_prompt"]
    current = agent.store.get(view.draft_id, actor)
    before = (root / path).read_bytes()
    text = (root / path).read_text(encoding="utf-8")
    agent.store.edit(
        view.draft_id,
        actor,
        current.revision,
        "test-edit",
        [FileEdit(path=path, before_checksum=checksum(before), content=text + "\n补充规则")],
        "explicit_instruction",
    )
    root, meta = agent.store.root_for(view.draft_id, actor)
    assert "RULE_UNCONFIRMED" in {i.code for i in validate_draft(root, meta).issues}


def test_published_package_worker_load_and_retry_freeze(context, tmp_path):
    for stage in ("classification", "scan", "completion"):
        state = generate_confirm(context, stage)
    agent, _, actor, view, *_ = context
    receipt = asyncio.run(agent.export(view.draft_id, state.draft.revision, actor))
    from src.agent.extraction_agent.application.incremental_worker import frozen_profile
    from src.profiles.package import checksum

    content = Path(receipt.archive_path).read_bytes()

    class Repository:
        def __init__(self):
            self.objects = {
                "profiles/" + str(actor.user_id) + f"/sample_rules/1.0.0/{checksum(content)[7:]}.zip": content
            }
            self.cached = None
            self.requests = 0

        async def artifact(self, run, name):
            return self.cached

        async def request(self, method, path, **kwargs):
            self.requests += 1
            assert kwargs["params"]["checksum"] == "eq." + receipt.checksum
            return httpx.Response(
                200, json=[{"resource_ref": "storage://project-assets/" + next(iter(self.objects))}]
            )

        async def get(self, bucket, path):
            return self.objects[path]

        async def put(self, bucket, path, value, mime):
            self.objects[path] = value

    class Session:
        repository = Repository()
        run, project = str(uuid4()), str(uuid4())
        profile = {"key": "sample_rules", "version": "1.0.0", "checksum": receipt.checksum}

        async def commit(self, key, step):
            self.repository.cached = step.model_dump(mode="json")

    session = Session()
    path = tmp_path / "worker"
    path.mkdir()
    binding = asyncio.run(frozen_profile(session, AgentSettings(workspace_root=ROOT), path))
    assert binding.profile.key == "sample_rules"
    binding = asyncio.run(frozen_profile(session, AgentSettings(workspace_root=ROOT), path))
    assert session.repository.requests == 1  # Retry reads only frozen task ZIP.


def test_generate_retry_is_idempotent_after_response_loss(context):
    agent, wizard, actor, view, source, _, gateway = context
    body = StageGenerate(revision=view.revision, description="读取工作区和页号", source_image=source)
    first = asyncio.run(wizard.generate(view.draft_id, "classification", body, actor))
    retry = asyncio.run(wizard.generate(view.draft_id, "classification", body, actor))
    assert retry.draft.revision == first.draft.revision and len(gateway.calls) == 1
    changed = body.model_copy(update={"description": "不同输入"})
    with pytest.raises(ProfileError, match="输入已变化"):
        asyncio.run(wizard.generate(view.draft_id, "classification", changed, actor))


def test_replacing_completion_removes_old_task_cases(context):
    for stage in ("classification", "scan", "completion"):
        state = generate_confirm(context, stage)
    agent, wizard, actor, view, source, target, _ = context
    scan = state.candidates["scan"]
    scan.cases[0].expected["units"][0]["connections"] = scan.cases[0].expected["units"][0]["connections"][:1]
    state = wizard.confirm(
        view.draft_id,
        "scan",
        StageConfirm(
            revision=state.draft.revision,
            candidate_id=scan.id,
            rule_text=scan.rule_text,
            expected=[scan.cases[0].expected],
        ),
        actor,
    )
    # One remaining unresolved task is enough to verify replacement; no model call is needed.
    state = asyncio.run(
        wizard.generate(
            view.draft_id,
            "completion",
            StageGenerate(
                revision=state.draft.revision,
                description="匹配不到则留空",
                source_image=source,
                targets=[TargetImage(attachment_id=target, function="999.X", page=99)],
            ),
            actor,
        )
    )
    candidate = state.candidates["completion"]
    state = wizard.confirm(
        view.draft_id,
        "completion",
        StageConfirm(
            revision=state.draft.revision,
            candidate_id=candidate.id,
            rule_text=candidate.rule_text,
            expected=[c.expected for c in candidate.cases],
        ),
        actor,
    )
    from src.agent.profile_agent.validation import case_files

    root, meta = agent.store.root_for(view.draft_id, actor)
    cases = [c for c in case_files(root) if c["stage"] == "completion"]
    assert len(cases) == 1 and cases[0]["id"] == "wizard_completion_0"
    assert not (root / RESOURCES["wiring_examples"] / "completion/wizard_completion_1.expected.json").exists()
    assert validate_draft(root, meta).ready
