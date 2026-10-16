from __future__ import annotations

# Historical old-table/Supervisor contract fixture. New management tests live separately.

import copy
import importlib.util
import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "workbench_api", ROOT / "apps/api/src/main.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
from wiring_server.config import Settings

USER, OTHER, PROJECT, DRAWING, CONNECTION, RESULT, SOURCE = [
    str(uuid4()) for _ in range(7)
]


class FakeBackend:
    def __init__(self) -> None:
        self.requests = []
        self.storage_delete_fails = False
        self.agent_auth_fails = False
        self.tables = {
            "projects": [
                {
                    "id": PROJECT,
                    "name": "test0",
                    "owner_id": USER,
                    "status": "ready",
                    "updated_at": "2026-10-12T00:00:00Z",
                    "published_classification_snapshot_id": "snapshot",
                }
            ],
            "project_members": [],
            "workspaces": [
                {
                    "id": "workspace",
                    "project_id": PROJECT,
                    "name": "006.M",
                    "code": "006.M",
                    "classification_snapshot_id": "snapshot",
                    "sort_order": 0,
                }
            ],
            "drawings": [
                {
                    "id": DRAWING,
                    "project_id": PROJECT,
                    "workspace_id": "workspace",
                    "pdf_page_number": 1,
                    "workspace_page": "1",
                    "status": "scanned",
                    "classification_snapshot_id": "snapshot",
                    "image_bucket": "project-assets",
                    "image_path": "private.png",
                }
            ],
            "document_files": [
                {
                    "id": SOURCE,
                    "project_id": PROJECT,
                    "kind": "source_pdf",
                    "original_filename": "test.pdf",
                }
            ],
            "result_versions": [
                {
                    "id": RESULT,
                    "project_id": PROJECT,
                    "version": 4,
                    "revision": 4,
                    "profile": {
                        "key": "zh",
                        "version": "1.0.0",
                        "checksum": "sha256:fixture",
                    },
                }
            ],
            "wiring_connection_rows": [
                {
                    "connection_id": CONNECTION,
                    "project_id": PROJECT,
                    "workspace_id": "workspace",
                    "workspace_name": "006.M",
                    "drawing_id": DRAWING,
                    "wiring_unit_id": "unit",
                    "workspace_page": "1",
                    "pdf_page_number": 1,
                    "wire_number": 1001,
                    "core_order": 1,
                    "result_version_id": RESULT,
                    "result_version": 4,
                    "result_revision": 4,
                    "record_version": 2,
                    "start_terminal": "XD3:113",
                    "end_terminal": "999",
                    "is_cross_page": "cross_page",
                    "needs_review": False,
                    "status": "confirmed",
                    "source_document_id": SOURCE,
                }
            ],
            "wiring_connections": [
                {
                    "id": CONNECTION,
                    "wiring_unit_id": "unit",
                    "source_drawing_id": DRAWING,
                    "record_version": 2,
                    "start_terminal": "XD3:113",
                    "end_terminal": "999",
                    "is_cross_page": "cross_page",
                    "confidence": 0.9,
                    "raw_payload": {"end": {"terminal": "999"}},
                }
            ],
            "result_proposals": [],
            "feedback_items": [],
            "agent_runs": [],
            "connection_evidence": [],
        }

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path == "/auth/v1/token":
            data = json.loads(request.content)
            if (
                data.get("password") == "invalid"
                or data.get("refresh_token") == "expired-refresh"
            ):
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(
                200,
                json={
                    "access_token": "valid",
                    "refresh_token": "rotated-refresh",
                    "expires_in": 3600,
                    "user": {"id": USER, "email": "fixture@example.invalid"},
                },
            )
        if path == "/auth/v1/logout":
            return httpx.Response(
                401 if request.headers.get("authorization") == "Bearer expired" else 204
            )
        if path == "/auth/v1/user":
            if request.headers.get("authorization") == "Bearer expired":
                return httpx.Response(401, json={})
            return httpx.Response(
                200,
                json={
                    "id": OTHER
                    if request.headers.get("authorization") == "Bearer outsider"
                    else USER
                },
            )
        if path.startswith("/storage/v1/object/sign/"):
            return httpx.Response(
                200, json={"signedURL": "/object/sign/private.png?token=fixture"}
            )
        if path.startswith("/storage/v1/object/list/"):
            folder = json.loads(request.content)["prefix"]
            objects = (
                [{"name": "page.png", "id": "image-object"}]
                if folder.endswith("/workspaces")
                else [
                    {"name": "original.pdf", "id": "pdf-object"},
                    {"name": "workspaces", "id": None},
                ]
            )
            return httpx.Response(200, json=objects)
        if path == "/storage/v1/object/project-assets" and request.method == "DELETE":
            if self.storage_delete_fails:
                return httpx.Response(503, json={"message": "fixture failure"})
            return httpx.Response(200, json=[])
        if path == "/rest/v1/rpc/apply_confirmed_result_patch":
            value = json.loads(request.content)["value"]
            operation = value["changes"][0]
            assert operation["before"]["end_terminal"] == "999"
            assert operation["record"]["start_terminal"] == "XD3:113"
            assert (
                operation["record"]["end_terminal"]
                == operation["after"]["end_terminal"]
            )
            return httpx.Response(
                200, json={"update_mode": "in_place", "result_revision": 5}
            )
        if path.startswith("/rest/v1/"):
            table = path.rsplit("/", 1)[1]
            if request.method == "POST":
                row = json.loads(request.content)
                if table == "projects":
                    row = {
                        "id": str(uuid4()),
                        "status": "draft",
                        "updated_at": "2026-10-12T00:00:00Z",
                        **row,
                    }
                self.tables.setdefault(table, []).append(row)
                return httpx.Response(201, json=[row])
            rows = copy.deepcopy(self.tables.get(table, []))
            for key, value in request.url.params.items():
                if value.startswith("eq."):
                    rows = [r for r in rows if str(r.get(key)) == value[3:]]
                elif value.startswith("lt."):
                    rows = [r for r in rows if int(r.get(key, 0)) < int(value[3:])]
                elif value.startswith("in.("):
                    rows = [
                        r for r in rows if str(r.get(key)) in value[4:-1].split(",")
                    ]
            if request.method == "PATCH":
                values = json.loads(request.content)
                selected_ids = {r["id"] for r in rows}
                for row in self.tables[table]:
                    if row["id"] in selected_ids:
                        row.update(values)
                        row["updated_at"] = "2026-10-12T00:00:01Z"
                rows = [r for r in self.tables[table] if r["id"] in selected_ids]
            if request.method == "DELETE":
                selected_ids = {r["id"] for r in rows}
                self.tables[table] = [
                    r for r in self.tables[table] if r["id"] not in selected_ids
                ]
                return httpx.Response(204)
            return httpx.Response(
                200, json=rows[: int(request.url.params.get("limit", "1000"))]
            )
        if path == "/v1/imports":
            assert request.url.params["user_id"] == USER
            return httpx.Response(
                201,
                json={
                    "project_id": PROJECT,
                    "source_document_id": SOURCE,
                    "attachment_id": SOURCE,
                    "filename": "fixture.pdf",
                    "checksum": "sha256:fixture",
                    "size": 20,
                    "page_count": 1,
                    "persistence_backend": "supabase",
                },
            )
        if path == "/v1/profiles/packages" and request.method == "POST":
            assert request.headers["Authorization"] == "Bearer internal-secret"
            assert request.url.params["user_id"] == USER
            data = json.loads(request.content)
            if data["profile_key"] == "occupied":
                return httpx.Response(
                    409,
                    json={
                        "detail": {
                            "code": "PROFILE_KEY_EXISTS",
                            "message": "private detail",
                        }
                    },
                )
            return httpx.Response(
                201,
                json={
                    "id": str(uuid4()),
                    "profile_key": data["profile_key"],
                    "status": "active",
                    "registered": True,
                },
            )
        if path.startswith("/v1/profiles/packages/") and request.method == "DELETE":
            assert request.url.params["user_id"] == USER
            assert request.url.params["confirmed"] == "true"
            return httpx.Response(
                200,
                json={
                    "id": path.rsplit("/", 1)[1],
                    "status": "retired",
                    "historical_resources_retained": True,
                },
            )
        if path == "/v1/supervisor/turns/stream":
            if self.agent_auth_fails:
                return httpx.Response(
                    401, json={"detail": "Internal service authorization is invalid."}
                )
            data = json.loads(request.content)
            assert data["user_id"] == USER
            assert request.headers.get("Authorization") == "Bearer internal-secret"
            return httpx.Response(
                200, text='event: response\ndata: {"receipt": null}\n\n'
            )
        return httpx.Response(404, json={})


@pytest.fixture
def client():
    backend = FakeBackend()
    app = module.create_app(
        Settings(
            "http://supabase",
            "service-secret",
            agent_url="http://agent",
            agent_token="internal-secret",
        ),
        httpx.MockTransport(backend),
    )
    with TestClient(app) as client:
        yield client, backend


def headers(token: str = "valid") -> dict[str, str]:
    return {"Authorization": "Bearer " + token}


def test_login_refresh_cookie_and_expired_logout(client) -> None:
    http, _ = client
    login = http.post(
        "/api/v1/auth/login",
        json={"email": "fixture@example.invalid", "password": "fixture-password"},
    )
    assert login.status_code == 200
    assert login.json()["user"]["id"] == USER
    assert "refresh_token" not in login.json()
    cookie = login.headers["set-cookie"].lower()
    assert (
        "httponly" in cookie
        and "samesite=lax" in cookie
        and "path=/api/v1/auth" in cookie
    )
    refreshed = http.post(
        "/api/v1/auth/refresh", headers={"Origin": "http://localhost:5174"}
    )
    assert refreshed.status_code == 200
    assert refreshed.json()["expiresIn"] == 3600
    logged_out = http.post(
        "/api/v1/auth/logout",
        headers={**headers("expired"), "Origin": "http://localhost:5174"},
    )
    assert logged_out.status_code == 204
    assert "max-age=0" in logged_out.headers["set-cookie"].lower()


def test_refresh_origin_and_invalid_credentials(client) -> None:
    http, _ = client
    assert (
        http.post(
            "/api/v1/auth/login",
            json={"email": "fixture@example.invalid", "password": "invalid"},
        ).status_code
        == 401
    )
    assert (
        http.post(
            "/api/v1/auth/refresh", headers={"Origin": "https://untrusted.example"}
        ).status_code
        == 403
    )
    assert (
        http.post(
            "/api/v1/auth/logout", headers={"Origin": "https://untrusted.example"}
        ).status_code
        == 403
    )


def test_auth_required_and_expired(client) -> None:
    http, _ = client
    assert http.get("/api/v1/projects").status_code == 401
    assert http.get("/api/v1/projects", headers=headers("expired")).status_code == 401


def test_project_tree_and_private_drawing(client) -> None:
    http, backend = client
    tree = http.get(f"/api/v1/projects/{PROJECT}", headers=headers())
    assert tree.status_code == 200
    assert tree.json()["workspaces"][0]["drawings"][0]["pdf_page_number"] == 1
    image = http.get(f"/api/v1/drawings/{DRAWING}", headers=headers()).json()
    assert "token=fixture" in image["image_url"]
    assert "service-secret" not in json.dumps(image)
    assert backend.requests


def test_other_user_cannot_read_project_drawing_or_connection(client) -> None:
    http, _ = client
    for path in (
        f"/api/v1/projects/{PROJECT}",
        f"/api/v1/drawings/{DRAWING}",
        f"/api/v1/connections/{CONNECTION}/target",
    ):
        assert http.get(path, headers=headers("outsider")).status_code == 403


def test_real_fields_pagination_and_unknown_target(client) -> None:
    http, _ = client
    data = http.get(f"/api/v1/projects/{PROJECT}/connections", headers=headers()).json()
    assert data["items"][0]["wire_number"] == 1001
    assert data["items"][0]["start_terminal"] == "XD3:113"
    assert data["result_revision"] == 4
    assert (
        http.get(
            f"/api/v1/connections/{CONNECTION}/target", headers=headers()
        ).status_code
        == 409
    )


def test_editor_commits_complete_record_and_audit(client) -> None:
    http, backend = client
    data = {
        "result_version_id": RESULT,
        "result_revision": 4,
        "record_version": 2,
        "changes": {"end_terminal": "X3:1"},
    }
    response = http.patch(
        f"/api/v1/connections/{CONNECTION}",
        headers={**headers(), "Idempotency-Key": "edit1"},
        json=data,
    )
    assert response.status_code == 200, response.text
    assert response.json()["result_revision"] == 5
    assert backend.tables["feedback_items"][0]["requested_by"] == USER


def test_unit_fields_keep_original_shared_values_in_audit(client) -> None:
    http, backend = client
    backend.tables["wiring_connection_rows"][0].update(
        voltage_level="380VAC", terminal_strip="X0"
    )
    data = {
        "result_version_id": RESULT,
        "result_revision": 4,
        "record_version": 2,
        "changes": {"voltage_level": "24VDC", "terminal_strip": "X3"},
    }
    response = http.patch(
        f"/api/v1/connections/{CONNECTION}",
        headers={**headers(), "Idempotency-Key": "unit-edit"},
        json=data,
    )
    assert response.status_code == 200, response.text
    operation = backend.tables["result_proposals"][0]["payload"]["operations"][0]
    assert operation["before"]["voltage_level"] == "380VAC"
    assert operation["before"]["terminal_strip"] == "X0"
    assert operation["after"]["voltage_level"] == "24VDC"
    assert operation["after"]["terminal_strip"] == "X3"


def test_stale_edit_and_illegal_fields_denied(client) -> None:
    http, backend = client
    data = {
        "result_version_id": RESULT,
        "result_revision": 3,
        "record_version": 2,
        "changes": {"end_terminal": "X3:1"},
    }
    assert (
        http.patch(
            f"/api/v1/connections/{CONNECTION}",
            headers={**headers(), "Idempotency-Key": "edit2"},
            json=data,
        ).status_code
        == 409
    )
    data["changes"] = {"wire_number": 2000}
    assert (
        http.patch(
            f"/api/v1/connections/{CONNECTION}",
            headers={**headers(), "Idempotency-Key": "edit3"},
            json=data,
        ).status_code
        == 422
    )
    assert not backend.tables["feedback_items"]


def test_historical_target_requires_complete_source_identity_and_unique_evidence(
    client,
) -> None:
    http, backend = client
    current = backend.tables["wiring_connection_rows"][0]
    current.update(principle_number="M001", start_code="+01", end_code="+02")
    historical_id, target_id = str(uuid4()), str(uuid4())
    historical = {**current, "connection_id": historical_id, "result_version": 3}
    backend.tables["wiring_connection_rows"].append(historical)
    backend.tables["drawings"].append(
        {**backend.tables["drawings"][0], "id": target_id, "pdf_page_number": 4}
    )
    backend.tables["connection_evidence"].append(
        {"connection_id": historical_id, "drawing_id": target_id, "kind": "target"}
    )
    response = http.get(f"/api/v1/connections/{CONNECTION}/target", headers=headers())
    assert response.status_code == 200, response.text
    assert response.json()["id"] == target_id
    assert "V3" in response.json()["reference_note"]
    historical["start_code"] = "+99"
    assert (
        http.get(
            f"/api/v1/connections/{CONNECTION}/target", headers=headers()
        ).status_code
        == 409
    )


def test_ambiguous_historical_target_not_guessed(client) -> None:
    http, backend = client
    current = backend.tables["wiring_connection_rows"][0]
    current.update(principle_number="M001", start_code="+01", end_code="+02")
    for version in (2, 3):
        historical_id, target_id = str(uuid4()), str(uuid4())
        backend.tables["wiring_connection_rows"].append(
            {**current, "connection_id": historical_id, "result_version": version}
        )
        backend.tables["drawings"].append(
            {**backend.tables["drawings"][0], "id": target_id}
        )
        backend.tables["connection_evidence"].append(
            {"connection_id": historical_id, "drawing_id": target_id, "kind": "target"}
        )
    assert (
        http.get(
            f"/api/v1/connections/{CONNECTION}/target", headers=headers()
        ).status_code
        == 409
    )


def test_project_create_uses_authenticated_owner_and_rename_checks_permissions(
    client,
) -> None:
    http, backend = client
    response = http.post(
        "/api/v1/projects", headers=headers(), json={"name": "  新工程  "}
    )
    assert response.status_code == 201, response.text
    new = response.json()
    assert new["owner_id"] == USER and new["name"] == "新工程"
    renamed = http.patch(
        f"/api/v1/projects/{new['id']}", headers=headers(), json={"name": "重命名工程"}
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["name"] == "重命名工程"
    assert (
        http.patch(
            f"/api/v1/projects/{new['id']}",
            headers=headers("outsider"),
            json={"name": "越权名称"},
        ).status_code
        == 403
    )
    assert (
        http.post(
            "/api/v1/projects",
            headers=headers(),
            json={"name": "工程", "owner_id": OTHER},
        ).status_code
        == 422
    )
    assert any(p["name"] == "重命名工程" for p in backend.tables["projects"])


def test_project_delete_requires_confirmation_and_owner(client) -> None:
    http, _ = client
    url = f"/api/v1/projects/{PROJECT}?expected_updated_at=2026-10-12T00:00:00Z"
    assert http.delete(url, headers=headers()).status_code == 422
    assert (
        http.delete(url + "&confirmed=true", headers=headers("outsider")).status_code
        == 403
    )


def test_active_run_prevents_storage_delete(client) -> None:
    http, backend = client
    backend.tables["agent_runs"].append(
        {"id": str(uuid4()), "project_id": PROJECT, "status": "RUNNING"}
    )
    response = http.delete(
        f"/api/v1/projects/{PROJECT}?confirmed=true&expected_updated_at=2026-10-12T00:00:00Z",
        headers=headers(),
    )
    assert response.status_code == 409
    assert not any(r.method == "DELETE" for r in backend.requests)


def test_project_delete_cleans_private_paths_before_database(client) -> None:
    http, backend = client
    backend.tables["document_files"][0]["storage_bucket"] = "project-assets"
    response = http.delete(
        f"/api/v1/projects/{PROJECT}?confirmed=true&expected_updated_at=2026-10-12T00:00:00Z",
        headers=headers(),
    )
    assert response.status_code == 204, response.text
    deletes = [r for r in backend.requests if r.method == "DELETE"]
    assert deletes[-1].url.path == "/rest/v1/projects"
    prefixes = json.loads(deletes[0].content)["prefixes"]
    assert all(p.startswith(f"projects/{PROJECT}/") for p in prefixes)
    assert any(p.endswith("/page.png") for p in prefixes)
    assert not backend.tables["projects"]


def test_storage_delete_failure_archives_and_allows_confirmed_retry(client) -> None:
    http, backend = client
    backend.tables["document_files"][0]["storage_bucket"] = "project-assets"
    backend.storage_delete_fails = True
    url = f"/api/v1/projects/{PROJECT}?confirmed=true&expected_updated_at=2026-10-12T00:00:00Z"
    assert http.delete(url, headers=headers()).status_code == 503
    assert backend.tables["projects"][0]["status"] == "archived"
    assert not any(
        r.method == "DELETE" and r.url.path == "/rest/v1/projects"
        for r in backend.requests
    )
    backend.storage_delete_fails = False
    retry = f"/api/v1/projects/{PROJECT}?confirmed=true&expected_updated_at=2026-10-12T00:00:01Z"
    assert http.delete(retry, headers=headers()).status_code == 204


def test_supervisor_stream_identity_and_credentials(client) -> None:
    http, _ = client
    data = {
        "conversation_id": "conversation1",
        "turn_id": str(uuid4()),
        "project_id": PROJECT,
        "message": "查询结果",
    }
    response = http.post(
        "/api/v1/supervisor/turns/stream", headers=headers(), json=data
    )
    assert response.status_code == 200
    assert "event: response" in response.text
    data["user_id"] = OTHER
    assert (
        http.post(
            "/api/v1/supervisor/turns/stream", headers=headers(), json=data
        ).status_code
        == 422
    )


def test_internal_agent_auth_failure_does_not_expire_browser_login(client) -> None:
    http, backend = client
    backend.agent_auth_fails = True
    data = {
        "conversation_id": "fixture",
        "turn_id": str(uuid4()),
        "project_id": PROJECT,
        "message": "查询结果",
    }
    response = http.post(
        "/api/v1/supervisor/turns/stream", headers=headers(), json=data
    )
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "AGENT_SERVICE_AUTH_FAILED"
    assert "internal-secret" not in response.text
    assert http.get("/api/v1/projects", headers=headers()).status_code == 200


def test_import_requires_idempotency_header_before_agent_call(client) -> None:
    http, backend = client
    response = http.post(
        "/api/v1/imports?conversation_id=fixture&project_name=fixture&filename=fixture.pdf",
        headers=headers(),
        content=b"%PDF-1.7\nfixture",
    )
    assert response.status_code == 422
    assert not any(r.url.host == "agent" for r in backend.requests)


def test_import_matches_complete_agent_response_contract(client) -> None:
    http, _ = client
    response = http.post(
        "/api/v1/imports?conversation_id=fixture&project_name=fixture&filename=fixture.pdf",
        headers={
            **headers(),
            "Idempotency-Key": "import-fixture",
            "Content-Type": "application/pdf",
        },
        content=b"%PDF-1.7\nfixture",
    )
    assert response.status_code == 201, response.text
    assert response.json()["persistence_backend"] == "supabase"
    assert response.json()["attachment_id"] == SOURCE


def test_supervisor_rejects_invalid_target_before_agent_call(client) -> None:
    http, backend = client
    payload = {
        "conversation_id": "fixture",
        "turn_id": str(uuid4()),
        "project_id": PROJECT,
        "message": "确认",
        "target_hint": {"agent_run_id": "not-a-uuid"},
    }
    assert (
        http.post(
            "/api/v1/supervisor/turns/stream", json=payload, headers=headers()
        ).status_code
        == 422
    )
    assert not any(r.url.host == "agent" for r in backend.requests)


def test_terminal_create_requires_start_and_idempotency_key(client) -> None:
    http, _ = client
    body = {
        "result_version_id": RESULT,
        "result_revision": 4,
        "wiring_unit_id": str(uuid4()),
        "source_drawing_id": DRAWING,
        "fields": {"start_terminal": "XD3:1"},
    }
    url = f"/api/v1/projects/{PROJECT}/connections"
    assert http.post(url, headers=headers(), json=body).status_code == 422
    body["fields"]["start_terminal"] = "  "
    assert (
        http.post(
            url, headers={**headers(), "Idempotency-Key": "add"}, json=body
        ).status_code
        == 422
    )


def test_terminal_delete_requires_explicit_confirmation(client) -> None:
    http, _ = client
    body = {
        "result_version_id": RESULT,
        "result_revision": 4,
        "record_version": 2,
        "confirmed": False,
    }
    response = http.request(
        "DELETE",
        f"/api/v1/projects/{PROJECT}/connections/{CONNECTION}",
        headers={**headers(), "Idempotency-Key": "remove"},
        json=body,
    )
    assert response.status_code == 422


def test_terminal_mutations_without_transaction_connection_fail_closed(client) -> None:
    http, backend = client
    create = {
        "result_version_id": RESULT,
        "result_revision": 4,
        "wiring_unit_id": str(uuid4()),
        "source_drawing_id": DRAWING,
        "fields": {"start_terminal": "XD3:1"},
    }
    response = http.post(
        f"/api/v1/projects/{PROJECT}/connections",
        json=create,
        headers={**headers(), "Idempotency-Key": "add"},
    )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "TRANSACTION_CONNECTION_REQUIRED"
    response = http.request(
        "DELETE",
        f"/api/v1/projects/{PROJECT}/connections/{CONNECTION}",
        headers={**headers(), "Idempotency-Key": "remove"},
        json={
            "result_version_id": RESULT,
            "result_revision": 4,
            "record_version": 2,
            "confirmed": True,
        },
    )
    assert response.status_code == 503
    assert not any(r.method in {"POST", "PATCH", "DELETE"} for r in backend.requests)


def rule_fixture(backend, owner: str = USER, status: str = "active") -> str:
    package = str(uuid4())
    backend.tables["profile_resource_packages"] = [
        {
            "id": package,
            "profile_key": "zh",
            "profile_version": "1.0.0",
            "source_profile_checksum": "sha256:fixture",
            "package_checksum": "sha256:fixture",
            "status": status,
            "created_by": owner,
            "created_at": "2026-10-12",
        }
    ]
    return package


def test_rule_create_forwards_authenticated_user_and_safe_conflict(client) -> None:
    http, backend = client
    package = rule_fixture(backend)
    body = {
        "base_package_id": package,
        "profile_key": "custom",
        "display_name": "自定义规则",
        "detection_summary": "图框特征",
        "strong_signals": ["特征"],
        "confirmed": True,
    }
    assert (
        http.post("/api/v1/rule-library", headers=headers(), json=body).status_code
        == 201
    )
    body["profile_key"] = "occupied"
    response = http.post("/api/v1/rule-library", headers=headers(), json=body)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "PROFILE_KEY_EXISTS"
    assert "private detail" not in response.text
    body["user_id"] = OTHER
    assert (
        http.post("/api/v1/rule-library", headers=headers(), json=body).status_code
        == 422
    )


def test_rule_delete_owner_confirmation_and_library_visibility(client) -> None:
    http, backend = client
    package = rule_fixture(backend)
    url = f"/api/v1/rule-library/{package}"
    assert http.delete(url, headers=headers()).status_code == 422
    assert (
        http.delete(url + "?confirmed=true", headers=headers("outsider")).status_code
        == 403
    )
    assert not any(r.url.host == "agent" for r in backend.requests)
    assert (
        http.get("/api/v1/rule-library", headers=headers()).json()[0]["can_delete"]
        is True
    )
    assert (
        http.get("/api/v1/rule-library", headers=headers("outsider")).json()[0][
            "can_delete"
        ]
        is False
    )
    response = http.delete(url + "?confirmed=true", headers=headers())
    assert (
        response.status_code == 200 and response.json()["historical_resources_retained"]
    )
    backend.tables["profile_resource_packages"][0]["status"] = "retired"
    assert http.get("/api/v1/rule-library", headers=headers()).json() == []


def test_shared_manual_rule_is_visible_to_other_authenticated_users(client) -> None:
    http, backend = client
    package = rule_fixture(backend, status="draft")
    row = http.get("/api/v1/rule-library", headers=headers("outsider")).json()[0]
    assert row["id"] == package
    assert row["can_delete"] is False


def test_rule_library_lists_only_latest_usable_version_per_key(client) -> None:
    http, backend = client
    first = rule_fixture(backend)
    newer = copy.deepcopy(backend.tables["profile_resource_packages"][0])
    newer.update(
        id=str(uuid4()),
        profile_version="1.1.2",
        created_at="2026-10-12T01:00:00Z",
        package_checksum="sha256:newer",
    )
    backend.tables["profile_resource_packages"].append(newer)
    rows = http.get("/api/v1/rule-library", headers=headers()).json()
    assert len(rows) == 1
    assert rows[0]["id"] != first
    assert rows[0]["profile_version"] == "1.1.2"


def test_rule_template_unavailable_and_invalid_input_never_calls_agent(client) -> None:
    http, backend = client
    package = rule_fixture(backend, status="retired")
    body = {
        "base_package_id": package,
        "profile_key": "custom",
        "display_name": "自定义规则",
        "detection_summary": "图框特征",
        "strong_signals": ["特征"],
        "confirmed": True,
    }
    assert (
        http.post("/api/v1/rule-library", headers=headers(), json=body).status_code
        == 404
    )
    body["strong_signals"] = ["  "]
    assert (
        http.post("/api/v1/rule-library", headers=headers(), json=body).status_code
        == 422
    )
    assert not any(r.url.host == "agent" for r in backend.requests)
