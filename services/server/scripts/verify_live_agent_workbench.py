"""Explicit real-model Web acceptance using disposable Auth/project/Storage data."""

from __future__ import annotations

import argparse
import atexit
import os
import secrets
import socket
import subprocess
import sys
import time
from pathlib import Path
from uuid import uuid4

import httpx

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services/server/src"))
from wiring_server.config import Settings
from wiring_server.local_supabase import local_dsn


def port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-real-model", action="store_true")
    parser.add_argument("--allow-temporary-data", action="store_true")
    parser.add_argument("--local-container", required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument(
        "--resume-project", help="Resume only a disposable live-web acceptance project"
    )
    args = parser.parse_args()
    if not (args.allow_real_model and args.allow_temporary_data):
        parser.error("Both explicit real-model and temporary-data approvals required")
    if os.getenv("SERVER_ACCEPTANCE_ALLOW_REAL_MODEL") != "true":
        parser.error("Set SERVER_ACCEPTANCE_ALLOW_REAL_MODEL=true")
    pdf = args.pdf.resolve(strict=True)
    settings = Settings.from_env()
    dsn = local_dsn(args.local_container)
    auth = {
        "apikey": settings.service_key,
        "Authorization": "Bearer " + settings.service_key,
    }
    agent_auth = (
        {"Authorization": "Bearer " + settings.agent_token}
        if settings.agent_token
        else {}
    )
    actor = None
    resume_run = None
    processes: list[subprocess.Popen[bytes]] = []

    def stop_owned_processes() -> None:
        for process in processes:
            if process.poll() is None:
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            process.wait(timeout=10)

    # Also stop owned helpers if cleanup raises; never terminate the existing Agent.
    atexit.register(stop_owned_processes)
    begin = time.monotonic()
    with httpx.Client(timeout=30) as http:
        ready = http.get(settings.agent_url + "/health/ready", headers=agent_auth)
        if not ready.is_success:
            raise RuntimeError(
                f"Existing Agent not ready ({ready.status_code}); no data created"
            )
        try:
            password = secrets.token_urlsafe(24)
            if args.resume_project:
                project = http.get(
                    settings.supabase_url + "/rest/v1/projects",
                    headers=auth,
                    params={"id": "eq." + args.resume_project, "select": "owner_id"},
                )
                project.raise_for_status()
                if len(project.json()) != 1:
                    raise RuntimeError("Disposable project not found")
                owner = project.json()[0]["owner_id"]
                account = http.get(
                    settings.supabase_url + "/auth/v1/admin/users/" + owner,
                    headers=auth,
                )
                account.raise_for_status()
                email = account.json().get("email", "")
                if not (
                    email.startswith("live-web-") and email.endswith("@example.invalid")
                ):
                    raise RuntimeError("Refusing to resume a non-acceptance account")
                runs = http.get(
                    settings.supabase_url + "/rest/v1/agent_runs",
                    headers=auth,
                    params={
                        "project_id": "eq." + args.resume_project,
                        "run_type": "eq.FULL_EXTRACTION",
                        "status": "eq.SUCCEEDED",
                        "order": "created_at.desc",
                        "limit": "1",
                        "select": "id",
                    },
                )
                runs.raise_for_status()
                if not runs.json():
                    raise RuntimeError("No successful extraction to resume")
                resume_run = runs.json()[0]["id"]
                reset = http.put(
                    settings.supabase_url + "/auth/v1/admin/users/" + owner,
                    headers=auth,
                    json={"password": password},
                )
                reset.raise_for_status()
                actor = owner
            else:
                email = f"live-web-{uuid4()}@example.invalid"
                response = http.post(
                    settings.supabase_url + "/auth/v1/admin/users",
                    headers=auth,
                    json={"email": email, "password": password, "email_confirm": True},
                )
                if response.is_error:
                    raise RuntimeError("Disposable Auth account creation failed")
                actor = response.json()["id"]
            api, web = port(), port()
            env = {
                **os.environ,
                "SERVER_DATABASE_URL": dsn,
                "SERVER_WEB_ORIGIN": f"http://127.0.0.1:{web}",
                "SERVER_SUPABASE_URL": settings.supabase_url,
                "SERVER_SUPABASE_SERVICE_ROLE_KEY": settings.service_key,
                "SERVER_AGENT_URL": settings.agent_url,
                "AGENT_INTERNAL_TOKEN": settings.agent_token,
            }
            commands = [
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
                    str(api),
                ],
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
                    str(web),
                ],
            ]
            for command in commands:
                processes.append(
                    subprocess.Popen(
                        command,
                        cwd=ROOT,
                        env=env,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        creationflags=subprocess.CREATE_NO_WINDOW,
                    )
                )
            for _ in range(60):
                try:
                    if (
                        http.get(f"http://127.0.0.1:{api}/health").is_success
                        and http.get(f"http://127.0.0.1:{web}").is_success
                    ):
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.2)
            else:
                raise RuntimeError("Temporary API/Web startup failed")
            import json

            browser_env = {
                **env,
                "WIRING_BROWSER_FIXTURE": json.dumps(
                    {
                        "api": f"http://127.0.0.1:{api}",
                        "web": f"http://127.0.0.1:{web}",
                        "email": email,
                        "password": password,
                        "pdf": str(pdf),
                        "resumeProject": args.resume_project,
                        "resumeRun": resume_run,
                    }
                ),
            }
            print(
                "REAL MODEL: existing Agent; normal human-confirmation API; no rule publication",
                flush=True,
            )
            result = subprocess.run(
                ["node", "services/server/scripts/live_agent_browser.mjs"],
                cwd=ROOT,
                env=browser_env,
                timeout=2400,
                check=False,
            )
            if result.returncode:
                raise RuntimeError("Real browser Agent acceptance did not pass")
            print(
                f"ELAPSED: {time.monotonic() - begin:.1f}s; cost unavailable (provider dependent)",
                flush=True,
            )
        finally:
            # Find only projects owned by the newly created random account, never test0.
            safe_cleanup = True
            if actor:
                projects = http.get(
                    settings.supabase_url + "/rest/v1/projects",
                    headers=auth,
                    params={"owner_id": "eq." + actor, "select": "id,name"},
                )
                projects.raise_for_status()
                for project in projects.json():
                    pid = project["id"]
                    runs = http.get(
                        settings.supabase_url + "/rest/v1/agent_runs",
                        headers=auth,
                        params={"project_id": "eq." + pid, "select": "id,status"},
                    )
                    runs.raise_for_status()
                    active = [
                        r
                        for r in runs.json()
                        if r["status"] in {"QUEUED", "RUNNING", "WAITING_INPUT"}
                    ]
                    if active:
                        safe_cleanup = False
                        print(
                            f"RETAINED: owned temporary project {pid}; active runs prevent unsafe cleanup",
                            flush=True,
                        )
                        continue
                    # Use the real Server deletion policy and the temporary owner's JWT.
                    login = http.post(
                        f"http://127.0.0.1:{api}/api/v1/auth/login",
                        json={"email": email, "password": password},
                    )
                    login.raise_for_status()
                    headers = {"Authorization": "Bearer " + login.json()["accessToken"]}
                    detail = http.get(
                        f"http://127.0.0.1:{api}/api/v1/projects/{pid}", headers=headers
                    )
                    detail.raise_for_status()
                    deleted = http.delete(
                        f"http://127.0.0.1:{api}/api/v1/projects/{pid}",
                        headers=headers,
                        params={
                            "confirmed": "true",
                            "expected_updated_at": detail.json()["updated_at"],
                        },
                    )
                    if deleted.status_code != 204:
                        safe_cleanup = False
                        print(
                            f"RETAINED: temporary project {pid}; deletion failed ({deleted.status_code})",
                            flush=True,
                        )
                if safe_cleanup:
                    removed = http.delete(
                        settings.supabase_url + "/auth/v1/admin/users/" + actor,
                        headers=auth,
                    )
                    removed.raise_for_status()
                    print(
                        "CLEANED: disposable projects/objects/Auth; test0 and existing Agent untouched",
                        flush=True,
                    )
            stop_owned_processes()


if __name__ == "__main__":
    main()
