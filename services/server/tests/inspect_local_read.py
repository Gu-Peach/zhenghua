"""Explicit local read-only smoke; never calls a model or writes a row."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "services/server/src"))
import httpx
from wiring_server.config import Settings
from wiring_server.repository import Repository
from wiring_server.workbench import WorkbenchService


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--user-id", required=True)
    args = parser.parse_args()
    settings = Settings.from_env()
    async with httpx.AsyncClient(timeout=30) as http:
        db = Repository(settings, http)
        service = WorkbenchService(db)
        project = args.project_id
        user = args.user_id
        detail = await service.detail(project, user)
        page = await service.results(project, user, offset=0, limit=100)
        packages = await db.rows(
            "profile_resource_packages", {"status": "in.(active,retired)"}
        )
        resource_checks = []
        for package in packages:
            content = await service.package(package["id"], settings.service_key)
            resource_checks.append(
                {
                    "profile": package["profile_key"],
                    "verified_text_files": len(content["files"]),
                    "signed_images": len(content["images"]),
                    "has_stage3_prompt": any(
                        "cross_page_prompt" in file["path"] for file in content["files"]
                    ),
                }
            )
        rows = await db.rows(
            "wiring_connection_rows",
            {
                "project_id": f"eq.{project}",
                "start_terminal": "eq.XD3:113",
                "order": "result_version.desc",
            },
        )
        references = []
        target_summary = None
        for row in rows:
            connection = (
                await db.rows(
                    "wiring_connections", {"id": f"eq.{row['connection_id']}"}
                )
            )[0]
            evidence = await db.rows(
                "connection_evidence", {"connection_id": f"eq.{row['connection_id']}"}
            )
            references.append(
                {
                    "version": row["result_version"],
                    "has_references": bool(connection["raw_payload"].get("references")),
                    "evidence_count": len(evidence),
                }
            )
            if row["result_version"] == page.result_version:
                target = await service.target(row["connection_id"], user)
                target_summary = {
                    "pdf_page_number": target["pdf_page_number"],
                    "workspace_page": target["workspace_page"],
                    "historical_evidence": bool(target.get("reference_note")),
                }
        print(
            json.dumps(
                {
                    "project": detail["name"],
                    "workspaces": len(detail["workspaces"]),
                    "rows": len(page.items),
                    "published_packages": len(packages),
                    "verified_resources": resource_checks,
                    "references": references,
                    "cross_page_target": target_summary,
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    asyncio.run(main())
