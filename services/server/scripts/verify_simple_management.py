"""Explicit local-only HTTP/Storage acceptance; all synthetic accounts/data are removed."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path
from uuid import uuid4

import httpx
import pymupdf
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services/server/src"))
spec = importlib.util.spec_from_file_location(
    "management_acceptance_api", ROOT / "apps/api/src/main.py"
)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def run() -> None:
    settings = module.Settings.from_env()
    if settings.supabase_url != "http://127.0.0.1:54321":
        raise RuntimeError(
            "This acceptance only permits the local zhenghua_test Supabase URL"
        )
    headers = {
        "apikey": settings.service_key,
        "Authorization": "Bearer " + settings.service_key,
    }
    actors: list[str] = []
    profiles: list[str] = []
    projects: list[str] = []
    assets: list[str] = []

    def expect(response: httpx.Response, status: int) -> dict:
        if response.status_code != status:
            code = ""
            try:
                code = str(response.json().get("detail", {}).get("code", ""))
            except (ValueError, AttributeError):
                pass
            raise AssertionError(
                f"Unexpected HTTP status {response.status_code}, expected {status}; code={code}"
            )
        return (
            response.json()
            if response.content and "json" in response.headers.get("content-type", "")
            else {}
        )

    with httpx.Client(
        base_url=settings.supabase_url, headers=headers, timeout=30
    ) as storage:
        try:
            email = f"simple-management-{uuid4().hex}@example.invalid"
            password = uuid4().hex + "Aa!9"
            identity = expect(
                storage.post(
                    "/auth/v1/admin/users",
                    json={"email": email, "password": password, "email_confirm": True},
                ),
                200,
            )
            actor = identity["id"]
            actors.append(actor)
            with TestClient(module.create_app(settings)) as client:
                session = expect(
                    client.post(
                        "/api/v1/auth/login",
                        json={"email": email, "password": password},
                    ),
                    200,
                )
                client.headers["Authorization"] = "Bearer " + session["accessToken"]
                assert client.get("/api/v1/projects").json() == []
                options = expect(client.get("/api/v1/rule-library/local"), 200)
                assert any(option["profile_key"] == "zh" for option in options)
                registered = expect(
                    client.post("/api/v1/rule-library", json={"profile_key": "zh"}), 201
                )
                if registered["can_delete"]:
                    profiles.append(registered["id"])
                preview = expect(
                    client.get(f"/api/v1/rule-library/{registered['id']}"), 200
                )
                assert preview["files"] and preview["images"]
                with pymupdf.open() as document:
                    document.new_page(width=400, height=300)
                    document.new_page(width=400, height=300)
                    pdf = document.tobytes()
                    png = document[0].get_pixmap().tobytes("png")
                url = "/api/v1/imports?profile_key=zh&project_name=simple-management-probe&filename=probe.pdf"
                uploaded = expect(
                    client.post(
                        url,
                        content=pdf,
                        headers={"Idempotency-Key": "acceptance-upload"},
                    ),
                    201,
                )
                project = uploaded["project_id"]
                projects.append(project)
                assets.append(f"projects/{project}/source/original.pdf")
                assert uploaded["extraction_started"] is False
                detail = expect(client.get(f"/api/v1/projects/{project}"), 200)
                assert detail["source_saved"] and not detail["workspaces"]
                source = expect(client.get(f"/api/v1/projects/{project}/source"), 200)
                expect(httpx.get(source["url"], timeout=15), 200)
                assert (
                    expect(
                        client.post(
                            url,
                            content=pdf,
                            headers={"Idempotency-Key": "acceptance-upload"},
                        ),
                        201,
                    )["project_id"]
                    == project
                )
                indexed = []
                for number in (1, 2):
                    path = f"projects/{project}/pages/{number}.png"
                    expect(
                        storage.post(
                            "/storage/v1/object/project-assets/" + path,
                            content=png,
                            headers={"Content-Type": "image/png", "x-upsert": "false"},
                        ),
                        200,
                    )
                    assets.append(path)
                    indexed.append(
                        {
                            "pdf_page_number": number,
                            "workspace_code": "003.C",
                            "drawing_page": f"003C0{number}",
                            "image_path": path,
                        }
                    )
                row = storage.get(
                    "/rest/v1/extraction_projects", params={"id": f"eq.{project}"}
                ).json()[0]
                expect(
                    storage.patch(
                        "/rest/v1/extraction_projects",
                        params={"id": f"eq.{project}"},
                        json={
                            "drawing_index": {**row["drawing_index"], "pages": indexed}
                        },
                    ),
                    204,
                )
                detail = expect(client.get(f"/api/v1/projects/{project}"), 200)
                drawings = detail["workspaces"][0]["drawings"]
                body = {
                    "batch_id": "acceptance",
                    "source_drawing_id": drawings[0]["id"],
                    "target_drawing_id": drawings[1]["id"],
                    "fields": {"start_terminal": "XA:8", "end_terminal": "XD10:1"},
                }
                created = expect(
                    client.post(
                        f"/api/v1/projects/{project}/connections",
                        json=body,
                        headers={"Idempotency-Key": "add-one"},
                    ),
                    201,
                )
                connection = created["connection_id"]
                start_point = {"x": 0.17773, "y": 0.53735, "pdf_page_number": 1}
                end_point = {"x": 0.17773, "y": 0.17302, "pdf_page_number": 2}
                expect(storage.patch("/rest/v1/extraction_connection_rows", params={"id": f"eq.{connection}"}, json={"start_terminal_coordinates": start_point, "end_terminal_coordinates": end_point}), 204)
                coordinate_row = expect(client.get(f"/api/v1/projects/{project}/connections"), 200)["items"][0]
                assert coordinate_row["start_terminal_coordinates"] == start_point
                assert coordinate_row["end_terminal_coordinates"] == end_point
                assert expect(
                    client.post(
                        f"/api/v1/projects/{project}/connections",
                        json=body,
                        headers={"Idempotency-Key": "add-one"},
                    ),
                    201,
                )["idempotent"]
                edit = {"record_version": 2, "changes": {"end_terminal": "XD10:2"}}
                expect(
                    client.patch(
                        f"/api/v1/connections/{connection}",
                        json=edit,
                        headers={"Idempotency-Key": "edit-one"},
                    ),
                    200,
                )
                expect(
                    client.patch(
                        f"/api/v1/connections/{connection}",
                        json=edit,
                        headers={"Idempotency-Key": "stale-edit"},
                    ),
                    409,
                )
                coordinate_row = expect(client.get(f"/api/v1/projects/{project}/connections"), 200)["items"][0]
                assert coordinate_row["start_terminal_coordinates"] == start_point
                assert coordinate_row["end_terminal_coordinates"] is None
                target = expect(
                    client.get(f"/api/v1/connections/{connection}/target"), 200
                )
                assert target["pdf_page_number"] == 2
                expect(httpx.get(target["image_url"], timeout=15), 200)
                expect(
                    client.request(
                        "DELETE",
                        f"/api/v1/projects/{project}/connections/{connection}",
                        json={"record_version": 3, "confirmed": True},
                        headers={"Idempotency-Key": "remove-one"},
                    ),
                    200,
                )
                detail = expect(client.get(f"/api/v1/projects/{project}"), 200)
                expect(
                    client.delete(
                        f"/api/v1/projects/{project}",
                        params={
                            "confirmed": "true",
                            "expected_updated_at": detail["updated_at"],
                        },
                    ),
                    204,
                )
                assert (
                    storage.get(
                        "/rest/v1/extraction_projects", params={"id": f"eq.{project}"}
                    ).json()
                    == []
                )
                for path in assets:
                    assert (
                        storage.get(
                            "/storage/v1/object/project-assets/" + path
                        ).status_code
                        >= 400
                    )
            print(
                "PASS: real local Auth, projects, rule references/preview, immutable PDF upload, JSON index, row CRUD/replay/conflict and private image/delete"
            )
        finally:
            if assets:
                storage.request(
                    "DELETE",
                    "/storage/v1/object/project-assets",
                    json={"prefixes": assets},
                )
            for identifier in projects:
                storage.delete(
                    "/rest/v1/extraction_projects",
                    params={"id": f"eq.{identifier}", "owner_id": f"eq.{actors[0]}"},
                )
            for identifier in profiles:
                storage.delete(
                    "/rest/v1/extraction_profiles",
                    params={"id": f"eq.{identifier}", "created_by": f"eq.{actors[0]}"},
                )
            for identifier in actors:
                expect(storage.delete("/auth/v1/admin/users/" + identifier), 200)
            print(
                "Synthetic local account, projects, rule references and Storage objects cleaned"
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-local-write", action="store_true", required=True)
    parser.parse_args()
    run()
