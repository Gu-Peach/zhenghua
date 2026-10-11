"""Explicit one-time bootstrap deployment, not an acceptance/Agent test script."""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_service.config import AgentSettings
from agent_service.infrastructure.supabase_client import SupabaseClient
from agent_service.infrastructure.supabase_profile_packages import SupabaseProfilePackageRepository
from agent_service.profiles.package import build_package
from agent_service.profiles.registry import ProfileRegistry


async def main() -> None:
    parser = argparse.ArgumentParser(description="Publish an explicitly approved bootstrap Profile package.")
    parser.add_argument("profile_key")
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--approve-bootstrap", action="store_true")
    args = parser.parse_args()
    if not args.approve_bootstrap:
        parser.error(
            "Explicit --approve-bootstrap is required; never run this for model-generated candidates."
        )
    settings = AgentSettings.from_env()
    registry = ProfileRegistry(
        profile_root=settings.profile_root,
        workspace_root=settings.workspace_root,
        allow_legacy_references=True,
    )
    registry.load_all()
    client = SupabaseClient(
        base_url=settings.supabase_url or "", service_role_key=settings.supabase_service_role_key or ""
    )
    packages = SupabaseProfilePackageRepository(
        client, cache_root=settings.workspace_root / "services" / "agent" / ".runtime" / "profile-packages"
    )
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / "package"
        manifest = await asyncio.to_thread(build_package, registry.resolve(args.profile_key), root)
        row = await packages.upload(root, created_by=args.user_id, status="draft")
        await client.update(
            "profile_resource_packages", {"approved_by": args.user_id}, filters={"id": f"eq.{row['id']}"}
        )
        await client.rpc("publish_profile_package", {"package_id": row["id"], "reviewer": args.user_id})
        print(f"Published {manifest.profile_key}@{manifest.profile_version} {manifest.package_checksum}")


if __name__ == "__main__":
    asyncio.run(main())
