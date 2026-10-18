from __future__ import annotations

import json
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
from test_simple_management_api import OTHER, OWNER, PROJECT, ROW, Backend, api
from wiring_server.explain_contract import ConnectionEditProposal


def test_owner_bound_preview_decision_and_payload_cannot_replace_changes():
    backend = Backend()
    identifier = str(uuid4())
    proposal = {
        "proposal_id": identifier,
        "project_id": PROJECT,
        "batch_id": "run-one",
        "checksum": "sha256:" + "a" * 64,
        "status": "pending",
        "request": {
            "scope": {"workspace_code": "003.C"},
            "operation": {"kind": "swap_endpoints"},
            "reason": "用户要求",
        },
        "matched_count": 1,
        "changed_count": 1,
        "changes": [
            {
                "connection_id": ROW,
                "record_version": 1,
                "principle_number": "P1",
                "before": {"start_terminal": "XA:1", "end_terminal": "XD3:1"},
                "after": {"start_terminal": "XD3:1", "end_terminal": "XA:1"},
            }
        ],
        "created_at": "2026-10-18T00:00:00Z",
        "expires_at": "2026-10-19T00:00:00Z",
    }
    calls = []

    def respond(request):
        if request.url.path.endswith("/connection_edit_proposals"):
            assert request.url.params["created_by"] == f"eq.{OWNER}"
            return httpx.Response(200, json=[proposal])
        if request.url.path.endswith("/rpc/decide_explain_connection_edit"):
            body = json.loads(request.content)["value"]
            calls.append(body)
            assert body["actor"] == OWNER and body["proposal_id"] == identifier
            return httpx.Response(
                200,
                json={
                    "proposal_id": identifier,
                    "project_id": PROJECT,
                    "batch_id": "run-one",
                    "status": "applied" if body["accepted"] else "rejected",
                    "changed_count": 1 if body["accepted"] else 0,
                    "versions": {ROW: 2},
                    "idempotent": False,
                },
            )
        return backend.respond(request)

    app = api.create_app(
        api.Settings("http://database", "private-test-key"),
        httpx.MockTransport(respond),
    )
    with TestClient(app, headers={"Authorization": "Bearer owner"}) as client:
        base = f"/api/v1/projects/{PROJECT}/connection-edits"
        assert client.get(base).status_code == 200
        assert (
            ConnectionEditProposal.model_validate(
                client.get(base + "/" + identifier).json()
            ).changed_count
            == 1
        )
        response = client.post(
            base + f"/{identifier}/decision",
            json={
                "checksum": proposal["checksum"],
                "accepted": True,
                "changes": {"start_terminal": "forged"},
            },
        )
        assert response.status_code == 422 and not calls
        assert (
            client.post(
                base + f"/{identifier}/decision",
                json={"checksum": proposal["checksum"], "accepted": True},
                headers={"Authorization": "Bearer other"},
            ).status_code
            == 403
        )
        assert not calls
        response = client.post(
            base + f"/{identifier}/decision",
            json={"checksum": proposal["checksum"], "accepted": True},
            headers={"X-Explain-User-Id": OTHER},
        )
        assert response.status_code == 200 and response.json()["versions"][ROW] == 2
