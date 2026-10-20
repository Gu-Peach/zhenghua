from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import httpx
import pytest
from test_main_assistant_api import AssistantBackend, client_for, seed_turn
from test_simple_management_api import OTHER, OWNER


class DeletionBackend(AssistantBackend):
    def respond(self, request):
        if (
            request.url.path == "/storage/v1/object/project-assets"
            and request.method == "DELETE"
        ):
            self.calls.append(request)
            if self.fail_delete:
                return httpx.Response(503, json={})
            for path in json.loads(request.content)["prefixes"]:
                self.uploads.pop(f"/storage/v1/object/project-assets/{path}", None)
            return httpx.Response(200, json={})
        if request.url.path.endswith("/rpc/assistant_delete_conversation"):
            body = json.loads(request.content)
            rows = self.tables["assistant_conversations"]
            saved = next((r for r in rows if r["id"] == body["conversation"]), None)
            if saved and saved["owner_id"] != body["actor"]:
                return httpx.Response(404, json={"code": "PT404"})
            if saved:
                turns = [
                    r
                    for r in self.tables["assistant_turns"]
                    if r["conversation_id"] == saved["id"]
                ]
                if any(
                    r["status"] == "running"
                    and r.get("lease_until", "")
                    > datetime.now(timezone.utc).isoformat()
                    for r in turns
                ):
                    return httpx.Response(409, json={"code": "PT409"})
                for asset in self.tables["assistant_attachments"]:
                    if asset["conversation_id"] == saved["id"]:
                        self.tables["assistant_asset_gc"].append({**asset})
                for table in (
                    "assistant_conversations",
                    "assistant_turns",
                    "assistant_actions",
                    "assistant_attachments",
                ):
                    self.tables[table] = [
                        r
                        for r in self.tables[table]
                        if (
                            r["id"]
                            if table == "assistant_conversations"
                            else r["conversation_id"]
                        )
                        != saved["id"]
                    ]
            return httpx.Response(200, json=True)
        return super().respond(request)


def seed_history(backend):
    conversation, turn, _ = seed_turn(backend)
    backend.tables["assistant_turns"][-1]["status"] = "completed"
    asset = str(uuid4())
    path = f"assistant/{OWNER}/{conversation}/{asset}/fixture"
    backend.tables["assistant_attachments"].append(
        {
            "id": asset,
            "owner_id": OWNER,
            "conversation_id": conversation,
            "storage_path": path,
            "uploaded": True,
        }
    )
    backend.uploads[f"/storage/v1/object/project-assets/{path}"] = b"fixture"
    backend.tables["assistant_actions"].append(
        {
            "id": str(uuid4()),
            "turn_id": turn,
            "owner_id": OWNER,
            "conversation_id": conversation,
            "status": "completed",
            "result": {"kind": "rescan", "run_id": "independent-run"},
        }
    )
    return conversation, path


def test_delete_history_is_physical_idempotent_and_keeps_business_records():
    backend = DeletionBackend()
    conversation, path = seed_history(backend)
    other, _, _ = seed_turn(backend)
    business = json.dumps(backend.tables["extraction_connection_rows"], sort_keys=True)
    with client_for(backend) as client:
        result = client.delete(f"/api/v1/assistant/conversations/{conversation}")
        assert result.status_code == 204, result.text
        assert not result.content
        assert (
            client.get(f"/api/v1/assistant/conversations/{conversation}").status_code
            == 404
        )
        assert (
            client.delete(f"/api/v1/assistant/conversations/{conversation}").status_code
            == 204
        )
    assert backend.tables["assistant_actions"] == []
    assert backend.tables["assistant_attachments"] == []
    assert [r["id"] for r in backend.tables["assistant_conversations"]] == [other]
    assert f"/storage/v1/object/project-assets/{path}" not in backend.uploads
    assert backend.tables["assistant_asset_gc"] == []
    assert (
        json.dumps(backend.tables["extraction_connection_rows"], sort_keys=True)
        == business
    )


def test_delete_denies_other_owner_and_live_turn():
    backend = DeletionBackend()
    conversation, _, _ = seed_turn(backend)
    backend.tables["assistant_turns"][-1]["lease_until"] = (
        datetime.now(timezone.utc) + timedelta(minutes=10)
    ).isoformat()
    with client_for(backend) as client:
        denied = client.delete(
            f"/api/v1/assistant/conversations/{conversation}",
            headers={"Authorization": "Bearer other"},
        )
        assert denied.status_code == 404
        assert (
            client.delete(f"/api/v1/assistant/conversations/{conversation}").status_code
            == 409
        )
        assert (
            client.delete(
                f"/api/v1/assistant/conversations/{conversation}",
                headers={"Authorization": ""},
            ).status_code
            == 401
        )
    assert backend.tables["assistant_conversations"][0]["owner_id"] == OWNER
    assert backend.tables["assistant_asset_gc"] == []


def test_storage_failure_keeps_durable_cleanup_for_later_list_retry():
    backend = DeletionBackend()
    conversation, path = seed_history(backend)
    backend.fail_delete = True
    with client_for(backend) as client:
        result = client.delete(f"/api/v1/assistant/conversations/{conversation}")
        assert result.status_code == 204
        assert backend.tables["assistant_conversations"] == []
        assert backend.tables["assistant_asset_gc"]
        backend.fail_delete = False
        assert client.get("/api/v1/assistant/conversations").json() == []
    assert backend.tables["assistant_asset_gc"] == []
    assert f"/storage/v1/object/project-assets/{path}" not in backend.uploads


@pytest.mark.parametrize(
    "path",
    [
        f"projects/{uuid4()}/original.pdf",
        f"assistant/{OTHER}/conversation/asset/file",
        "assistant/../file",
    ],
)
def test_cleanup_rejects_foreign_or_non_assistant_storage(path):
    backend = DeletionBackend()
    backend.tables["assistant_asset_gc"].append(
        {
            "id": str(uuid4()),
            "owner_id": OWNER,
            "conversation_id": str(uuid4()),
            "storage_path": path,
        }
    )
    with client_for(backend) as client:
        assert client.get("/api/v1/assistant/conversations").status_code == 200
    assert not any(
        r.method == "DELETE" and "/storage/" in r.url.path for r in backend.calls
    )
