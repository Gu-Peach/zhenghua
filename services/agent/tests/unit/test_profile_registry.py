from __future__ import annotations

from pathlib import Path

import pytest

from agent_service.profiles import DrawingProfile, ProfileRegistry, ProfileRegistryError

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
PROFILE_ROOT = REPOSITORY_ROOT / "services" / "agent" / "profiles"


def build_registry() -> ProfileRegistry:
    registry = ProfileRegistry(
        profile_root=PROFILE_ROOT,
        workspace_root=REPOSITORY_ROOT,
        allow_legacy_references=True,
    )
    registry.load_all()
    return registry


def test_registry_loads_active_zh_and_experimental_abb() -> None:
    registry = build_registry()
    snapshots = registry.list_profiles()
    assert [(item.manifest.key, item.manifest.status.value) for item in snapshots] == [
        ("abb", "experimental"),
        ("zh", "active"),
    ]
    assert registry.resolve("zh").manifest.adapter == "zh_native"
    assert isinstance(registry.drawing_profile("zh"), DrawingProfile)
    binding = registry.bind("zh")
    assert binding.rules.profile_key == "zh"
    assert binding.profile.checksum == registry.resolve("zh").checksum
    with pytest.raises(ProfileRegistryError, match="experimental"):
        registry.resolve("abb", "0.1.0")
    assert registry.resolve("abb", "0.1.0", allow_experimental=True).manifest.key == "abb"


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
