"""Offline Profile Agent acceptance: real fixture pixels, Fake VLM, no business DB or model calls."""

from __future__ import annotations

import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from src.agent.profile_agent import DraftCreate, ProfileActor, ProfileError, ProfileTurn, create_profile_agent
from src.agent.profile_agent.models import ExampleCase, FileEdit, ProposalRequest, TemplateFields
from src.agent.profile_agent.template import RESOURCES
from src.agent.profile_agent.tools import ProfileTools
from src.agent.profile_agent.validation import case_files, validate_draft
from src.config import AgentSettings
from src.harness.model_gateway import FakeModelGateway, ModelResponse, ModelToolCall
from src.profiles.package import PackageManifest, checksum, verify_package
from src.profiles.registry import ProfileRegistry

ROOT = Path(__file__).resolve().parents[4]


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("Profile tests must not contact paid models or business databases")

    monkeypatch.setattr(httpx.AsyncClient, "request", forbidden)


@pytest.fixture
def setup(tmp_path):
    actor = ProfileActor(user_id=uuid4())
    gateway = FakeModelGateway([])
    agent = create_profile_agent(
        AgentSettings(workspace_root=ROOT), state_root=tmp_path / "drafts", gateway=gateway
    )
    return actor, gateway, agent


def create(setup, source=False):
    actor, _, agent = setup
    return asyncio.run(
        agent.create(
            DraftCreate(
                key="zh" if source else "demo",
                display_name="规则草稿",
                source_profile="zh" if source else None,
            ),
            actor,
        )
    )


def call(name, value, identifier="tool-one"):
    return ModelResponse(
        content="",
        parsed=None,
        model="fake",
        duration_seconds=0,
        attempts=1,
        tool_calls=(ModelToolCall(identifier, name, json.dumps(value, ensure_ascii=False)),),
    )


def replace_text(agent, actor, draft, path, old, new):
    file = agent.store.read(draft.draft_id, actor, path, 0, 300000)
    assert old in file["text"]
    return FileEdit(path=path, before_checksum=file["checksum"], content=file["text"].replace(old, new))


def test_template_does_not_copy_zh_answers_or_company_claims(setup):
    actor, _, agent = setup
    draft = create(setup)
    root, meta = agent.store.root_for(draft.draft_id, actor)
    assert draft.template and draft.template.company_signals == []
    assert not case_files(root)
    assert not any(name.endswith(".png") for name in draft.files)
    report = validate_draft(root, meta)
    assert not report.ready
    assert {issue.code for issue in report.issues} >= {"TEMPLATE_INCOMPLETE", "CASE_MISSING"}
    assert not agent.store.audit(draft.draft_id, actor)[0]["audit"]


def test_fork_is_self_contained_versioned_and_never_edits_source(setup):
    actor, _, agent = setup
    original = ROOT / "services/agent/src/agent/extraction_agent/profiles/zh/profile.json"
    before = original.read_bytes()
    draft = create(setup, True)
    assert draft.key == "zh" and draft.version == "2.1.2"
    assert draft.source["version"] == "2.1.1"
    root, meta = agent.store.root_for(draft.draft_id, actor)
    assert validate_draft(root, meta).ready
    assert original.read_bytes() == before


@pytest.mark.parametrize(
    "path",
    [
        "../secret.md",
        "resources/../../secret.md",
        "E:/secret.md",
        "a\\b.md",
        "profile.json",
        "schema.json",
        "template.json",
        "resources/common.md",
        "resources/evil.py",
    ],
)
def test_unsafe_and_protected_writes_never_change_head(setup, path):
    actor, _, agent = setup
    draft = create(setup)
    with pytest.raises((ProfileError, ValueError)):
        agent.store.edit(
            draft.draft_id,
            actor,
            draft.revision,
            "bad",
            [FileEdit(path=path, content="x")],
            "explicit_instruction",
        )
    assert agent.store.get(draft.draft_id, actor).checksum == draft.checksum


def test_partial_batch_rolls_back_and_contract_cannot_change(setup):
    actor, _, agent = setup
    draft = create(setup, True)
    path = "resources/page_scan_prompt.md"
    edit = replace_text(agent, actor, draft, path, "端子", "实际端子")
    with pytest.raises(ProfileError):
        agent.store.edit(
            draft.draft_id,
            actor,
            1,
            "bad-batch",
            [edit, FileEdit(path="schema.json", content="{}")],
            "explicit_instruction",
        )
    assert agent.store.get(draft.draft_id, actor).checksum == draft.checksum
    rule = agent.store.read(draft.draft_id, actor, "resources/routing_rules.json")
    value = json.loads(rule["text"])
    value["extraction"]["output_contract"] = "model_invented_shape"
    with pytest.raises(ProfileError, match="输出协议"):
        agent.store.edit(
            draft.draft_id,
            actor,
            1,
            "contract",
            [FileEdit(path=rule["path"], before_checksum=rule["checksum"], content=json.dumps(value))],
            "explicit_instruction",
        )


def test_proposal_confirmation_rejection_staleness_and_audit(setup):
    actor, _, agent = setup
    draft = create(setup, True)
    path = "resources/page_scan_prompt.md"
    edit = replace_text(agent, actor, draft, path, "端子", "实际端子")
    proposal = agent.store.propose(
        draft.draft_id, actor, 1, uuid4(), ProposalRequest(summary="明确实际端子", edits=[edit])
    )
    assert agent.store.get(draft.draft_id, actor).revision == 1
    assert proposal.diffs[0].before != proposal.diffs[0].after
    refused = agent.store.propose(
        draft.draft_id, actor, 1, uuid4(), ProposalRequest(summary="另一建议", edits=[edit])
    )
    agent.store.confirm(draft.draft_id, actor, refused.id, 1, False)
    with pytest.raises(ProfileError, match="拒绝"):
        agent.store.confirm(draft.draft_id, actor, refused.id, 1, True)
    accepted = agent.store.confirm(draft.draft_id, actor, proposal.id, 1, True)
    assert accepted.revision == 2
    assert agent.store.confirm(draft.draft_id, actor, proposal.id, 1, True).revision == 2
    assert agent.store.audit(draft.draft_id, actor)[-1]["audit"]["authorization"] == "confirmed_proposal"
    stale_edit = replace_text(agent, actor, accepted, path, "实际端子", "图中实际端子")
    stale = agent.store.propose(
        draft.draft_id, actor, 2, uuid4(), ProposalRequest(summary="过期建议", edits=[stale_edit])
    )
    agent.store.edit(draft.draft_id, actor, 2, "other", [stale_edit], "explicit_instruction")
    with pytest.raises(ProfileError, match="不一致"):
        agent.store.confirm(draft.draft_id, actor, stale.id, 2, True)


def test_concurrent_accept_reject_has_one_consistent_outcome(setup):
    actor, _, agent = setup
    draft = create(setup, True)
    edit = replace_text(agent, actor, draft, "resources/page_scan_prompt.md", "端子", "实际端子")
    proposal = agent.store.propose(
        draft.draft_id, actor, 1, uuid4(), ProposalRequest(summary="并发确认", edits=[edit])
    )

    def decide(accepted):
        try:
            return agent.store.confirm(draft.draft_id, actor, proposal.id, 1, accepted)
        except ProfileError as exc:
            return exc.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(decide, [True, False]))
    saved = agent.store.proposal(draft.draft_id, actor, proposal.id)
    assert agent.store.get(draft.draft_id, actor).revision == (2 if saved.status == "accepted" else 1)


def test_authorization_owner_and_idempotency_are_program_controlled(setup):
    actor, _, agent = setup
    draft = create(setup)
    other = ProfileActor(user_id=uuid4())
    for operation in (
        lambda: agent.store.get(draft.draft_id, other),
        lambda: agent.store.read(draft.draft_id, other, "profile.json"),
        lambda: agent.store.audit(draft.draft_id, other),
    ):
        with pytest.raises(ProfileError) as error:
            operation()
        assert error.value.status == 403
    path = RESOURCES["page_scan_prompt"]
    edit = replace_text(agent, actor, draft, path, "本模板", "当前模板")
    with pytest.raises(ProfileError, match="确认"):
        agent.store.edit(draft.draft_id, actor, 1, "same", [edit], "model_says_confirmed")
    after = agent.store.edit(draft.draft_id, actor, 1, "same", [edit], "explicit_instruction")
    assert (
        agent.store.edit(draft.draft_id, actor, 1, "same", [edit], "explicit_instruction").revision
        == after.revision
    )
    with pytest.raises(ProfileError, match="内容已变化"):
        agent.store.edit(
            draft.draft_id,
            actor,
            1,
            "same",
            [edit.model_copy(update={"content": edit.content + "different"})],
            "explicit_instruction",
        )


def test_model_diagnosis_proposal_then_human_confirmation(setup):
    actor, _, agent = setup
    draft = create(setup, True)
    path = "resources/page_scan_prompt.md"
    original = agent.store.read(draft.draft_id, actor, path, 0, 300000)
    bad = original["text"] + "\n无论图纸是否标注，都添加GTR前缀。"
    draft = agent.store.edit(
        draft.draft_id,
        actor,
        1,
        "seed",
        [FileEdit(path=path, before_checksum=original["checksum"], content=bad)],
        "explicit_instruction",
    )
    proposal = {
        "summary": "移除无依据的GTR前缀",
        "edits": [
            {
                "path": path,
                "before_checksum": agent.store.read(draft.draft_id, actor, path)["checksum"],
                "content": original["text"],
            }
        ],
        "findings": [
            {
                "category": "rule_issue",
                "explanation": "Prompt强制添加前缀",
                "evidence": [{"path": path, "quote": "无论图纸是否标注，都添加GTR前缀。"}],
            }
        ],
    }
    agent.gateway = FakeModelGateway(
        [
            call("read_file", {"path": path, "limit": 40000}),
            call("propose_edits", proposal),
            "规则中明确要求无条件添加GTR。建议移除该条，是否采用？",
        ]
    )
    turn = ProfileTurn(message="为什么我的端子每次前缀都会加上GTR？", expected_revision=2)
    reply = asyncio.run(agent.ask(draft.draft_id, turn, actor))
    assert reply.findings[0].category == "rule_issue"
    assert reply.revision == 2 and not reply.changed_files
    assert reply.proposals[0].status == "pending"
    confirmed = asyncio.run(agent.confirm(draft.draft_id, reply.proposals[0].id, 2, True, actor))
    assert confirmed.revision == 3
    assert "无论图纸是否标注" not in agent.store.read(draft.draft_id, actor, path, 0, 300000)["text"]


def test_direct_instruction_uses_edit_tool_and_survives_final_model_failure(setup):
    actor, _, agent = setup
    draft = create(setup)
    path = RESOURCES["page_scan_prompt"]
    edit = replace_text(agent, actor, draft, path, "按本模板放线标记", "按图中小圆圈放线标记")
    gateway = FakeModelGateway(
        [
            call("apply_edits", {"edits": [edit.model_dump()], "summary": "改成小圆圈"}),
            RuntimeError("model unavailable"),
        ]
    )
    agent.gateway = gateway
    turn = ProfileTurn(message="把放线标记修改为小圆圈", intent="edit", expected_revision=1)
    result = asyncio.run(agent.ask(draft.draft_id, turn, actor))
    assert result.revision == 2 and result.changed_files == [path]
    assert "总结未完成" in result.answer
    assert asyncio.run(agent.ask(draft.draft_id, turn, actor)).cached
    assert len(gateway.calls) == 2
    assert "apply_edits" not in {item["function"]["name"] for item in gateway.calls[-1].tools}


def test_discussion_cannot_write_or_fake_confirmation_or_groundless_diagnosis(setup):
    actor, _, agent = setup
    draft = create(setup)
    path = RESOURCES["page_scan_prompt"]
    edit = replace_text(agent, actor, draft, path, "本模板", "当前模板")
    agent.gateway = FakeModelGateway(
        [
            call("apply_edits", {"edits": [edit.model_dump()], "summary": "模型声称已确认"}),
            call("confirm_expected", {"files": {}}),
            call(
                "record_diagnosis",
                {"findings": [{"category": "model_deviation", "explanation": "一定是幻觉", "evidence": []}]},
            ),
            "目前缺少原图和实际输出，不能确定是幻觉。请补充样本。",
        ]
    )
    reply = asyncio.run(
        agent.ask(draft.draft_id, ProfileTurn(message="为什么加前缀？", expected_revision=1), actor)
    )
    assert reply.revision == 1 and not reply.changed_files and not reply.findings
    results = [json.loads(m["content"]) for m in agent.gateway.calls[-1].messages if m["role"] == "tool"]
    assert {r["error"] for r in results} >= {"EDIT_NOT_AUTHORIZED", "TOOL_NOT_ALLOWED", "EVIDENCE_REQUIRED"}


def test_export_and_persistent_reopen_keep_fixed_schema_and_no_publication(setup, tmp_path):
    actor, _, agent = setup
    draft = create(setup, True)
    receipt = asyncio.run(agent.export(draft.draft_id, draft.revision, actor))
    assert not receipt.published and receipt.key == "zh" and receipt.version == "2.1.2"
    import zipfile

    folder = tmp_path / "verify" / "package"
    with zipfile.ZipFile(receipt.archive_path) as archive:
        archive.extractall(folder)
    manifest = PackageManifest.model_validate_json((folder / "manifest.json").read_text(encoding="utf-8"))
    verify_package(folder, manifest)
    registry = ProfileRegistry(profile_root=folder.parent, workspace_root=tmp_path)
    registry.load_all()
    assert (
        registry.bind("zh", allow_experimental=True).rules.extraction.output_contract
        == "wiring_connection_v1"
    )
    second = create_profile_agent(
        AgentSettings(workspace_root=ROOT), state_root=agent.store.root, gateway=FakeModelGateway([])
    )
    assert second.store.get(draft.draft_id, actor).checksum == draft.checksum
    assert asyncio.run(second.export(draft.draft_id, draft.revision, actor)).checksum == receipt.checksum


def test_new_template_real_images_and_ai_expected_need_human_confirmation(setup):
    actor, _, agent = setup
    draft = create(setup)
    examples = ROOT / "services/agent/src/agent/extraction_agent/prompts/zh/examples_wiring/002c"
    classification = (
        ROOT / "services/agent/src/agent/extraction_agent/prompts/zh/examples_page_classification"
    )
    manifest = json.loads((examples / "manifest.json").read_text(encoding="utf-8"))
    class_case = json.loads((classification / "manifest.json").read_text(encoding="utf-8"))["cases"][0]
    cases = [
        ("classification", class_case, classification),
        ("scan", manifest["stage2_cases"][0], examples),
        ("completion", manifest["stage3_cases"][0], examples),
        ("completion", manifest["stage3_cases"][-1], examples),
    ]
    answers = []
    for stage, case, directory in cases:
        images = []
        for image in case["images"]:
            identifier = uuid4()
            file = directory / image["path"]
            draft = agent.store.attach(
                draft.draft_id, actor, draft.revision, identifier, file.name, file.read_bytes()
            )
            images.append(
                {
                    "attachment_id": identifier,
                    "role": "target_page" if stage == "completion" else "source_page",
                }
            )
        answers.append(
            ExampleCase(
                id=case["id"],
                stage=stage,
                title=case["title"],
                images=images,
                kind="negative" if case == cases[-1][1] else "positive",
                expected=json.loads(
                    (directory / case.get("expected", f"{case['id']}/expected.json")).read_text(
                        encoding="utf-8"
                    )
                ),
                input=json.loads((directory / case["input"]).read_text(encoding="utf-8"))
                if case.get("input")
                else None,
            )
        )
    fields = TemplateFields(
        key="demo",
        display_name="振华测试模板",
        company_signals=["ZPMC"],
        wire_marker="放线斜杠",
        grouping_rule="Plant Function",
        page_number_rule="Page Number正整数",
        page_naming_rule="function/页号",
        cross_page_rule="功能区+页号+列回指",
        cross_page_input_mode="target_only",
    )
    tools = ProfileTools(
        agent.store,
        draft.draft_id,
        actor,
        ProfileTurn(message="按样例填写模板", intent="edit", expected_revision=draft.revision),
    )
    response = ModelToolCall(
        "fill",
        "fill_template",
        json.dumps(
            {"fields": fields.model_dump(), "cases": [case.model_dump(mode="json") for case in answers]},
            ensure_ascii=False,
        ),
    )
    result, _ = asyncio.run(tools.execute(response))
    root, meta = agent.store.root_for(draft.draft_id, actor)
    report = validate_draft(root, meta)
    assert not report.ready and {issue.code for issue in report.issues} == {"EXPECTED_UNCONFIRMED"}
    with pytest.raises(ProfileError, match="未由用户确认"):
        asyncio.run(agent.export(draft.draft_id, result["revision"], actor))
    expected = {
        case["expected_path"]: checksum((root / case["expected_path"]).read_bytes())
        for case in case_files(root)
    }
    confirmed = agent.store.confirm_expected(draft.draft_id, actor, result["revision"], expected)
    root, meta = agent.store.root_for(draft.draft_id, actor)
    assert validate_draft(root, meta).ready
    receipt = asyncio.run(agent.export(draft.draft_id, confirmed.revision, actor))
    assert receipt.checksum and not receipt.published


def test_editing_expected_invalidates_only_its_previous_confirmation(setup):
    actor, _, agent = setup
    draft = create(setup, True)
    root, _ = agent.store.root_for(draft.draft_id, actor)
    path = case_files(root)[0]["expected_path"]
    value = agent.store.read(draft.draft_id, actor, path)
    expected = json.loads(value["text"])
    expected["reason"] = "补充标题栏证据说明"
    after = agent.store.edit(
        draft.draft_id,
        actor,
        1,
        "change-answer",
        [
            FileEdit(
                path=path, before_checksum=value["checksum"], content=json.dumps(expected, ensure_ascii=False)
            )
        ],
        "explicit_instruction",
    )
    root, meta = agent.store.root_for(draft.draft_id, actor)
    unconfirmed = [
        issue.path for issue in validate_draft(root, meta).issues if issue.code == "EXPECTED_UNCONFIRMED"
    ]
    assert unconfirmed == [path]
    with pytest.raises(ProfileError, match="已变化"):
        agent.store.confirm_expected(draft.draft_id, actor, after.revision, {path: value["checksum"]})
    value = agent.store.read(draft.draft_id, actor, path)
    agent.store.confirm_expected(draft.draft_id, actor, after.revision, {path: value["checksum"]})
    root, meta = agent.store.root_for(draft.draft_id, actor)
    assert validate_draft(root, meta).ready


def test_fill_will_not_silently_overwrite_previous_precise_edits(setup):
    actor, _, agent = setup
    draft = create(setup)
    path = RESOURCES["page_scan_prompt"]
    edit = replace_text(agent, actor, draft, path, "按本模板放线标记", "按图纸细小圆圈标记")
    after = agent.store.edit(draft.draft_id, actor, 1, "custom", [edit], "explicit_instruction")
    turn = ProfileTurn(message="继续补充案例", intent="edit", expected_revision=after.revision)
    tools = ProfileTools(agent.store, draft.draft_id, actor, turn)
    asyncio.run(
        tools.execute(
            ModelToolCall("same", "fill_template", json.dumps({"fields": after.template.model_dump()}))
        )
    )
    assert "按图纸细小圆圈标记" in agent.store.read(draft.draft_id, actor, path)["text"]
    current = agent.store.get(draft.draft_id, actor)
    tools = ProfileTools(
        agent.store,
        draft.draft_id,
        actor,
        turn.model_copy(update={"turn_id": uuid4(), "expected_revision": current.revision}),
    )
    changed = current.template.model_copy(update={"wire_marker": "粗斜杠"})
    with pytest.raises(ProfileError, match="已有精确编辑"):
        asyncio.run(
            tools.execute(
                ModelToolCall("overwrite", "fill_template", json.dumps({"fields": changed.model_dump()}))
            )
        )
    assert agent.store.get(draft.draft_id, actor).revision == current.revision


def test_missing_image_reference_and_out_of_band_edits_are_not_silently_accepted(setup):
    actor, _, agent = setup
    draft = create(setup, True)
    path = "resources/wiring_examples/manifest.json"
    value = agent.store.read(draft.draft_id, actor, path)
    manifest = json.loads(value["text"])
    manifest["stage2_cases"][0]["images"][0]["path"] = "missing.png"
    with pytest.raises(ProfileError, match="不存在"):
        agent.store.edit(
            draft.draft_id,
            actor,
            1,
            "bad-reference",
            [FileEdit(path=path, before_checksum=value["checksum"], content=json.dumps(manifest))],
            "explicit_instruction",
        )
    assert agent.store.get(draft.draft_id, actor).revision == 1
    root, _ = agent.store.root_for(draft.draft_id, actor)
    (root / "resources/page_scan_prompt.md").write_text("external change", encoding="utf-8")
    with pytest.raises(ProfileError) as error:
        agent.store.get(draft.draft_id, actor)
    assert error.value.code == "DRAFT_CHANGED_EXTERNALLY"


def test_unsupported_address_mode_blocks_ready_output_and_blank_signals_stay_unknown(setup):
    actor, _, agent = setup
    draft = create(setup)
    fields = draft.template.model_copy(update={"reference_mode": "adapter_change_required"})
    tools = ProfileTools(
        agent.store,
        draft.draft_id,
        actor,
        ProfileTurn(message="填写新引用模式", intent="edit", expected_revision=1),
    )
    asyncio.run(
        tools.execute(ModelToolCall("fill", "fill_template", json.dumps({"fields": fields.model_dump()})))
    )
    root, meta = agent.store.root_for(draft.draft_id, actor)
    assert "ADAPTER_REQUIRED" in {issue.code for issue in validate_draft(root, meta).issues}
    assert TemplateFields(key="demo", display_name="Demo", company_signals=[" "]).company_signals == []


def test_proposal_is_recoverable_when_model_summary_fails(setup):
    actor, _, agent = setup
    draft = create(setup, True)
    edit = replace_text(agent, actor, draft, "resources/page_scan_prompt.md", "端子", "实际端子")
    agent.gateway = FakeModelGateway(
        [
            call("propose_edits", {"summary": "明确端子", "edits": [edit.model_dump()]}),
            RuntimeError("model failed"),
        ]
    )
    reply = asyncio.run(
        agent.ask(draft.draft_id, ProfileTurn(message="是否可以强调实际端子？", expected_revision=1), actor)
    )
    assert reply.proposals and reply.revision == 1 and not reply.changed_files
    assert "尚未修改" in reply.answer


def test_tool_budget_is_bounded_and_never_invents_edits(setup):
    actor, _, agent = setup
    draft = create(setup)
    gateway = FakeModelGateway(
        [
            *[call("inspect_profile", {}, str(index)) for index in range(12)],
            "已达到工具上限，现有资料不足以确认，请补充样例。",
        ]
    )
    agent.gateway = gateway
    reply = asyncio.run(
        agent.ask(draft.draft_id, ProfileTurn(message="检查规则", expected_revision=1), actor)
    )
    assert reply.tool_limited and not reply.changed_files and reply.revision == 1
    assert not gateway.calls[-1].tools and len(gateway.calls) == 13
    assert len(reply.model_calls) == 13


def test_first_turn_loads_rules_representative_answers_and_actual_pixels(setup):
    actor, _, agent = setup
    draft = create(setup, True)
    gateway = FakeModelGateway(["已获取规则和代表案例；没有实际异常输出，不能确认模型偏离。"])
    agent.gateway = gateway
    result = asyncio.run(
        agent.ask(draft.draft_id, ProfileTurn(message="检查前缀问题", expected_revision=1), actor)
    )
    context = next(
        message["content"]
        for message in gateway.calls[0].messages
        if isinstance(message["content"], str) and "当前可信草稿快照" in message["content"]
    )
    loaded = json.loads(context.split("\n", 1)[1])["loaded_sources"]
    paths = {item["path"] for item in loaded["readings"]}
    assert {"profile.json", "resources/routing_rules.json", "resources/page_scan_prompt.md"}.issubset(paths)
    assert any("expected.json" in path for path in paths)
    images = [
        part
        for message in gateway.calls[0].messages
        if isinstance(message.get("content"), list)
        for part in message["content"]
        if part.get("type") == "image_url"
    ]
    assert images and len(images) == len(result.viewed_images)
    assert not result.changed_files


def test_source_is_refreshed_before_fork_in_a_long_lived_agent(tmp_path):
    from src.agent.profile_agent.template import render_template

    source = tmp_path / "registry" / "demo"
    source.mkdir(parents=True)
    render_template(source, TemplateFields(key="demo", display_name="Demo"))
    registry = ProfileRegistry(profile_root=source.parent, workspace_root=tmp_path)
    registry.load_all()
    original = registry.resolve("demo", allow_experimental=True).checksum
    agent = create_profile_agent(
        AgentSettings(workspace_root=ROOT),
        state_root=tmp_path / "drafts",
        registry=registry,
        gateway=FakeModelGateway([]),
    )
    file = source / RESOURCES["page_scan_prompt"]
    file.write_text(file.read_text(encoding="utf-8") + "\n新的图纸约定", encoding="utf-8")
    actor = ProfileActor(user_id=uuid4())
    draft = asyncio.run(
        agent.create(DraftCreate(key="demo", display_name="Demo", source_profile="demo"), actor)
    )
    assert draft.source["checksum"] != original
    assert "新的图纸约定" in agent.store.read(draft.draft_id, actor, "resources/page_scan_prompt.md")["text"]
