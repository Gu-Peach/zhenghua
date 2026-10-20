from __future__ import annotations

import asyncio
import hashlib
import json
from uuid import uuid4

import pytest
from test_main_assistant_api import AssistantBackend, client_for, seed_turn
from test_simple_management_api import OWNER, PROFILE, PROJECT
from wiring_server.assistant_contract import AssistantScope, ProfileDiagnosis
from wiring_server.assistant_evidence import AssistantEvidence, BoundProfile
from wiring_server.assistant_profile import AssistantProfile
from wiring_server.assistant_store import fingerprint
from wiring_server.profile_authoring import ProfileAuthoring
from wiring_server.profile_references import ProfileReferences
from wiring_server.repository import ServiceError


def test_unexpected_tool_exception_is_persisted_and_safely_reported(
    monkeypatch, caplog
):
    from wiring_server.assistant_tools import AssistantTools

    backend = AssistantBackend()
    _, turn, headers = seed_turn(backend, {"project_id": PROJECT})

    async def broken(self, *args):
        raise ImportError("private-module-secret")

    monkeypatch.setattr(AssistantTools, "dispatch", broken)
    with client_for(backend) as client:
        response = client.post(
            f"/api/internal/assistant/turns/{turn}/tools",
            headers=headers,
            json={"name": "diagnose_profile", "arguments": {"question": "检查规则"}},
        )
    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "ASSISTANT_TOOL_INTERNAL_ERROR"
    action = backend.tables["assistant_actions"][0]
    assert action["status"] == "failed"
    assert action["result"]["code"] == "ASSISTANT_TOOL_INTERNAL_ERROR"
    assert action["id"] in caplog.text and "ImportError" in caplog.text
    assert "private-module-secret" not in caplog.text + response.text + json.dumps(
        action
    )


@pytest.mark.parametrize("frozen_key", ["zh", "zh_crop", "abb"])
def test_diagnosis_reads_frozen_archive_then_proposes_on_latest_editable(
    monkeypatch, frozen_key
):
    calls = []
    latest_id = str(uuid4())

    async def bound(self, scope, user):
        return BoundProfile(
            {"id": PROFILE},
            {"key": frozen_key, "version": "2.1.1", "display_name": "振华"},
            {},
            b"frozen-old",
            "sha256:old",
            "frozen_run_artifact",
        )

    async def overview(self, scope, user):
        return {"scope": scope.model_dump(mode="json"), "records": [], "gaps": []}

    async def attach(self, turn, draft, scope, state):
        return state["draft"]["revision"]

    async def profiles(self, user):
        return [
            {
                "id": latest_id,
                "profile_key": "zh",
                "checksum": "sha256:latest",
                "created_by": OWNER,
            }
        ]

    async def fork(self, identifier, draft, checksum, user):
        calls.append(("fork", identifier, checksum))
        assert identifier == latest_id and checksum == "sha256:latest"
        return {"draft": {"revision": 1}}

    async def call(self, method, path, user, body=None):
        calls.append((path, body))
        if path == "/imports":
            assert body["read_only"] and body["profile_version"] == "2.1.1"
            assert body["profile_key"] == frozen_key
            assert body["source_checksum"] == "sha256:old"
            return {"draft": {"revision": 1}}
        if "只读诊断" in body["message"]:
            return {"answer": "旧规则的引用说明不足", "findings": []}
        assert body["intent"] == "discuss" and "不得调用apply_edits" in body["message"]
        return {
            "answer": "最新版本仍需补充引用校对",
            "proposals": [
                {
                    "id": str(uuid4()),
                    "status": "pending",
                    "base_revision": 1,
                    "base_checksum": "draft",
                    "diffs": [{"path": "prompt.md", "before": "old", "after": "new"}],
                }
            ],
        }

    monkeypatch.setattr(AssistantEvidence, "bound_profile", bound)
    monkeypatch.setattr(AssistantEvidence, "overview", overview)
    monkeypatch.setattr(AssistantProfile, "attach", attach)
    monkeypatch.setattr(ProfileReferences, "list", profiles)
    monkeypatch.setattr(ProfileAuthoring, "fork", fork)
    monkeypatch.setattr(ProfileAuthoring, "call", call)
    backend = AssistantBackend()
    with client_for(backend) as client:
        service = AssistantProfile(client.app.state.db)
        result = asyncio.run(
            service.diagnose(
                {"owner_id": OWNER, "conversation_id": str(uuid4()), "request": {}},
                {"id": str(uuid4())},
                AssistantScope(project_id=PROJECT, workspace_code="003.C"),
                ProfileDiagnosis(question="检查并建议修改", propose_changes=True),
            )
        )
        if frozen_key == "abb":
            assert (
                result["needs_profile_selection"]
                and "旧规则的引用说明不足" in result["answer"]
            )
            assert not any(item[0] == "fork" for item in calls)
            return
        assert (
            result["kind"] == "profile"
            and result["frozen_profile"]["version"] == "2.1.1"
        )
        assert result["latest_profile_id"] == latest_id
        if frozen_key == "zh_crop":
            assert (
                result["frozen_profile"]["key"] == "zh_crop"
                and result["editing_profile"]["key"] == "zh"
            )
        assert not any(
            "confirm" in str(item[0]) or "publish" in str(item[0]) for item in calls
        )


@pytest.mark.parametrize("lost_review_receipt", [False, True])
def test_profile_confirmation_resumes_publication_without_reapplying_diff(
    monkeypatch, lost_review_receipt
):
    backend = AssistantBackend()
    conversation, turn, _ = seed_turn(backend, {"project_id": PROJECT})
    identifier, draft, proposal = map(str, (uuid4(), uuid4(), uuid4()))
    diffs = [{"path": "resources/prompt.md", "before": "原值", "after": "新值"}]
    result = {
        "kind": "profile",
        "scope": {"project_id": PROJECT},
        "draft_id": draft,
        "proposal_id": proposal,
        "base_revision": 1,
        "base_checksum": "draft-1",
        "proposal_fingerprint": hashlib.sha256(
            json.dumps(diffs, sort_keys=True).encode()
        ).hexdigest(),
    }
    checksum = fingerprint(result)
    backend.tables["assistant_actions"].append(
        {
            "id": identifier,
            "conversation_id": conversation,
            "turn_id": turn,
            "owner_id": OWNER,
            "tool_name": "diagnose_profile",
            "status": "awaiting_confirmation",
            "result": result,
            "checksum": checksum,
            "arguments": {},
        }
    )
    calls, revision, publications = [], 1, 0

    async def call(self, method, path, user, body=None):
        nonlocal revision
        calls.append(path)
        if path.endswith("/confirm"):
            revision = max(revision, 2)
            return {"revision": revision}
        if path.endswith("/editor/accept"):
            revision = 3
            return {"draft": {"revision": revision}}
        return {
            "diffs": diffs,
            "base_checksum": "draft-1",
            "applied_revision": 2,
            "status": "pending" if revision == 1 else "accepted",
        }

    async def publish(self, draft_id, reviewed, user):
        nonlocal publications
        publications += 1
        assert reviewed == 3
        if publications == 1:
            raise ServiceError(503, "PROFILE_STORAGE_FAILED", "存储暂不可用")
        return {"id": str(uuid4()), "profile_version": "2.3.1"}

    monkeypatch.setattr(ProfileAuthoring, "call", call)
    monkeypatch.setattr(ProfileAuthoring, "publish", publish)
    with client_for(backend) as client:
        path = f"/api/v1/assistant/actions/{identifier}/decision"
        assert (
            client.post(path, json={"checksum": "wrong", "accepted": True}).status_code
            == 409
        )
        assert not calls
        body = {"checksum": checksum, "accepted": True}
        assert client.post(path, json=body).status_code == 503
        assert backend.tables["assistant_actions"][0]["result"]["review_revision"] == 3
        if lost_review_receipt:
            backend.tables["assistant_actions"][0]["result"].pop("review_revision")
        response = client.post(path, json=body)
        assert response.status_code == 200, response.text
        assert response.json()["status"] == "applied"
        assert sum(path.endswith("/editor/accept") for path in calls) == (
            2 if lost_review_receipt else 1
        )
        assert (
            client.post(path, json=body).json()["status"] == "applied"
            and publications == 2
        )
        assert client.post(path, json={**body, "accepted": False}).status_code == 409
