"""Upload a verified Profile resource package; stored packages are immediately usable."""

from __future__ import annotations

import argparse
import asyncio
import sys
import tempfile
from pathlib import Path
from uuid import UUID

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_service.config import AgentSettings
from agent_service.domain.enums import ProfileStatus
from agent_service.infrastructure.supabase_client import SupabaseClient
from agent_service.infrastructure.supabase_profile_packages import SupabaseProfilePackageRepository
from agent_service.profiles.package import build_package, checksum, verify_package
from agent_service.profiles.registry import ProfileRegistry


async def main() -> None:
    parser = argparse.ArgumentParser(description="Upload and register a verified Profile resource package.")
    parser.add_argument("profile_key")
    parser.add_argument("--user-id", required=True, type=UUID)
    args = parser.parse_args()
    settings = AgentSettings.from_env()
    registry = ProfileRegistry(
        profile_root=settings.profile_root,
        workspace_root=settings.workspace_root,
        allow_legacy_references=True,
    )
    registry.load_all()
    snapshot = registry.resolve(args.profile_key, allow_experimental=True)
    if snapshot.manifest.status not in {ProfileStatus.ACTIVE, ProfileStatus.EXPERIMENTAL}:
        parser.error("Only a usable local Profile can be uploaded.")
    client = SupabaseClient(
        base_url=settings.supabase_url or "", service_role_key=settings.supabase_service_role_key or ""
    )
    packages = SupabaseProfilePackageRepository(
        client, cache_root=settings.workspace_root / "services" / "agent" / ".runtime" / "profile-packages"
    )
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary) / "package"
        manifest = await asyncio.to_thread(build_package, snapshot, root)
        row = await packages.upload(root, created_by=str(args.user_id), status="active")
        if row["status"] == "retired":
            raise ValueError("Identical package was retired and cannot be re-enabled implicitly.")
        remote = await client.download(bucket=packages.bucket, object_path=str(row["manifest_path"]))
        if checksum(remote) != row["manifest_checksum"]:
            raise ValueError("Uploaded manifest checksum differs.")
        # Download every file into a fresh temporary directory: no local cache can mask a bad upload.
        verified = Path(temporary) / "readback"
        for entry in manifest.files:
            value = await client.download(
                bucket=packages.bucket, object_path=f"{row['storage_prefix']}/{entry.path}"
            )
            target = verified / entry.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(value)
        await asyncio.to_thread(verify_package, verified, manifest)
        print(
            f"Uploaded usable package {manifest.profile_key}@{manifest.profile_version}; "
            "readback verified."
        )
        print(f"package_id={row['id']}")
        print(f"bucket={packages.bucket}; prefix={row['storage_prefix']}")
        print(f"checksum={manifest.package_checksum}; files={len(manifest.files)}")


if __name__ == "__main__":
    asyncio.run(main())
