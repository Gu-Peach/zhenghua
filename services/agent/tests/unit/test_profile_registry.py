from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.domain.enums import ProfileStatus
from src.profiles import DrawingProfile, ProfileRegistry, ProfileRegistryError

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
PROFILE_ROOT = REPOSITORY_ROOT / "services" / "agent" / "src/agent/extraction_agent/profiles"


def build_registry() -> ProfileRegistry:
    registry = ProfileRegistry(
        profile_root=PROFILE_ROOT,
        workspace_root=REPOSITORY_ROOT,
        allow_legacy_references=True,
    )
    registry.load_all()
    return registry


def test_registry_loads_local_manifests_and_enforces_experimental_status() -> None:
    registry = build_registry()
    snapshots = registry.list_profiles()
    expected = [json.loads(path.read_text(encoding="utf-8")) for path in PROFILE_ROOT.glob("*/profile.json")]
    assert [(item.manifest.key, item.manifest.status.value) for item in snapshots] == sorted(
        (item["key"], item["status"]) for item in expected
    )
    assert registry.resolve("zh").manifest.adapter == "zh_native"
    assert isinstance(registry.drawing_profile("zh"), DrawingProfile)
    binding = registry.bind("zh")
    assert binding.rules.profile_key == "zh"
    assert binding.profile.checksum == registry.resolve("zh").checksum
    abb = registry.resolve("abb", allow_experimental=True)
    registry.register_snapshot(
        abb.model_copy(
            update={"manifest": abb.manifest.model_copy(update={"status": ProfileStatus.EXPERIMENTAL})}
        )
    )
    with pytest.raises(ProfileRegistryError, match="experimental"):
        registry.resolve("abb", abb.manifest.version)
    assert registry.resolve("abb", abb.manifest.version, allow_experimental=True).manifest.key == "abb"


def test_registry_checksum_is_stable() -> None:
    first = build_registry().resolve("zh").checksum
    second = build_registry().resolve("zh").checksum
    assert first == second
    assert first.startswith("sha256:")


def test_registry_rejects_resource_outside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    profile_dir = workspace / "profiles" / "bad"
    profile_dir.mkdir(parents=True)
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")
    (profile_dir / "profile.json").write_text(
        """{
          "manifest_version": 1,
          "key": "bad",
          "version": "1.0.0",
          "display_name": "Bad",
          "status": "active",
          "adapter": "none",
          "resource_mode": "legacy_reference",
          "resources": {"prompt": "../../../secret.txt"}
        }""",
        encoding="utf-8",
    )
    registry = ProfileRegistry(
        profile_root=workspace / "profiles",
        workspace_root=workspace,
        allow_legacy_references=True,
    )
    with pytest.raises(ProfileRegistryError):
        registry.load_all()
