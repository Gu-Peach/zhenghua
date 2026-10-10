from __future__ import annotations

from pathlib import PurePosixPath
from uuid import UUID


def project_source_pdf_path(project_id: str) -> str:
    return str(PurePosixPath("projects", _uuid(project_id), "original.pdf"))


def drawing_image_path(project_id: str, workspace_id: str, drawing_id: str) -> str:
    return str(
        PurePosixPath(
            "projects",
            _uuid(project_id),
            "workspaces",
            _uuid(workspace_id),
            "drawings",
            f"{_uuid(drawing_id)}.png",
        )
    )


def run_artifact_path(project_id: str, run_id: str, stage: str, filename: str) -> str:
    safe_stage = _segment(stage)
    safe_filename = PurePosixPath(filename).name
    if not safe_filename or safe_filename in {".", ".."}:
        raise ValueError("Artifact filename is required.")
    return str(
        PurePosixPath(
            "projects",
            _uuid(project_id),
            "runs",
            _uuid(run_id),
            safe_stage,
            safe_filename,
        )
    )


def _uuid(value: str) -> str:
    return str(UUID(value))


def _segment(value: str) -> str:
    candidate = value.strip().lower().replace("_", "-")
    if not candidate or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-" for char in candidate):
        raise ValueError(f"Unsafe storage path segment: {value!r}.")
    return candidate
