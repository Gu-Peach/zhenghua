"""Self-contained, content-addressed Profile assets; Python policy stays in code."""

from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path, PurePosixPath
from typing import Literal

from pydantic import Field, model_validator

from ..domain.models.common import StrictModel
from ..domain.models.extraction_stages import CrossPageCompletionData, PageClassificationData, PageScanData
from ..domain.models.profiles import ProfileManifest, ProfileRuleSet, ProfileSnapshot


class PackageFile(StrictModel):
    path: str
    checksum: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    size: int = Field(ge=0)


class PackageManifest(StrictModel):
    schema_version: Literal[1] = 1
    profile_key: str
    profile_version: str
    source_profile_checksum: str
    files: list[PackageFile] = Field(min_length=1)
    package_checksum: str

    @model_validator(mode="after")
    def validate_files(self) -> PackageManifest:
        paths = [entry.path for entry in self.files]
        if len(set(paths)) != len(paths) or "profile.json" not in paths:
            raise ValueError("Package file inventory must be unique and include profile.json.")
        for entry in self.files:
            safe_path(entry.path)
        if self.package_checksum != inventory_checksum(self.files):
            raise ValueError("Profile package inventory checksum mismatch.")
        return self


def safe_path(value: str) -> Path:
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or "\\" in value
        or ":" in value
        or any(part in {".", ".."} for part in path.parts)
        or path.as_posix() != value
    ):
        raise ValueError("Unsafe Profile package path.")
    return Path(*path.parts)


def checksum(content: bytes) -> str:
    return f"sha256:{hashlib.sha256(content).hexdigest()}"


def inventory_checksum(files: list[PackageFile]) -> str:
    payload = [entry.model_dump() for entry in sorted(files, key=lambda entry: entry.path)]
    return checksum(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode())


def seal_package(root: Path, *, source_checksum: str) -> PackageManifest:
    """Validate and seal a sandbox; manifest itself is excluded from its digest."""
    profile = ProfileManifest.model_validate_json((root / "profile.json").read_text(encoding="utf-8"))
    if profile.resource_mode != "packaged":
        raise ValueError("Remote packages must be self-contained.")
    for resource_path in profile.resources.values():
        resource = root / safe_path(resource_path)
        if not resource.exists() or resource.is_symlink():
            raise ValueError("Package manifest references missing or unsafe resources.")
    rules = ProfileRuleSet.model_validate_json(
        (root / safe_path(profile.resources["routing_rules"])).read_text(encoding="utf-8")
    )
    if rules.profile_key != profile.key:
        raise ValueError("Profile rules belong to a different package.")
    for relative_resource in profile.resources.values():
        directory = root / safe_path(relative_resource)
        example_manifest = directory / "manifest.json"
        if not directory.is_dir() or not example_manifest.is_file():
            continue
        payload = json.loads(example_manifest.read_text(encoding="utf-8"))
        for section in ("cases", "stage2_cases", "stage3_cases"):
            for case in payload.get(section, []):
                expected = case.get("expected") or f"{case['id']}/expected.json"
                required = [expected] + [image["path"] for image in case.get("images", [])]
                if case.get("input"):
                    required.append(case["input"])
                if not case.get("images"):
                    raise ValueError("Few-shot case requires actual images.")
                for value in required:
                    if not (directory / safe_path(value)).is_file():
                        raise ValueError("Few-shot manifest references missing image/expected JSON.")
    files = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise ValueError("Profile packages cannot contain symlinks.")
        if path.is_file() and path.name != "manifest.json" and ".suggestions" not in path.parts:
            content = path.read_bytes()
            if path.suffix == ".json":
                json.loads(content)
            files.append(
                PackageFile(
                    path=path.relative_to(root).as_posix(), checksum=checksum(content), size=len(content)
                )
            )
    # Nested few-shot manifests ARE part of the inventory, only the top manifest is excluded.
    for path in root.rglob("manifest.json"):
        if path != root / "manifest.json":
            content = path.read_bytes()
            json.loads(content)
            files.append(
                PackageFile(
                    path=path.relative_to(root).as_posix(), checksum=checksum(content), size=len(content)
                )
            )
    manifest = PackageManifest(
        profile_key=profile.key,
        profile_version=profile.version,
        source_profile_checksum=source_checksum,
        files=files,
        package_checksum=inventory_checksum(files),
    )
    (root / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    return manifest


def build_package(snapshot: ProfileSnapshot, destination: Path) -> PackageManifest:
    """Copy all resolved resources, including legacy assets outside profile_root."""
    destination.mkdir(parents=True, exist_ok=False)
    resources = {}
    for name, source in snapshot.resolved_resources.items():
        if not name.replace("_", "").isalnum() or source.is_symlink():
            raise ValueError("Unsafe Profile resource.")
        relative = f"resources/{name}" + (source.suffix if source.is_file() else "")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            if any(path.is_symlink() for path in source.rglob("*")):
                raise ValueError("Unsafe Profile resource symlink.")
            shutil.copytree(source, target)
        else:
            shutil.copyfile(source, target)
        resources[name] = relative
    profile = snapshot.manifest.model_copy(update={"resource_mode": "packaged", "resources": resources})
    (destination / "profile.json").write_text(profile.model_dump_json(indent=2), encoding="utf-8")
    schemas = {
        "stage1": PageClassificationData.model_json_schema(),
        "stage2": PageScanData.model_json_schema(),
        "stage3": CrossPageCompletionData.model_json_schema(),
    }
    (destination / "schema.json").write_text(
        json.dumps(schemas, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return seal_package(destination, source_checksum=snapshot.checksum)


def verify_package(root: Path, manifest: PackageManifest) -> None:
    for entry in manifest.files:
        path = root / safe_path(entry.path)
        if path.is_symlink() or not path.is_file():
            raise ValueError("Missing Profile package file.")
        content = path.read_bytes()
        if len(content) != entry.size or checksum(content) != entry.checksum:
            raise ValueError("Profile package file checksum mismatch.")
