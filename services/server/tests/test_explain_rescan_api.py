from __future__ import annotations

import base64
import json
from uuid import uuid4

import httpx
import pymupdf
from fastapi.testclient import TestClient
from test_simple_management_api import OTHER, OWNER, PROJECT, Backend, api


def test_detail_upload_is_private_page_bound_idempotent_and_validated():
    backend = Backend()
    backend.tables["connection_rescan_assets"] = []
    app = api.create_app(
        api.Settings("http://database", "test-key"),
        httpx.MockTransport(backend.respond),
    )
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 30))
    pix.clear_with(255)
    value = {
        "conversation_id": str(uuid4()),
        "pdf_page_number": 1,
        "role": "source",
        "content_base64": base64.b64encode(pix.tobytes("png")).decode(),
    }
    with TestClient(app, headers={"Authorization": "Bearer owner"}) as client:
        path = f"/api/v1/projects/{PROJECT}/rescan-assets"
        response = client.post(path, json=value)
        assert response.status_code == 200, response.text
        asset = response.json()
        assert (
            asset["width"] == 20
            and asset["height"] == 30
            and "storage_path" not in asset
        )
        assert backend.tables["connection_rescan_assets"][0]["created_by"] == OWNER
        assert len(backend.uploads) == 1
        assert (
            client.post(path, json=value).json()["id"] == asset["id"]
            and len(backend.uploads) == 1
        )
        assert client.get(path + "/" + asset["id"]).status_code == 200
        assert (
            client.get(
                path + "/" + asset["id"], headers={"Authorization": "Bearer other"}
            ).status_code
            == 403
        )
        assert (
            client.post(path, json={**value, "pdf_page_number": 999}).status_code == 422
        )
        assert (
            client.post(
                path,
                json={
                    **value,
                    "content_base64": base64.b64encode(b"not an image").decode(),
                },
            ).status_code
            == 422
        )
        assert (
            client.post(
                path, json=value, headers={"Authorization": "Bearer other"}
            ).status_code
            == 403
        )
        assert len(backend.uploads) == 1


def test_candidate_read_and_confirmation_bind_owner_and_disallow_client_patch():
    backend = Backend()
    identifier = str(uuid4())
    calls = []
    run = {
        "id": identifier,
        "project_id": PROJECT,
        "batch_id": "run-one",
        "conversation_id": str(uuid4()),
        "status": "ready",
        "stage": "ready",
        "request": {
            "scope": {"workspace_code": "003.C"},
            "fields": "end",
            "instructions": "终点重扫",
        },
        "profile": {"key": "zh", "version": "1.0.0"},
        "checksum": "sha256:" + "a" * 64,
        "created_at": "now",
        "updated_at": "now",
    }

    def respond(request):
        if request.url.path.endswith("/connection_rescan_runs"):
            assert (
                request.url.params["project_id"] == f"eq.{PROJECT}"
                and request.url.params["created_by"] == f"eq.{OWNER}"
            )
            return httpx.Response(200, json=[run])
        if request.url.path.endswith("/rpc/decide_connection_rescan"):
            body = json.loads(request.content)["value"]
            calls.append(body)
            assert body["actor"] == OWNER and body["project_id"] == PROJECT
            return httpx.Response(200, json={**run, "status": "applied"})
        return backend.respond(request)

    app = api.create_app(
        api.Settings("http://database", "test-key"), httpx.MockTransport(respond)
    )
    with TestClient(app, headers={"Authorization": "Bearer owner"}) as client:
        path = f"/api/v1/projects/{PROJECT}/rescans/{identifier}"
        assert client.get(path).status_code == 200
        assert (
            client.get(path, headers={"Authorization": "Bearer other"}).status_code
            == 403
        )
        assert (
            client.post(
                path + "/decision",
                json={
                    "checksum": run["checksum"],
                    "accepted": True,
                    "changes": {"end_terminal": "forged"},
                },
            ).status_code
            == 422
        )
        assert not calls
        assert (
            client.post(
                path + "/decision",
                json={"checksum": run["checksum"], "accepted": True},
                headers={"X-Explain-User-Id": OTHER},
            ).status_code
            == 200
        )
        assert len(calls) == 1


def test_failed_upload_is_pending_and_project_delete_cleans_registered_details():
    backend = Backend()
    backend.fail_upload = True
    app = api.create_app(
        api.Settings("http://database", "test-key"),
        httpx.MockTransport(backend.respond),
    )
    pix = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 12, 12))
    pix.clear_with(255)
    value = {
        "conversation_id": str(uuid4()),
        "pdf_page_number": 1,
        "role": "source",
        "content_base64": base64.b64encode(pix.tobytes("png")).decode(),
    }
    with TestClient(app, headers={"Authorization": "Bearer owner"}) as client:
        path = f"/api/v1/projects/{PROJECT}/rescan-assets"
        assert client.post(path, json=value).status_code >= 400
        assert backend.tables["connection_rescan_assets"][0]["uploaded"] is False
        backend.fail_upload = False
        response = client.post(path, json=value)
        assert response.status_code == 200
        asset_path = backend.tables["connection_rescan_assets"][0]["storage_path"]
        stamp = backend.tables["extraction_projects"][0]["updated_at"]
        assert (
            client.delete(
                f"/api/v1/projects/{PROJECT}",
                params={"confirmed": "true", "expected_updated_at": stamp},
            ).status_code
            == 204
        )
        removals = [
            json.loads(request.content)
            for request in backend.calls
            if request.method == "DELETE"
            and request.url.path == "/storage/v1/object/project-assets"
        ]
        assert any(asset_path in request["prefixes"] for request in removals)
