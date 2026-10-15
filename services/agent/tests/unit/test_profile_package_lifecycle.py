from __future__ import annotations

import asyncio
import copy
import json
from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from src.agents.profile_router import ProfileRouterAgent
from src.application.profile_package_lifecycle import (
    CreateProfilePackage,
    PackageLifecycleError,
    ProfilePackageLifecycle,
)
from src.harness import FakeModelGateway
from src.infrastructure.supabase_client import SupabaseClient
from src.infrastructure.supabase_profile_packages import SupabaseProfilePackageRepository
from src.profiles import ProfileRegistry, ProfileRegistryError
from src.profiles.package import build_package
from src.tools.pdf_first_page import FirstPageImage

ROOT = Path(__file__).resolve().parents[4]
USER, OTHER = str(uuid4()), str(uuid4())


class PackageBackend:
    """HTTP fixture for immutable Storage and the existing publication RPC; no live services."""

    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.objects: dict[str, bytes] = {}
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        path = request.url.path
        if path.startswith("/storage/v1/object/"):
            if request.method == "POST":
                if path in self.objects:
                    return httpx.Response(409, json={"message": "already exists"})
                self.objects[path] = request.content
                return httpx.Response(200, json={})
            return httpx.Response(200, content=self.objects[path])
        if path.endswith("/rpc/publish_profile_package"):
            data = json.loads(request.content)
            row = next(row for row in self.rows if row["id"] == data["package_id"])
            assert row["approved_by"] == data["reviewer"]
            row["status"] = "active"
            return httpx.Response(200, json=row)
        if request.method == "POST":
            row = json.loads(request.content)
            assert all(existing["id"] != row["id"] for existing in self.rows)
            self.rows.append(row)
            return httpx.Response(201, json=[row])
        rows = self.rows
        for field, value in request.url.params.items():
            if value.startswith("eq."):
                rows = [row for row in rows if str(row.get(field)) == value[3:]]
        if request.method == "PATCH":
            for row in rows:
                row.update(json.loads(request.content))
        return httpx.Response(200, json=copy.deepcopy(rows))


def local_registry() -> ProfileRegistry:
    registry = ProfileRegistry(
        profile_root=ROOT / "services/agent/src/agent/extraction_agent/profiles", workspace_root=ROOT, allow_legacy_references=True
    )
    registry.load_all()
    return registry


def create_input(base: str, key: str = "custom-test") -> CreateProfilePackage:
    return CreateProfilePackage(
        base_package_id=base,
        profile_key=key,
        display_name="独立验收规则",
        detection_summary="验收图框",
        strong_signals=["独立标识"],
        prompts={"page_scan_prompt": "只读取指定线路，无法确认置空。"},
        confirmed=True,
    )


def test_create_register_retry_delete_and_historical_binding(tmp_path: Path) -> None:
    async def run() -> None:
        backend = PackageBackend()
        client = SupabaseClient(
            base_url="http://fixture", service_role_key="fixture", transport=httpx.MockTransport(backend)
        )
        packages = SupabaseProfilePackageRepository(client, cache_root=tmp_path / "cache")
        registry = local_registry()
        base_root = tmp_path / "base"
        base_manifest = build_package(registry.resolve("zh"), base_root)
        base = await packages.upload(base_root, created_by=USER, status="active")
        lifecycle = ProfilePackageLifecycle(packages, registry)
        receipt = await lifecycle.create(create_input(base["id"]), USER)
        binding = registry.bind("custom-test")
        assert receipt["registered"] is True
        assert binding.rules.detection.strong_signals == ["独立标识"]
        assert binding.rules.display_name == "独立验收规则"
        gateway = FakeModelGateway(
            [
                json.dumps(
                    {
                        "recognized": True,
                        "selected_profile_key": "custom-test",
                        "confidence": 0.99,
                        "candidates": [
                            {"profile_key": "custom-test", "score": 0.99, "matched_signals": ["独立标识"]}
                        ],
                        "observed_signals": ["独立标识"],
                        "reason": "识别到新规则标识",
                    }
                )
            ]
        )
        detected = await ProfileRouterAgent(
            gateway=gateway,
            registry=registry,
            prompt_path=ROOT / "services/agent/src/agent/extraction_agent/prompts/profile_router.md",
        ).detect(
            first_page=FirstPageImage(
                content=b"fixture", mime_type="image/png", width=1, height=1, checksum="sha256:" + "a" * 64
            ),
            run_id="fixture-run",
            project_id="fixture-project",
        )
        assert detected.assigned_profile == binding.profile
        assert "custom-test" in gateway.calls[0].metadata["candidate_profiles"]
        assert binding.resolved_resources["page_scan_prompt"].read_text(encoding="utf-8").startswith("只读取")
        assert (binding.resolved_resources["wiring_examples"] / "images/003c01.png").is_file()
        assert (
            base_manifest.package_checksum
            == json.loads((base_root / "manifest.json").read_text())["package_checksum"]
        )
        repeated = await lifecycle.create(create_input(base["id"]), USER)
        assert repeated == receipt and len(backend.rows) == 2
        with pytest.raises(PackageLifecycleError, match="标识已占用"):
            await lifecycle.create(create_input(base["id"]), OTHER)
        different = create_input(base["id"]).model_copy(update={"display_name": "不同内容"})
        with pytest.raises(PackageLifecycleError, match="内容不同"):
            await lifecycle.create(different, USER)
        with pytest.raises(PackageLifecycleError, match="自己创建"):
            await lifecycle.retire(str(receipt["id"]), OTHER)
        worker_registry = local_registry()
        await packages.load_registry(worker_registry)
        assert worker_registry.bind("custom-test").profile == binding.profile
        storage_before = dict(backend.objects)
        await lifecycle.retire(str(receipt["id"]), USER)
        await packages.load_registry(worker_registry)
        for active_registry in (registry, worker_registry):
            with pytest.raises(ProfileRegistryError):
                active_registry.bind("custom-test")
            with pytest.raises(ProfileRegistryError):
                active_registry.bind("custom-test", allow_experimental=True)
        # Exact frozen refs continue to resolve after deletion, including after cache restart.
        restarted = SupabaseProfilePackageRepository(client, cache_root=tmp_path / "restarted")
        assert (await restarted.bind(binding.profile)).profile == binding.profile
        assert backend.objects == storage_before
        await lifecycle.retire(str(receipt["id"]), USER)
        with pytest.raises(PackageLifecycleError, match="已停用"):
            await lifecycle.create(create_input(base["id"]), USER)
        # Even the last active package can be retired; no fallback to local defaults.
        await lifecycle.retire(base["id"], USER)
        with pytest.raises(ProfileRegistryError):
            registry.bind("zh")

    asyncio.run(run())


def test_failed_registration_retry_and_corrupt_refresh_is_atomic(tmp_path: Path, monkeypatch) -> None:
    async def run() -> None:
        backend = PackageBackend()
        client = SupabaseClient(
            base_url="http://fixture", service_role_key="fixture", transport=httpx.MockTransport(backend)
        )
        packages = SupabaseProfilePackageRepository(client, cache_root=tmp_path / "cache")
        registry = local_registry()
        base_root = tmp_path / "base"
        build_package(registry.resolve("zh"), base_root)
        base = await packages.upload(base_root, created_by=USER, status="active")
        await packages.load_registry(registry)
        lifecycle = ProfilePackageLifecycle(packages, registry)
        original = packages.load_registry

        async def fail(_registry: ProfileRegistry) -> None:
            raise ValueError("temporary registration failure")

        monkeypatch.setattr(packages, "load_registry", fail)
        with pytest.raises(ValueError, match="temporary"):
            await lifecycle.create(create_input(base["id"]), USER)
        monkeypatch.setattr(packages, "load_registry", original)
        receipt = await lifecycle.create(create_input(base["id"]), USER)
        assert receipt["registered"] and len(backend.rows) == 2
        binding = registry.bind("custom-test")
        row = next(row for row in backend.rows if row["id"] == receipt["id"])
        row["package_checksum"] = "sha256:" + "f" * 64
        with pytest.raises(ValueError, match="identity mismatch"):
            await packages.load_registry(registry)
        assert registry.bind("custom-test") == binding

    asyncio.run(run())
