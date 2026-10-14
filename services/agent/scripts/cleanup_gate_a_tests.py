"""Cleanup only explicitly named synthetic Gate A project UUIDs and private objects."""

from __future__ import annotations

import asyncio
import sys
from uuid import UUID

import httpx

from src.config import AgentSettings
from src.infrastructure.supabase_client import SupabaseClient


async def main() -> None:
    settings = AgentSettings.from_env()
    if settings.supabase_url != "http://127.0.0.1:54321":
        raise ValueError("Cleanup is restricted to the local acceptance stack.")
    client = SupabaseClient(
        base_url=settings.supabase_url, service_role_key=settings.supabase_service_role_key or ""
    )
    headers = {
        "apikey": settings.supabase_service_role_key or "",
        "Authorization": f"Bearer {settings.supabase_service_role_key}",
    }
    for raw in sys.argv[1:]:
        project = str(UUID(raw))
        rows = await client.select("projects", params={"id": f"eq.{project}", "limit": "1"})
        if not rows:
            print(f"Already absent: {project}")
            continue
        if rows[0]["name"] != "Gate A isolated acceptance":
            raise ValueError("Refusing a non-test project.")
        owner = rows[0]["owner_id"]
        async with httpx.AsyncClient(timeout=30) as http:
            response = await http.get(f"{settings.supabase_url}/auth/v1/admin/users/{owner}", headers=headers)
            response.raise_for_status()
            email = response.json().get("email", "")
            if not email.startswith("gate-a-") or not email.endswith("@example.invalid"):
                raise ValueError("Refusing a non-test owner.")

            async def objects(prefix: str) -> list[str]:
                listing = await http.post(
                    f"{settings.supabase_url}/storage/v1/object/list/project-assets",
                    headers=headers,
                    json={"prefix": prefix, "limit": 1000},
                )
                listing.raise_for_status()
                result: list[str] = []
                for entry in listing.json():
                    path = prefix + "/" + entry["name"]
                    if entry.get("id"):
                        result.append(path)
                    else:
                        result.extend(await objects(path))
                return result

            paths = await objects(f"projects/{project}")
            if any(not p.startswith(f"projects/{project}/") for p in paths):
                raise ValueError("Object path escaped the test project.")
            await client.remove_objects(bucket="project-assets", object_paths=paths)
            await client.delete("projects", filters={"id": f"eq.{project}"})
            other_projects = await client.select("projects", params={"owner_id": f"eq.{owner}", "limit": "1"})
            if not other_projects:
                deleted = await http.delete(
                    f"{settings.supabase_url}/auth/v1/admin/users/{owner}", headers=headers
                )
                deleted.raise_for_status()
        print(f"Cleaned synthetic project: {project} ({len(paths)} objects)")


if __name__ == "__main__":
    asyncio.run(main())
