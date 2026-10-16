from __future__ import annotations

from typing import Any
from uuid import NAMESPACE_URL, uuid5

from .simple_models import DrawingIndex


def workspace_id(project: str, code: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"extraction-workspace:{project}:{code}"))


def drawing_id(project: str, page: int) -> str:
    return str(uuid5(NAMESPACE_URL, f"extraction-drawing:{project}:{page}"))


def index_drawings(project: dict[str, Any]) -> list[dict[str, Any]]:
    """Project JSON is the sole drawing catalog; never invent business page labels."""
    index = DrawingIndex.model_validate(project.get("drawing_index") or {})
    return [
        {
            "id": drawing_id(project["id"], page.pdf_page_number),
            "project_id": project["id"],
            "workspace_id": workspace_id(project["id"], page.workspace_code),
            "workspace_code": page.workspace_code,
            "workspace_page": page.drawing_page,
            "pdf_page_number": page.pdf_page_number,
            "status": page.status,
            "image_bucket": page.image_bucket,
            "image_path": page.image_path,
        }
        for page in sorted(index.pages, key=lambda page: page.pdf_page_number)
    ]


def project_read(
    project: dict[str, Any], profile_key: str | None = None
) -> dict[str, Any]:
    catalog = index_drawings(project)
    groups: dict[str, dict[str, Any]] = {}
    for page in catalog:
        code = page["workspace_code"]
        groups.setdefault(
            code,
            {
                "id": page["workspace_id"],
                "code": code,
                "name": code or "未分类",
                "drawings": [],
            },
        )
        groups[code]["drawings"].append(page)
    index = DrawingIndex.model_validate(project.get("drawing_index") or {})
    source = index.source
    return {
        **{
            key: project[key]
            for key in ("id", "name", "owner_id", "status", "profile_id", "updated_at")
        },
        "standard_profile": profile_key,
        "workspaces": list(groups.values()),
        "sources": [
            {
                "id": project["id"],
                "original_filename": source.get("filename", ""),
                "page_count": source.get("page_count", 0),
            }
        ]
        if source
        else [],
        "batch_id": index.active_batch_id,
        "extraction_available": True,
        "processing": project.get("drawing_index", {}).get("processing"),
        "source_saved": project.get("drawing_index", {}).get("upload_state") == "saved",
    }


def connection_read(row: dict[str, Any]) -> dict[str, Any]:
    return {
        **row,
        "connection_id": row["id"],
        "workspace_id": workspace_id(
            row["project_id"], row.get("workspace_code") or ""
        ),
        "workspace_name": row.get("workspace_code") or "未分类",
        "drawing_id": drawing_id(row["project_id"], row["source_pdf_page_number"]),
        "workspace_page": row.get("source_drawing_page"),
        "pdf_page_number": row["source_pdf_page_number"],
        "voltage_level": (row.get("evidence") or {}).get("voltage_level"),
        "processing_status": (row.get("evidence") or {}).get("processing_status", "completed"),
        "review_reasons": (row.get("evidence") or {}).get("review_reasons", []),
    }
