"""Explicit disposable real Supabase/Auth/API CRUD acceptance. Never touches test0."""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from uuid import UUID, uuid4

import asyncpg
import httpx
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services/server/src"))
from wiring_server.config import Settings
from wiring_server.local_supabase import local_dsn
from wiring_server.models import ConnectionCreate
from wiring_server.repository import ServiceError


async def seed(
    dsn: str, actor: str, project: UUID, ids: dict[str, UUID], profile: dict[str, str]
) -> None:
    db = await asyncpg.connect(dsn)
    try:
        async with db.transaction():
            await db.execute(
                "INSERT INTO public.projects(id,owner_id,name,status) VALUES($1,$2,$3,'ready')",
                project,
                UUID(actor),
                f"Disposable CRUD {project}",
            )
            await db.execute(
                "INSERT INTO public.workspaces(id,project_id,code,name,classification_snapshot_id) VALUES($1,$2,'E2E','E2E',$3)",
                ids["workspace"],
                project,
                f"fixture:{project}",
            )
            await db.execute(
                "INSERT INTO public.document_files(id,project_id,original_filename,storage_path,checksum,mime_type,size_bytes) VALUES($1,$2,'fixture.pdf',$3,'fixture','application/pdf',20)",
                ids["source"],
                project,
                f"projects/{project}/original.pdf",
            )
            run = uuid4()
            await db.execute(
                "INSERT INTO public.agent_runs(id,idempotency_key,request_fingerprint,run_type,status,project_id,source_document_id,requested_by,scope) VALUES($1,$2,'fixture','FULL_EXTRACTION','SUCCEEDED',$3,$4,$5,$6::jsonb)",
                run,
                f"fixture:{project}",
                project,
                ids["source"],
                UUID(actor),
                json.dumps({"type": "PROJECT", "id": str(project)}),
            )
            await db.execute(
                "INSERT INTO public.agent_artifacts(artifact_id,agent_run_id,kind,payload) VALUES($1,$2,'fixture_classification','{}')",
                f"fixture:{project}",
                run,
            )
            await db.execute(
                "UPDATE public.projects SET published_classification_snapshot_id=$2 WHERE id=$1",
                project,
                f"fixture:{project}",
            )
            for key, page in (("drawing", 1), ("target", 2)):
                await db.execute(
                    "INSERT INTO public.drawings(id,project_id,workspace_id,pdf_page_number,workspace_page,image_path,classification_snapshot_id) VALUES($1,$2,$3,$4,$5,$6,$7)",
                    ids[key],
                    project,
                    ids["workspace"],
                    page,
                    str(page),
                    f"projects/{project}/{key}.png",
                    f"fixture:{project}",
                )
            await db.execute(
                "INSERT INTO public.result_versions(id,project_id,version,status,created_by,profile) VALUES($1,$2,1,'accepted',$3,$4::jsonb)",
                ids["result"],
                project,
                UUID(actor),
                json.dumps(profile),
            )
            await db.execute(
                "INSERT INTO public.wiring_units(id,project_id,result_version_id,workspace_id,drawing_id,wire_number,terminal_strip,voltage_level) VALUES($1,$2,$3,$4,$5,1000,'XD3','24VDC')",
                ids["unit"],
                project,
                ids["result"],
                ids["workspace"],
                ids["drawing"],
            )
            await db.execute(
                "INSERT INTO public.wiring_connections(id,wiring_unit_id,source_drawing_id,core_order,start_terminal,end_terminal,is_cross_page) VALUES($1,$2,$3,1,'XD3:1','X3:1','same_page')",
                ids["baseline"],
                ids["unit"],
                ids["drawing"],
            )
    finally:
        await db.close()


async def database_state(dsn: str, project: UUID) -> dict[str, object]:
    db = await asyncpg.connect(dsn)
    try:
        rows = await db.fetch(
            "SELECT c.id,c.core_order,u.wire_number FROM public.wiring_connections c JOIN public.wiring_units u ON u.id=c.wiring_unit_id WHERE u.project_id=$1 ORDER BY c.core_order",
            project,
        )
        return {
            "rows": [dict(r) for r in rows],
            "versions": await db.fetchval(
                "SELECT count(*) FROM public.result_versions WHERE project_id=$1",
                project,
            ),
            "audit_count": await db.fetchval(
                "SELECT count(*) FROM public.feedback_items WHERE project_id=$1 AND status='accepted'",
                project,
            ),
        }
    finally:
        await db.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-temporary-data", action="store_true")
    parser.add_argument(
        "--local-container",
        help="Explicit local Supabase DB container; credentials stay in process memory",
    )
    parser.add_argument(
        "--browser",
        action="store_true",
        help="Also run real browser CRUD with owned temporary API/Web processes",
    )
    args = parser.parse_args()
    if not args.allow_temporary_data:
        parser.error("Explicit --allow-temporary-data is required")
    settings = Settings.from_env()
    dsn = settings.database_url or (
        local_dsn(args.local_container) if args.local_container else ""
    )
    if not dsn:
        parser.error("Set SERVER_DATABASE_URL or explicitly identify a local container")
    settings = replace(settings, database_url=dsn)
    spec = importlib.util.spec_from_file_location(
        "acceptance_server", ROOT / "apps/api/src/main.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    project = uuid4()
    ids = {
        key: uuid4()
        for key in (
            "workspace",
            "source",
            "drawing",
            "target",
            "result",
            "unit",
            "baseline",
        )
    }
    email, password = f"crud-{project}@example.invalid", secrets.token_urlsafe(24)
    admin = {
        "apikey": settings.service_key,
        "Authorization": f"Bearer {settings.service_key}",
    }
    actor = None
    try:
        with httpx.Client(timeout=30) as supabase:
            response = supabase.post(
                settings.supabase_url + "/auth/v1/admin/users",
                headers=admin,
                json={"email": email, "password": password, "email_confirm": True},
            )
            if response.is_error:
                raise RuntimeError("Temporary Auth account creation failed")
            actor = response.json()["id"]
            packages = supabase.get(
                settings.supabase_url + "/rest/v1/profile_resource_packages",
                headers=admin,
                params={"profile_key": "eq.zh", "status": "eq.active"},
            ).json()
            profile = {
                "key": "zh",
                "version": packages[0]["profile_version"],
                "checksum": packages[0]["source_profile_checksum"],
            }
            asyncio.run(seed(dsn, actor, project, ids, profile))
            image = (ROOT / "apps/web/public/demo/zh-002c-11.png").read_bytes()
            for path, content, mime in (
                ("original.pdf", b"%PDF-1.7\nfixture", "application/pdf"),
                ("drawing.png", image, "image/png"),
                ("target.png", image, "image/png"),
            ):
                uploaded = supabase.post(
                    settings.supabase_url
                    + f"/storage/v1/object/project-assets/projects/{project}/{path}",
                    headers={**admin, "Content-Type": mime},
                    content=content,
                )
                if uploaded.is_error:
                    raise RuntimeError("Temporary Storage fixture upload failed")
        with TestClient(module.create_app(settings)) as client:
            logged_in = client.post(
                "/api/v1/auth/login", json={"email": email, "password": password}
            )
            assert logged_in.status_code == 200, "Real Auth login failed"
            headers = {"Authorization": "Bearer " + logged_in.json()["accessToken"]}
            base = f"/api/v1/projects/{project}"
            assert client.get(base, headers=headers).status_code == 200
            assert (
                client.post(
                    "/api/v1/auth/refresh", headers={"Origin": settings.web_origin}
                ).status_code
                == 200
            )
            add = {
                "result_version_id": str(ids["result"]),
                "result_revision": 1,
                "wiring_unit_id": str(ids["unit"]),
                "source_drawing_id": str(ids["drawing"]),
                "target_drawing_id": str(ids["target"]),
                "fields": {
                    "start_terminal": "XD3:9",
                    "end_terminal": "X3:9",
                    "is_cross_page": "cross_page",
                },
            }
            app = client.app

            async def reject_outsider() -> None:
                try:
                    await app.state.connection_mutations.add(
                        str(project), str(uuid4()), ConnectionCreate(**add), "outsider"
                    )
                except ServiceError as exc:
                    assert exc.status == 403
                else:
                    raise AssertionError("Unauthorized terminal write was permitted")

            asyncio.run(reject_outsider())

            async def fail_audit(*args: object, **kwargs: object) -> None:
                raise asyncpg.DataError("Injected fixture audit failure")

            before_failure = asyncio.run(database_state(dsn, project))
            with patch.object(app.state.connection_mutations, "_audit", fail_audit):
                failed = client.post(
                    base + "/connections",
                    headers={**headers, "Idempotency-Key": "rollback"},
                    json=add,
                )
            assert failed.status_code == 503
            assert asyncio.run(database_state(dsn, project)) == before_failure
            created = client.post(
                base + "/connections",
                headers={**headers, "Idempotency-Key": "add-once"},
                json=add,
            )
            assert created.status_code == 201, created.text
            receipt = created.json()
            cid = receipt["connection_id"]
            assert receipt["result_revision"] == 2 and receipt["wire_number"] == 1000
            replay = client.post(
                base + "/connections",
                headers={**headers, "Idempotency-Key": "add-once"},
                json=add,
            )
            assert (
                replay.json()["idempotent"] is True
                and replay.json()["connection_id"] == cid
            )
            conflicting = {**add, "fields": {**add["fields"], "end_terminal": "other"}}
            assert (
                client.post(
                    base + "/connections",
                    headers={**headers, "Idempotency-Key": "add-once"},
                    json=conflicting,
                ).status_code
                == 409
            )
            assert (
                client.post(
                    base + "/connections",
                    headers={**headers, "Idempotency-Key": "stale"},
                    json=add,
                ).status_code
                == 409
            )
            target = client.get(f"/api/v1/connections/{cid}/target", headers=headers)
            assert target.status_code == 200 and target.json()["id"] == str(
                ids["target"]
            )
            edited = client.patch(
                f"/api/v1/connections/{cid}",
                headers={**headers, "Idempotency-Key": "edit-once"},
                json={
                    "result_version_id": str(ids["result"]),
                    "result_revision": 2,
                    "record_version": 1,
                    "changes": {"end_terminal": "X3:99"},
                },
            )
            assert edited.status_code == 200, edited.text
            deletion = {
                "result_version_id": str(ids["result"]),
                "result_revision": 3,
                "record_version": 2,
                "confirmed": True,
            }
            removed = client.request(
                "DELETE",
                base + f"/connections/{cid}",
                headers={**headers, "Idempotency-Key": "delete-once"},
                json=deletion,
            )
            assert removed.status_code == 200, removed.text
            assert removed.json()["result_revision"] == 4
            replay_delete = client.request(
                "DELETE",
                base + f"/connections/{cid}",
                headers={**headers, "Idempotency-Key": "delete-once"},
                json=deletion,
            )
            assert replay_delete.json()["idempotent"] is True
            state = asyncio.run(database_state(dsn, project))
            assert len(state["rows"]) == 1 and state["rows"][0]["id"] == ids["baseline"]
            assert state["versions"] == 1 and state["audit_count"] == 3
            if args.browser:
                with socket.socket() as sock:
                    sock.bind(("127.0.0.1", 0))
                    api_port = sock.getsockname()[1]
                with socket.socket() as sock:
                    sock.bind(("127.0.0.1", 0))
                    web_port = sock.getsockname()[1]
                env = {
                    **os.environ,
                    "SERVER_DATABASE_URL": dsn,
                    "SERVER_WEB_ORIGIN": f"http://127.0.0.1:{web_port}",
                    "SERVER_SUPABASE_URL": settings.supabase_url,
                    "SERVER_SUPABASE_SERVICE_ROLE_KEY": settings.service_key,
                }
                api_process = subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "main:app",
                        "--app-dir",
                        "apps/api/src",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(api_port),
                    ],
                    cwd=ROOT,
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                web_process = subprocess.Popen(
                    [
                        "corepack.cmd",
                        "pnpm",
                        "--filter",
                        "@wiring/web",
                        "exec",
                        "vite",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        str(web_port),
                    ],
                    cwd=ROOT,
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                try:
                    with httpx.Client(timeout=2) as probe:
                        ready = False
                        for _ in range(50):
                            try:
                                ready = (
                                    probe.get(
                                        f"http://127.0.0.1:{api_port}/health"
                                    ).status_code
                                    == 200
                                    and probe.get(
                                        f"http://127.0.0.1:{web_port}"
                                    ).status_code
                                    == 200
                                )
                                if ready:
                                    break
                            except httpx.HTTPError:
                                pass
                            time.sleep(0.2)
                        if not ready:
                            raise RuntimeError("Temporary API/Web startup failed")
                    browser_env = {
                        **env,
                        "WIRING_BROWSER_FIXTURE": json.dumps(
                            {
                                "api": f"http://127.0.0.1:{api_port}",
                                "web": f"http://127.0.0.1:{web_port}",
                                "project": str(project),
                                "target": str(ids["target"]),
                                "email": email,
                                "password": password,
                            }
                        ),
                    }
                    browser = subprocess.run(
                        ["node", "services/server/scripts/crud_browser.mjs"],
                        cwd=ROOT,
                        env=browser_env,
                        timeout=90,
                        check=False,
                    )
                    if browser.returncode:
                        raise RuntimeError("Real browser CRUD failed")
                finally:
                    for process in (api_process, web_process):
                        if process.poll() is None:
                            subprocess.run(
                                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                                check=False,
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL,
                            )
                    api_process.wait(timeout=10)
                    web_process.wait(timeout=10)
                state = asyncio.run(database_state(dsn, project))
                assert (
                    len(state["rows"]) == 1
                    and state["rows"][0]["id"] == ids["baseline"]
                    and state["audit_count"] == 6
                )
            detail = client.get(base, headers=headers).json()
            deleted = client.delete(
                base,
                headers=headers,
                params={
                    "confirmed": "true",
                    "expected_updated_at": detail["updated_at"],
                },
            )
            assert deleted.status_code == 204, deleted.text
            print(
                "PASS: real Auth, stable-ID CRUD, target lookup, permission/stale/key-conflict rejection, rollback, replay/audits, project/Storage cleanup"
            )
    finally:
        # Only generated fixture identities; no existing project/user IDs enter these deletes.
        async def cleanup() -> None:
            db = await asyncpg.connect(dsn)
            try:
                await db.execute(
                    "DELETE FROM public.projects WHERE id=$1 AND name=$2",
                    project,
                    f"Disposable CRUD {project}",
                )
            finally:
                await db.close()

        asyncio.run(cleanup())
        with httpx.Client(timeout=30) as supabase:
            supabase.request(
                "DELETE",
                settings.supabase_url + "/storage/v1/object/project-assets",
                headers=admin,
                json={
                    "prefixes": [
                        f"projects/{project}/{name}"
                        for name in ("original.pdf", "drawing.png", "target.png")
                    ]
                },
            )
            if actor:
                response = supabase.delete(
                    settings.supabase_url + f"/auth/v1/admin/users/{actor}",
                    headers=admin,
                )
                if response.is_error:
                    raise RuntimeError(
                        "Temporary Auth cleanup failed; inspect acceptance fixture only"
                    )
        print("CLEANED: temporary project, objects and Auth account; test0 untouched")


if __name__ == "__main__":
    main()
