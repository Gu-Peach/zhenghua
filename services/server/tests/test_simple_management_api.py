from __future__ import annotations

import importlib.util
import json
from copy import deepcopy
from pathlib import Path
from uuid import uuid4

import httpx
import pymupdf
import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location(
    "simple_management_api", ROOT / "apps/api/src/main.py"
)
assert spec and spec.loader
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)

OWNER, OTHER, PROJECT, PROFILE, ROW = [str(uuid4()) for _ in range(5)]
STAMP = "2026-10-16T00:00:00+00:00"


class Backend:
    def __init__(self) -> None:
        self.calls: list[httpx.Request] = []
        self.uploads: dict[str, bytes] = {}
        self.fail_delete = False
        self.fail_upload = False
        self.tables: dict[str, list[dict]] = {
            "extraction_profiles": [
                {
                    "id": PROFILE,
                    "profile_key": "zh",
                    "profile_version": "2.1.0",
                    "display_name": "振华",
                    "checksum": "sha256:" + "0" * 64,
                    "resource_ref": "local://zh/profile.json",
                    "created_by": OWNER,
                    "created_at": STAMP,
                }
            ],
            "extraction_projects": [
                {
                    "id": PROJECT,
                    "owner_id": OWNER,
                    "profile_id": PROFILE,
                    "name": "项目",
                    "status": "ready",
                    "created_at": STAMP,
                    "updated_at": STAMP,
                    "drawing_index": {
                        "pages": [
                            {
                                "pdf_page_number": 1,
                                "workspace_code": "003.C",
                                "drawing_page": "003C01",
                                "image_path": f"projects/{PROJECT}/pages/1.png",
                            },
                            {
                                "pdf_page_number": 2,
                                "workspace_code": "004.C",
                                "drawing_page": "004C01",
                                "image_path": f"projects/{PROJECT}/pages/2.png",
                            },
                        ]
                    },
                }
            ],
            "extraction_connection_rows": [
                {
                    "id": ROW,
                    "project_id": PROJECT,
                    "batch_id": "run-one",
                    "workspace_code": "003.C",
                    "source_pdf_page_number": 1,
                    "source_drawing_page": "003C01",
                    "target_pdf_page_number": 2,
                    "target_drawing_page": "004C01",
                    "row_order": 0,
                    "record_version": 1,
                    "start_terminal": "XA:8",
                    "end_terminal": "XD10:1",
                    "is_cross_page": True,
                    "needs_review": False,
                    "created_at": STAMP,
                }
            ],
            "agent_runs": [],
        }

    def respond(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        path = request.url.path
        if path == "/auth/v1/user":
            return httpx.Response(
                200,
                json={
                    "id": OTHER
                    if request.headers.get("Authorization") == "Bearer other"
                    else OWNER
                },
            )
        if path.startswith("/storage/v1/object/sign/"):
            return httpx.Response(
                200,
                json={
                    "signedURL": "/object/sign/project-assets/fixture?token=temporary"
                },
            )
        if path == "/storage/v1/object/project-assets" and request.method == "DELETE":
            return httpx.Response(503 if self.fail_delete else 200, json={})
        if path.startswith("/storage/v1/object/project-assets/"):
            if request.method == "POST":
                if self.fail_upload or path in self.uploads:
                    return httpx.Response(400, json={})
                self.uploads[path] = request.content
                return httpx.Response(200, json={})
            return (
                httpx.Response(200, content=self.uploads[path])
                if path in self.uploads
                else httpx.Response(404, json={})
            )
        if path == "/rest/v1/rpc/manage_extraction_connection":
            value = json.loads(request.content)["value"]
            return httpx.Response(
                200,
                json={
                    "connection_id": value.get("connection_id") or str(uuid4()),
                    "batch_id": "run-one",
                    "action": value["action"],
                    "record_version": 2,
                },
            )
        table = path.removeprefix("/rest/v1/")
        assert table in self.tables, f"Unexpected old table or external call: {path}"
        rows = self.tables[table]

        def matches(row: dict) -> bool:
            return all(
                str(row.get(key)) == value[3:]
                for key, value in request.url.params.items()
                if value.startswith("eq.")
            )

        selected = [row for row in rows if matches(row)]
        if request.method == "GET":
            offset = int(request.url.params.get("offset", 0))
            limit = int(request.url.params.get("limit", 1000))
            return httpx.Response(200, json=selected[offset : offset + limit])
        if request.method == "POST":
            row = {
                "id": str(uuid4()),
                "status": "draft",
                "drawing_index": {},
                "created_at": STAMP,
                "updated_at": STAMP,
                **json.loads(request.content),
            }
            if any(previous["id"] == row["id"] for previous in rows):
                return httpx.Response(409, json={"code": "23505"})
            rows.append(row)
            return httpx.Response(201, json=[row])
        if request.method == "PATCH":
            for row in selected:
                row.update(json.loads(request.content))
                row["updated_at"] = "2026-10-16T00:00:01+00:00"
            return httpx.Response(200, json=selected)
        if request.method == "DELETE":
            self.tables[table] = [row for row in rows if row not in selected]
            return httpx.Response(204)
        raise AssertionError(request.method)


@pytest.fixture
def management(monkeypatch: pytest.MonkeyPatch):
    from wiring_server.profile_references import ProfileReferences

    backend = Backend()
    option = {**backend.tables["extraction_profiles"][0]}
    monkeypatch.setattr(ProfileReferences, "catalog", lambda self: {"zh": option})
    app = api.create_app(
        api.Settings("http://database", "test-key"),
        httpx.MockTransport(backend.respond),
    )
    with TestClient(app, headers={"Authorization": "Bearer owner"}) as client:
        yield client, backend


def pdf_bytes() -> bytes:
    with pymupdf.open() as document:
        document.new_page()
        return document.tobytes()


def test_project_tree_and_pagination_use_json_index(management) -> None:
    client, backend = management
    tree = client.get(f"/api/v1/projects/{PROJECT}").json()
    assert tree["workspaces"][0]["drawings"][0]["workspace_page"] == "003C01"
    assert tree["extraction_available"] is False
    page = client.get(f"/api/v1/projects/{PROJECT}/connections").json()
    assert page["batch_id"] == "run-one"
    assert page["items"][0]["start_terminal"] == "XA:8"
    assert page["items"][0]["wire_number"] is None
    assert page["items"][0]["start_terminal_coordinates"] is None
    assert page["items"][0]["end_terminal_coordinates"] is None
    assert not client.get(
        f"/api/v1/projects/{PROJECT}/connections?batch_id=missing"
    ).is_success
    assert all("wiring_units" not in str(call.url) for call in backend.calls)


def test_coordinates_are_returned_with_each_endpoint_physical_page(management) -> None:
    client, backend = management
    start = {"x": 0.17773, "y": 0.53735, "pdf_page_number": 60}
    end = {"x": 0.17773, "y": 0.17302, "pdf_page_number": 403}
    backend.tables["extraction_connection_rows"][0].update(
        start_terminal_coordinates=start, end_terminal_coordinates=end
    )
    page = client.get(f"/api/v1/projects/{PROJECT}/connections").json()
    assert page["items"][0]["start_terminal_coordinates"] == start
    assert page["items"][0]["end_terminal_coordinates"] == end


@pytest.mark.parametrize(
    "point",
    [
        {"x": -0.01, "y": 0.5, "pdf_page_number": 1},
        {"x": 0.5, "y": 1.01, "pdf_page_number": 1},
        {"x": float("inf"), "y": 0.5, "pdf_page_number": 1},
        {"x": 0.5, "y": 0.5, "pdf_page_number": 0},
        {"x": 0.5, "y": 0.5},
    ],
)
def test_coordinate_contract_rejects_out_of_range_or_incomplete_points(point) -> None:
    from pydantic import ValidationError
    from wiring_server.simple_models import TerminalCoordinates

    with pytest.raises(ValidationError):
        TerminalCoordinates.model_validate(point)


def test_project_access_denied_before_results_or_storage(management) -> None:
    client, backend = management
    backend.calls.clear()
    response = client.get(
        f"/api/v1/projects/{PROJECT}", headers={"Authorization": "Bearer other"}
    )
    assert response.status_code == 403
    assert not any(
        "extraction_connection_rows" in str(call.url) for call in backend.calls
    )
    assert (
        client.get(
            f"/api/v1/projects/{PROJECT}/source",
            headers={"Authorization": "Bearer other"},
        ).status_code
        == 403
    )


def test_cross_page_image_and_invalid_foreign_asset_path(management) -> None:
    client, backend = management
    assert (
        client.get(f"/api/v1/connections/{ROW}/target").json()["pdf_page_number"] == 2
    )
    backend.tables["extraction_projects"][0]["drawing_index"]["pages"][1][
        "image_path"
    ] = "projects/another-project/private.png"
    assert client.get(f"/api/v1/connections/{ROW}/target").status_code == 409


def test_local_rule_reference_registration_and_in_use_guard(management) -> None:
    client, _ = management
    response = client.get("/api/v1/rule-library/local")
    assert response.status_code == 200
    assert "resource_ref" not in response.json()[0]
    assert (
        client.delete(f"/api/v1/rule-library/{PROFILE}?confirmed=true").status_code
        == 409
    )
    assert (
        client.post("/api/v1/rule-library", json={"profile_key": "zh"}).status_code
        == 201
    )


def test_import_saves_pdf_and_retries_without_starting_agent(management) -> None:
    client, backend = management
    data = pdf_bytes()
    url = "/api/v1/imports?profile_key=zh&project_name=uploaded&filename=uploaded.pdf"
    response = client.post(url, content=data, headers={"Idempotency-Key": "upload-1"})
    assert response.status_code == 201, response.text
    assert response.json()["extraction_started"] is False
    again = client.post(url, content=data, headers={"Idempotency-Key": "upload-1"})
    assert again.status_code == 201
    assert again.json()["project_id"] == response.json()["project_id"]
    assert len(backend.uploads) == 1
    assert not any("8100" in str(call.url) for call in backend.calls)
    assert (
        client.post(
            url, content=pdf_bytes(), headers={"Idempotency-Key": "upload-1"}
        ).status_code
        == 409
    )


def test_invalid_pdf_and_disabled_supervisor_do_not_touch_business_data(
    management,
) -> None:
    client, backend = management
    before = deepcopy(backend.tables)
    assert (
        client.post(
            "/api/v1/imports?profile_key=zh&project_name=x&filename=x.pdf",
            content=b"%PDF-invalid",
            headers={"Idempotency-Key": "bad"},
        ).status_code
        == 422
    )
    assert client.post("/api/v1/supervisor/turns/stream", json={}).status_code == 503
    assert backend.tables == before


def test_manual_edit_passes_only_authenticated_actor_to_atomic_rpc(management) -> None:
    client, backend = management
    response = client.patch(
        f"/api/v1/connections/{ROW}",
        json={"record_version": 1, "changes": {"end_terminal": "XD10:2"}},
        headers={"Idempotency-Key": "edit-1"},
    )
    assert response.status_code == 200, response.text
    rpc = next(call for call in backend.calls if "/rpc/" in str(call.url))
    value = json.loads(rpc.content)["value"]
    assert value["actor"] == OWNER and value["body"]["record_version"] == 1
    assert (
        client.patch(
            f"/api/v1/connections/{ROW}",
            json={"record_version": 1, "actor": OTHER, "changes": {}},
            headers={"Idempotency-Key": "bad"},
        ).status_code
        == 422
    )


def test_storage_delete_failure_keeps_archived_project_for_retry(management) -> None:
    client, backend = management
    backend.fail_delete = True
    response = client.delete(
        f"/api/v1/projects/{PROJECT}?confirmed=true&expected_updated_at={STAMP.replace('+', '%2B')}"
    )
    assert response.status_code == 503
    assert backend.tables["extraction_projects"][0]["status"] == "archived"
    backend.fail_delete = False
    updated = client.get(f"/api/v1/projects/{PROJECT}").json()["updated_at"]
    response = client.delete(
        f"/api/v1/projects/{PROJECT}",
        params={"confirmed": "true", "expected_updated_at": updated},
    )
    assert response.status_code == 204
    assert not backend.tables["extraction_projects"]


def test_failed_upload_can_retry_same_key_without_pretending_source_is_saved(
    management,
) -> None:
    client, backend = management
    data = pdf_bytes()
    url = "/api/v1/imports?profile_key=zh&project_name=retry&filename=retry.pdf"
    backend.fail_upload = True
    assert (
        client.post(
            url, content=data, headers={"Idempotency-Key": "retry-upload"}
        ).status_code
        == 503
    )
    project = next(
        row for row in backend.tables["extraction_projects"] if row["name"] == "retry"
    )
    assert project["status"] == "failed"
    assert (
        client.get(f"/api/v1/projects/{project['id']}").json()["source_saved"] is False
    )
    backend.fail_upload = False
    response = client.post(
        url, content=data, headers={"Idempotency-Key": "retry-upload"}
    )
    assert response.status_code == 201
    assert (
        client.get(f"/api/v1/projects/{project['id']}").json()["source_saved"] is True
    )


def test_blank_name_and_identity_required_before_project_creation(management) -> None:
    client, _ = management
    assert (
        client.post(
            "/api/v1/projects", json={"name": "   ", "profile_id": PROFILE}
        ).status_code
        == 422
    )
    assert (
        client.get("/api/v1/projects", headers={"Authorization": ""}).status_code == 401
    )


def test_empty_projects_use_only_new_business_tables() -> None:
    calls: list[str] = []

    def backend(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/auth/v1/user":
            return httpx.Response(
                200, json={"id": "00000000-0000-0000-0000-000000000001"}
            )
        if request.url.path.startswith("/rest/v1/extraction_"):
            return httpx.Response(200, json=[])
        return httpx.Response(400, json={"code": "PGRST205"})

    app = api.create_app(
        api.Settings("http://database", "test-key"), httpx.MockTransport(backend)
    )
    with TestClient(app) as client:
        response = client.get(
            "/api/v1/projects", headers={"Authorization": "Bearer owner"}
        )
    assert response.status_code == 200, response.text
    assert response.json() == []
    assert "/rest/v1/projects" not in calls
