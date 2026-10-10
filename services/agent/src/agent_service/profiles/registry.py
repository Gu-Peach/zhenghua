from __future__ import annotations

import hashlib
import json
from pathlib import Path

from pydantic import ValidationError

from ..domain.enums import ErrorCode, ProfileStatus
from ..domain.errors import AgentServiceError
from ..domain.models.profiles import (
    ProfileBinding,
    ProfileManifest,
    ProfileRuleSet,
    ProfileSnapshot,
)
from ..domain.models.runs import ProfileRef
from .protocols import SnapshotDrawingProfile


class ProfileRegistryError(AgentServiceError):
    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(
            ErrorCode.PROFILE_INVALID,
            message,
            retryable=False,
            details=details,
        )


class ProfileRegistry:
    def __init__(
        self,
        *,
        profile_root: Path,
        workspace_root: Path,
        allow_legacy_references: bool = False,
    ) -> None:
        self.profile_root = profile_root.resolve()
        self.workspace_root = workspace_root.resolve()
        self.allow_legacy_references = allow_legacy_references
        self._snapshots: dict[tuple[str, str], ProfileSnapshot] = {}
        self.errors: list[str] = []

    def load_all(self, *, strict: bool = True) -> list[ProfileSnapshot]:
        self._snapshots.clear()
        self.errors.clear()
        if not self.profile_root.is_dir():
            message = f"Profile root does not exist: {self.profile_root}"
            self.errors.append(message)
            if strict:
                raise ProfileRegistryError(message)
            return []

        manifest_paths = sorted(self.profile_root.glob("*/profile.json"))
        if not manifest_paths:
            message = f"No profile manifests found under {self.profile_root}"
            self.errors.append(message)
            if strict:
                raise ProfileRegistryError(message)
            return []

        for manifest_path in manifest_paths:
            try:
                snapshot = self._load_manifest(manifest_path)
                self.load_rules(snapshot)
                key = (snapshot.manifest.key, snapshot.manifest.version)
                if key in self._snapshots:
                    raise ProfileRegistryError(
                        f"Duplicate profile version {key[0]}@{key[1]}.",
                    )
                self._snapshots[key] = snapshot
            except (OSError, json.JSONDecodeError, ValidationError, ProfileRegistryError) as exc:
                self.errors.append(f"{manifest_path}: {exc}")

        if strict and self.errors:
            raise ProfileRegistryError(
                "One or more profiles are invalid.",
                details={"errors": list(self.errors)},
            )
        return self.list_profiles()

    def list_profiles(self) -> list[ProfileSnapshot]:
        return sorted(
            self._snapshots.values(),
            key=lambda item: (item.manifest.key, item.manifest.semantic_version),
        )

    def resolve(
        self,
        key: str,
        version: str | None = None,
        *,
        allow_experimental: bool = False,
    ) -> ProfileSnapshot:
        candidates = [
            snapshot
            for (profile_key, profile_version), snapshot in self._snapshots.items()
            if profile_key == key and (version is None or profile_version == version)
        ]
        if not candidates:
            raise ProfileRegistryError(f"Profile {key!r} version {version or 'active'} was not found.")
        if version is None:
            active_candidates = [
                snapshot for snapshot in candidates if snapshot.manifest.status == ProfileStatus.ACTIVE
            ]
            if active_candidates:
                candidates = active_candidates
            elif allow_experimental:
                candidates = [
                    snapshot
                    for snapshot in candidates
                    if snapshot.manifest.status == ProfileStatus.EXPERIMENTAL
                ]
            else:
                raise ProfileRegistryError(f"Profile {key!r} has no active version.")
        selected = max(candidates, key=lambda item: item.manifest.semantic_version)
        if selected.manifest.status == ProfileStatus.EXPERIMENTAL and not allow_experimental:
            raise ProfileRegistryError(f"Profile {key!r}@{selected.manifest.version} is experimental.")
        if selected.manifest.status == ProfileStatus.RETIRED:
            raise ProfileRegistryError(f"Profile {key!r}@{selected.manifest.version} is retired.")
        return selected

    def drawing_profile(
        self,
        key: str,
        version: str | None = None,
        *,
        allow_experimental: bool = False,
    ) -> SnapshotDrawingProfile:
        return SnapshotDrawingProfile(self.resolve(key, version, allow_experimental=allow_experimental))

    def load_rules(self, snapshot: ProfileSnapshot) -> ProfileRuleSet:
        try:
            rules_path = snapshot.resource("routing_rules")
        except KeyError as exc:
            raise ProfileRegistryError(
                f"Profile {snapshot.manifest.key}@{snapshot.manifest.version} has no routing_rules."
            ) from exc
        if not rules_path.is_file():
            raise ProfileRegistryError(f"Profile routing rules must be a file: {rules_path}")
        try:
            rules = ProfileRuleSet.model_validate_json(rules_path.read_text(encoding="utf-8"))
        except (OSError, ValidationError, ValueError) as exc:
            raise ProfileRegistryError(f"Invalid profile routing rules: {rules_path}") from exc
        if rules.profile_key != snapshot.manifest.key:
            raise ProfileRegistryError(
                f"Rule profile key {rules.profile_key!r} does not match manifest {snapshot.manifest.key!r}."
            )
        referenced_resources = {
            resource_name for names in rules.extraction.dynamic_resources.values() for resource_name in names
        }
        missing = sorted(referenced_resources - snapshot.resolved_resources.keys())
        if missing:
            raise ProfileRegistryError(f"Profile rules reference missing resources: {', '.join(missing)}")
        return rules

    def bind(
        self,
        key: str,
        version: str | None = None,
        *,
        allow_experimental: bool = False,
    ) -> ProfileBinding:
        snapshot = self.resolve(key, version, allow_experimental=allow_experimental)
        return ProfileBinding(
            profile=ProfileRef(
                key=snapshot.manifest.key,
                version=snapshot.manifest.version,
                checksum=snapshot.checksum,
            ),
            status=snapshot.manifest.status,
            adapter=snapshot.manifest.adapter,
            rules=self.load_rules(snapshot),
            resolved_resources=dict(snapshot.resolved_resources),
        )

    def _load_manifest(self, manifest_path: Path) -> ProfileSnapshot:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest = ProfileManifest.model_validate(payload)
        profile_dir = manifest_path.parent.resolve()
        if profile_dir.parent != self.profile_root:
            raise ProfileRegistryError("Profile manifest must be one directory below profile_root.")

        resources = {
            name: self._resolve_resource(profile_dir, raw_path, manifest.resource_mode)
            for name, raw_path in manifest.resources.items()
        }
        checksum = self._checksum(manifest_path.resolve(), resources)
        return ProfileSnapshot(
            manifest=manifest,
            profile_root=profile_dir,
            manifest_path=manifest_path.resolve(),
            resolved_resources=resources,
            checksum=f"sha256:{checksum}",
        )

    def _resolve_resource(self, profile_dir: Path, raw_path: str, resource_mode: str) -> Path:
        path = (profile_dir / raw_path).resolve()
        allowed_root = profile_dir if resource_mode == "packaged" else self.workspace_root
        if resource_mode == "legacy_reference" and not self.allow_legacy_references:
            raise ProfileRegistryError("Legacy profile references are disabled.")
        if not self._is_within(path, allowed_root):
            raise ProfileRegistryError(f"Profile resource escapes its allowed root: {raw_path}")
        if not path.exists():
            raise ProfileRegistryError(f"Profile resource does not exist: {path}")
        if path.is_symlink():
            raise ProfileRegistryError(f"Profile resources cannot be symlinks: {path}")
        return path

    def _checksum(self, manifest_path: Path, resources: dict[str, Path]) -> str:
        digest = hashlib.sha256()
        files: set[Path] = {manifest_path}
        for resource in resources.values():
            if resource.is_file():
                files.add(resource)
            elif resource.is_dir():
                files.update(path for path in resource.rglob("*") if path.is_file())

        for path in sorted(files, key=lambda item: str(item).lower()):
            if path.is_symlink() or not self._is_within(path.resolve(), self.workspace_root):
                raise ProfileRegistryError(f"Unsafe profile resource encountered: {path}")
            relative = path.resolve().relative_to(self.workspace_root)
            digest.update(relative.as_posix().encode("utf-8"))
            digest.update(b"\0")
            with path.open("rb") as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            digest.update(b"\0")
        return digest.hexdigest()

    @staticmethod
    def _is_within(path: Path, root: Path) -> bool:
        try:
            path.resolve().relative_to(root.resolve())
            return True
        except ValueError:
            return False
