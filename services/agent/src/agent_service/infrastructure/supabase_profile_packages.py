from __future__ import annotations

import asyncio
import json
import mimetypes
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from ..domain.enums import ProfileStatus
from ..domain.models.improvement import ProfileCandidate
from ..domain.models.profiles import ProfileBinding, ProfileManifest, ProfileRuleSet, ProfileSnapshot
from ..domain.models.runs import ProfileRef
from ..profiles.package import PackageManifest, checksum, safe_path, verify_package
from ..profiles.registry import ProfileRegistry
from .correction_data import _atomic_write
from .supabase_client import SupabaseClient


class SupabaseProfilePackageRepository:
    """Immutable private assets, checked caches, and metadata-only database rows."""

    def __init__(self, client: SupabaseClient, *, cache_root: Path) -> None:
        self.client = client
        self.cache_root = cache_root.resolve()
        self.bucket = "agent-profile-assets"
        self._registry_lock = asyncio.Lock()
        self._loaded_sets: dict[ProfileRegistry, tuple[tuple[str, str], ...]] = {}

    async def upload(
        self,
        root: Path,
        *,
        created_by: str,
        status: str = "candidate",
        candidate_id: str | None = None,
        base_package_id: str | None = None,
        package_id: str | None = None,
    ) -> dict[str, object]:
        manifest_bytes = await asyncio.to_thread((root / "manifest.json").read_bytes)
        manifest = PackageManifest.model_validate_json(manifest_bytes)
        await asyncio.to_thread(verify_package, root, manifest)
        prefix = f"{manifest.profile_key}/{manifest.profile_version}/{manifest.package_checksum[7:]}"
        package_id = package_id or str(uuid5(NAMESPACE_URL, f"profile-package:{prefix}"))
        existing = await self.client.select("profile_resource_packages", params={"id": f"eq.{package_id}"})
        if existing:
            if existing[0]["package_checksum"] != manifest.package_checksum:
                raise ValueError("Profile package identity already contains different content.")
            return existing[0]
        for entry in manifest.files:
            content = await asyncio.to_thread((root / safe_path(entry.path)).read_bytes)
            await self._upload_once(f"{prefix}/{entry.path}", content)
        await self._upload_once(f"{prefix}/manifest.json", manifest_bytes)
        rows = await self.client.insert(
            "profile_resource_packages",
            {
                "id": package_id,
                "profile_key": manifest.profile_key,
                "profile_version": manifest.profile_version,
                "source_profile_checksum": manifest.source_profile_checksum,
                "package_checksum": manifest.package_checksum,
                "manifest_checksum": checksum(manifest_bytes),
                "storage_bucket": self.bucket,
                "storage_prefix": prefix,
                "manifest_path": f"{prefix}/manifest.json",
                "status": status,
                "created_by": created_by,
                "candidate_id": candidate_id,
                "base_package_id": base_package_id,
            },
        )
        return rows[0]

    async def _upload_once(self, path: str, content: bytes) -> None:
        from ..domain.errors import AgentServiceError

        try:
            await self.client.upload(
                bucket=self.bucket,
                object_path=path,
                content=content,
                content_type=mimetypes.guess_type(path)[0] or "application/octet-stream",
                upsert=False,
            )
        except AgentServiceError:
            existing = await self.client.download(bucket=self.bucket, object_path=path)
            if checksum(existing) != checksum(content):
                raise ValueError("Existing Profile object differs; overwrites are forbidden.") from None

    async def resolve(self, profile: ProfileRef) -> tuple[Path, PackageManifest]:
        params = {"profile_key": f"eq.{profile.key}", "profile_version": f"eq.{profile.version}"}
        rows = await self.client.select("profile_resource_packages", params=params)
        matches = [
            row
            for row in rows
            if row["status"] in {"active", "retired"}
            and profile.checksum in {row["source_profile_checksum"], row["package_checksum"]}
        ]
        if len(matches) != 1:
            raise ValueError("No unique published Profile resource package matches the frozen checksum.")
        row = matches[0]
        return await self._resolve_row(row)

    async def candidate_package(self, candidate: ProfileCandidate) -> tuple[Path, PackageManifest]:
        """Read an unpublished package only when its exact candidate identity/checksum matches."""
        rows = await self.client.select(
            "profile_resource_packages",
            params={
                "id": f"eq.{candidate.resource_package_id}",
                "candidate_id": f"eq.{candidate.candidate_id}",
            },
        )
        if len(rows) != 1 or rows[0]["package_checksum"] != candidate.resource_package_checksum:
            raise ValueError("Candidate resource package identity/checksum mismatch.")
        return await self._resolve_row(rows[0])

    async def _resolve_row(self, row: dict[str, object]) -> tuple[Path, PackageManifest]:
        content = await self.client.download(
            bucket=str(row["storage_bucket"]), object_path=str(row["manifest_path"])
        )
        if checksum(content) != row["manifest_checksum"]:
            raise ValueError("Profile manifest checksum mismatch.")
        manifest = PackageManifest.model_validate_json(content)
        if (manifest.profile_key, manifest.profile_version, manifest.package_checksum) != (
            row["profile_key"],
            row["profile_version"],
            row["package_checksum"],
        ):
            raise ValueError("Profile package identity mismatch.")
        root = self.cache_root / str(row["id"])
        for entry in manifest.files:
            destination = root / safe_path(entry.path)
            valid = destination.is_file() and not destination.is_symlink()
            if valid:
                valid = checksum(await asyncio.to_thread(destination.read_bytes)) == entry.checksum
            if not valid:
                value = await self.client.download(
                    bucket=str(row["storage_bucket"]), object_path=f"{row['storage_prefix']}/{entry.path}"
                )
                if checksum(value) != entry.checksum or len(value) != entry.size:
                    raise ValueError("Profile resource checksum mismatch.")
                await asyncio.to_thread(_atomic_write, destination, value)
        await asyncio.to_thread(_atomic_write, root / "manifest.json", content)
        await asyncio.to_thread(verify_package, root, manifest)
        return root, manifest

    async def bind(self, profile: ProfileRef) -> ProfileBinding:
        root, _ = await self.resolve(profile)
        manifest = ProfileManifest.model_validate_json((root / "profile.json").read_text(encoding="utf-8"))
        resources = {key: root / safe_path(value) for key, value in manifest.resources.items()}
        rules = ProfileRuleSet.model_validate_json(resources["routing_rules"].read_text(encoding="utf-8"))
        return ProfileBinding(
            profile=profile,
            status=manifest.status,
            adapter=manifest.adapter,
            rules=rules,
            resolved_resources=resources,
        )

    async def load_registry(self, registry: ProfileRegistry) -> None:
        async with self._registry_lock:
            rows = await self.client.select("profile_resource_packages", params={"status": "eq.active"})
            signature = tuple(sorted((str(row["id"]), str(row["package_checksum"])) for row in rows))
            if self._loaded_sets.get(registry) == signature:
                return
            snapshots = await self._registry_snapshots(rows)
            registry.replace_active_packages(snapshots)
            self._loaded_sets[registry] = signature

    async def _registry_snapshots(self, rows: list[dict[str, object]]) -> list[ProfileSnapshot]:
        snapshots = []
        for row in rows:
            ref = ProfileRef(
                key=str(row["profile_key"]),
                version=str(row["profile_version"]),
                checksum=str(row["source_profile_checksum"]),
            )
            root, _ = await self.resolve(ref)
            binding = await self.bind(ref)
            manifest = ProfileManifest.model_validate_json(
                (root / "profile.json").read_text(encoding="utf-8")
            ).model_copy(update={"status": ProfileStatus.ACTIVE})
            snapshots.append(
                ProfileSnapshot(
                    manifest=manifest,
                    profile_root=root,
                    manifest_path=root / "profile.json",
                    resolved_resources=binding.resolved_resources,
                    checksum=str(ref.checksum),
                )
            )
        return snapshots

    async def display(self, profile: ProfileRef) -> dict[str, object]:
        root, manifest = await self.resolve(profile)
        files = []
        for entry in manifest.files:
            path = root / safe_path(entry.path)
            if path.suffix.lower() in {".md", ".json", ".yaml", ".yml", ".txt"}:
                files.append(
                    {
                        "path": entry.path,
                        "checksum": entry.checksum,
                        "content": await asyncio.to_thread(path.read_text, encoding="utf-8"),
                    }
                )
        rows = await self.client.select(
            "profile_resource_packages",
            params={
                "package_checksum": f"eq.{manifest.package_checksum}",
                "profile_key": f"eq.{profile.key}",
            },
        )
        row = rows[0]
        images = [
            {
                "path": entry.path,
                "url": await self.client.create_signed_url(
                    bucket=self.bucket, object_path=f"{row['storage_prefix']}/{entry.path}"
                ),
            }
            for entry in manifest.files
            if Path(entry.path).suffix.lower() in {".png", ".jpg", ".jpeg"}
        ]
        return {"manifest": json.loads(manifest.model_dump_json()), "files": files, "images": images}
