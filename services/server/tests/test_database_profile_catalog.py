"""The operational catalog never falls back to local definitions."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from typing import Any

import pytest
from wiring_server.profile_references import ProfileReferences
from wiring_server.repository import ServiceError
from wiring_server.simple_management import ManagementService

OWNER = "00000000-0000-0000-0000-000000000011"


def stored(version: str, identifier: str = "stored") -> dict[str, Any]:
    return {
        "id": identifier,
        "profile_key": "zh",
        "profile_version": version,
        "checksum": "sha256:" + "a" * 64,
        "created_by": OWNER,
        "resource_ref": f"storage://project-assets/profiles/{OWNER}/zh/{version}/"
        + "a" * 64
        + ".zip",
    }


class MemoryCatalog:
    def __init__(self, profiles: list[dict[str, Any]]) -> None:
        self.profiles = profiles
        self.settings = SimpleNamespace(profile_root=None)

    async def all_rows(self, table: str, params: Any, **kwargs: Any) -> Any:
        if table == "extraction_projects":
            return [
                {
                    "id": "project",
                    "owner_id": OWNER,
                    "profile_id": "legacy",
                    "name": "Existing",
                    "status": "ready",
                    "updated_at": "2026-10-19",
                    "drawing_index": {},
                }
            ]
        assert table == "extraction_profiles"
        return deepcopy(self.profiles)

    async def rows(self, table: str, params: Any, **kwargs: Any) -> Any:
        assert table == "extraction_profiles"
        return [
            deepcopy(row) for row in self.profiles if params["id"] == "eq." + row["id"]
        ]


def test_database_packages_win_without_reading_local_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Operational selection must not read local Profiles")

    monkeypatch.setattr(ProfileReferences, "catalog", forbidden)

    async def check() -> None:
        legacy = {
            **stored("99.0.0", "legacy"),
            "resource_ref": "local://zh/profile.json",
        }
        invalid = {**stored("10.0.0", "bad"), "checksum": "sha256:" + "b" * 64}
        db = MemoryCatalog([legacy, invalid, stored("2.2.0", "old"), stored("2.3.0")])
        references = ProfileReferences(db)
        rows = await references.list(OWNER)
        assert [row["id"] for row in rows] == ["stored"]
        assert (await references.available(OWNER))["zh"]["id"] == "stored"
        assert (await references.register("zh", OWNER))["id"] == "stored"
        assert (await references.get("legacy"))["resource_ref"].startswith("local://")
        projects = await ManagementService(db).projects(OWNER, "offline")
        assert projects[0]["standard_profile"] == "zh"

    asyncio.run(check())


def test_missing_package_stays_empty_and_cannot_create_local_reference() -> None:
    async def check() -> None:
        references = ProfileReferences(MemoryCatalog([]))
        assert await references.list(OWNER) == []
        assert await references.available(OWNER) == {}
        with pytest.raises(ServiceError) as error:
            await references.register("zh", OWNER)
        assert error.value.code == "PROFILE_NOT_AVAILABLE"

    asyncio.run(check())
