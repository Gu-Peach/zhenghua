"""Prepare/publish the three reviewed local Profiles to the operational database catalog."""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse
from uuid import UUID

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services/agent"))
sys.path.insert(0, str(ROOT / "services/server/src"))

import httpx  # noqa: E402
from wiring_server.config import Settings  # noqa: E402
from wiring_server.profile_packages import download, object_request, unpack  # noqa: E402
from wiring_server.profile_references import ProfileReferences  # noqa: E402
from wiring_server.repository import Repository  # noqa: E402

from src.agent.profile_agent.validation import check_structure  # noqa: E402
from src.config import AgentSettings  # noqa: E402
from src.domain.models.profiles import ProfileManifest  # noqa: E402
from src.profiles.package import build_package, checksum, seal_package, verify_package  # noqa: E402
from src.profiles.registry import ProfileRegistry  # noqa: E402

VERSIONS = {"zh": "2.3.0", "abb": "1.3.1", "zh_gantry_reel": "0.2.1"}


def prepare(registry: ProfileRegistry, directory: Path) -> list[dict[str, Any]]:
    """Package unchanged resource bytes with explicit publication identities, without network calls."""
    prepared = []
    for key, version in VERSIONS.items():
        source = registry.resolve(key, allow_experimental=True)
        with tempfile.TemporaryDirectory(dir=directory) as temporary:
            package = Path(temporary) / "selected"
            build_package(source, package)
            value = json.loads((package / "profile.json").read_text(encoding="utf-8"))
            value.update(version=version, status="active")
            manifest = ProfileManifest.model_validate(value)
            (package / "profile.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
            inventory = seal_package(package, source_checksum=source.checksum)
            verify_package(package, inventory)
            issues = check_structure(package)
            if issues:
                raise ValueError(f"{key}: invalid package: {issues}")
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
                for path in sorted(package.rglob("*")):
                    if path.is_file():
                        info = zipfile.ZipInfo(path.relative_to(package).as_posix(), (2026, 1, 1, 0, 0, 0))
                        info.compress_type = zipfile.ZIP_DEFLATED
                        info.external_attr = 0o100644 << 16
                        archive.writestr(info, path.read_bytes())
            content = stream.getvalue()
            unpack(content, checksum(content))
            destination = directory / f"{key}-{version}.zip"
            destination.write_bytes(content)
            prepared.append(
                {
                    "key": key,
                    "version": version,
                    "source_version": source.manifest.version,
                    "name": manifest.display_name,
                    "checksum": checksum(content),
                    "archive": str(destination),
                    "bytes": len(content),
                    "files": len(inventory.files),
                }
            )
    return prepared


async def business_identity(db: Repository, owner: str) -> dict[str, str]:
    projects = await db.all_rows(
        "extraction_projects",
        {
            "owner_id": f"eq.{owner}",
            "select": "id,profile_id,status,updated_at",
            "order": "id.asc",
        },
    )
    ids = [row["id"] for row in projects]
    rows = (
        await db.all_rows(
            "extraction_connection_rows",
            {
                "project_id": "in.(" + ",".join(ids) + ")",
                "order": "id.asc",
                "select": "id,project_id,batch_id,record_version,updated_at",
            },
        )
        if ids
        else []
    )
    return {
        "projects": checksum(json.dumps(projects, sort_keys=True).encode()),
        "row_versions": checksum(json.dumps(rows, sort_keys=True).encode()),
    }


async def publish(db: Repository, item: dict[str, Any], owner: str) -> dict[str, Any]:
    content = await asyncio.to_thread(Path(item["archive"]).read_bytes)
    await asyncio.to_thread(unpack, content, item["checksum"])
    path = f"profiles/{owner}/{item['key']}/{item['version']}/{item['checksum'][7:]}.zip"
    url = "/storage/v1/object/project-assets/" + quote(path, safe="/")
    response = await object_request(
        db, "POST", url, content=content, headers={"Content-Type": "application/zip", "x-upsert": "false"}
    )
    if response.is_error:
        if response.status_code not in {400, 409}:
            raise RuntimeError(f"{item['key']}: Storage upload rejected ({response.status_code})")
        existing = await object_request(db, "GET", url)
        if existing.is_error or checksum(existing.content) != item["checksum"]:
            raise RuntimeError(f"{item['key']}: existing Storage content differs")
    row = await db.rpc(
        "publish_extraction_profile",
        {
            "actor": owner,
            "profile_key_value": item["key"],
            "version_value": item["version"],
            "name_value": item["name"],
            "checksum_value": item["checksum"],
            "ref_value": "storage://project-assets/" + path,
        },
    )
    readback = await download(db, row)
    unpack(readback, row["checksum"])
    if readback != content:
        raise RuntimeError(f"{item['key']}: uploaded bytes differ")
    return {
        "id": row["id"],
        "key": row["profile_key"],
        "version": row["profile_version"],
        "checksum": row["checksum"],
        "resource_ref": row["resource_ref"],
        "readback_verified": True,
    }


async def run(args: argparse.Namespace) -> None:
    directory = await asyncio.to_thread(Path(args.output_dir).resolve)
    directory.mkdir(parents=True, exist_ok=True)
    settings = AgentSettings.from_env()
    registry = ProfileRegistry(
        profile_root=settings.profile_root, workspace_root=ROOT, allow_legacy_references=True
    )
    registry.load_all()
    prepared = await asyncio.to_thread(prepare, registry, directory)
    server = Settings.from_env()
    owner = str(args.owner_id)
    async with httpx.AsyncClient(timeout=60) as http:
        db = Repository(server, http)
        auth = await http.get(
            server.supabase_url + "/auth/v1/admin/users/" + owner,
            headers={"apikey": server.service_key, "Authorization": "Bearer " + server.service_key},
        )
        if auth.status_code != 200 or auth.json().get("id") != owner:
            raise ValueError("Publication owner must be an existing Auth user")
        existing = await db.all_rows("extraction_profiles", {"order": "created_at.asc"})
        for item in prepared:
            for row in existing:
                if row["profile_key"] != item["key"]:
                    continue
                if row["created_by"] != owner:
                    raise ValueError("Profile key belongs to another owner")
                if row["profile_version"] == item["version"] and (
                    row["checksum"] != item["checksum"] or not ProfileReferences.is_uploaded(row)
                ):
                    raise ValueError(f"{item['key']}: immutable target version already exists")
        report: dict[str, Any] = {
            "database_host": urlparse(server.supabase_url).netloc,
            "owner": owner,
            "apply": args.apply,
            "prepared": prepared,
            "published": [],
        }
        if args.apply:
            before = await business_identity(db, owner)
            if not await asyncio.to_thread((directory / "before.json").exists):
                (directory / "before.json").write_text(
                    json.dumps({"profiles": existing, "business": before}, indent=2), encoding="utf-8"
                )
            for item in prepared:
                report["published"].append(await publish(db, item, owner))
                (directory / "receipt.json").write_text(
                    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            after = await business_identity(db, owner)
            if before != after:
                raise RuntimeError(
                    "Project bindings or row versions changed during publication; inspect activity"
                )
            report["business_identity_unchanged"] = True
        (directory / ("receipt.json" if args.apply else "preflight.json")).write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(report, ensure_ascii=True))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-id", required=True, type=UUID)
    parser.add_argument("--output-dir", default=str(ROOT / ".runtime/profile-catalog-upload"))
    parser.add_argument(
        "--apply", action="store_true", help="Upload and register; default only builds/checks packages"
    )
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
