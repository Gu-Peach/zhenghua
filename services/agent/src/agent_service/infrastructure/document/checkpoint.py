from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from agent_service.application.document_extraction.runtime import GraphRuntime
from agent_service.graphs.document_extraction.state import (
    GraphState,
)

logger = logging.getLogger(__name__)


def _diagnostics_dir(output_path: Path, output_mode: str) -> Path:
    if output_mode == "library" or output_path.is_dir():
        return output_path / "agent"
    return output_path.parent / f"{output_path.stem}.agent"


def _cross_page_checkpoint_path(state: GraphState, runtime: GraphRuntime) -> Path:
    diagnostics_dir = _diagnostics_dir(Path(state["output_path"]), runtime.output_mode)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    return diagnostics_dir / "cross-page-checkpoint.json"


def _load_cross_page_checkpoint(path: Path, tasks: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, Any]]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        expected_ids = [str(task.get("task_id")) for task in tasks]
        if payload.get("task_ids") != expected_ids:
            return {}
        completed = payload.get("completed") or {}
        return completed if isinstance(completed, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning("Ignoring invalid cross-page checkpoint %s: %s", path, exc)
        return {}


def _write_cross_page_checkpoint(
    path: Path,
    tasks: Sequence[Mapping[str, Any]],
    completed: Mapping[str, Any],
    errors: Mapping[str, str],
) -> None:
    _write_json_atomic(
        path,
        {
            "version": 1,
            "task_ids": [str(task.get("task_id")) for task in tasks],
            "completed": dict(completed),
            "errors": dict(errors),
        },
    )


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.warning("Ignoring invalid checkpoint %s: %s", path, exc)
        return {}


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(6):
            try:
                os.replace(temporary, path)
                return
            except PermissionError:
                if attempt == 5:
                    raise
                time.sleep(0.05 * (2**attempt))
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            logger.debug("Could not remove temporary checkpoint file %s", temporary)


def _write_runtime_diagnostics(diagnostics_dir: Path, runtime: GraphRuntime) -> None:
    _write_json_atomic(diagnostics_dir / "errors.json", runtime.extraction_errors or {})
    _write_json_atomic(diagnostics_dir / "validation-warnings.json", runtime.validation_warnings or [])


def _write_page_scan_checkpoint(
    path: Path,
    *,
    processed_pages: list[int],
    page_scan_results: Mapping[str, Any],
) -> None:
    _write_json_atomic(
        path,
        {
            "version": 3,
            "processed_pages": processed_pages,
            "page_scan_results": dict(page_scan_results),
        },
    )


def _write_wire_units_checkpoint(path: Path, wire_units: Mapping[str, Any]) -> None:
    _write_json_atomic(path, {"version": 3, "wire_units": dict(wire_units)})
