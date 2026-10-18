from __future__ import annotations

import asyncio
import base64
import io
import json
import zipfile
from uuid import uuid4

import httpx
import pytest

from src.agent.profile_agent import create_profile_agent
from src.agent.profile_agent.editing import ProfileEditor
from src.agent.profile_agent.evidence import load_initial_evidence
from src.agent.profile_agent.models import (
    EvidenceAnchor,
    FileEdit,
    Finding,
    ProfileActor,
    ProfileEditState,
    ProfileError,
    ProfileImport,
    ProfileTurn,
    ProposalRequest,
)
from src.agent.profile_agent.template import fixed_schemas
from src.agent.profile_agent.tools import ProfileTools
from src.config import AgentSettings
from src.harness.model_gateway import FakeModelGateway, ModelResponse, ModelToolCall
from src.profiles.package import checksum, seal_package
from tests.unit.test_profile_validation import package as package


@pytest.fixture
def editor_ctx(package, tmp_path, monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("No model or database network in editing tests")

    monkeypatch.setattr(httpx.AsyncClient, "request", forbidden)
    root, *_ = package
    seal_package(root, source_checksum="sha256:" + "0" * 64)
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for file in root.rglob("*"):
            if file.is_file():
                archive.writestr(file.relative_to(root).as_posix(), file.read_bytes())
    body = ProfileImport(
        draft_id=uuid4(),
        profile_id=uuid4(),
        profile_key="optional_negative",
        profile_version="1.0.0",
        source_checksum=checksum(stream.getvalue()),
        display_name="编辑测试",
        content_base64=base64.b64encode(stream.getvalue()).decode(),
    )
    agent = create_profile_agent(
        AgentSettings(), state_root=tmp_path / "editing", gateway=FakeModelGateway([])
    )
    actor = ProfileActor(user_id=uuid4())
    editor = ProfileEditor(agent.store)
    state = editor.import_profile(body, actor)
    return agent, actor, editor, state, body


def test_import_manual_edit_review_and_export_do_not_overwrite_source(editor_ctx):
    agent, actor, editor, state, body = editor_ctx
    assert state.draft.version == "1.0.1" and state.validation.ready
    assert editor.import_profile(body, actor).draft == state.draft
    file = next(f for f in state.package.files if f.path == "resources/scan.md")
    changed = agent.store.edit(
        state.draft.draft_id,
        actor,
        state.draft.revision,
        "manual-1",
        [FileEdit(path=file.path, before_checksum=file.checksum, content=file.content + "\n仅识别实际标记")],
        "explicit_instruction",
    )
    assert not editor.state(changed.draft_id, actor).validation.ready
    with pytest.raises(ProfileError, match="尚未就绪"):
        asyncio.run(agent.export(changed.draft_id, changed.revision, actor))
    accepted = editor.accept(changed.draft_id, actor, changed.revision)
    assert accepted.validation.ready
    receipt = asyncio.run(agent.export(changed.draft_id, accepted.draft.revision, actor))
    assert receipt.version == "1.0.1" and not receipt.published
    with pytest.raises(ProfileError):
        editor.state(changed.draft_id, ProfileActor(user_id=uuid4()))


def test_image_result_diagnosis_proposes_and_applies_only_after_confirmation(editor_ctx):
    agent, actor, editor, state, _ = editor_ctx
    file = next(f for f in state.package.files if f.path == "resources/scan.md")
    request = ProposalRequest(
        summary="避免强制补前缀",
        edits=[
            FileEdit(
                path=file.path,
                before_checksum=file.checksum,
                content=file.content + "\n不要添加图中未出现的GTR前缀",
            )
        ],
    )
    agent.gateway = FakeModelGateway(
        [
            ModelResponse(
                content="",
                model="fake",
                parsed=None,
                duration_seconds=0,
                attempts=1,
                tool_calls=(ModelToolCall("proposal", "propose_edits", request.model_dump_json()),),
            ),
            "已结合原图、样例及用户实际输出提出建议，请确认差异。",
        ]
    )
    reply = asyncio.run(
        agent.ask(
            state.draft.draft_id,
            ProfileTurn(
                message="结果端子多了GTR前缀，分析并提出修改",
                expected_revision=state.draft.revision,
                observations=[{"actual_result": "GTR-X3:1", "expected": "X3:1"}],
                focus_stage="scan",
            ),
            actor,
        )
    )
    assert reply.proposals and not reply.changed_files and reply.revision == state.draft.revision
    prompt = json.dumps(agent.gateway.calls[0].messages, ensure_ascii=False)
    assert "GTR-X3:1" in prompt and "expected.json" in prompt and "image_url" in prompt
    proposal = reply.proposals[0]
    updated = asyncio.run(agent.confirm(state.draft.draft_id, proposal.id, reply.revision, True, actor))
    assert updated.revision == state.draft.revision + 1
    assert not editor.state(updated.draft_id, actor).validation.ready
    accepted = editor.accept(updated.draft_id, actor, updated.revision)
    assert accepted.validation.ready
    with pytest.raises(ProfileError, match="先提出"):
        asyncio.run(
            agent.ask(
                updated.draft_id,
                ProfileTurn(message="直接修改", intent="edit", expected_revision=accepted.draft.revision),
                actor,
            )
        )


def test_bad_archive_and_stale_manual_save_are_rejected(editor_ctx):
    agent, actor, editor, state, body = editor_ctx
    with pytest.raises(ProfileError, match="校验失败"):
        editor.import_profile(body.model_copy(update={"content_base64": "invalid"}), actor)
    file = next(f for f in state.package.files if f.path == "resources/scan.md")
    with pytest.raises(ProfileError, match="摘要"):
        agent.store.edit(
            state.draft.draft_id,
            actor,
            state.draft.revision,
            "stale",
            [FileEdit(path=file.path, before_checksum="sha256:" + "f" * 64, content="bad")],
            "explicit_instruction",
        )


def test_old_published_schema_upgrades_only_the_new_edit_draft(editor_ctx):
    agent, actor, editor, state, body = editor_ctx
    with zipfile.ZipFile(io.BytesIO(base64.b64decode(body.content_base64))) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    prior = json.loads(files["schema.json"])
    prior["stage2"]["description"] = "Previous extraction protocol"
    files["schema.json"] = json.dumps(prior).encode()
    inventory = json.loads(files["manifest.json"])
    entry = next(item for item in inventory["files"] if item["path"] == "schema.json")
    entry.update(checksum=checksum(files["schema.json"]), size=len(files["schema.json"]))
    inventory["package_checksum"] = checksum(
        json.dumps(
            sorted(inventory["files"], key=lambda item: item["path"]), sort_keys=True, separators=(",", ":")
        ).encode()
    )
    files["manifest.json"] = json.dumps(inventory).encode()
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    upgraded = editor.import_profile(
        body.model_copy(
            update={
                "draft_id": uuid4(),
                "source_checksum": checksum(stream.getvalue()),
                "content_base64": base64.b64encode(stream.getvalue()).decode(),
            }
        ),
        actor,
    )
    schema = next(item for item in upgraded.package.files if item.path == "schema.json")
    assert json.loads(schema.content) == fixed_schemas()
    assert upgraded.validation.ready and any("旧字段定义" in warning for warning in upgraded.draft.warnings)
    assert json.loads(files["schema.json"]) == prior
    with pytest.raises(ProfileError, match="不能"):
        agent.store.edit(
            state.draft.draft_id,
            actor,
            state.draft.revision,
            "protected",
            [FileEdit(path="profile.json", before_checksum=None, content="{}")],
            "explicit_instruction",
        )


def evidence_request(state: ProfileEditState, anchors: list[EvidenceAnchor]) -> ProposalRequest:
    file = next(f for f in state.package.files if f.path == "resources/scan.md")
    return ProposalRequest(
        summary="保留完整端子标识，等待用户核对",
        edits=[
            FileEdit(
                path=file.path, before_checksum=file.checksum, content=file.content + "\n保留完整端子标识"
            )
        ],
        findings=[Finding(category="rule_issue", explanation="核对完整端子标识的约束", evidence=anchors)],
    )


def test_viewed_image_evidence_records_and_persists_a_proposal(editor_ctx):
    agent, actor, _, state, _ = editor_ctx
    tools = ProfileTools(
        agent.store,
        state.draft.draft_id,
        actor,
        ProfileTurn(message="请分析端子标识", expected_revision=state.draft.revision),
    )
    load_initial_evidence(tools)
    image = next(iter(tools.viewed))
    request = evidence_request(state, [EvidenceAnchor(path=image, quote="图片中的端子标识需要人工核对")])
    diagnosis, _ = asyncio.run(
        tools.execute(
            ModelToolCall(
                "diagnosis",
                "record_diagnosis",
                json.dumps({"findings": [f.model_dump() for f in request.findings]}),
            )
        )
    )
    assert diagnosis["evidence_verification"][0]["verification"] == "viewed_image"
    result, _ = asyncio.run(
        tools.execute(ModelToolCall("proposal", "propose_edits", request.model_dump_json()))
    )
    assert agent.store.proposal(tools.draft, actor, result["id"]).status == "pending"
    assert agent.store.get(tools.draft, actor).revision == state.draft.revision


@pytest.mark.parametrize("source", ["image", "observation"])
def test_store_revalidates_trusted_evidence_context(editor_ctx, source):
    agent, actor, _, state, _ = editor_ctx
    image = state.package.images[0].path
    anchors = [EvidenceAnchor(path=image, quote="可见标记")]
    if source == "observation":
        anchors.append(EvidenceAnchor(path="observations/0", quote='端子 "XD3:251"\n实际结果'))
    request = evidence_request(state, anchors)
    with pytest.raises(ProfileError) as failure:
        agent.store.propose(state.draft.draft_id, actor, state.draft.revision, uuid4(), request)
    assert failure.value.code == "EVIDENCE_IMAGE_NOT_VIEWED"
    proposal = agent.store.propose(
        state.draft.draft_id,
        actor,
        state.draft.revision,
        uuid4(),
        request,
        viewed_images={image},
        observations=[{"actual": {"text": '端子 "XD3:251"\n实际结果'}}],
    )
    assert proposal.status == "pending"


@pytest.mark.parametrize(
    "path,quote,code",
    [
        ("../foreign/scan.md", "伪造", "INVALID_EVIDENCE_PATH"),
        ("resources/scan.md", "不存在的规则原文-abc123", "INVALID_EVIDENCE"),
        ("observations/9", "XD3:251", "INVALID_EVIDENCE"),
        ("observations/no", "XD3:251", "INVALID_EVIDENCE"),
        ("user_message", "未提供的内容", "INVALID_EVIDENCE"),
    ],
)
def test_forged_diagnostic_anchors_are_rejected(editor_ctx, path, quote, code):
    agent, actor, _, state, _ = editor_ctx
    tools = ProfileTools(
        agent.store,
        state.draft.draft_id,
        actor,
        ProfileTurn(message="请分析", expected_revision=state.draft.revision),
    )
    with pytest.raises(ProfileError) as failure:
        tools.check_findings(evidence_request(state, [EvidenceAnchor(path=path, quote=quote)]).findings)
    assert failure.value.code == code


def test_user_claims_alone_do_not_prove_attribution(editor_ctx):
    agent, actor, _, state, _ = editor_ctx
    tools = ProfileTools(
        agent.store,
        state.draft.draft_id,
        actor,
        ProfileTurn(message="每次都出错", expected_revision=state.draft.revision),
    )
    with pytest.raises(ProfileError) as failure:
        tools.check_findings(
            evidence_request(state, [EvidenceAnchor(path="user_message", quote="每次都出错")]).findings
        )
    assert failure.value.code == "EVIDENCE_REQUIRED"


def test_graph_recovers_bad_anchor_then_records_and_proposes(editor_ctx, caplog):
    agent, actor, _, state, _ = editor_ctx
    image = state.package.images[0].path
    request = evidence_request(
        state,
        [
            EvidenceAnchor(path=image, quote="图中可见标识，仍需用户核对"),
            EvidenceAnchor(path="observations/0", quote="251"),
        ],
    )
    bad = request.model_copy(deep=True)
    bad.findings[0].evidence[0].path = "../foreign.png"

    def response(name: str, args: dict, identifier: str) -> ModelResponse:
        return ModelResponse(
            content="",
            model="fake",
            parsed=None,
            duration_seconds=0,
            attempts=1,
            tool_calls=(ModelToolCall(identifier, name, json.dumps(args)),),
        )

    agent.gateway = FakeModelGateway(
        [
            response("record_diagnosis", {"findings": [f.model_dump() for f in bad.findings]}, "bad"),
            response(
                "record_diagnosis", {"findings": [f.model_dump() for f in request.findings]}, "diagnosis"
            ),
            response("propose_edits", request.model_dump(), "proposal"),
            "已提交待确认建议，请核对差异。",
        ]
    )
    reply = asyncio.run(
        agent.ask(
            state.draft.draft_id,
            ProfileTurn(
                message="请结合图纸分析并提出建议",
                expected_revision=state.draft.revision,
                observations=[{"actual_result": "251"}],
                focus_stage="scan",
            ),
            actor,
        )
    )
    assert len(reply.proposals) == 1 and not reply.changed_files
    assert reply.revision == state.draft.revision
    assert "INVALID_EVIDENCE_PATH" in json.dumps(agent.gateway.calls[1].messages, ensure_ascii=False)
    assert "viewed_image" in json.dumps(agent.gateway.calls[2].messages, ensure_ascii=False)
    assert "profile_tool_rejected tool=record_diagnosis code=INVALID_EVIDENCE_PATH" in caplog.text
    assert "../foreign.png" not in caplog.text
